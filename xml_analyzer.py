import os
import xml.etree.ElementTree as ET
from pathlib import Path
import json
import re
from difflib import SequenceMatcher


class GrobidXMLAnalyzer:
    """Analizador para los archivos XML generados por Grobid"""

    def __init__(self):
        self.namespaces = {
            'tei': 'http://www.tei-c.org/ns/1.0'
        }

        self.section_mappings = {
            'resumen': ['resumen', 'summary', 'abstract', 'síntesis'],
            'abstract': ['abstract', 'resumen', 'summary'],
            'introduccion': ['introducción', 'introduction', 'intro', 'presentación'],
            'antecedentes': ['antecedentes', 'background', 'marco histórico', 'contexto histórico'],
            'estado_del_arte': ['estado del arte', 'state of the art', 'revisión bibliográfica', 'literature review',
                                'marco teórico'],
            'objetivos': ['objetivos', 'objectives', 'goals', 'propósitos'],
            'justificacion': ['justificación', 'justification', 'motivación', 'motivation'],
            'objetivo_general': ['objetivo general', 'general objective', 'main objective', 'propósito general'],
            'hipotesis': ['hipótesis', 'hypothesis', 'supuestos', 'assumptions'],
            'metodologia': ['metodología', 'methodology', 'métodos', 'methods', 'diseño metodológico'],
            'resultados': ['resultados', 'results', 'findings', 'hallazgos'],
            'conclusiones': ['conclusiones', 'conclusions', 'conclusión', 'conclusion', 'cierre']
        }

    def analyze_xml_file(self, xml_path):
        """
        Analiza un archivo XML de Grobid y extrae información estructurada

        Args:
            xml_path (str): Ruta al archivo XML

        Returns:
            dict: Información extraída del XML
        """
        try:
            print(f"Intentando leer archivo: {xml_path}")

            # Verificar que el archivo existe y no está vacío
            if not os.path.exists(xml_path):
                raise FileNotFoundError(f"El archivo {xml_path} no existe")

            file_size = os.path.getsize(xml_path)
            if file_size == 0:
                raise ValueError(f"El archivo {xml_path} está vacío")

            print(f"Tamaño del archivo: {file_size} bytes")

            # Leer el contenido del archivo para debugging
            with open(xml_path, 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"Primeros 200 caracteres: {repr(content[:200])}")

                # Verificar si el contenido parece ser XML válido
                if not content.strip():
                    raise ValueError("El archivo está vacío o solo contiene espacios en blanco")

                if not content.strip().startswith('<?xml') and not content.strip().startswith('<'):
                    raise ValueError("El archivo no parece ser XML válido - no comienza con declaración XML o elemento")

            # Intentar parsear el XML
            try:
                tree = ET.parse(xml_path)
                root = tree.getroot()
                print(f"XML parseado exitosamente. Root element: {root.tag}")
            except ET.ParseError as pe:
                print(f"Error de parsing XML: {pe}")
                # Intentar con diferentes encodings
                for encoding in ['utf-8', 'latin-1', 'cp1252']:
                    try:
                        print(f"Intentando con encoding: {encoding}")
                        with open(xml_path, 'r', encoding=encoding) as f:
                            content = f.read()

                        # Limpiar posibles caracteres problemáticos
                        content = content.replace('\x00', '')  # Remover null bytes
                        content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '',
                                         content)  # Remover caracteres de control

                        root = ET.fromstring(content)
                        print(f"XML parseado exitosamente con encoding {encoding}")
                        break
                    except Exception as e:
                        print(f"Falló con encoding {encoding}: {e}")
                        continue
                else:
                    raise pe  # Si ningún encoding funcionó, lanzar el error original

            # Extraer metadatos básicos
            metadata = self.extract_metadata(root)

            # Extraer contenido del documento
            content = self.extract_content(root)

            # Extraer referencias bibliográficas
            references = self.extract_references(root)

            return {
                'file': os.path.basename(xml_path),
                'metadata': metadata,
                'content': content,
                'references': references,
                'status': 'success'
            }

        except Exception as e:
            print(f"Error procesando {xml_path}: {str(e)}")
            return {
                'file': os.path.basename(xml_path),
                'error': str(e),
                'status': 'error'
            }

    def extract_metadata(self, root):
        """Extrae metadatos del documento"""
        metadata = {}

        # Título - buscar en múltiples ubicaciones
        title = self.extract_real_title(root)
        metadata['title'] = title

        # Autores
        authors = []
        author_elems = root.findall('.//tei:sourceDesc//tei:author', self.namespaces)
        for author in author_elems:
            name_parts = []
            forename = author.find('.//tei:forename', self.namespaces)
            surname = author.find('.//tei:surname', self.namespaces)

            if forename is not None:
                name_parts.append(forename.text)
            if surname is not None:
                name_parts.append(surname.text)

            if name_parts:
                authors.append(' '.join(name_parts))

        metadata['authors'] = authors

        # Fecha
        date_elem = root.find('.//tei:publicationStmt/tei:date', self.namespaces)
        metadata['date'] = date_elem.get('when') if date_elem is not None else None

        # Abstract
        abstract_elem = root.find('.//tei:abstract', self.namespaces)
        if abstract_elem is not None:
            abstract_text = ' '.join([p.text for p in abstract_elem.findall('.//tei:p', self.namespaces) if p.text])
            metadata['abstract'] = abstract_text
        else:
            metadata['abstract'] = None

        return metadata

    def clean_and_validate_title(self, title):
        """
        Limpia y valida títulos, detectando títulos institucionales incorrectos

        Args:
            title (str): Título a validar

        Returns:
            str: Título limpio o None si no es válido
        """
        if not title or not title.strip():
            return None

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
                return None

        # Verificar longitud mínima y máxima razonable
        if len(title) < 15:  # Títulos muy cortos probablemente no son títulos reales
            return None

        if len(title) > 500:  # Títulos muy largos probablemente son errores
            return None

        # Verificar que no sea solo mayúsculas (común en headers institucionales)
        if title.isupper() and len(title) > 50:
            return None

        # Limpiar caracteres extraños y espacios múltiples
        title = re.sub(r'\s+', ' ', title)
        title = re.sub(r'[^\w\s\-\.\,\:\;\(\)\[\]áéíóúñüÁÉÍÓÚÑÜ]', '', title)

        return title.strip()

    def extract_real_title(self, root):
        """
        Extrae el título real del documento, buscando en múltiples ubicaciones

        Args:
            root: Elemento raíz del XML

        Returns:
            str: Título extraído o "Sin título válido"
        """
        # 1. Buscar en titleStmt/title (ubicación estándar)
        title_elem = root.find('.//tei:titleStmt/tei:title', self.namespaces)
        if title_elem is not None and title_elem.text:
            cleaned_title = self.clean_and_validate_title(title_elem.text)
            if cleaned_title:
                return cleaned_title

        # 2. Buscar en sourceDesc (metadatos del documento fuente)
        source_title = root.find('.//tei:sourceDesc//tei:title', self.namespaces)
        if source_title is not None and source_title.text:
            cleaned_title = self.clean_and_validate_title(source_title.text)
            if cleaned_title:
                return cleaned_title

        # 3. Buscar en el primer div/head del body (primer encabezado del contenido)
        first_head = root.find('.//tei:body//tei:div/tei:head', self.namespaces)
        if first_head is not None and first_head.text:
            cleaned_title = self.clean_and_validate_title(first_head.text)
            if cleaned_title:
                return cleaned_title

        # 4. Buscar en los primeros párrafos del documento
        first_paragraphs = root.findall('.//tei:body//tei:p', self.namespaces)[:5]
        for p in first_paragraphs:
            if p.text and len(p.text.strip()) > 20:
                # Buscar líneas que podrían ser títulos
                lines = p.text.strip().split('\n')
                for line in lines[:3]:  # Solo las primeras 3 líneas
                    line = line.strip()
                    if len(line) > 20 and len(line) < 300:
                        cleaned_title = self.clean_and_validate_title(line)
                        if cleaned_title:
                            return cleaned_title

        # 5. Buscar en abstract si existe (a veces el título está ahí)
        abstract_elem = root.find('.//tei:abstract', self.namespaces)
        if abstract_elem is not None:
            # Buscar en el primer párrafo del abstract
            first_p = abstract_elem.find('.//tei:p', self.namespaces)
            if first_p is not None and first_p.text:
                lines = first_p.text.strip().split('\n')
                for line in lines[:2]:  # Solo las primeras 2 líneas
                    line = line.strip()
                    if len(line) > 30 and len(line) < 300:
                        cleaned_title = self.clean_and_validate_title(line)
                        if cleaned_title:
                            return cleaned_title

        return "Sin título válido"

    def detect_language(self, text):
        """Detecta si el texto está principalmente en español o inglés"""
        spanish_indicators = ['de', 'la', 'el', 'en', 'que', 'con', 'por', 'para', 'del', 'los', 'las', 'una', 'uno']
        english_indicators = ['the', 'of', 'and', 'to', 'in', 'for', 'with', 'on', 'at', 'by', 'from', 'this', 'that']

        words = text.lower().split()[:100]  # Analizar las primeras 100 palabras

        spanish_count = sum(1 for word in words if word in spanish_indicators)
        english_count = sum(1 for word in words if word in english_indicators)

        return 'spanish' if spanish_count > english_count else 'english'

    def similarity(self, a, b):
        """Calcula la similitud entre dos strings"""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def categorize_section(self, section_title, content=""):
        """Categoriza una sección basada en su título y contenido"""
        section_title_clean = re.sub(r'[^\w\s]', '', section_title.lower())

        best_match = None
        best_score = 0

        for category, keywords in self.section_mappings.items():
            for keyword in keywords:
                # Buscar coincidencias en el título
                if keyword in section_title_clean:
                    score = self.similarity(section_title_clean, keyword)
                    if score > best_score:
                        best_score = score
                        best_match = category

                # También buscar en las primeras líneas del contenido
                content_start = content[:200].lower() if content else ""
                if keyword in content_start:
                    score = 0.7  # Puntuación menor para coincidencias en contenido
                    if score > best_score:
                        best_score = score
                        best_match = category

        return best_match if best_score > 0.6 else 'otros'

    def extract_content(self, root):
        """Extrae el contenido principal del documento"""
        content = {
            'sections': [],
            'categorized_sections': {},
            'full_text': '',
            'language': 'unknown'
        }

        # Extraer secciones
        sections = root.findall('.//tei:body//tei:div', self.namespaces)
        all_text_for_language = ""

        for section in sections:
            section_data = {}

            # Título de la sección
            head = section.find('.//tei:head', self.namespaces)
            section_title = head.text if head is not None else "Sin título"
            section_data['title'] = section_title

            # Contenido de la sección
            paragraphs = section.findall('.//tei:p', self.namespaces)
            section_text = []
            for p in paragraphs:
                if p.text:
                    section_text.append(p.text.strip())

            section_content = ' '.join(section_text)
            section_data['content'] = section_content

            category = self.categorize_section(section_title, section_content)
            section_data['category'] = category

            # Agregar a categorías
            if category not in content['categorized_sections']:
                content['categorized_sections'][category] = []

            content['categorized_sections'][category].append({
                'title': section_title,
                'content': section_content
            })

            content['sections'].append(section_data)
            all_text_for_language += section_content + " "

        content['language'] = self.detect_language(all_text_for_language)

        # Texto completo
        all_paragraphs = root.findall('.//tei:body//tei:p', self.namespaces)
        full_text_parts = []
        for p in all_paragraphs:
            if p.text and p.text.strip():
                full_text_parts.append(p.text.strip())

        content['full_text'] = ' '.join(full_text_parts)

        return content

    def extract_references(self, root):
        """Extrae las referencias bibliográficas"""
        references = []

        ref_elems = root.findall('.//tei:listBibl/tei:biblStruct', self.namespaces)
        for ref in ref_elems:
            ref_data = {}

            # Título
            title = ref.find('.//tei:title', self.namespaces)
            ref_data['title'] = title.text if title is not None else None

            # Autores
            authors = []
            author_elems = ref.findall('.//tei:author', self.namespaces)
            for author in author_elems:
                name_parts = []
                forename = author.find('.//tei:forename', self.namespaces)
                surname = author.find('.//tei:surname', self.namespaces)

                if forename is not None:
                    name_parts.append(forename.text)
                if surname is not None:
                    name_parts.append(surname.text)

                if name_parts:
                    authors.append(' '.join(name_parts))

            ref_data['authors'] = authors

            # Fecha
            date = ref.find('.//tei:date', self.namespaces)
            ref_data['date'] = date.get('when') if date is not None else None

            references.append(ref_data)

        return references

    def generate_structured_xml(self, analysis_data, output_path):
        """
        Genera un XML estructurado con las categorías personalizadas de tesis

        Args:
            analysis_data (dict): Datos del análisis
            output_path (str): Ruta donde guardar el XML estructurado
        """
        root = ET.Element("tesis")

        # Metadatos
        metadata_elem = ET.SubElement(root, "metadatos")
        ET.SubElement(metadata_elem, "titulo").text = analysis_data['metadata']['title']
        ET.SubElement(metadata_elem, "idioma").text = analysis_data['content']['language']

        autores_elem = ET.SubElement(metadata_elem, "autores")
        for author in analysis_data['metadata']['authors']:
            ET.SubElement(autores_elem, "autor").text = author

        if analysis_data['metadata']['date']:
            ET.SubElement(metadata_elem, "fecha").text = analysis_data['metadata']['date']

        # Contenido categorizado
        contenido_elem = ET.SubElement(root, "contenido")

        # Orden preferido de secciones
        section_order = [
            'resumen', 'abstract', 'introduccion', 'antecedentes', 'estado_del_arte',
            'objetivos', 'objetivo_general', 'justificacion', 'hipotesis',
            'metodologia', 'resultados', 'conclusiones', 'otros'
        ]

        categorized = analysis_data['content']['categorized_sections']

        for category in section_order:
            if category in categorized and categorized[category]:
                category_elem = ET.SubElement(contenido_elem, category)

                for section in categorized[category]:
                    seccion_elem = ET.SubElement(category_elem, "seccion")
                    ET.SubElement(seccion_elem, "titulo").text = section['title']
                    ET.SubElement(seccion_elem, "texto").text = section['content']

        # Referencias
        if analysis_data['references']:
            referencias_elem = ET.SubElement(root, "referencias")
            for ref in analysis_data['references']:
                ref_elem = ET.SubElement(referencias_elem, "referencia")
                if ref['title']:
                    ET.SubElement(ref_elem, "titulo").text = ref['title']
                if ref['authors']:
                    autores_ref = ET.SubElement(ref_elem, "autores")
                    for author in ref['authors']:
                        ET.SubElement(autores_ref, "autor").text = author
                if ref['date']:
                    ET.SubElement(ref_elem, "fecha").text = ref['date']

        # Guardar XML
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ", level=0)
        tree.write(output_path, encoding='utf-8', xml_declaration=True)

    def analyze_directory(self, xml_directory, output_file=None, generate_structured=True):
        """
        Analiza todos los archivos XML en un directorio

        Args:
            xml_directory (str): Directorio con archivos XML
            output_file (str): Archivo opcional para guardar resultados en JSON
            generate_structured (bool): Si generar XMLs estructurados personalizados
        """
        print(f"🔍 Analizando archivos XML en: {xml_directory}")

        if not os.path.exists(xml_directory):
            print(f"❌ El directorio {xml_directory} no existe")
            return []

        xml_files = list(Path(xml_directory).glob("*.xml"))

        if not xml_files:
            print("❌ No se encontraron archivos XML")
            print(f"📁 Archivos en el directorio:")
            for file in Path(xml_directory).iterdir():
                print(f"  - {file.name}")
            return []

        print(f"📄 Encontrados {len(xml_files)} archivos XML")

        results = []
        structured_dir = Path(xml_directory).parent / "structured_xml"

        if generate_structured:
            structured_dir.mkdir(exist_ok=True)

        for xml_file in xml_files:
            print(f"📄 Analizando: {xml_file.name}")
            analysis = self.analyze_xml_file(str(xml_file))
            results.append(analysis)

            if analysis['status'] == 'success':
                print(f"  ✅ Título: {analysis['metadata']['title']}")
                print(f"  🌐 Idioma: {analysis['content']['language']}")
                print(f"  👥 Autores: {', '.join(analysis['metadata']['authors'])}")
                print(f"  📝 Secciones: {len(analysis['content']['sections'])}")
                print(f"  🏷️  Categorías encontradas: {', '.join(analysis['content']['categorized_sections'].keys())}")
                print(f"  📚 Referencias: {len(analysis['references'])}")

                if generate_structured:
                    structured_path = structured_dir / f"{xml_file.stem}_structured.xml"
                    self.generate_structured_xml(analysis, str(structured_path))
                    print(f"  📋 XML estructurado: {structured_path.name}")
            else:
                print(f"  ❌ Error: {analysis['error']}")
            print()

        # Guardar resultados si se especifica archivo de salida
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"💾 Resultados guardados en: {output_file}")

        return results


def main():
    """Función principal para analizar XMLs de Grobid"""

    XML_DIRECTORY = "output/grobid_xml"
    OUTPUT_JSON = "output/thesis_analysis.json"

    print("🔬 ANALIZADOR DE XML DE GROBID")
    print("=" * 40)

    analyzer = GrobidXMLAnalyzer()
    results = analyzer.analyze_directory(XML_DIRECTORY, OUTPUT_JSON)

    if results:
        successful = sum(1 for r in results if r['status'] == 'success')
        failed = len(results) - successful

        print("📊 RESUMEN DEL ANÁLISIS")
        print("=" * 30)
        print(f"✅ Archivos analizados exitosamente: {successful}")
        print(f"❌ Archivos con errores: {failed}")
        print(f"📁 Total de archivos: {len(results)}")


if __name__ == "__main__":
    main()
