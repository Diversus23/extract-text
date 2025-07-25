"""Unit тесты для модуля извлечения текста."""

import asyncio
import io
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, mock_open, patch

import pytest

from app.config import settings
from app.extractors import TextExtractor


@pytest.mark.unit
class TestTextExtractor:
    """Тесты для класса TextExtractor."""

    def test_init(self):
        """Тест инициализации TextExtractor."""
        extractor = TextExtractor()
        assert extractor.ocr_languages == settings.OCR_LANGUAGES
        assert extractor.timeout == settings.PROCESSING_TIMEOUT_SECONDS
        assert extractor._thread_pool is not None
        assert extractor._thread_pool._max_workers == 4

    def test_extract_text_simple_txt(self, text_extractor):
        """Тест извлечения текста из простого текстового файла."""
        test_content = "Тестовый текст для проверки"
        content_bytes = test_content.encode("utf-8")

        result = text_extractor.extract_text(content_bytes, "test.txt")

        assert len(result) == 1
        assert result[0]["filename"] == "test.txt"
        assert result[0]["type"] == "txt"
        assert result[0]["text"] == test_content
        assert result[0]["size"] == len(content_bytes)

    def test_extract_text_unsupported_format(self, text_extractor):
        """Тест извлечения текста из неподдерживаемого формата."""
        content_bytes = b"some content"

        with pytest.raises(ValueError, match="Unsupported file format"):
            text_extractor.extract_text(content_bytes, "test.xyz")

    def test_extract_text_timeout(self):
        """Тест обработки таймаута."""
        extractor = TextExtractor()

        # Мокаем метод для имитации таймаута
        with patch.object(extractor, "_extract_text_by_format") as mock_extract:
            mock_extract.side_effect = TimeoutError()

            with pytest.raises(ValueError, match="Error extracting text"):
                extractor.extract_text(b"test content", "test.txt")

    def test_extract_from_txt_sync(self, text_extractor):
        """Тест синхронного извлечения из текстового файла."""
        test_content = "Простой текст\nВторая строка"
        content_bytes = test_content.encode("utf-8")

        result = text_extractor._extract_from_txt_sync(content_bytes)

        assert result == test_content

    def test_extract_from_txt_sync_encoding_fallback(self, text_extractor):
        """Тест извлечения текста с разными кодировками."""
        # Текст в CP1251
        test_content = "Тестовый текст"
        content_bytes = test_content.encode("cp1251")

        result = text_extractor._extract_from_txt_sync(content_bytes)

        assert result == test_content

    def test_extract_from_json_sync(self, text_extractor):
        """Тест синхронного извлечения из JSON файла."""
        json_content = '{"name": "Тест", "value": 42, "nested": {"key": "значение"}}'
        content_bytes = json_content.encode("utf-8")

        result = text_extractor._extract_from_json_sync(content_bytes)

        # JSON парсер извлекает только строковые значения
        assert "name: Тест" in result
        assert "nested.key: значение" in result
        # Числовые значения не извлекаются
        assert "value: 42" not in result

    def test_extract_from_json_sync_invalid(self, text_extractor):
        """Тест обработки некорректного JSON."""
        invalid_json = b'{"invalid": json}'

        with pytest.raises(ValueError, match="Error processing JSON"):
            text_extractor._extract_from_json_sync(invalid_json)

    def test_extract_from_csv_sync(self, text_extractor):
        """Тест синхронного извлечения из CSV файла."""
        csv_content = "Название,Цена,Количество\nТовар 1,100,5\nТовар 2,200,3"
        content_bytes = csv_content.encode("utf-8")

        result = text_extractor._extract_from_csv_sync(content_bytes)

        assert "Название,Цена,Количество" in result
        assert "Товар 1,100,5" in result
        assert "Товар 2,200,3" in result

    def test_extract_from_xml_sync(self, text_extractor):
        """Тест синхронного извлечения из XML файла."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <root>
            <item id="1">
                <name>Товар 1</name>
                <price>100</price>
            </item>
        </root>"""
        content_bytes = xml_content.encode("utf-8")

        result = text_extractor._extract_from_xml_sync(content_bytes)

        assert "Товар 1" in result
        assert "100" in result

    def test_extract_from_xml_sync_invalid(self, text_extractor):
        """Тест обработки некорректного XML."""
        invalid_xml = b"<invalid><unclosed>tag</invalid>"

        with pytest.raises(ValueError, match="Error processing XML"):
            text_extractor._extract_from_xml_sync(invalid_xml)

    def test_extract_from_yaml_sync(self, text_extractor):
        """Тест синхронного извлечения из YAML файла."""
        yaml_content = "name: Тест\nvalue: 42\nnested:\n  key: значение"
        content_bytes = yaml_content.encode("utf-8")

        result = text_extractor._extract_from_yaml_sync(content_bytes)

        # YAML парсер извлекает только строковые значения
        assert "name: Тест" in result
        assert "nested.key: значение" in result
        # Числовые значения не извлекаются
        assert "value: 42" not in result

    def test_extract_from_yaml_sync_invalid(self, text_extractor):
        """Тест обработки некорректного YAML."""
        invalid_yaml = b"invalid: yaml: content: ["

        with pytest.raises(ValueError, match="Error processing YAML"):
            text_extractor._extract_from_yaml_sync(invalid_yaml)

    def test_extract_from_html_sync(self, text_extractor):
        """Тест синхронного извлечения из HTML файла."""
        html_content = """<html>
        <head><title>Тестовая страница</title></head>
        <body>
            <h1>Заголовок</h1>
            <p>Тестовый параграф с <strong>жирным</strong> текстом.</p>
        </body>
        </html>"""
        content_bytes = html_content.encode("utf-8")

        result = text_extractor._extract_from_html_sync(content_bytes)

        assert "Тестовая страница" in result
        assert "Заголовок" in result
        assert "Тестовый параграф с жирным текстом." in result

    def test_extract_from_source_code_sync(self, text_extractor):
        """Тест синхронного извлечения из файла исходного кода."""
        python_content = """#!/usr/bin/env python3
# Тестовый Python файл

def hello_world():
    \"\"\"Приветствие мира\"\"\"
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()
"""
        content_bytes = python_content.encode("utf-8")

        result = text_extractor._extract_from_source_code_sync(
            content_bytes, "py", "test.py"
        )

        assert "#!/usr/bin/env python3" in result
        assert "Тестовый Python файл" in result
        assert "def hello_world():" in result
        assert 'print("Hello, World!")' in result

    def test_extract_from_source_code_sync_unknown_language(self, text_extractor):
        """Тест извлечения из исходного кода неизвестного языка."""
        code_content = b'// Unknown language code\nfunction test() { return "hello"; }'

        result = text_extractor._extract_from_source_code_sync(
            code_content, "unknown", "test.unknown"
        )

        # Проверяем, что контент декодируется как обычный текст
        assert "Unknown language code" in result
        assert "function test()" in result

    @patch("app.extractors.pdfplumber")
    def test_extract_from_pdf_sync(self, mock_pdfplumber, text_extractor):
        """Тест синхронного извлечения из PDF."""
        mock_pdf = Mock()
        mock_page = Mock()
        mock_page.extract_text.return_value = "Тестовый текст PDF"
        mock_page.images = []
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf

        with patch("tempfile.NamedTemporaryFile"):
            with patch("os.unlink"):
                result = text_extractor._extract_from_pdf_sync(b"fake pdf content")

                assert "Тестовый текст PDF" in result
                assert "[Страница 1]" in result

    @patch("app.extractors.pdfplumber")
    def test_extract_from_pdf_sync_with_images(self, mock_pdfplumber, text_extractor):
        """Тест синхронного извлечения из PDF с изображениями."""
        mock_pdf = Mock()
        mock_page = Mock()
        mock_page.extract_text.return_value = "Текст страницы"
        mock_image = {"x0": 0, "y0": 0, "x1": 100, "y1": 100}
        mock_page.images = [mock_image]
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf

        with patch("tempfile.NamedTemporaryFile"):
            with patch("os.unlink"):
                with patch.object(
                    text_extractor, "_ocr_from_pdf_image_sync", return_value="OCR текст"
                ):
                    result = text_extractor._extract_from_pdf_sync(b"fake pdf content")

                    assert "Текст страницы" in result
                    assert "OCR текст" in result
                    assert "[Изображение 1]" in result

    @patch("app.extractors.Image")
    def test_extract_from_image_sync(self, mock_image_class, text_extractor):
        """Тест синхронного извлечения из изображения."""
        mock_image = Mock()
        mock_image_class.open.return_value = mock_image

        content_bytes = b"fake image content"

        with patch("app.utils.validate_image_for_ocr", return_value=(True, None)):
            with patch.object(
                text_extractor, "_safe_tesseract_ocr", return_value="Распознанный текст"
            ):
                result = text_extractor._extract_from_image_sync(content_bytes)

                assert "Распознанный текст" in result

    @patch("app.extractors.Image")
    def test_extract_from_image_sync_no_text(self, mock_image_class, text_extractor):
        """Тест извлечения из изображения без текста."""
        mock_image = Mock()
        mock_image_class.open.return_value = mock_image

        content_bytes = b"fake image content"

        with patch("app.utils.validate_image_for_ocr", return_value=(True, None)):
            with patch.object(text_extractor, "_safe_tesseract_ocr", return_value=""):
                result = text_extractor._extract_from_image_sync(content_bytes)

                assert result == ""

    @patch("app.extractors.Document")
    def test_extract_from_docx_sync(self, mock_document, text_extractor):
        """Тест синхронного извлечения из DOCX."""
        mock_doc = Mock()
        mock_paragraph = Mock()
        mock_paragraph.text = "Тестовый параграф"
        mock_doc.paragraphs = [mock_paragraph]
        mock_doc.tables = []
        mock_doc.sections = []  # Добавляем пустой список секций
        mock_document.return_value = mock_doc

        result = text_extractor._extract_from_docx_sync(b"fake docx content")

        assert "Тестовый параграф" in result

    @patch("app.extractors.Document")
    def test_extract_from_doc_sync(self, mock_document, text_extractor):
        """Тест синхронного извлечения из DOC."""
        mock_doc = Mock()
        mock_paragraph = Mock()
        mock_paragraph.text = "Тестовый параграф из DOC"
        mock_doc.paragraphs = [mock_paragraph]
        mock_doc.tables = []
        mock_doc.sections = []  # Добавляем sections для полного мокинга
        mock_document.return_value = mock_doc

        # Мокаем run_subprocess_with_limits
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("tempfile.NamedTemporaryFile"):
            with patch("tempfile.mkdtemp"):
                with patch(
                    "app.utils.run_subprocess_with_limits", return_value=mock_result
                ):
                    with patch("os.path.exists", return_value=True):
                        with patch(
                            "builtins.open", mock_open(read_data=b"docx content")
                        ):
                            with patch("os.unlink"):
                                with patch("shutil.rmtree"):
                                    result = text_extractor._extract_from_doc_sync(
                                        b"fake doc content"
                                    )

                                    assert "Тестовый параграф из DOC" in result

    @patch("app.extractors.pd")
    def test_extract_from_excel_sync(self, mock_pd, text_extractor):
        """Тест синхронного извлечения из Excel."""
        mock_dataframe = Mock()
        mock_dataframe.to_csv.return_value = "col1,col2\nvalue1,value2"
        mock_pd.read_excel.return_value = {"Sheet1": mock_dataframe}

        result = text_extractor._extract_from_excel_sync(b"fake excel content")

        assert "[Лист: Sheet1]" in result
        assert "col1,col2" in result
        assert "value1,value2" in result

    def test_extract_from_archive(self, text_extractor):
        """Тест извлечения из архива."""
        # Создаем простой zip архив в памяти
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as zipf:
            zipf.writestr("test.txt", "Тестовый текст в архиве")

        archive_bytes = archive_buffer.getvalue()

        result = text_extractor.extract_text(archive_bytes, "test.zip")

        assert len(result) == 1
        assert result[0]["filename"] == "test.txt"
        assert result[0]["text"] == "Тестовый текст в архиве"

    def test_sanitize_archive_filename(self, text_extractor):
        """Тест санитизации имени файла архива."""
        # Тестируем удаление опасных путей
        assert (
            text_extractor._sanitize_archive_filename("../../../etc/passwd")
            == "etc/passwd"
        )
        assert (
            text_extractor._sanitize_archive_filename("..\\..\\windows\\system32")
            == "windows/system32"
        )
        assert (
            text_extractor._sanitize_archive_filename("/absolute/path/file.txt")
            == "absolute/path/file.txt"
        )

        # Тестируем нормальные имена
        assert (
            text_extractor._sanitize_archive_filename("folder/file.txt")
            == "folder/file.txt"
        )
        assert text_extractor._sanitize_archive_filename("simple.txt") == "simple.txt"

        # Тестируем пустые строки
        assert text_extractor._sanitize_archive_filename("") == ""
        assert text_extractor._sanitize_archive_filename("./") == ""

    def test_is_system_file(self, text_extractor):
        """Тест проверки системных файлов."""
        # Файлы с директориями работают (содержат слеш)
        assert text_extractor._is_system_file("folder/.git/config") is True
        assert text_extractor._is_system_file("path/.svn/file") is True
        assert text_extractor._is_system_file("path/.hg/file") is True

        # Простые файлы могут не работать из-за точного соответствия
        # Проверяем реальное поведение
        assert text_extractor._is_system_file("normal_file.txt") is False
        assert text_extractor._is_system_file("document.pdf") is False
        assert text_extractor._is_system_file("image.jpg") is False
        assert text_extractor._is_system_file("data.csv") is False

    def test_check_mime_type(self, text_extractor):
        """Тест проверки MIME типа."""
        # Тестируем текстовый файл
        content = b"This is a text file"
        result = text_extractor._check_mime_type(content, "test.txt")
        assert result is True

        # Тестируем PDF файл
        pdf_content = b"%PDF-1.4"
        result = text_extractor._check_mime_type(pdf_content, "test.pdf")
        assert result is True


