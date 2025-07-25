"""Unit тесты для модуля утилит."""

import logging
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.utils import (
    get_file_extension,
    is_archive_format,
    is_supported_format,
    safe_filename,
    sanitize_filename,
    setup_logging,
    validate_file_type,
)


@pytest.mark.unit
class TestGetFileExtension:
    """Тесты для функции get_file_extension."""

    def test_simple_extension(self):
        """Тест простого расширения."""
        assert get_file_extension("document.pdf") == "pdf"
        assert get_file_extension("image.jpg") == "jpg"
        assert get_file_extension("data.csv") == "csv"

    def test_compound_extension(self):
        """Тест составного расширения."""
        assert get_file_extension("archive.tar.gz") == "tar.gz"
        assert get_file_extension("backup.tar.bz2") == "tar.bz2"
        assert get_file_extension("data.tar.xz") == "tar.xz"
        assert get_file_extension("file.tgz") == "tar.gz"
        assert get_file_extension("file.tbz2") == "tar.bz2"
        assert get_file_extension("file.txz") == "tar.xz"

    def test_multiple_dots(self):
        """Тест файлов с несколькими точками."""
        assert get_file_extension("file.name.txt") == "txt"
        assert get_file_extension("data.backup.json") == "json"

    def test_uppercase_extension(self):
        """Тест расширения в верхнем регистре."""
        assert get_file_extension("document.PDF") == "pdf"
        assert get_file_extension("IMAGE.JPG") == "jpg"

    def test_no_extension(self):
        """Тест файлов без расширения."""
        assert get_file_extension("README") is None
        assert get_file_extension("Makefile") is None
        assert get_file_extension("file_no_ext") is None

    def test_empty_filename(self):
        """Тест пустого имени файла."""
        assert get_file_extension("") is None
        assert get_file_extension("   ") is None

    def test_hidden_file(self):
        """Тест скрытого файла."""
        assert get_file_extension(".gitignore") == "gitignore"
        assert get_file_extension(".env") == "env"
        assert get_file_extension(".config.json") == "json"


@pytest.mark.unit
class TestSanitizeFilename:
    """Тесты для функции sanitize_filename."""

    def test_normal_filename(self):
        """Тест нормального имени файла."""
        assert sanitize_filename("document.pdf") == "document.pdf"
        assert sanitize_filename("image.jpg") == "image.jpg"
        assert sanitize_filename("data_file.txt") == "data_file.txt"

    def test_path_traversal_attack(self):
        """Тест защиты от path traversal атак."""
        # Наша новая функция удаляет все опасные символы для path traversal
        assert sanitize_filename("../../../etc/passwd") == "etcpasswd"
        assert (
            sanitize_filename("..\\..\\windows\\system32\\config")
            == "windowssystem32config"
        )
        assert sanitize_filename("./malicious.exe") == "malicious.exe"

    def test_unicode_characters(self):
        """Тест обработки Unicode символов."""
        # Проверяем корректную обработку кириллицы
        result = sanitize_filename("файл_с_русскими_символами.txt")
        assert result == "файл_с_русскими_символами.txt"

        # Проверяем другие unicode символы
        assert sanitize_filename("测试文件.pdf") == "测试文件.pdf"  # Китайский
        assert sanitize_filename("тест.md") == "тест.md"  # Кириллица
        assert (
            sanitize_filename("файл#с@символами.docx") == "файл#с@символами.docx"
        )  # Кириллица + безопасные символы
        assert (
            sanitize_filename("файл<с>символами.docx") == "файлссимволами.docx"
        )  # Кириллица + опасные символы

    def test_empty_filename(self):
        """Тест обработки пустого имени файла."""
        assert sanitize_filename("") == "unknown_file"
        assert (
            sanitize_filename("   ") == "sanitized_file"
        )  # werkzeug.secure_filename удаляет пробелы

    def test_filename_with_slashes(self):
        """Тест обработки имен файлов со слешами."""
        # Наша функция удаляет все слеши для безопасности
        assert sanitize_filename("path/to/file.txt") == "pathtofile.txt"
        assert sanitize_filename("path\\to\\file.txt") == "pathtofile.txt"

    def test_filename_with_special_chars(self):
        """Тест обработки специальных символов."""
        # werkzeug.secure_filename удаляет опасные символы
        result = sanitize_filename("file<>|.txt")
        assert result is not None
        # Проверяем, что опасные символы удалены
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result


