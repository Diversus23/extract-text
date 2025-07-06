"""
Unit тесты для модуля извлечения текста
"""
import pytest
import asyncio
from unittest.mock import patch, Mock, AsyncMock, mock_open
from pathlib import Path
import tempfile
import os

from app.extractors import TextExtractor
from app.config import settings


@pytest.mark.unit
class TestTextExtractor:
    """Тесты для класса TextExtractor"""
    
    def test_init(self):
        """Тест инициализации TextExtractor"""
        extractor = TextExtractor()
        assert extractor.executor is not None
        assert extractor.executor._max_workers == 4
    
    def test_get_file_type_from_extension(self, text_extractor):
        """Тест определения типа файла по расширению"""
        assert text_extractor._get_file_type_from_extension("test.txt") == "txt"
        assert text_extractor._get_file_type_from_extension("document.pdf") == "pdf"
        assert text_extractor._get_file_type_from_extension("image.jpg") == "jpg"
        assert text_extractor._get_file_type_from_extension("script.py") == "py"
        assert text_extractor._get_file_type_from_extension("data.json") == "json"
        assert text_extractor._get_file_type_from_extension("archive.tar.gz") == "tar.gz"
        assert text_extractor._get_file_type_from_extension("unknown.xyz") == "xyz"
    
    def test_is_supported_format(self, text_extractor):
        """Тест проверки поддерживаемых форматов"""
        assert text_extractor._is_supported_format("txt") == True
        assert text_extractor._is_supported_format("pdf") == True
        assert text_extractor._is_supported_format("docx") == True
        assert text_extractor._is_supported_format("jpg") == True
        assert text_extractor._is_supported_format("zip") == True
        assert text_extractor._is_supported_format("py") == True
        assert text_extractor._is_supported_format("json") == True
        assert text_extractor._is_supported_format("xyz") == False
    
    @pytest.mark.asyncio
    async def test_extract_text_simple_txt(self, text_extractor):
        """Тест извлечения текста из простого текстового файла"""
        test_content = "Тестовый текст для проверки"
        content_bytes = test_content.encode('utf-8')
        
        result = await text_extractor.extract_text(content_bytes, "test.txt")
        
        assert len(result) == 1
        assert result[0]["filename"] == "test.txt"
        assert result[0]["type"] == "txt"
        assert result[0]["text"] == test_content
        assert result[0]["size"] == len(content_bytes)
    
    @pytest.mark.asyncio
    async def test_extract_text_unsupported_format(self, text_extractor):
        """Тест извлечения текста из неподдерживаемого формата"""
        content_bytes = b"some content"
        
        with pytest.raises(ValueError, match="Unsupported file format"):
            await text_extractor.extract_text(content_bytes, "test.xyz")
    
    def test_extract_from_text_sync(self, text_extractor):
        """Тест синхронного извлечения из текстового файла"""
        test_content = "Простой текст\nВторая строка"
        content_bytes = test_content.encode('utf-8')
        
        result = text_extractor._extract_from_text_sync(content_bytes, "test.txt")
        
        assert result == test_content
    
    def test_extract_from_text_sync_encoding_fallback(self, text_extractor):
        """Тест извлечения текста с разными кодировками"""
        # Текст в CP1251
        test_content = "Тестовый текст"
        content_bytes = test_content.encode('cp1251')
        
        result = text_extractor._extract_from_text_sync(content_bytes, "test.txt")
        
        assert result == test_content
    
    def test_extract_from_json_sync(self, text_extractor):
        """Тест синхронного извлечения из JSON файла"""
        json_content = '{"name": "Тест", "value": 42, "nested": {"key": "значение"}}'
        content_bytes = json_content.encode('utf-8')
        
        result = text_extractor._extract_from_json_sync(content_bytes, "test.json")
        
        assert "name: Тест" in result
        assert "value: 42" in result
        assert "nested.key: значение" in result
    
    def test_extract_from_json_sync_invalid(self, text_extractor):
        """Тест извлечения из некорректного JSON"""
        invalid_json = '{"name": "Тест", "value": 42,}'  # Лишняя запятая
        content_bytes = invalid_json.encode('utf-8')
        
        with pytest.raises(ValueError, match="Invalid JSON"):
            text_extractor._extract_from_json_sync(content_bytes, "test.json")
    
    def test_extract_from_csv_sync(self, text_extractor):
        """Тест синхронного извлечения из CSV файла"""
        csv_content = "Название,Цена,Количество\nТовар 1,100,5\nТовар 2,200,3"
        content_bytes = csv_content.encode('utf-8')
        
        result = text_extractor._extract_from_csv_sync(content_bytes, "test.csv")
        
        assert "Название,Цена,Количество" in result
        assert "Товар 1,100,5" in result
        assert "Товар 2,200,3" in result
    
    def test_extract_from_xml_sync(self, text_extractor):
        """Тест синхронного извлечения из XML файла"""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <root>
            <item id="1">
                <name>Товар 1</name>
                <price>100</price>
            </item>
        </root>"""
        content_bytes = xml_content.encode('utf-8')
        
        result = text_extractor._extract_from_xml_sync(content_bytes, "test.xml")
        
        assert "Товар 1" in result
        assert "100" in result
    
    def test_extract_from_xml_sync_invalid(self, text_extractor):
        """Тест извлечения из некорректного XML"""
        invalid_xml = "<root><item>Товар 1</root>"  # Неправильно закрытый тег
        content_bytes = invalid_xml.encode('utf-8')
        
        with pytest.raises(ValueError, match="Invalid XML"):
            text_extractor._extract_from_xml_sync(content_bytes, "test.xml")
    
    def test_extract_from_yaml_sync(self, text_extractor):
        """Тест синхронного извлечения из YAML файла"""
        yaml_content = """name: Тестовый проект