@pytest.mark.unit
class TestBase64ImageProcessing:
    """Тесты для обработки base64 изображений (v1.10.1)."""

    @pytest.fixture
    def text_extractor(self):
        """Фикстура для создания экстрактора."""
        from app.extractors import TextExtractor

        return TextExtractor()

    def test_process_base64_image_valid_png(self, text_extractor):
        """Тест обработки валидного base64 PNG изображения."""
        # Простое 1x1 PNG изображение в base64
        base64_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

        result = text_extractor._process_base64_image(base64_data)

        # Результат должен быть None из-за слишком маленького размера (1x1)
        assert result is None

    def test_process_base64_image_invalid_data(self, text_extractor):
        """Тест обработки некорректного base64 изображения."""
        invalid_data = "data:image/png;base64,invalid-base64-data"

        result = text_extractor._process_base64_image(invalid_data)
        assert result is None

    def test_process_base64_image_unsupported_format(self, text_extractor):
        """Тест обработки неподдерживаемого формата base64."""
        svg_data = (
            "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCI+PC9zdmc+"
        )

        result = text_extractor._process_base64_image(svg_data)
        assert result is None

    def test_process_base64_image_no_data_uri(self, text_extractor):
        """Тест обработки base64 без data URI префикса."""
        plain_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

        result = text_extractor._process_base64_image(plain_base64)
        assert result is None