@pytest.mark.unit
class TestValidateFileType:
    """Тесты для функции validate_file_type."""

    def test_valid_pdf_file(self):
        """Тест валидного PDF файла."""
        # Простой PDF заголовок
        pdf_content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"

        with patch("app.utils.magic.from_buffer", return_value="application/pdf"):
            is_valid, error = validate_file_type(pdf_content, "document.pdf")
            assert is_valid is True
            assert error is None

    def test_invalid_extension_mismatch(self):
        """Тест несоответствия расширения содержимому."""
        # Текстовый контент с PDF расширением
        text_content = b"This is plain text, not PDF"

        with patch("app.utils.magic.from_buffer", return_value="text/plain"):
            is_valid, error = validate_file_type(text_content, "document.pdf")
            assert is_valid is False
            assert error is not None
            assert "не соответствует" in error

    def test_text_file_valid(self):
        """Тест валидного текстового файла."""
        text_content = b"This is a text file"

        with patch("app.utils.magic.from_buffer", return_value="text/plain"):
            is_valid, error = validate_file_type(text_content, "file.txt")
            assert is_valid is True
            assert error is None

    def test_source_code_file_valid(self):
        """Тест валидного файла исходного кода."""
        python_content = b'print("Hello, World!")'

        with patch("app.utils.magic.from_buffer", return_value="text/plain"):
            is_valid, error = validate_file_type(python_content, "script.py")
            assert is_valid is True
            assert error is None

    def test_empty_content(self):
        """Тест пустого содержимого."""
        is_valid, error = validate_file_type(b"", "file.txt")
        assert is_valid is False
        assert error is not None
        assert "отсутствуют" in error

    def test_empty_filename(self):
        """Тест пустого имени файла."""
        is_valid, error = validate_file_type(b"content", "")
        assert is_valid is False
        assert error is not None
        assert "отсутствуют" in error

    def test_no_extension(self):
        """Тест файла без расширения."""
        is_valid, error = validate_file_type(b"content", "README")
        assert is_valid is False
        assert error is not None
        assert "расширение" in error

    def test_magic_library_not_available(self):
        """Тест когда magic library недоступна."""
        with patch(
            "app.utils.magic.from_buffer", side_effect=Exception("Magic not available")
        ):
            is_valid, error = validate_file_type(b"content", "file.txt")
            assert is_valid is False  # Fail-closed стратегия при ошибке
            assert "Не удалось определить тип файла" in error


@pytest.mark.unit
class TestSetupLogging:
    """Тесты для функции setup_logging."""

    def test_setup_logging_calls(self):
        """Тест вызова setup_logging."""
        with patch("logging.getLogger") as mock_get_logger:
            with patch("logging.StreamHandler"):
                with patch("logging.Formatter"):
                    mock_root_logger = Mock()
                    mock_uvicorn_logger = Mock()
                    mock_get_logger.side_effect = [
                        mock_root_logger,
                        mock_uvicorn_logger,
                    ]

                    setup_logging()

                    # Проверяем что логгеры настроены
                    mock_root_logger.setLevel.assert_called_with(logging.INFO)
                    mock_uvicorn_logger.setLevel.assert_called_with(logging.INFO)
                    assert mock_uvicorn_logger.propagate is False

    def test_logging_level_setup(self):
        """Тест настройки уровней логирования."""
        with patch("logging.getLogger") as mock_get_logger:
            with patch("logging.StreamHandler"):
                with patch("logging.Formatter"):
                    mock_root_logger = Mock()
                    mock_uvicorn_logger = Mock()
                    mock_get_logger.side_effect = [
                        mock_root_logger,
                        mock_uvicorn_logger,
                    ]

                    setup_logging()

                    # Проверяем уровни логирования
                    mock_root_logger.setLevel.assert_called_with(logging.INFO)
                    mock_uvicorn_logger.setLevel.assert_called_with(logging.INFO)


