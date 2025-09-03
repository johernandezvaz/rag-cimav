# semantic_search.py
import faiss
import numpy as np
import json
from sentence_transformers import SentenceTransformer

class FaissSemanticSearch:
    def __init__(self, faiss_index_path, metadata_path, model_name="all-MiniLM-L6-v2"):
        self.faiss_index_path = faiss_index_path
        self.metadata_path = metadata_path
        self.model = SentenceTransformer(model_name)

        # Cargar índice FAISS
        self.index = faiss.read_index(faiss_index_path)

        # Cargar metadatos enriquecidos (chunks + metadata)
        with open(metadata_path, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        assert self.index.ntotal == len(self.metadata), "❌ FAISS index and metadata size mismatch"

    def search(self, query, sections=None, k=5):
        """
        Realiza una búsqueda semántica en el índice FAISS.
        :param query: texto de búsqueda
        :param sections: lista de secciones donde buscar (e.g. ["Abstract", "Title"])
        :param k: número máximo de resultados deseados
        :return: lista de resultados relevantes con metadata
        """
        query_vec = self.model.encode([query], convert_to_numpy=True).astype(np.float32)
        D, I = self.index.search(query_vec, k * 5)  # buscamos más de k para permitir filtrado

        results = []
        for rank, idx in enumerate(I[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue
            item = self.metadata[idx]
            if sections is None or item.get("section") in sections:
                results.append({
                    "id": item.get("id"),
                    "pdf_id": item.get("pdf_id"),
                    "section": item.get("section"),
                    "subsection": item.get("subsection", ""),
                    "text": item.get("text", ""),
                    "score": float(D[0][rank]),
                    # Campos enriquecidos desde metadata
                    "title": item.get("title", ""),
                    "student_name": item.get("student_name", ""),
                    "source_file": item.get("source_file", ""),
                    "journal": item.get("journal", ""),
                    "doi": item.get("doi", ""),
                    "published_date": item.get("published_date", ""),
                    "conference": item.get("conference", ""),
                    "isbn": item.get("isbn", "")
                })
                if len(results) >= k:
                    break
        return results
