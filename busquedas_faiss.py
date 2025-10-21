import faiss, numpy as np, json

# Cargar índice y datos
index = faiss.read_index("indice_publicaciones.faiss")
ids = np.load("ids_publicaciones.npy")

# Buscar un texto
query = "biotecnología y energía solar"
from generar_indice import obtener_vector_local
vec = obtener_vector_local(query).reshape(1, -1)

D, I = index.search(vec, k=5)
for i, dist in zip(I[0], D[0]):
    print(f"ID: {ids[i]}, Distancia: {dist:.4f}")
