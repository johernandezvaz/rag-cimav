import sqlite3

# Crear conexión (si no existe el archivo .db, se crea)
conn = sqlite3.connect("pdf_metadata.db")

# Crear cursor
cur = conn.cursor()

cur.execute("DROP TABLE IF EXISTS chunks")
cur.execute("DROP TABLE IF EXISTS metadata")

if False:
    # Crear tabla (si no existe)
    cur.execute('''
    CREATE TABLE IF NOT EXISTS metadata (
        pdf_id INTEGER PRIMARY KEY,
        source_file TEXT,
        student_id INTEGER,
        student_name TEXT,
        language TEXT,
        created_at TEXT,
        type TEXT
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        pdf_id INTEGER,
        section TEXT,
        subsection TEXT,
        text TEXT,
        tokens INTEGER,
        FOREIGN KEY (pdf_id) REFERENCES metadata(pdf_id)
    )    
    ''')

# Guardar cambios y cerrar
conn.commit()
conn.close()

print("Base de datos SQLite lista.")
