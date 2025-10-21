import os
import json
from PyPDF2 import PdfReader

# Ruta al directorio con los PDFs
pdf_directory = "RAG/tesis"

# Lista para almacenar los metadatos de todos los PDFs
all_metadata = []

for filename in os.listdir(pdf_directory):
    if filename.lower().endswith(".pdf"):
        filepath = os.path.join(pdf_directory, filename)

        try:
            reader = PdfReader(filepath)
            metadata = reader.metadata  # Dicc con metadatos

            # Convertimos los metadatos en JSON serializable
            meta_dict = {key.replace("/", ""): value for key, value in metadata.items()} if metadata else {}

            # Agregamos información adicional útil
            meta_dict["filename"] = filename
            meta_dict["num_pages"] = len(reader.pages)

            all_metadata.append(meta_dict)
            print(f"✅ Procesado: {filename}")

        except Exception as e:
            print(f"❌ Error procesando {filename}: {e}")

# Guardar todo en un archivo JSON
with open("metadata_tesis.json", "w", encoding="utf-8") as json_file:
    json.dump(all_metadata, json_file, indent=4, ensure_ascii=False)

print("\n📁 Metadatos guardados en metadata_tesis.json")
