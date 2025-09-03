import sqlite3
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

class FaissSemanticSearchSQLite:
    def __init__(self, db_path, faiss_index_path, model_name="multi-qa-MiniLM-L6-dot-v1"):
        self.db_path = db_path
        self.index = faiss.read_index(faiss_index_path)
        self.model = SentenceTransformer(model_name)

        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.chunk_ids = self._load_chunk_ids()

    def _load_chunk_ids(self):
        cur = self.conn.cursor()
        cur.execute("SELECT chunk_id FROM chunks WHERE text IS NOT NULL AND LENGTH(text) > 20")
        return [row[0] for row in cur.fetchall()]

    def search(self, query, k=5, sections=None, filters=None):
        query_vec = self.model.encode([query], convert_to_numpy=True).astype(np.float32)
        D, I = self.index.search(query_vec, k * 10)

        results = []
        for rank, idx in enumerate(I[0]):
            if idx < 0 or idx >= len(self.chunk_ids):
                continue

            chunk_id = self.chunk_ids[idx]
            chunk = self._get_chunk_with_metadata(chunk_id)
            if not chunk:
                continue

            # Filtro por sección
            if sections and chunk["section"] not in sections:
                continue

            # Filtros adicionales
            if filters:
                if "title" in filters and filters["title"].lower() not in chunk["title"].lower():
                    continue
                if "student_id" in filters and filters["student_id"] != chunk["student_id"]:
                    continue
                if "student_name" in filters and filters["student_name"].lower() not in chunk["student_name"].lower():
                    continue
                if "author" in filters:
                    authors_filter = filters["author"]
                    if isinstance(authors_filter, str):
                        authors_filter = [x.strip() for x in authors_filter.split(";")]
                    match = any(name.lower() in chunk["authors"].lower() for name in authors_filter)
                    if not match:
                        continue
                if "journal" in filters and filters["journal"].lower() not in chunk["journal"].lower():
                    continue
                if "editorial" in filters and filters["editorial"].lower() not in chunk["editorial"].lower():
                    continue
                if "year" in filters and chunk["published_date"]:
                    if filters["year"] != chunk["published_date"][:4]:
                        continue
                if "abstract" in filters and filters["abstract"].lower() not in chunk["abstract"].lower():
                    continue
                if "keywords" in filters and filters["keywords"].lower() not in chunk["keywords"].lower():
                    continue
                if "affiliations" in filters and filters["affiliations"].lower() not in chunk["affiliations"].lower():
                    continue

            results.append({
                "chunk_id": chunk["chunk_id"],
                "section": chunk["section"],
                "subsection": chunk["subsection"],
                "text": chunk["text"],
                "score": float(D[0][rank]),
                "title": chunk["title"],
                "abstract": chunk["abstract"],
                "keywords": chunk["keywords"],
                "affiliations": chunk["affiliations"],
                "student_name": chunk["student_name"],
                "student_id": chunk["student_id"],
                "authors": chunk["authors"],
                "journal": chunk["journal"],
                "doi": chunk["doi"],
                "published_date": chunk["published_date"],
                "conference": chunk["conference"],
                "isbn": chunk["isbn"]
            })

            if len(results) >= k:
                break

        return results

    def _get_chunk_with_metadata(self, chunk_id):
        cur = self.conn.cursor()
        cur.execute("""
        SELECT c.chunk_id, c.section, c.subsection, c.text,
               m.student_id, m.student_name, m.journal, m.editorial, m.doi,
               m.published_date, m.conference, m.isbn,
               m.title, m.abstract, m.keywords, m.affiliations, m.authors
        FROM chunks c
        JOIN metadata m ON c.pdf_id = m.pdf_id
        WHERE c.chunk_id = ?
        """, (chunk_id,))
        return cur.fetchone()

