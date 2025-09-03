import requests
import os

# --- CONFIGURACIÓN ---
fn = "2002.01650v5"
pdf_path = f"papers/{fn}.pdf"
output_tei_path = f"teis/{fn}.tei.xml"
grobid_url = "http://localhost:8070/api/processFulltextDocument"

# --- VERIFICACIONES ---
if not os.path.exists(pdf_path):
    raise FileNotFoundError(f"❌ PDF no encontrado: {pdf_path}")

# --- PROCESAR PDF CON GROBID ---
with open(pdf_path, 'rb') as f:
    files = {'input': (os.path.basename(pdf_path), f, 'application/pdf')}
    response = requests.post(grobid_url, files=files)

if response.status_code != 200:
    print(f"❌ Error al procesar el PDF. Código HTTP: {response.status_code}")
    exit()

# --- GUARDAR RESULTADO ---
os.makedirs(os.path.dirname(output_tei_path), exist_ok=True)

with open(output_tei_path, "w", encoding="utf8") as f:
    f.write(response.text)

print(f"✅ TEI guardado en: {output_tei_path}")

