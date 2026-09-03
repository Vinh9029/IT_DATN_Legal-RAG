from neo4j import GraphDatabase
from loguru import logger
from tqdm import tqdm
from pathlib import Path
from datasets import load_dataset
import json

def build_neo4j_graph(uri: str, user: str, password: str, dataset_name: str, chunks_path: Path):
    """
    Tạo các Node từ chunks (mỗi văn bản là 1 Node)
    Tạo các Cạnh từ dataset config 'relationships'
    """
    logger.info("Kết nối tới Neo4j...")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    # 1. Thu thập danh sách văn bản và tạo Nodes
    logger.info("Thu thập metadata từ các documents...")
    docs = {}
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in tqdm(f, desc="Đọc chunks để lấy Docs"):
            item = json.loads(line)
            doc_id = item.get("doc_id")
            if doc_id and doc_id not in docs:
                # Giữ lại document info đầu tiên (các chunks có metadata giống nhau)
                docs[doc_id] = item.get("metadata", {})
                
    logger.info(f"Đã thu thập {len(docs)} văn bản. Đang tạo Nodes trên Neo4j...")
    with driver.session() as session:
        # Xóa dữ liệu cũ
        session.run("MATCH (n) DETACH DELETE n")
        
        # Batch insert nodes
        nodes_data = []
        for doc_id, meta in docs.items():
            nodes_data.append({
                "doc_id": str(doc_id),
                "so_hieu": meta.get("so_hieu", ""),
                "loai_van_ban": meta.get("loai_van_ban", ""),
                "co_quan_ban_hanh": meta.get("co_quan_ban_hanh", ""),
                "tinh_trang": meta.get("tinh_trang", ""),
                "ngay_ban_hanh": meta.get("ngay_ban_hanh", "")
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
        
        # Insert 1000 nodes mỗi batch
        batch_size = 1000
        for i in range(0, len(nodes_data), batch_size):
            batch = nodes_data[i:i+batch_size]
            session.run(query_nodes, batch=batch)
            
    logger.info("Tạo Nodes hoàn tất.")
    
    # 2. Tạo Edges từ config 'relationships'
    logger.info("Tải config 'relationships' từ HuggingFace...")
    ds_rels = load_dataset(dataset_name, "relationships", split="data")
    
    edges_data = []
    for rel in tqdm(ds_rels, desc="Xử lý relations"):
        doc_id = rel.get("doc_id")
        other_doc_id = rel.get("other_doc_id")
        relationship = rel.get("relationship", "LIEN_QUAN")
        
        # Format relationship string to be valid Neo4j relationship type
        rel_type = relationship.upper().replace(" ", "_").replace(",", "")
        
        if doc_id and other_doc_id:
            edges_data.append({
                "source": str(doc_id),
                "target": str(other_doc_id),
                "type": rel_type
            })
            
    logger.info(f"Đã thu thập {len(edges_data)} quan hệ. Đang tạo Edges trên Neo4j...")
    with driver.session() as session:
        query_edges = """
        UNWIND $batch AS row
        MATCH (source:VanBan {doc_id: row.source})
        MATCH (target:VanBan {doc_id: row.target})
        CALL apoc.create.relationship(source, row.type, {}, target)
        YIELD rel
        RETURN count(*)
        """
        # Nếu không có APOC (Neo4j plugin), có thể dùng query động (nhưng apoc phổ biến hơn)
        # Cách không dùng APOC cho dynamic relationship types:
        # Không hỗ trợ parameterise relationship type trong Cypher thường.
        # Chúng ta sẽ group by relationship type
        
    # Group by type để query
    grouped_edges = {}
    for edge in edges_data:
        t = edge["type"]
        if t not in grouped_edges:
            grouped_edges[t] = []
        grouped_edges[t].append({"source": edge["source"], "target": edge["target"]})
        
    with driver.session() as session:
        for rel_type, batch in grouped_edges.items():
            # Chỉ allow alphanumeric + _ cho type
            safe_type = "".join([c if c.isalnum() else "_" for c in rel_type])
            
            query = f"""
            UNWIND $batch AS row
            MATCH (source:VanBan {{doc_id: row.source}})
            MATCH (target:VanBan {{doc_id: row.target}})
            MERGE (source)-[:{safe_type}]->(target)
            """
            
            # Insert theo batch nhỏ
            batch_size_edge = 2000
            for i in range(0, len(batch), batch_size_edge):
                small_batch = batch[i:i+batch_size_edge]
                session.run(query, batch=small_batch)
                
    driver.close()
    logger.info("Tạo Edges hoàn tất! Build Neo4j xong.")
