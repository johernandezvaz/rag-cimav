import os
import glob
import requests
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET


class GrobidThesisProcessor:
    def __init__(self, grobid_server="http://localhost:8070"):
        """
        Inicializa el procesador de tesis con Grobid

        Args:
            grobid_server (str): URL del servidor Grobid (por defecto localhost:8070)
        """
        self.grobid_server = grobid_server
        self.base_url = f"{grobid_server}/api"

    def check_grobid_status(self):
        """Verifica si el servidor Grobid está funcionando"""
        try:
            response = requests.get(f"{self.grobid_server}/api/isalive")
            if response.status_code == 200:
                print("✅ Servidor Grobid está funcionando correctamente")
                return True
            else:
                print(f"❌ Servidor Grobid respondió con código: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("❌ No se puede conectar al servidor Grobid")
            print("💡 Asegúrate de que Grobid esté ejecutándose en:", self.grobid_server)
            print("\n🐳 SOLUCIÓN CON DOCKER:")
            print("   1. Ejecuta: docker pull lfoppiano/grobid:0.8.0")
            print("   2. Ejecuta: docker run --rm -it -p 8070:8070 lfoppiano/grobid:0.8.0")
            print("   3. O usa: docker-compose up -d (si tienes el archivo docker-compose.yml)")
            print("   4. Verifica en tu navegador: http://localhost:8070")
            return False

    def find_thesis_files(self, directory="Rag/tesis"):
        """
        Busca archivos PDF de tesis en el directorio especificado

        Args:
            directory (str): Directorio donde buscar las tesis

        Returns:
            list: Lista de rutas de archivos PDF encontrados
        """
        pattern = os.path.join(directory, "Tesis_*.pdf")
        thesis_files = glob.glob(pattern)

        if not thesis_files:
            print(f"⚠️  No se encontraron archivos con el patrón 'Tesis_*.pdf' en {directory}")
            # Buscar cualquier PDF como alternativa
            alternative_pattern = os.path.join(directory, "*.pdf")
            thesis_files = glob.glob(alternative_pattern)
            if thesis_files:
                print(f"📁 Se encontraron {len(thesis_files)} archivos PDF alternativos")
        else:
            print(f"📚 Se encontraron {len(thesis_files)} archivos de tesis")

        return thesis_files

    def validate_and_save_xml(self, xml_content, xml_path, filename):
        """
        Valida y guarda el contenido XML

        Args:
            xml_content (str): Contenido XML a validar
            xml_path (str): Ruta donde guardar el archivo
            filename (str): Nombre del archivo para logging

        Returns:
            bool: True si se guardó exitosamente, False si hubo error
        """
        try:
            # Verificar que el contenido no esté vacío
            if not xml_content or not xml_content.strip():
                print(f"❌ Contenido XML vacío para {filename}")
                return False

            # Limpiar contenido problemático
            xml_content = xml_content.strip()

            # Verificar que comience con declaración XML o elemento XML
            if not (xml_content.startswith('<?xml') or xml_content.startswith('<')):
                print(f"❌ El contenido no parece ser XML válido para {filename}")
                print(f"Primeros 100 caracteres: {xml_content[:100]}")
                return False

            # Intentar parsear el XML para validar
            try:
                ET.fromstring(xml_content)
                print(f"XML válido para {filename}")
            except ET.ParseError as e:
                print(f"❌ XML malformado para {filename}: {str(e)}")
                print(f"Primeros 200 caracteres: {xml_content[:200]}")
                return False

            # Guardar el archivo
            with open(xml_path, 'w', encoding='utf-8') as xml_file:
                xml_file.write(xml_content)

            print(f"Archivo guardado exitosamente: {xml_path}")
            return True

        except Exception as e:
            print(f"❌ Error guardando XML para {filename}: {str(e)}")
            return False

    def process_pdf_with_grobid(self, pdf_path, output_dir="output"):
        """
        Procesa un PDF individual con Grobid

        Args:
            pdf_path (str): Ruta al archivo PDF
            output_dir (str): Directorio de salida para los XML

        Returns:
            dict: Resultado del procesamiento
        """
        filename = os.path.basename(pdf_path)
        print(f"🔄 Procesando: {filename}")

        # Crear directorio de salida si no existe
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        try:
            # Procesar documento completo (fulltext)
            with open(pdf_path, 'rb') as pdf_file:
                files = {'input': (filename, pdf_file, 'application/pdf')}

                print(f"Enviando solicitud a Grobid para {filename}")

                # Llamada a la API de Grobid para procesamiento completo
                response = requests.post(
                    f"{self.base_url}/processFulltextDocument",
                    files=files,
                    timeout=300  # 5 minutos de timeout
                )

                print(f"Respuesta de Grobid: {response.status_code}")
                print(f"Tamaño de respuesta: {len(response.text)} caracteres")

                if response.status_code == 200:
                    xml_filename = filename.replace('.pdf', '_fulltext.xml')
                    xml_path = os.path.join(output_dir, xml_filename)

                    if self.validate_and_save_xml(response.text, xml_path, filename):
                        print(f"✅ Procesado exitosamente: {xml_filename}")

                        # También procesar solo el header (metadatos)
                        self.process_header_only(pdf_path, output_dir)

                        return {
                            'status': 'success',
                            'pdf_file': filename,
                            'xml_file': xml_filename,
                            'xml_path': xml_path,
                            'xml_size': len(response.text)
                        }
                    else:
                        return {
                            'status': 'error',
                            'pdf_file': filename,
                            'error': 'XML inválido o vacío',
                            'message': 'El contenido devuelto por Grobid no es XML válido'
                        }
                else:
                    print(f"❌ Error procesando {filename}: HTTP {response.status_code}")
                    print(f"Contenido de error: {response.text[:200]}")
                    return {
                        'status': 'error',
                        'pdf_file': filename,
                        'error': f"HTTP {response.status_code}",
                        'message': response.text[:200] if response.text else "Sin mensaje"
                    }

        except requests.exceptions.Timeout:
            print(f"⏰ Timeout procesando {filename}")
            return {
                'status': 'timeout',
                'pdf_file': filename,
                'error': 'Timeout después de 5 minutos'
            }
        except Exception as e:
            print(f"❌ Error inesperado procesando {filename}: {str(e)}")
            return {
                'status': 'error',
                'pdf_file': filename,
                'error': str(e)
            }

    def process_header_only(self, pdf_path, output_dir):
        """
        Procesa solo los metadatos/header del PDF

        Args:
            pdf_path (str): Ruta al archivo PDF
            output_dir (str): Directorio de salida
        """
        filename = os.path.basename(pdf_path)

        try:
            with open(pdf_path, 'rb') as pdf_file:
                files = {'input': (filename, pdf_file, 'application/pdf')}

                response = requests.post(
                    f"{self.base_url}/processHeaderDocument",
                    files=files,
                    timeout=60
                )

                if response.status_code == 200:
                    xml_filename = filename.replace('.pdf', '_header.xml')
                    xml_path = os.path.join(output_dir, xml_filename)

                    if self.validate_and_save_xml(response.text, xml_path, f"{filename} (header)"):
                        print(f"📋 Metadatos extraídos: {xml_filename}")
                    else:
                        print(f"⚠️  Error validando metadatos XML de {filename}")

        except Exception as e:
            print(f"⚠️  Error extrayendo metadatos de {filename}: {str(e)}")

    def process_all_thesis(self, directory="RAG/tesis", output_dir="output"):
        """
        Procesa todas las tesis encontradas en el directorio

        Args:
            directory (str): Directorio de las tesis
            output_dir (str): Directorio de salida

        Returns:
            dict: Resumen del procesamiento
        """
        print("🚀 Iniciando procesamiento de tesis con Grobid")
        print("=" * 50)

        # Verificar estado de Grobid
        if not self.check_grobid_status():
            return {'error': 'Servidor Grobid no disponible'}

        # Buscar archivos de tesis
        thesis_files = self.find_thesis_files(directory)

        if not thesis_files:
            return {'error': 'No se encontraron archivos PDF para procesar'}

        # Procesar cada archivo
        results = []
        successful = 0
        failed = 0

        for i, pdf_path in enumerate(thesis_files, 1):
            print(f"\n📖 Procesando archivo {i}/{len(thesis_files)}")
            result = self.process_pdf_with_grobid(pdf_path, output_dir)
            results.append(result)

            if result['status'] == 'success':
                successful += 1
            else:
                failed += 1

            # Pequeña pausa entre procesamiento para no sobrecargar el servidor
            time.sleep(1)

        # Resumen final
        print("\n" + "=" * 50)
        print("📊 RESUMEN DEL PROCESAMIENTO")
        print("=" * 50)
        print(f"✅ Archivos procesados exitosamente: {successful}")
        print(f"❌ Archivos con errores: {failed}")
        print(f"📁 Archivos XML generados en: {output_dir}")

        return {
            'total_files': len(thesis_files),
            'successful': successful,
            'failed': failed,
            'results': results,
            'output_directory': output_dir
        }


def main():
    """Función principal para ejecutar el procesamiento"""

    # Configuración
    GROBID_SERVER = "http://localhost:8070"  # Cambiar si Grobid está en otro servidor
    THESIS_DIRECTORY = "Rag/tesis"
    OUTPUT_DIRECTORY = "output/grobid_xml"

    print("🎓 PROCESADOR DE TESIS CON GROBID")
    print("=" * 40)
    print(f"📂 Directorio de tesis: {THESIS_DIRECTORY}")
    print(f"📁 Directorio de salida: {OUTPUT_DIRECTORY}")
    print(f"🌐 Servidor Grobid: {GROBID_SERVER}")
    print("🐳 Asegúrate de que Grobid esté corriendo con Docker")
    print()

    # Crear procesador
    processor = GrobidThesisProcessor(grobid_server=GROBID_SERVER)

    # Procesar todas las tesis
    summary = processor.process_all_thesis(
        directory=THESIS_DIRECTORY,
        output_dir=OUTPUT_DIRECTORY
    )

    # Mostrar resumen final
    if 'error' not in summary:
        print(f"\n🎉 Procesamiento completado!")
        print(f"📊 Total: {summary['total_files']} archivos")
        print(f"✅ Exitosos: {summary['successful']}")
        print(f"❌ Fallidos: {summary['failed']}")

        # Mostrar detalles de errores si los hay
        if summary['failed'] > 0:
            print("\n❌ ARCHIVOS CON ERRORES:")
            for result in summary['results']:
                if result['status'] != 'success':
                    print(f"  - {result['pdf_file']}: {result.get('error', 'Error desconocido')}")
    else:
        print(f"\n❌ Error: {summary['error']}")


if __name__ == "__main__":
    main()
