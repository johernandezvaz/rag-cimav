import requests
from bs4 import BeautifulSoup
import sqlite3
import os
import time
import re

# ==========================
# Configuración inicial
# ==========================
BASE_URL = "https://cimav.repositorioinstitucional.mx/jspui/simple-search"
PARAMS = {"query": "", "sort_by": "score", "order": "desc", "rpp": "10", "etal": "0", "start": 0}

# Crear carpeta para PDFs
os.makedirs("pdfs", exist_ok=True)

# Conexión a la base de datos SQLite
conn = sqlite3.connect("scraping_cimav.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS publicaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT,
    autor TEXT,
    colaborador TEXT,
    nivel_acceso TEXT,
    licencia TEXT,
    materia TEXT,
    resumen TEXT,
    fecha_publicacion TEXT,
    tipo_publicacion TEXT,
    idioma TEXT,
    area_conocimiento TEXT,
    colecciones TEXT,
    pagina_origen TEXT,
    link_detalle TEXT,
    pdf_path TEXT
)
""")
conn.commit()


# ==========================
# Funciones auxiliares
# ==========================
def sanitize_filename(text):
    """Convierte texto en un nombre de archivo seguro."""
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', text)[:100]


def descargar_pdf(soup, titulo):
    """Busca y descarga el PDF dentro de la tabla id='tabla-archivos'."""
    tabla_pdf = soup.find("table", {"id": "tabla-archivos", "class": "table"})
    if tabla_pdf:
        enlace_pdf = tabla_pdf.find("a", href=True, class_="standard")
        if enlace_pdf:
            pdf_url = enlace_pdf["href"]
            if not pdf_url.startswith("http"):
                pdf_url = "https://cimav.repositorioinstitucional.mx" + pdf_url
            try:
                pdf_data = requests.get(pdf_url, timeout=15).content
                filename = f"pdfs/{sanitize_filename(titulo)}.pdf"
                with open(filename, "wb") as f:
                    f.write(pdf_data)
                return filename
            except Exception as e:
                print(f"No se pudo descargar PDF {pdf_url}: {e}")
                return None
    return None


def obtener_detalle(url_detalle, pagina_origen):
    try:
        res = requests.get(url_detalle, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        tabla = soup.find("table", class_="table itemDisplayTable")
        if not tabla:
            print(f"No se encontró tabla en {url_detalle}")
            return

        # Diccionario base con todos los campos vacíos
        datos = {
            "titulo": "",
            "autor": "",
            "colaborador": "",
            "nivel_acceso": "",
            "licencia": "",
            "materia": "",  #
            "resumen": "",
            "fecha_publicacion": "",
            "tipo_publicacion": "",
            "idioma": "",
            "area_conocimiento": "",
            "colecciones": ""
        }

        label_map = {
            "title :": "titulo",
            "authors:": "autor",
            "access level:": "nivel_acceso",
            "contributors:": "colaborador",
            "matter:": "materia",
            "licence:": "licencia",
            "summary or description:": "resumen",
            "issue date:": "fecha_publicacion",
            "type of publication:": "tipo_publicacion",
            "language:": "idioma",
            "knowledge area:": "area_conocimiento",
            "appears in collections:": "colecciones"
        }

        autor_ya_asignado = False

        # Recorrer todas las filas disponibles, sin asumir número fijo
        for tr in tabla.find_all("tr"):
            th = tr.find("td", class_="metadataFieldLabel")
            td = tr.find("td", class_="metadataFieldValue")
            if not th or not td:
                continue

            label = th.get_text(" ", strip=True).lower()
            valor = td.get_text(" ", strip=True)

            # Si el label es EXACTAMENTE authors:
            if label == "authors:":
                if not autor_ya_asignado:
                    # Primera vez → autores reales
                    datos["autor"] = valor
                    autor_ya_asignado = True
                else:
                    # Segunda vez o más → colaboradores
                    if datos["colaborador"]:
                        datos["colaborador"] += " ; " + valor
                    else:
                        datos["colaborador"] = valor
                continue  # Importante: seguimos con la siguiente fila

            # Coincidencias exactas para otros campos
            if label in label_map:
                campo = label_map[label]
                datos[campo] = valor

        # Descargar PDF (si hay título)
        pdf_path = descargar_pdf(soup, datos["titulo"])

        # Insertar en base de datos
        cursor.execute("""
            INSERT INTO publicaciones (
                titulo, autor, colaborador, nivel_acceso, licencia, materia, resumen,
                fecha_publicacion, tipo_publicacion, idioma, area_conocimiento,
                colecciones, pagina_origen, link_detalle, pdf_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datos["titulo"], datos["autor"], datos["colaborador"], datos["nivel_acceso"],
            datos["licencia"], datos["materia"], datos["resumen"], datos["fecha_publicacion"],
            datos["tipo_publicacion"], datos["idioma"], datos["area_conocimiento"],
            datos["colecciones"], pagina_origen, url_detalle, pdf_path
        ))
        conn.commit()

        print(f"✅ Guardado: {datos['titulo'] if datos['titulo'] else 'Sin título'}")

    except Exception as e:
        print(f"❌ Error accediendo a {url_detalle}: {e}")




# ==========================
# Scraper principal
# ==========================
while True:
    print(f"📄 Procesando página con start={PARAMS['start']}...")
    try:
        res = requests.get(BASE_URL, params=PARAMS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"No se pudo acceder a la página principal: {e}")
        break

    filas = soup.find_all("tr")
    if not filas:
        print("No se encontraron más resultados. Finalizando scraping.")
        break

    for fila in filas:
        celdas = fila.find_all("td")
        if len(celdas) >= 2:
            enlace = celdas[1].find("a", href=True)
            if enlace:
                detalle_url = enlace["href"]
                if not detalle_url.startswith("http"):
                    detalle_url = "https://cimav.repositorioinstitucional.mx" + detalle_url
                obtener_detalle(detalle_url, res.url)
                time.sleep(0.8)  # Delay para no saturar el servidor

    # Avanzar a la siguiente página
    PARAMS["start"] += 10
    time.sleep(1.5)

conn.close()
print("🏁 Scraping finalizado y datos almacenados en SQLite.")