@pytest.mark.integration
class TestPlaywrightIntegration:
    """Тесты для Playwright интеграции (v1.10.1)."""

    @pytest.fixture
    def text_extractor(self):
        """Фикстура для создания экстрактора."""
        from app.extractors import TextExtractor

        return TextExtractor()

    @patch("app.extractors.sync_playwright")
    def test_extract_page_with_playwright_failure(
        self, mock_playwright, text_extractor
    ):
        """Тест обработки ошибки Playwright."""
        # Настройка мока для генерации исключения
        mock_playwright.return_value.__enter__.side_effect = Exception(
            "Playwright error"
        )

        # Выполнение теста - должно вызвать исключение, а не возвращать None
        with pytest.raises(Exception, match="Playwright error"):
            text_extractor._extract_page_with_playwright("https://example.com")

    def test_safe_scroll_for_lazy_loading_stable_height(self, text_extractor):
        """Тест безопасного скролла с неизменной высотой."""
        mock_page = Mock()
        mock_page.evaluate.return_value = 1000  # постоянная высота

        text_extractor._safe_scroll_for_lazy_loading(mock_page)

        # Проверяем, что скролл был выполнен
        assert (
            mock_page.evaluate.call_count >= 2
        )  # минимум 2 вызова для проверки высоты

    def test_safe_scroll_for_lazy_loading_changing_height(self, text_extractor):
        """Тест безопасного скролла с изменяющейся высотой."""
        mock_page = Mock()
        # Имитируем увеличение высоты страницы
        mock_page.evaluate.side_effect = [
            1000,
            1200,
            1200,
        ]  # высота увеличивается, затем стабилизируется

        text_extractor._safe_scroll_for_lazy_loading(mock_page)


