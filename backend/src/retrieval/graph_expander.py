from neo4j import GraphDatabase
from loguru import logger
from typing import List

class GraphExpander:
    def __init__(self, uri: str, user: str, password: str):
        self.uri = uri
        self.user = user
        self.password = password
        self.driver = None
        self._connect()

    def _connect(self):
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            logger.info("Kết nối Neo4j thành công.")
        except Exception as e:
            logger.error(f"Lỗi kết nối Neo4j: {e}")

    def get_related_documents(self, doc_ids: List[str], depth: int = 1) -> List[dict]:
        """
        Tìm các văn bản liên quan đến các doc_id đã cho.
        Ví dụ: văn bản sửa đổi, bổ sung, hướng dẫn...
        """
        if not self.driver or not doc_ids:
            return []

        # Chỉ lấy max depth = 1 hoặc 2 để tránh nổ node
        query = f"""
        UNWIND $doc_ids AS doc_id
        MATCH (source:VanBan {{doc_id: doc_id}})-[r*1..{depth}]-(target:VanBan)
        RETURN DISTINCT target.doc_id AS related_doc_id, 
                        target.so_hieu AS so_hieu, 
                        type(r[0]) AS rel_type, 
                        source.doc_id AS source_doc
        LIMIT 20
        """
        
        results = []
        with self.driver.session() as session:
            try:
                records = session.run(query, doc_ids=doc_ids)
                for record in records:
                    results.append({
                        "source_doc_id": record["source_doc"],
                        "related_doc_id": record["related_doc_id"],
                        "so_hieu": record["so_hieu"],
                        "relation": record["rel_type"]
                    })
            except Exception as e:
                logger.error(f"Lỗi truy vấn Neo4j: {e}")
                
        return results

    def close(self):
        if self.driver:
            self.driver.close()
