import json
import sqlite3
import re
import os
from pathlib import Path
from datetime import datetime
import hashlib


class ThesisJSONToSQLConverter:
    """
    Convierte el JSON de análisis de tesis a base de datos SQL
    optimizada para tokenización y uso con FAISS
    """

    def __init__(self, db_path="thesis_database.db"):
        """
        Inicializa el convertidor con la base de datos SQLite

        Args:
            db_path (str): Ruta de la base de datos SQLite
        """
        self.db_path = db_path
        self.conn = None
        self.setup_database()

    def setup_database(self):
        """Crea las tablas necesarias para almacenar los datos de tesis"""
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()

        # Tabla principal de documentos
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS documents
                       (
                           id               INTEGER PRIMARY KEY AUTOINCREMENT,
                           filename         TEXT UNIQUE NOT NULL,
                           title            TEXT,
                           language         TEXT,
                           authors          TEXT,
                           date_published   TEXT,
                           abstract         TEXT,
                           processing_date  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           total_sections   INTEGER,
                           total_references INTEGER,
                           file_hash        TEXT
                       )
                       ''')

        # Tabla de secciones tokenizadas
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS sections
                       (
                           id               INTEGER PRIMARY KEY AUTOINCREMENT,
                           document_id      INTEGER,
                           section_title    TEXT,
                           section_category TEXT,
                           content          TEXT,
                           content_length   INTEGER,
                           tokens_count     INTEGER,
                           chunk_index      INTEGER,
                           embedding_vector TEXT,
                           FOREIGN KEY (document_id) REFERENCES documents (id)
                       )
                       ''')

        # Tabla de chunks para FAISS
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS text_chunks
                       (
                           id            INTEGER PRIMARY KEY AUTOINCREMENT,
                           document_id   INTEGER,
                           section_id    INTEGER,
                           chunk_text    TEXT,
                           chunk_size    INTEGER,
                           chunk_index   INTEGER,
                           overlap_start INTEGER,
                           overlap_end   INTEGER,
                           metadata_json TEXT,
                           vector_id     INTEGER,
                           FOREIGN KEY (document_id) REFERENCES documents (id),
                           FOREIGN KEY (section_id) REFERENCES sections (id)
                       )
                       ''')

        # Tabla de referencias bibliográficas
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS bibliographic_references
                       (
                           id          INTEGER PRIMARY KEY AUTOINCREMENT,
                           document_id INTEGER,
                           ref_title   TEXT,
                           ref_authors TEXT,
                           ref_date    TEXT,
                           ref_index   INTEGER,
                           FOREIGN KEY (document_id) REFERENCES documents (id)
                       )
                       ''')

        # Índices para optimizar búsquedas
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sections_category ON sections(section_category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chunks_document ON text_chunks(document_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chunks_vector ON text_chunks(vector_id)')
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_bibliographic_refs_document ON bibliographic_references(document_id)')

        self.conn.commit()
        print("✅ Base de datos inicializada correctamente")

    def calculate_file_hash(self, content):
        """Calcula hash MD5 del contenido para detectar duplicados"""
        return hashlib.md5(str(content).encode()).hexdigest()

    def tokenize_text(self, text, chunk_size=512, overlap=50):
        """
        Tokeniza texto en chunks optimizados para FAISS

        Args:
            text (str): Texto a tokenizar
            chunk_size (int): Tamaño máximo de cada chunk en caracteres
            overlap (int): Solapamiento entre chunks

        Returns:
            list: Lista de chunks con metadatos
        """
        if not text or len(text.strip()) < 10:
            return []

        # Limpiar texto
        text = re.sub(r'\s+', ' ', text.strip())

        chunks = []
        start = 0
        chunk_index = 0

        while start < len(text):
            # Calcular fin del chunk
            end = start + chunk_size

            # Si no es el último chunk, buscar un punto de corte natural
            if end < len(text):
                # Buscar el último punto, salto de línea o espacio antes del límite
                for separator in ['. ', '\n', ' ']:
                    last_sep = text.rfind(separator, start, end)
                    if last_sep > start:
                        end = last_sep + len(separator)
                        break

            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append({
                    'text': chunk_text,
                    'size': len(chunk_text),
                    'index': chunk_index,
                    'start_pos': start,
                    'end_pos': end,
                    'overlap_start': max(0, start - overlap) if chunk_index > 0 else 0,
                    'overlap_end': min(len(text), end + overlap)
                })
                chunk_index += 1

            # Mover al siguiente chunk con solapamiento
            start = max(start + 1, end - overlap)

        return chunks

    def estimate_tokens(self, text):
        """Estima el número de tokens (aproximadamente 4 caracteres por token)"""
        return len(text) // 4

    def clean_and_validate_title(self, title):
        """
        Limpia y valida títulos, detectando títulos institucionales incorrectos

        Args:
            title (str): Título a validar

        Returns:
            str: Título limpio o "Sin título válido" si no es válido
        """
        if not title or not title.strip():
            return "Sin título válido"

        title = title.strip()

        # Patrones que indican que NO es un título válido
        invalid_patterns = [
            r'centro de investigación',
            r'departamento de',
            r'universidad de',
            r'instituto de',
            r'facultad de',
            r'escuela de',
            r'división de',
            r'posgrado',
            r'postgrado',
            r'licenciatura',
            r'maestría',
            r'doctorado',
            r'tesis de',
            r'trabajo de',
            r'proyecto de',
            r'cimav',
            r's\.c\.',
            r'a\.c\.',
            r'estudios de posgrado'
        ]

        # Verificar si contiene patrones institucionales
        title_lower = title.lower()
        for pattern in invalid_patterns:
            if re.search(pattern, title_lower):
                return "Sin título válido"

        # Verificar longitud mínima y máxima razonable
        if len(title) < 10:
            return "Sin título válido"

        if len(title) > 500:  # Títulos muy largos probablemente son errores
            return "Sin título válido"

        # Verificar que no sea solo mayúsculas (común en headers institucionales)
        if title.isupper() and len(title) > 50:
            return "Sin título válido"

        # Limpiar caracteres extraños y espacios múltiples
        title = re.sub(r'\s+', ' ', title)
        title = re.sub(r'[^\w\s\-\.\,\:\;\(\)\[\]áéíóúñüÁÉÍÓÚÑÜ]', '', title)

        return title.strip()

    def extract_real_title_from_content(self, thesis_data):
        """
        Intenta extraer el título real del contenido del documento

        Args:
            thesis_data (dict): Datos del análisis de tesis

        Returns:
            str: Título extraído o "Sin título válido"
        """
        content = thesis_data.get('content', {})
        sections = content.get('sections', [])

        # Buscar en las primeras secciones
        for section in sections[:3]:  # Solo las primeras 3 secciones
            section_title = section.get('title', '').strip()
            section_content = section.get('content', '').strip()

            # Si el título de la sección parece ser el título real
            cleaned_title = self.clean_and_validate_title(section_title)
            if cleaned_title != "Sin título válido" and len(cleaned_title) > 20:
                return cleaned_title

            # Buscar en el contenido de la sección (primeras líneas)
            if section_content:
                lines = section_content.split('\n')[:5]  # Primeras 5 líneas
                for line in lines:
                    line = line.strip()
                    if len(line) > 20 and len(line) < 200:
                        cleaned_line = self.clean_and_validate_title(line)
                        if cleaned_line != "Sin título válido":
                            return cleaned_line

        # Buscar en el texto completo (primeras líneas)
        full_text = content.get('full_text', '')
        if full_text:
            lines = full_text.split('\n')[:10]  # Primeras 10 líneas
            for line in lines:
                line = line.strip()
                if len(line) > 30 and len(line) < 300:
                    cleaned_line = self.clean_and_validate_title(line)
                    if cleaned_line != "Sin título válido":
                        return cleaned_line

        return "Sin título válido"

    def insert_document(self, thesis_data):
        """
        Inserta un documento de tesis en la base de datos

        Args:
            thesis_data (dict): Datos del análisis de tesis

        Returns:
            int: ID del documento insertado
        """
        cursor = self.conn.cursor()

        # Extraer metadatos
        metadata = thesis_data.get('metadata', {})
        content = thesis_data.get('content', {})

        # Limpiar y validar título
        original_title = metadata.get('title', 'Sin título')
        cleaned_title = self.clean_and_validate_title(original_title)

        # Si el título no es válido, intentar extraerlo del contenido
        if cleaned_title == "Sin título válido":
            cleaned_title = self.extract_real_title_from_content(thesis_data)
            print(f"⚠️  Título original inválido: '{original_title[:50]}...'")
            print(f"✅ Título extraído del contenido: '{cleaned_title}'")

        # Calcular hash para detectar duplicados
        file_hash = self.calculate_file_hash(thesis_data)

        # Verificar si ya existe
        cursor.execute('SELECT id FROM documents WHERE file_hash = ?', (file_hash,))
        existing = cursor.fetchone()
        if existing:
            print(f"⚠️  Documento ya existe en la base de datos: {thesis_data.get('file', 'unknown')}")
            return existing[0]

        # Insertar documento
        cursor.execute('''
                       INSERT INTO documents (filename, title, language, authors, date_published,
                                              abstract, total_sections, total_references, file_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ''', (
                           thesis_data.get('file', 'unknown'),
                           cleaned_title,
                           content.get('language', 'unknown'),
                           json.dumps(metadata.get('authors', []), ensure_ascii=False),
                           metadata.get('date'),
                           metadata.get('abstract'),
                           len(content.get('sections', [])),
                           len(thesis_data.get('references', [])),
                           file_hash
                       ))

        document_id = cursor.lastrowid
        self.conn.commit()

        print(f"📄 Documento insertado: {cleaned_title} (ID: {document_id})")
        return document_id

    def insert_sections_and_chunks(self, document_id, thesis_data):
        """
        Inserta secciones y chunks tokenizados

        Args:
            document_id (int): ID del documento
            thesis_data (dict): Datos del análisis de tesis
        """
        cursor = self.conn.cursor()
        content = thesis_data.get('content', {})
        sections = content.get('sections', [])

        for section in sections:
            # Insertar sección
            section_content = section.get('content', '')
            tokens_count = self.estimate_tokens(section_content)

            cursor.execute('''
                           INSERT INTO sections (document_id, section_title, section_category,
                                                 content, content_length, tokens_count, chunk_index)
                           VALUES (?, ?, ?, ?, ?, ?, ?)
                           ''', (
                               document_id,
                               section.get('title', 'Sin título'),
                               section.get('category', 'otros'),
                               section_content,
                               len(section_content),
                               tokens_count,
                               0  # chunk_index inicial
                           ))

            section_id = cursor.lastrowid

            # Tokenizar contenido en chunks
            chunks = self.tokenize_text(section_content)

            for chunk in chunks:
                # Metadatos del chunk para FAISS
                chunk_metadata = {
                    'document_id': document_id,
                    'section_id': section_id,
                    'section_title': section.get('title', ''),
                    'section_category': section.get('category', 'otros'),
                    'chunk_index': chunk['index'],
                    'document_title': thesis_data.get('metadata', {}).get('title', ''),
                    'authors': thesis_data.get('metadata', {}).get('authors', []),
                    'language': content.get('language', 'unknown')
                }

                cursor.execute('''
                               INSERT INTO text_chunks (document_id, section_id, chunk_text, chunk_size,
                                                        chunk_index, overlap_start, overlap_end, metadata_json)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                               ''', (
                                   document_id,
                                   section_id,
                                   chunk['text'],
                                   chunk['size'],
                                   chunk['index'],
                                   chunk['overlap_start'],
                                   chunk['overlap_end'],
                                   json.dumps(chunk_metadata, ensure_ascii=False)
                               ))

        self.conn.commit()
        print(f"📝 Insertadas {len(sections)} secciones con chunks tokenizados")

    def insert_references(self, document_id, thesis_data):
        """
        Inserta referencias bibliográficas

        Args:
            document_id (int): ID del documento
            thesis_data (dict): Datos del análisis de tesis
        """
        cursor = self.conn.cursor()
        references = thesis_data.get('references', [])

        for i, ref in enumerate(references):
            cursor.execute('''
                           INSERT INTO bibliographic_references (document_id, ref_title, ref_authors, ref_date,
                                                                 ref_index)
                           VALUES (?, ?, ?, ?, ?)
                           ''', (
                               document_id,
                               ref.get('title'),
                               json.dumps(ref.get('authors', []), ensure_ascii=False),
                               ref.get('date'),
                               i
                           ))

        self.conn.commit()
        print(f"📚 Insertadas {len(references)} referencias bibliográficas")

    def convert_json_to_sql(self, json_path="output/thesis_analysis.json"):
        """
        Convierte el archivo JSON de análisis a base de datos SQL

        Args:
            json_path (str): Ruta al archivo JSON de análisis
        """
        print("🔄 CONVIRTIENDO JSON A SQL PARA FAISS")
        print("=" * 45)

        if not os.path.exists(json_path):
            print(f"❌ No se encontró el archivo: {json_path}")
            return

        # Cargar datos JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            thesis_analyses = json.load(f)

        print(f"📊 Cargados {len(thesis_analyses)} análisis de tesis")

        successful_conversions = 0
        failed_conversions = 0

        for thesis_data in thesis_analyses:
            if thesis_data.get('status') != 'success':
                print(f"⚠️  Saltando archivo con errores: {thesis_data.get('file', 'unknown')}")
                failed_conversions += 1
                continue

            try:
                # Insertar documento principal
                document_id = self.insert_document(thesis_data)

                # Insertar secciones y chunks
                self.insert_sections_and_chunks(document_id, thesis_data)

                # Insertar referencias
                self.insert_references(document_id, thesis_data)

                successful_conversions += 1
                print(f"✅ Conversión exitosa para: {thesis_data.get('file', 'unknown')}")

            except Exception as e:
                print(f"❌ Error convirtiendo {thesis_data.get('file', 'unknown')}: {str(e)}")
                failed_conversions += 1

        print("\n" + "=" * 45)
        print("📊 RESUMEN DE CONVERSIÓN")
        print("=" * 45)
        print(f"✅ Conversiones exitosas: {successful_conversions}")
        print(f"❌ Conversiones fallidas: {failed_conversions}")
        print(f"💾 Base de datos: {self.db_path}")

        # Mostrar estadísticas de la base de datos
        self.show_database_stats()

    def show_database_stats(self):
        """Muestra estadísticas de la base de datos creada"""
        cursor = self.conn.cursor()

        # Contar documentos
        cursor.execute('SELECT COUNT(*) FROM documents')
        doc_count = cursor.fetchone()[0]

        # Contar secciones
        cursor.execute('SELECT COUNT(*) FROM sections')
        section_count = cursor.fetchone()[0]

        # Contar chunks
        cursor.execute('SELECT COUNT(*) FROM text_chunks')
        chunk_count = cursor.fetchone()[0]

        # Contar referencias
        cursor.execute('SELECT COUNT(*) FROM bibliographic_references')
        ref_count = cursor.fetchone()[0]

        # Estadísticas de chunks (importante para FAISS)
        cursor.execute('SELECT AVG(chunk_size), MIN(chunk_size), MAX(chunk_size) FROM text_chunks')
        avg_size, min_size, max_size = cursor.fetchone()

        print(f"\n📈 ESTADÍSTICAS DE LA BASE DE DATOS")
        print("=" * 35)
        print(f"📄 Documentos: {doc_count}")
        print(f"📝 Secciones: {section_count}")
        print(f"🧩 Chunks de texto: {chunk_count}")
        print(f"📚 Referencias bibliográficas: {ref_count}")
        print(f"\n🎯 ESTADÍSTICAS DE CHUNKS (FAISS)")
        print("=" * 35)
        print(f"📏 Tamaño promedio: {avg_size:.0f} caracteres")
        print(f"📐 Tamaño mínimo: {min_size} caracteres")
        print(f"📐 Tamaño máximo: {max_size} caracteres")

    def export_for_faiss(self, output_file="faiss_data.json"):
        """
        Exporta los datos en formato optimizado para FAISS

        Args:
            output_file (str): Archivo de salida para datos de FAISS
        """
        cursor = self.conn.cursor()

        # Consulta optimizada para FAISS
        cursor.execute('''
                       SELECT tc.id   as chunk_id,
                              tc.chunk_text,
                              tc.metadata_json,
                              d.title as document_title,
                              d.filename,
                              s.section_title,
                              s.section_category
                       FROM text_chunks tc
                                JOIN documents d ON tc.document_id = d.id
                                JOIN sections s ON tc.section_id = s.id
                       ORDER BY d.id, s.id, tc.chunk_index
                       ''')

        faiss_data = []
        for row in cursor.fetchall():
            chunk_id, chunk_text, metadata_json, doc_title, filename, section_title, category = row

            # Parsear metadatos
            metadata = json.loads(metadata_json) if metadata_json else {}

            faiss_entry = {
                'id': chunk_id,
                'text': chunk_text,
                'metadata': {
                    **metadata,
                    'document_title': doc_title,
                    'filename': filename,
                    'section_title': section_title,
                    'category': category
                }
            }
            faiss_data.append(faiss_entry)

        # Guardar datos para FAISS
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(faiss_data, f, ensure_ascii=False, indent=2)

        print(f"🚀 Datos exportados para FAISS: {output_file}")
        print(f"📊 Total de chunks para vectorización: {len(faiss_data)}")

        return faiss_data

    def get_chunks_by_category(self, category):
        """
        Obtiene chunks filtrados por categoría de sección

        Args:
            category (str): Categoría de sección (ej: 'metodologia', 'resultados')

        Returns:
            list: Lista de chunks de la categoría especificada
        """
        cursor = self.conn.cursor()

        cursor.execute('''
                       SELECT tc.chunk_text, tc.metadata_json
                       FROM text_chunks tc
                                JOIN sections s ON tc.section_id = s.id
                       WHERE s.section_category = ?
                       ORDER BY tc.document_id, tc.chunk_index
                       ''', (category,))

        chunks = []
        for chunk_text, metadata_json in cursor.fetchall():
            metadata = json.loads(metadata_json) if metadata_json else {}
            chunks.append({
                'text': chunk_text,
                'metadata': metadata
            })

        return chunks

    def close(self):
        """Cierra la conexión a la base de datos"""
        if self.conn:
            self.conn.close()
            print("🔒 Conexión a base de datos cerrada")


def main():
    """Función principal para ejecutar la conversión"""

    JSON_INPUT = "output/thesis_analysis.json"
    DB_OUTPUT = "thesis_database.db"
    FAISS_OUTPUT = "faiss_data.json"

    print("🔄 CONVERTIDOR JSON → SQL → FAISS")
    print("=" * 40)
    print(f"📥 Archivo JSON: {JSON_INPUT}")
    print(f"💾 Base de datos: {DB_OUTPUT}")
    print(f"🚀 Salida FAISS: {FAISS_OUTPUT}")
    print()

    # Crear convertidor
    converter = ThesisJSONToSQLConverter(db_path=DB_OUTPUT)

    try:
        # Convertir JSON a SQL
        converter.convert_json_to_sql(JSON_INPUT)

        # Exportar para FAISS
        faiss_data = converter.export_for_faiss(FAISS_OUTPUT)

        print("\n🎉 CONVERSIÓN COMPLETADA")
        print("=" * 25)
        print("✅ Los datos están listos para:")
        print("   🤖 Entrenamiento de embeddings")
        print("   🔍 Indexación en FAISS")
        print("   💬 Integración con chatbot")

        # Mostrar ejemplo de uso
        print(f"\n💡 SIGUIENTE PASO:")
        print(f"   Usa {FAISS_OUTPUT} para crear embeddings y entrenar FAISS")

    except Exception as e:
        print(f"❌ Error durante la conversión: {str(e)}")

    finally:
        converter.close()


if __name__ == "__main__":
    main()