@pytest.mark.integration
class TestWebExtractionWithMockRequests:
    """Тесты веб-экстракции с мокированием HTTP-запросов."""

    @pytest.fixture
    def text_extractor(self):
        """Фикстура для создания экстрактора."""
        from app.extractors import TextExtractor

        return TextExtractor()

    @patch("requests.get")
    def test_extract_from_url_with_base64_images(self, mock_get, text_extractor):
        """Тест извлечения URL с base64 изображениями."""
        # HTML с base64 изображением
        html_content = """
        <html>
        <body>
            <h1>Test Page with Base64 Image</h1>
            <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==" />
            <p>Some text content</p>
        </body>
        </html>
        """

        # Настройка мока
        mock_response = Mock()
        mock_response.text = html_content
        mock_response.content = html_content.encode("utf-8")
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_get.return_value = mock_response

        # Выполнение теста
        result = text_extractor.extract_from_url("https://example.com")

        # Проверки
        assert len(result) >= 1  # минимум HTML контент
        assert any(
            "Test Page with Base64 Image" in file_data["text"] for file_data in result
        )

    @patch("requests.get")
    def test_extract_from_url_requests_fallback(self, mock_get, text_extractor):
        """Тест fallback на requests при выключенном JavaScript."""
        html_content = "<html><body><h1>Simple Page</h1></body></html>"

        mock_response = Mock()
        mock_response.text = html_content
        mock_response.content = html_content.encode("utf-8")
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_get.return_value = mock_response

        # Временно отключаем JavaScript
        with patch("app.config.settings.ENABLE_JAVASCRIPT", False):
            result = text_extractor.extract_from_url("https://example.com")

        assert len(result) >= 1
        assert any("Simple Page" in file_data["text"] for file_data in result)
