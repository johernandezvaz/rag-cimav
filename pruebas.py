import sqlite3
import numpy as np
import faiss
import re
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

# === CONFIGURACIÓN ===
DB_PATH = "scraping_cimav.db"
FAISS_PATH = "indice_publicaciones.faiss"
IDS_PATH = "ids_publicaciones.npy"

# === CONFIGURAR NLTK ===
nltk.download('punkt')
nltk.download('stopwords')
stop_words = set(stopwords.words('spanish'))

# === FUNCIONES DE TOKENIZACIÓN Y EMBEDDING ===
def tokenizar(texto):
    texto = texto.lower()
    texto = re.sub(r'[^a-záéíóúñü0-9\s]', '', texto)
    tokens = word_tokenize(texto)
    return [t for t in tokens if t not in stop_words and len(t) > 2]

def obtener_vector_local(texto):
    vec_size = 128
    tokens = tokenizar(texto)
    if not tokens:
        return None
    vector = np.zeros(vec_size, dtype=np.float32)
    for token in tokens:
        idx = abs(hash(token)) % vec_size
        vector[idx] += 1.0
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector /= norm
    return vector

# === CARGAR FAISS E IDS ===
index = faiss.read_index(FAISS_PATH)
ids = np.load(IDS_PATH)

# === CONECTAR A LA BASE DE DATOS ===
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

def buscar(query, k=5):
    query_vec = obtener_vector_local(query)
    if query_vec is None:
        print("⚠️ No se pudo generar vector para la consulta.")
        return

    query_vec = np.expand_dims(query_vec, axis=0)
    print(f"Dimensión del índice FAISS: {index.d}, dimensión del query: {query_vec.shape[1]}")

    distances, indices = index.search(query_vec, k)
    print(f"\n🔍 Resultados para: '{query}'\n")

    for i, (idx, dist) in enumerate(zip(indices[0], distances[0])):
        real_id = int(ids[idx])
        cursor.execute("""
            SELECT id, titulo, autor, materia, resumen, fecha_publicacion, tipo_publicacion, link_detalle
            FROM publicaciones
            WHERE id = ?
        """, (real_id,))
        row = cursor.fetchone()
        if row:
            (id_pub, titulo, autor, materia, resumen, fecha, tipo, link) = row
            print(f"🔹 Resultado {i+1}")
            print(f"🆔 ID: {id_pub} | 📏 Distancia: {dist:.4f}")
            print(f"📖 Título: {titulo or 'N/A'}")
            print(f"👤 Autor: {autor or 'N/A'}")
            print(f"📚 Materia: {materia or 'N/A'}")
            print(f"📅 Fecha: {fecha or 'N/A'}")
            print(f"🧾 Tipo: {tipo or 'N/A'}")
            print(f"🔗 Link: {link or 'N/A'}")
            print(f"📝 Resumen: {(resumen or 'Sin resumen')[:400]}...\n")
        else:
            print(f"⚠️ No se encontró el ID {real_id} en la base.\n")

if __name__ == "__main__":
    print("🤖 Buscador FAISS + SQLite listo. Escribe una consulta o 'salir' para terminar.\n")
    while True:
        pregunta = input("🔹 Pregunta: ")
        if pregunta.lower() == "salir":
            break
        buscar(pregunta)

conn.close()
