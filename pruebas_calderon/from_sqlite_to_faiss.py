# from_sqlite_to_faiss.py
import sqlite3
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# Configuración
db_path = "pdf_metadata.db"
model_name = "all-MiniLM-L6-v2" # "intfloat/e5-base-v2" "multi-qa-MiniLM-L6-dot-v1"
model_name = "multi-qa-MiniLM-L6-dot-v1"
faiss_index_path = "faiss.index"

# Conectar a SQLite y cargar los textos desde chunks
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("""
SELECT chunk_id, text FROM chunks 
WHERE text IS NOT NULL AND LENGTH(text) > 20
""")
rows = cur.fetchall()
conn.close()

print(f"✅ Se encontraron {len(rows)} chunks para indexar.")

# Extraer textos e IDs
ids = [row[0] for row in rows]
texts = [row[1] for row in rows]

# Embeddings
model = SentenceTransformer(model_name)
embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=True).astype(np.float32)

# Crear índice FAISS
dim = embeddings.shape[1]
index = faiss.IndexFlatL2(dim)
index.add(embeddings)

# Guardar índice
faiss.write_index(index, faiss_index_path)
print(f"✅ FAISS index guardado en: {faiss_index_path}")