version: 1.0.0
config:
  debug: true
  items:
    - item1
    - item2
"""
        content_bytes = yaml_content.encode('utf-8')
        
        result = text_extractor._extract_from_yaml_sync(content_bytes, "test.yaml")
        
        assert "name: Тестовый проект" in result
        assert "version: 1.0.0" in result
        assert "config.debug: true" in result
        assert "config.items[0]: item1" in result
    
    def test_extract_from_yaml_sync_invalid(self, text_extractor):
        """Тест извлечения из некорректного YAML"""
        invalid_yaml = "key: value\n  invalid: indentation"
        content_bytes = invalid_yaml.encode('utf-8')
        
        with pytest.raises(ValueError, match="Invalid YAML"):
            text_extractor._extract_from_yaml_sync(content_bytes, "test.yaml")
    
    def test_extract_from_html_sync(self, text_extractor):
        """Тест синхронного извлечения из HTML файла"""
        html_content = """<html>
        <head><title>Тестовая страница</title></head>
        <body>
            <h1>Заголовок</h1>
            <p>Тестовый параграф с <strong>жирным</strong> текстом.</p>
        </body>
        </html>"""
        content_bytes = html_content.encode('utf-8')
        
        result = text_extractor._extract_from_html_sync(content_bytes, "test.html")
        
        assert "Тестовая страница" in result
        assert "Заголовок" in result
        assert "Тестовый параграф с жирным текстом." in result
    
    def test_extract_from_source_code_sync(self, text_extractor):
        """Тест синхронного извлечения из файла исходного кода"""
        python_content = """#!/usr/bin/env python3
# Тестовый Python файл

