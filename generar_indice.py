import sqlite3
import generar_indice
import faiss
import numpy as np
import os
import json
import re
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

# ============================
# CONFIGURACIÓN
# ============================
DB_PATH = "scraping_cimav.db"
FAISS_PATH = "indice_publicaciones.faiss"
IDS_PATH = "ids_publicaciones.npy"
CACHE_PATH = "cache_embeddings.json"

# ============================
# CONFIGURAR NLTK (solo primera vez)
# ============================
nltk.download('punkt')
nltk.download('punkt_tab')
nltk.download('stopwords')

stop_words = set(stopwords.words('spanish'))

# ============================
# TOKENIZACIÓN Y EMBEDDING LOCAL
# ============================

def tokenizar(texto):
    """Tokeniza texto eliminando signos, minúsculas y stopwords."""
    texto = texto.lower()
    texto = re.sub(r'[^a-záéíóúñü0-9\s]', '', texto)
    tokens = word_tokenize(texto)
    return [t for t in tokens if t not in stop_words and len(t) > 2]

def obtener_vector_local(texto):
    """
    Convierte un texto a un vector numérico fijo usando una representación simple.
    (suma o promedio de índices hash de las palabras)
    """
    tokens = tokenizar(texto)
    if not tokens:
        return None

    # Convertir cada token a un número mediante un hash reproducible
    vec_size = 128  # dimensión del vector, puede ajustarse
    vector = np.zeros(vec_size, dtype=np.float32)

    for token in tokens:
        # Convertimos el token en un número y lo distribuimos en el vector
        idx = abs(hash(token)) % vec_size
        vector[idx] += 1.0

    # Normalizar
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector /= norm

    return vector


# ============================
# CARGAR CACHÉ EXISTENTE
# ============================
if os.path.exists(CACHE_PATH):
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        cache_embeddings = json.load(f)
else:
    cache_embeddings = {}


def obtener_embedding(texto):
    """Devuelve embedding reutilizando caché o generando nuevo."""
    texto = texto.strip()
    if not texto:
        return None

    if texto in cache_embeddings:
        return np.array(cache_embeddings[texto], dtype=np.float32)

    vector = obtener_vector_local(texto)
    if vector is not None:
        cache_embeddings[texto] = vector.tolist()
    return vector


# ============================
# LEER BASE DE DATOS
# ============================
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("""
    SELECT id,
           titulo,
           autor,
           colaborador,
           nivel_acceso,
           licencia,
           materia,
           resumen,
           fecha_publicacion,
           tipo_publicacion,
           idioma,
           area_conocimiento,
           colecciones
    FROM publicaciones
""")
registros = cursor.fetchall()
conn.close()


# ============================
# GENERAR TEXTOS POR DOCUMENTO
# ============================
documentos = []
ids = []

for fila in registros:
    (doc_id, titulo, autor, colaborador, nivel_acceso, licencia, materia, resumen,
     fecha_publicacion, tipo_publicacion, idioma, area_conocimiento, colecciones) = fila

    texto = f"""
    Título: {titulo or ""}
    Autores: {autor or ""}
    Colaboradores: {colaborador or ""}
    Nivel de acceso: {nivel_acceso or ""}
    Licencia: {licencia or ""}
    Materia: {materia or ""}
    Resumen: {resumen or ""}
    Fecha de publicación: {fecha_publicacion or ""}
    Tipo de publicación: {tipo_publicacion or ""}
    Idioma: {idioma or ""}
    Área de conocimiento: {area_conocimiento or ""}
    Colecciones: {colecciones or ""}
    """.strip()

    documentos.append(texto)
    ids.append(doc_id)


# ============================
# GENERAR EMBEDDINGS LOCALES
# ============================
vectores = []
ids_finales = []

for doc_id, doc in zip(ids, documentos):
    embedding = obtener_embedding(doc)
    if embedding is not None:
        vectores.append(embedding)
        ids_finales.append(doc_id)
    else:
        print(f"⚠️ Error generando embedding para ID {doc_id}")

# ============================
# CREAR ÍNDICE FAISS
# ============================
if vectores:
    vectores_np = np.vstack(vectores)
    dimension = vectores_np.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(vectores_np)

    faiss.write_index(index, FAISS_PATH)
    np.save(IDS_PATH, np.array(ids_finales))
    print(f"✅ {len(vectores)} embeddings locales almacenados en FAISS")
else:
    print("⚠️ No se generaron embeddings válidos")

# ============================
# GUARDAR CACHÉ EN DISCO
# ============================
with open(CACHE_PATH, "w", encoding="utf-8") as f:
    json.dump(cache_embeddings, f)

print(f"💾 Cache actualizado con {len(cache_embeddings)} textos únicos.")
