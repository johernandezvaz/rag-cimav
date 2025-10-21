from fastapi import FastAPI
from pydantic import BaseModel
import faiss, numpy as np
from sentence_transformers import SentenceTransformer
import sqlite3

app = FastAPI()
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
index = faiss.read_index("indice_semantico.faiss")
ids = np.load("ids_semanticos.npy")

class Query(BaseModel):
    query: str

@app.post("/query")
def query_faiss(data: Query):
    q_emb = model.encode([data.query], normalize_embeddings=True)
    scores, idxs = index.search(q_emb, 5)

    conn = sqlite3.connect("scraping_cimav.db")
    cursor = conn.cursor()
    results = []
    for i, idx in enumerate(idxs[0]):
        doc_id = int(ids[idx])
        cursor.execute("SELECT titulo, autor, resumen FROM publicaciones WHERE id=?", (doc_id,))
        r = cursor.fetchone()
        if r:
            titulo, autor, resumen = r
            results.append(f"{titulo} ({autor}): {resumen[:200]}...")
    conn.close()

    return {"response": "\n\n".join(results) if results else "No se encontraron coincidencias."}