def hello_world():
    \"\"\"Приветствие мира\"\"\"
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()
"""
        content_bytes = python_content.encode('utf-8')
        
        result = text_extractor._extract_from_source_code_sync(content_bytes, "test.py")
        
        assert "Язык программирования: Python" in result
        assert "Файл: test.py" in result
        assert "Количество строк: 9" in result
        assert "def hello_world():" in result
        assert "print(\"Hello, World!\")" in result
    
    def test_extract_from_source_code_sync_unknown_language(self, text_extractor):
        """Тест извлечения исходного кода неизвестного языка"""
        code_content = "some unknown code"
        content_bytes = code_content.encode('utf-8')
        
        result = text_extractor._extract_from_source_code_sync(content_bytes, "test.unknown")
        
        assert "Язык программирования: Unknown" in result
        assert "Файл: test.unknown" in result
        assert "some unknown code" in result
    
    @patch('app.extractors.PyPDF2.PdfReader')
    def test_extract_from_pdf_sync(self, mock_pdf_reader, text_extractor):
        """Тест синхронного извлечения из PDF файла"""
        # Мокаем PyPDF2
        mock_reader = Mock()
        mock_page = Mock()
        mock_page.extract_text.return_value = "Текст из PDF"
        mock_reader.pages = [mock_page]
        mock_pdf_reader.return_value = mock_reader
        
        content_bytes = b"fake pdf content"
        
        result = text_extractor._extract_from_pdf_sync(content_bytes, "test.pdf")
        
        assert "Текст из PDF" in result
        mock_pdf_reader.assert_called_once()
    
    @patch('app.extractors.PyPDF2.PdfReader')
    def test_extract_from_pdf_sync_with_images(self, mock_pdf_reader, text_extractor):
        """Тест извлечения из PDF с изображениями"""
        # Мокаем PyPDF2
        mock_reader = Mock()
        mock_page = Mock()
        mock_page.extract_text.return_value = "Текст со страницы"
        mock_page.images = {"img1": b"fake image data"}
        mock_reader.pages = [mock_page]
        mock_pdf_reader.return_value = mock_reader
        
        with patch.object(text_extractor, '_extract_from_image_sync') as mock_ocr:
            mock_ocr.return_value = "Текст с изображения"
            
            content_bytes = b"fake pdf content"
            result = text_extractor._extract_from_pdf_sync(content_bytes, "test.pdf")
            
            assert "Текст со страницы" in result
            assert "--- OCR ---" in result
            assert "Текст с изображения" in result
    
    @patch('app.extractors.pytesseract.image_to_string')
    @patch('app.extractors.Image.open')
    def test_extract_from_image_sync(self, mock_image_open, mock_tesseract, text_extractor):
        """Тест синхронного извлечения из изображения с OCR"""
        mock_tesseract.return_value = "Распознанный текст"
        mock_image = Mock()
        mock_image_open.return_value = mock_image
        
        content_bytes = b"fake image data"
        
        result = text_extractor._extract_from_image_sync(content_bytes, "test.jpg")
        
        assert result == "Распознанный текст"
        mock_tesseract.assert_called_once_with(mock_image, lang=settings.OCR_LANGUAGES)
    
    @patch('app.extractors.pytesseract.image_to_string')
    @patch('app.extractors.Image.open')
    def test_extract_from_image_sync_no_text(self, mock_image_open, mock_tesseract, text_extractor):
        """Тест извлечения из изображения без текста"""
        mock_tesseract.return_value = ""
        mock_image = Mock()
        mock_image_open.return_value = mock_image
        
        content_bytes = b"fake image data"
        
        result = text_extractor._extract_from_image_sync(content_bytes, "test.jpg")
        
        assert result == ""
    
    @patch('app.extractors.Document')
    def test_extract_from_docx_sync(self, mock_document, text_extractor):
        """Тест синхронного извлечения из DOCX файла"""
        mock_doc = Mock()
        mock_paragraph = Mock()
        mock_paragraph.text = "Тестовый параграф"
        mock_doc.paragraphs = [mock_paragraph]
        mock_document.return_value = mock_doc
        
        content_bytes = b"fake docx content"
        
        result = text_extractor._extract_from_docx_sync(content_bytes, "test.docx")
        
        assert "Тестовый параграф" in result
        mock_document.assert_called_once()
    
    @patch('app.extractors.subprocess.run')
    def test_extract_from_doc_sync(self, mock_subprocess, text_extractor):
        """Тест синхронного извлечения из DOC файла"""
        mock_subprocess.return_value.returncode = 0
        
        with patch.object(text_extractor, '_extract_from_docx_sync') as mock_docx:
            mock_docx.return_value = "Текст из DOC"
            
            content_bytes = b"fake doc content"
            
            with patch('tempfile.NamedTemporaryFile'):
                with patch('os.path.exists', return_value=True):
                    with patch('builtins.open', mock_open(read_data=b"converted docx")):
                        result = text_extractor._extract_from_doc_sync(content_bytes, "test.doc")
                        
                        assert result == "Текст из DOC"
    
    @patch('app.extractors.pandas.read_excel')
    def test_extract_from_xlsx_sync(self, mock_read_excel, text_extractor):
        """Тест синхронного извлечения из XLSX файла"""
        mock_df = Mock()
        mock_df.to_csv.return_value = "col1,col2\nval1,val2"
        mock_read_excel.return_value = {"Sheet1": mock_df}
        
        content_bytes = b"fake xlsx content"
        
        result = text_extractor._extract_from_xlsx_sync(content_bytes, "test.xlsx")
        
        assert "Sheet1:" in result
        assert "col1,col2" in result
        assert "val1,val2" in result
    
    @patch('app.extractors.zipfile.ZipFile')
    def test_extract_from_archive_sync(self, mock_zipfile, text_extractor):
        """Тест синхронного извлечения из архива"""
        mock_zip = Mock()
        mock_zip.namelist.return_value = ["file1.txt", "file2.txt"]
        mock_zip.read.side_effect = [b"content1", b"content2"]
        mock_zipfile.return_value.__enter__.return_value = mock_zip
        
        with patch.object(text_extractor, '_process_extracted_file') as mock_process:
            mock_process.side_effect = [
                ("file1.txt", "file1.txt", 8, "txt", "content1"),
                ("file2.txt", "file2.txt", 8, "txt", "content2")
            ]
            
            content_bytes = b"fake zip content"
            
            result = text_extractor._extract_from_archive_sync(content_bytes, "test.zip")
            
            assert len(result) == 2
            assert result[0]["filename"] == "file1.txt"
            assert result[1]["filename"] == "file2.txt"
    
    def test_sanitize_archive_filename(self, text_extractor):
        """Тест санитизации имен файлов в архиве"""
        assert text_extractor._sanitize_archive_filename("normal_file.txt") == "normal_file.txt"
        assert text_extractor._sanitize_archive_filename("../../../etc/passwd") == "etc/passwd"
        assert text_extractor._sanitize_archive_filename("..\\..\\windows\\system32") == "windows/system32"
        assert text_extractor._sanitize_archive_filename("./file.txt") == "file.txt"
    
    def test_is_system_file(self, text_extractor):
        """Тест проверки системных файлов"""
        assert text_extractor._is_system_file(".DS_Store") == True
        assert text_extractor._is_system_file("Thumbs.db") == True
        assert text_extractor._is_system_file(".git/config") == True
        assert text_extractor._is_system_file("regular_file.txt") == False
        assert text_extractor._is_system_file("document.pdf") == False
    
    def test_get_language_from_extension(self, text_extractor):
        """Тест определения языка программирования по расширению"""
        assert text_extractor._get_language_from_extension("py") == "Python"
        assert text_extractor._get_language_from_extension("js") == "JavaScript"
        assert text_extractor._get_language_from_extension("java") == "Java"
        assert text_extractor._get_language_from_extension("cpp") == "C++"
        assert text_extractor._get_language_from_extension("rs") == "Rust"
        assert text_extractor._get_language_from_extension("bsl") == "1C:Enterprise"
        assert text_extractor._get_language_from_extension("os") == "OneScript"
        assert text_extractor._get_language_from_extension("unknown") == "Unknown"
    
    def test_flatten_json_simple(self, text_extractor):
        """Тест сплющивания простого JSON"""
        data = {"name": "Тест", "value": 42}
        result = text_extractor._flatten_json(data)
        expected = {"name": "Тест", "value": 42}
        assert result == expected
    
    def test_flatten_json_nested(self, text_extractor):
        """Тест сплющивания вложенного JSON"""
        data = {
            "user": {
                "name": "Иван",
                "age": 30,
                "address": {
                    "city": "Москва",
                    "country": "Россия"
                }
            }
        }
        result = text_extractor._flatten_json(data)
        expected = {
            "user.name": "Иван",
            "user.age": 30,
            "user.address.city": "Москва",
            "user.address.country": "Россия"
        }
        assert result == expected
    
    def test_flatten_json_with_arrays(self, text_extractor):
        """Тест сплющивания JSON с массивами"""
        data = {
            "items": ["item1", "item2"],
            "nested": {
                "list": [{"id": 1}, {"id": 2}]
            }
        }
        result = text_extractor._flatten_json(data)
        expected = {
            "items[0]": "item1",
            "items[1]": "item2",
            "nested.list[0].id": 1,
            "nested.list[1].id": 2
        }
        assert result == expected
    
    def test_flatten_yaml_simple(self, text_extractor):
        """Тест сплющивания простого YAML"""
        data = {"name": "Тест", "value": 42}
        result = text_extractor._flatten_yaml(data)
        expected = {"name": "Тест", "value": 42}
        assert result == expected
    
    def test_flatten_yaml_nested(self, text_extractor):
        """Тест сплющивания вложенного YAML"""
        data = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "credentials": {
                    "username": "user",
                    "password": "pass"
                }
            }
        }
        result = text_extractor._flatten_yaml(data)
        expected = {
            "database.host": "localhost",
            "database.port": 5432,
            "database.credentials.username": "user",
            "database.credentials.password": "pass"
        }
        assert result == expected 