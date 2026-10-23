import json
import time
from pathlib import Path
from datasets import load_dataset
from loguru import logger
from neo4j import GraphDatabase
from tqdm import tqdm


def build_neo4j_graph(
    uri: str,
    user: str,
    password: str,
    dataset_name: str,
    chunks_path: Path,
    force_recreate_nodes: bool = False,
):
    """
    Tạo các Node từ chunks (mỗi văn bản là 1 Node)
    Tạo các Cạnh từ dataset config 'relationships'

    Tối ưu hóa:
    - Tạo Index / Constraint trên doc_id (giúp MATCH tức thì, tránh Timeout)
    - Chỉ tạo edges giữa các documents THỰC SỰ CÓ trong dữ liệu (184k edges thay vì 1M edges rác)
    - Tự động bỏ qua bước tạo Nodes nếu đã có sẵn 76,203 nodes trên database
    """
    logger.info("Kết nối tới Neo4j...")
    driver = GraphDatabase.driver(
        uri,
        auth=(user, password),
        connection_timeout=60.0,
        max_connection_lifetime=300.0,
        keep_alive=True,
    )

    # 1. Thu thập danh sách văn bản từ chunks
    logger.info("Thu thập metadata từ các documents...")
    docs = {}
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in tqdm(f, desc="Đọc chunks để lấy Docs"):
            item = json.loads(line)
            doc_id = item.get("doc_id")
            if doc_id and doc_id not in docs:
                docs[str(doc_id)] = item.get("metadata", {})

    total_docs = len(docs)
    logger.info(f"Đã thu thập {total_docs:,} văn bản từ chunks.")

    with driver.session() as session:
        # Tạo Unique Constraint (Index) trước để tăng tốc độ truy vấn gấp hàng ngàn lần
        logger.info("Đảm bảo Index / Unique Constraint trên doc_id...")
        session.run(
            "CREATE CONSTRAINT vanban_doc_id IF NOT EXISTS "
            "FOR (d:VanBan) REQUIRE d.doc_id IS UNIQUE"
        )

        # Kiểm tra xem nodes đã có sẵn trên database chưa
        res = session.run("MATCH (n:VanBan) RETURN count(n) AS cnt").single()
        current_node_count = res["cnt"] if res else 0

        if current_node_count >= total_docs and not force_recreate_nodes:
            logger.success(
                f"✅ Database đã có sẵn {current_node_count:,} Nodes (:VanBan). "
                "Bỏ qua bước tạo lại Nodes (tiết kiệm 30 phút)."
            )
        else:
            if force_recreate_nodes:
                logger.warning("force_recreate_nodes=True: Đang xóa dữ liệu cũ...")
                session.run("MATCH (n) DETACH DELETE n")

            logger.info(f"Đang tạo {total_docs:,} Nodes trên Neo4j...")
            nodes_data = []
            for doc_id, meta in docs.items():
                nodes_data.append({
                    "doc_id": doc_id,
                    "so_hieu": meta.get("so_hieu", ""),
                    "loai_van_ban": meta.get("loai_van_ban", ""),
                    "co_quan_ban_hanh": meta.get("co_quan_ban_hanh", ""),
                    "tinh_trang": meta.get("tinh_trang", ""),
                    "ngay_ban_hanh": meta.get("ngay_ban_hanh", ""),
                })

            query_nodes = """
            UNWIND $batch AS row
            MERGE (d:VanBan {doc_id: row.doc_id})
            SET d.so_hieu = row.so_hieu,
                d.loai_van_ban = row.loai_van_ban,
                d.co_quan_ban_hanh = row.co_quan_ban_hanh,
                d.tinh_trang = row.tinh_trang,
                d.ngay_ban_hanh = row.ngay_ban_hanh
            """
            batch_size = 1000
            for i in tqdm(range(0, len(nodes_data), batch_size), desc="Tạo Nodes"):
                batch = nodes_data[i : i + batch_size]
                session.run(query_nodes, batch=batch)

            logger.info("Tạo Nodes hoàn tất.")

    # 2. Tạo Edges từ config 'relationships'
    logger.info("Tải config 'relationships' từ HuggingFace...")
    ds_rels = load_dataset(dataset_name, "relationships", split="data")

    edges_data = []
    skipped_count = 0
    docs_set = set(docs.keys())

    for rel in tqdm(ds_rels, desc="Lọc quan hệ hợp lệ"):
        doc_id = str(rel.get("doc_id", ""))
        other_doc_id = str(rel.get("other_doc_id", ""))
        relationship = rel.get("relationship", "LIEN_QUAN")

        # Chỉ giữ lại quan hệ nếu CẢ 2 văn bản đều có mặt trong hệ thống
        if doc_id in docs_set and other_doc_id in docs_set:
            rel_type = relationship.upper().replace(" ", "_").replace(",", "")
            edges_data.append({
                "source": doc_id,
                "target": other_doc_id,
                "type": rel_type,
            })
        else:
            skipped_count += 1

    logger.info(
        f"Lọc quan hệ hoàn tất: {len(edges_data):,} quan hệ hợp lệ "
        f"(đã loại bỏ {skipped_count:,} quan hệ trỏ tới văn bản không tồn tại)."
    )

    # Group by type để chạy Cypher MERGE theo label type
    grouped_edges = {}
    for edge in edges_data:
        t = edge["type"]
        if t not in grouped_edges:
            grouped_edges[t] = []
        grouped_edges[t].append({"source": edge["source"], "target": edge["target"]})

    logger.info(f"Đang tạo {len(edges_data):,} Edges trên Neo4j (đã có Index)...")
    batch_size_edge = 1000

    def run_batch_with_retry(query, batch, max_retries=5):
        for attempt in range(max_retries):
            try:
                with driver.session() as session:
                    session.run(query, batch=batch)
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 5 * (attempt + 1)
                    logger.warning(
                        f"Mạng chập chờn ({e.__class__.__name__}). Tự động kết nối lại lần {attempt+2}/{max_retries} sau {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    raise

    for rel_type, batch in grouped_edges.items():
        safe_type = "".join([c if c.isalnum() else "_" for c in rel_type])
        query = f"""
        UNWIND $batch AS row
        MATCH (source:VanBan {{doc_id: row.source}})
        MATCH (target:VanBan {{doc_id: row.target}})
        MERGE (source)-[:{safe_type}]->(target)
        """

        for i in tqdm(range(0, len(batch), batch_size_edge), desc=f"Edge {safe_type}", leave=False):
            small_batch = batch[i : i + batch_size_edge]
            run_batch_with_retry(query, small_batch)

    driver.close()
    logger.success("✅ Tạo Edges hoàn tất! Toàn bộ Knowledge Graph đã sẵn sàng trên Neo4j.")