@pytest.mark.unit
class TestFormatSupportFunctions:
    """Тесты для функций проверки поддержки форматов."""

    def test_is_supported_format(self):
        """Тест проверки поддержки формата."""
        supported_formats = {
            "text": ["txt", "md"],
            "pdf": ["pdf"],
            "archives": ["zip", "tar"],
        }

        assert is_supported_format("document.pdf", supported_formats) is True
        assert is_supported_format("readme.txt", supported_formats) is True
        assert is_supported_format("archive.zip", supported_formats) is True
        assert is_supported_format("unknown.xyz", supported_formats) is False

    def test_is_archive_format(self):
        """Тест проверки архивного формата."""
        supported_formats = {
            "text": ["txt", "md"],
            "pdf": ["pdf"],
            "archives": ["zip", "tar", "gz"],
        }

        assert is_archive_format("archive.zip", supported_formats) is True
        assert is_archive_format("backup.tar", supported_formats) is True
        assert is_archive_format("data.gz", supported_formats) is True
        assert is_archive_format("document.pdf", supported_formats) is False
        assert is_archive_format("readme.txt", supported_formats) is False

    def test_safe_filename(self):
        """Тест безопасного имени файла."""
        assert safe_filename("document.pdf") == "document.pdf"
        assert safe_filename("file with spaces.txt") == "file_with_spaces.txt"
        assert safe_filename("file@#$%^&*()name.txt") == "file_________name.txt"
        assert safe_filename("") == "unknown_file"
        # Проверяем реальное поведение с кириллицей
        result = safe_filename("файл.txt")
        assert result is not None
        assert len(result) > 0


@pytest.mark.unit
class TestWebUtilityFunctions:
    """Тесты для новых утилитарных функций веб-экстракции (v1.10.1)."""

    def test_get_extension_from_mime_jpg(self):
        """Тест получения расширения из MIME-типа для JPEG."""
        from app.config import settings
        from app.utils import get_extension_from_mime

        # Тестируем JPEG
        assert (
            get_extension_from_mime("image/jpeg", settings.SUPPORTED_FORMATS) == "jpg"
        )
        assert get_extension_from_mime("image/jpg", settings.SUPPORTED_FORMATS) == "jpg"

    def test_get_extension_from_mime_png(self):
        """Тест получения расширения из MIME-типа для PNG."""
        from app.config import settings
        from app.utils import get_extension_from_mime

        assert get_extension_from_mime("image/png", settings.SUPPORTED_FORMATS) == "png"

    def test_get_extension_from_mime_webp(self):
        """Тест получения расширения из MIME-типа для WebP."""
        from app.config import settings
        from app.utils import get_extension_from_mime

        assert (
            get_extension_from_mime("image/webp", settings.SUPPORTED_FORMATS) == "webp"
        )

    def test_get_extension_from_mime_unsupported(self):
        """Тест для неподдерживаемого MIME-типа."""
        from app.config import settings
        from app.utils import get_extension_from_mime

        assert (
            get_extension_from_mime("image/svg+xml", settings.SUPPORTED_FORMATS) is None
        )
        assert (
            get_extension_from_mime(
                "application/octet-stream", settings.SUPPORTED_FORMATS
            )
            is None
        )
        assert get_extension_from_mime("", settings.SUPPORTED_FORMATS) is None

    def test_extract_mime_from_base64_data_uri_jpg(self):
        """Тест извлечения MIME-типа из base64 data URI для JPEG."""
        from app.utils import extract_mime_from_base64_data_uri

        data_uri = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD..."
        assert extract_mime_from_base64_data_uri(data_uri) == "image/jpeg"

    def test_extract_mime_from_base64_data_uri_png(self):
        """Тест извлечения MIME-типа из base64 data URI для PNG."""
        from app.utils import extract_mime_from_base64_data_uri

        data_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        assert extract_mime_from_base64_data_uri(data_uri) == "image/png"

    def test_extract_mime_from_base64_data_uri_invalid(self):
        """Тест для некорректного data URI."""
        from app.utils import extract_mime_from_base64_data_uri

        assert extract_mime_from_base64_data_uri("invalid-data-uri") is None
        assert (
            extract_mime_from_base64_data_uri("data:text/plain;base64,SGVsbG8=") is None
        )  # не изображение
        assert extract_mime_from_base64_data_uri("") is None

    def test_decode_base64_image_valid(self):
        """Тест декодирования валидного base64 изображения."""
        from app.utils import decode_base64_image

        # Полный data URI с 1x1 PNG
        data_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

        result = decode_base64_image(data_uri)
        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_decode_base64_image_invalid(self):
        """Тест декодирования некорректного base64."""
        from app.utils import decode_base64_image

        assert decode_base64_image("invalid-base64!@#$") is None
        assert decode_base64_image("") is None
        assert decode_base64_image("notbase64") is None
        # Обычная base64 строка без data URI префикса должна вернуть None
        assert (
            decode_base64_image(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
            )
            is None
        )

    def test_decode_base64_image_from_data_uri(self):
        """Тест декодирования base64 из полного data URI."""
        from app.utils import decode_base64_image

        # Полный data URI с 1x1 PNG
        data_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

        result = decode_base64_image(data_uri)
        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 0
