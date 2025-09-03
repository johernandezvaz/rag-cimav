from lxml import etree
import sqlite3
import os
from datetime import datetime

# --- CONFIGURACIÓN ---
fn = "2002.01650v5"
tei_path = f"teis/{fn}.tei.xml"
sqlite_db = "pdf_metadata.db"
student_id = 12345
student_name = "Juan Calderón"
source_file = f"{fn}.pdf"
doc_type = "paper"
language = "en"
current_date = datetime.today().strftime("%Y-%m-%d")

# --- VERIFICACIÓN DE ARCHIVO XML ---
if not os.path.exists(tei_path):
    raise FileNotFoundError(f"❌ Archivo no encontrado: {tei_path}")

# --- CONEXIÓN SQLITE Y CREACIÓN DE TABLAS ---
conn = sqlite3.connect(sqlite_db)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS metadata (
    pdf_id INTEGER PRIMARY KEY,
    source_file TEXT UNIQUE,
    student_id INTEGER,
    student_name TEXT,
    language TEXT,
    created_at DATE,
    type TEXT,
    journal TEXT,
    editorial TEXT,
    doi TEXT,
    published_date DATE,
    conference TEXT,
    isbn TEXT,
    title TEXT,
    abstract TEXT,
    keywords TEXT,
    affiliations TEXT,
    authors TEXT,
    first_author TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    pdf_id INTEGER,
    section TEXT,
    subsection TEXT,
    text TEXT,
    tokens INTEGER,
    FOREIGN KEY (pdf_id) REFERENCES metadata(pdf_id)
)
""")

# --- PARSEO DEL XML ---
xml = etree.parse(tei_path)
ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
Not_found = ""

# --- EXTRACCIÓN DEL HEADER ---
title = xml.findtext(".//tei:titleStmt/tei:title", namespaces=ns) or Not_found
abstract = xml.findtext(".//tei:abstract/tei:p", namespaces=ns) or Not_found
keywords = [kw.text for kw in xml.findall(".//tei:textClass/tei:keywords/tei:term", namespaces=ns) if kw.text]
keywords_str = ", ".join(keywords) if keywords else Not_found

# Autores
author_nodes = xml.findall(".//tei:sourceDesc//tei:author/tei:persName", namespaces=ns)
authors = []
for a in author_nodes:
    fname = a.findtext("tei:forename", namespaces=ns) or ""
    lname = a.findtext("tei:surname", namespaces=ns) or ""
    full = f"{fname.strip()} {lname.strip()}".strip()
    if full:
        authors.append(full)
all_authors = "; ".join(authors) if authors else Not_found
first_author_full = authors[0] if authors else Not_found

# Afiliaciones de los Autores
aff_nodes = xml.findall(".//tei:affiliation//tei:orgName[@type='institution']", namespaces=ns)
affiliations = [a.text.strip() for a in aff_nodes if a.text]
affiliations_str = "; ".join(affiliations) if affiliations else Not_found

# Campos adicionales utiles para las búsquedas estructurales/filtros
journal = xml.findtext(".//tei:monogr/tei:title", namespaces=ns) or Not_found
editorial = xml.findtext(".//tei:monogr/tei:imprint/tei:publisher", namespaces=ns) or Not_found
doi = xml.findtext(".//tei:idno[@type='DOI']", namespaces=ns) or Not_found
published_node = xml.find(".//tei:monogr/tei:imprint/tei:date", namespaces=ns)
published_date = published_node.get("when") if published_node is not None and published_node.get("when") else None
conference = xml.findtext(".//tei:meeting", namespaces=ns) or Not_found
isbn = xml.findtext(".//tei:idno[@type='ISBN']", namespaces=ns) or Not_found

# --- VERIFICAR SI YA EXISTE ESTE PDF ---
cur.execute("SELECT pdf_id FROM metadata WHERE source_file = ?", (source_file,))
row = cur.fetchone()

if row:
    pdf_db_id = row[0]
    print(f"⚠️ Ya existe un registro para '{source_file}' con pdf_id={pdf_db_id}. Insertando solo chunks nuevos.")
else:
    cur.execute("""
    INSERT INTO metadata (
        source_file, student_id, student_name, language, created_at, type,
        journal, editorial, doi, published_date, conference, isbn,
        title, abstract, keywords, affiliations, authors, first_author
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        source_file, student_id, student_name, language, current_date, doc_type,
        journal, editorial, doi, published_date, conference, isbn,
        title, abstract, keywords_str, affiliations_str, all_authors, first_author_full
    ))
    pdf_db_id = cur.lastrowid
    print(f"✅ Nuevo registro insertado en metadata con pdf_id={pdf_db_id}")

# --- Mapeo de encabezados conocidos ---
section_map = {
    "title": "Title",
    "abstract": "Abstract",
    "introduction": "Introduction",
    "background": "Background",
    "state of the art": "State_of_the_Art",
    "related work": "State_of_the_Art",
    "methodology": "Methods",
    "methods": "Methods",
    "our approach": "Methods",
    "approach": "Methods",
    "experiments": "Results",
    "experimental results": "Results",
    "evaluation": "Results",
    "discussion": "Discussion",
    "conclusion": "Conclusion",
    "future work": "Future_Work",
    "references": "References",
}

def normalize_section(head):
    if not head:
        return "Other"
    head_norm = head.lower().strip()
    for key, value in section_map.items():
        if key in head_norm:
            return value
    return "Other"

# --- INSERTAR CHUNKS EN DB SI NO EXISTEN ---
chunk_id = 0
inserted_chunks = 0

def insert_chunk(section, subsection, text):
    global chunk_id, inserted_chunks
    if text and text.strip():
        chunk_key = f"{pdf_db_id:03}_chunk_{chunk_id:04}"
        cur.execute("SELECT 1 FROM chunks WHERE chunk_id = ?", (chunk_key,))
        if not cur.fetchone():
            cur.execute("""
            INSERT INTO chunks (chunk_id, pdf_id, section, subsection, text, tokens)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (chunk_key, pdf_db_id, section, subsection, text.strip(), len(text.split())))
            inserted_chunks += 1
        chunk_id += 1

# --- INSERTAR HEADER COMO CHUNKS TAMBIÉN (opcional) ---
insert_chunk("Title", "Title", title)
insert_chunk("Abstract", "Abstract", abstract)
insert_chunk("Keywords", "Keywords", keywords_str)
insert_chunk("Affiliations", "Affiliations", affiliations_str)
insert_chunk("Authors", "Authors", all_authors)
insert_chunk("First_Author", "First_Author", first_author_full)

# --- INSERTAR CONTENIDO DEL CUERPO ---
for div in xml.findall(".//tei:text//tei:div", namespaces=ns):
    head = div.findtext("tei:head", namespaces=ns)
    if head and "appendix" in head.lower():
        continue
    paragraphs = div.findall("tei:p", namespaces=ns)
    text = "\n".join(p.text for p in paragraphs if p is not None and p.text)
    if text:
        norm_section = normalize_section(head)
        insert_chunk(norm_section, head.strip() if head else norm_section, text)

# --- FINALIZAR ---
conn.commit()
conn.close()
print(f"✅ {inserted_chunks} nuevos chunks insertados para pdf_id={pdf_db_id} en SQLite → {sqlite_db}")
