"""
Тесты для модуля утилит
"""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, mock_open

from app.utils import (
    get_file_extension,
    is_archive_format,
    sanitize_filename,
    validate_file_type,
    setup_logging
)


@pytest.mark.unit
class TestFileExtension:
    """Тесты для функции get_file_extension"""
    
    def test_simple_extension(self):
        """Тест простого расширения"""
        assert get_file_extension("test.txt") == "txt"
        assert get_file_extension("document.pdf") == "pdf"
        assert get_file_extension("image.jpg") == "jpg"
    
    def test_compound_extension(self):
        """Тест составного расширения"""
        assert get_file_extension("archive.tar.gz") == "tar.gz"
        assert get_file_extension("backup.tar.bz2") == "tar.bz2"
        assert get_file_extension("data.tar.xz") == "tar.xz"
    
    def test_no_extension(self):
        """Тест файла без расширения"""
        assert get_file_extension("README") is None
        assert get_file_extension("Makefile") is None
    
    def test_hidden_file(self):
        """Тест скрытого файла"""
        assert get_file_extension(".gitignore") == "gitignore"
        assert get_file_extension(".env") == "env"
    
    def test_multiple_dots(self):
        """Тест файла с множественными точками"""
        assert get_file_extension("file.name.with.dots.txt") == "txt"
        assert get_file_extension("complex.file.name.tar.gz") == "tar.gz"
    
    def test_case_insensitive(self):
        """Тест нечувствительности к регистру"""
        assert get_file_extension("FILE.TXT") == "txt"
        assert get_file_extension("Document.PDF") == "pdf"
        assert get_file_extension("Archive.TAR.GZ") == "tar.gz"
    
    def test_empty_filename(self):
        """Тест пустого имени файла"""
        assert get_file_extension("") is None
        assert get_file_extension(".") is None
    
    def test_none_filename(self):
        """Тест None в качестве имени файла"""
        assert get_file_extension(None) is None


@pytest.mark.unit
class TestArchiveFormat:
    """Тесты для функции is_archive_format"""
    
    def setUp(self):
        """Настройка поддерживаемых форматов для тестов"""
        self.supported_formats = {
            "archives": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "tbz2", "txz", "tar.gz", "tar.bz2", "tar.xz"]
        }
    
    def test_zip_formats(self):
        """Тест ZIP форматов"""
        supported_formats = {
            "archives": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "tbz2", "txz", "tar.gz", "tar.bz2", "tar.xz"]
        }
        assert is_archive_format("test.zip", supported_formats) == True
        assert is_archive_format("archive.ZIP", supported_formats) == True
    
    def test_tar_formats(self):
        """Тест TAR форматов"""
        supported_formats = {
            "archives": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "tbz2", "txz", "tar.gz", "tar.bz2", "tar.xz"]
        }
        assert is_archive_format("backup.tar", supported_formats) == True
        assert is_archive_format("data.tar.gz", supported_formats) == True
        assert is_archive_format("archive.tar.bz2", supported_formats) == True
        assert is_archive_format("backup.tar.xz", supported_formats) == True
        assert is_archive_format("file.tgz", supported_formats) == True
        assert is_archive_format("data.tbz2", supported_formats) == True
        assert is_archive_format("archive.txz", supported_formats) == True
    
    def test_other_formats(self):
        """Тест других архивных форматов"""
        supported_formats = {
            "archives": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "tbz2", "txz", "tar.gz", "tar.bz2", "tar.xz"]
        }
        assert is_archive_format("archive.rar", supported_formats) == True
        assert is_archive_format("backup.7z", supported_formats) == True
        assert is_archive_format("file.gz", supported_formats) == True
        assert is_archive_format("data.bz2", supported_formats) == True
        assert is_archive_format("archive.xz", supported_formats) == True
    
    def test_non_archive_formats(self):
        """Тест не архивных форматов"""
        supported_formats = {
            "archives": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "tbz2", "txz", "tar.gz", "tar.bz2", "tar.xz"]
        }
        assert is_archive_format("document.pdf", supported_formats) == False
        assert is_archive_format("image.jpg", supported_formats) == False
        assert is_archive_format("text.txt", supported_formats) == False
        assert is_archive_format("script.py", supported_formats) == False
        assert is_archive_format("data.json", supported_formats) == False
    
    def test_edge_cases(self):
        """Тест граничных случаев"""
        supported_formats = {
            "archives": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "tbz2", "txz", "tar.gz", "tar.bz2", "tar.xz"]
        }
        assert is_archive_format("", supported_formats) == False
        assert is_archive_format("file_without_extension", supported_formats) == False
        assert is_archive_format(".zip", supported_formats) == True  # Скрытый архив


@pytest.mark.unit
class TestSanitizeFilename:
    """Тесты для функции sanitize_filename"""
    
    def test_normal_filename(self):
        """Тест нормального имени файла"""
        assert sanitize_filename("document.pdf") == "document.pdf"
        assert sanitize_filename("image.jpg") == "image.jpg"
        assert sanitize_filename("data_file.txt") == "data_file.txt"
    
    def test_path_traversal_attack(self):
        """Тест защиты от path traversal атак"""
        assert sanitize_filename("../../../etc/passwd") == "etc_passwd"
        assert sanitize_filename("..\\..\\windows\\system32\\config") == "windows_system32_config"
        assert sanitize_filename("./malicious.exe") == "malicious.exe"
    
    def test_special_characters(self):
        """Тест специальных символов"""
        assert sanitize_filename("file<>name.txt") == "filename.txt"
        assert sanitize_filename("file|name.txt") == "filename.txt"
        assert sanitize_filename("file?name.txt") == "filename.txt"
        assert sanitize_filename("file*name.txt") == "filename.txt"
        assert sanitize_filename("file:name.txt") == "filename.txt"
        assert sanitize_filename('file"name.txt') == "filename.txt"
    
    def test_unicode_characters(self):
        """Тест Unicode символов"""
        assert sanitize_filename("документ.pdf") == "документ.pdf"
        assert sanitize_filename("файл с пробелами.txt") == "файл с пробелами.txt"
        assert sanitize_filename("测试文件.doc") == "测试文件.doc"
    
    def test_empty_and_special_names(self):
        """Тест пустых и специальных имен"""
        assert sanitize_filename("") == "unknown_file"
        assert sanitize_filename("...") == "unknown_file"
        assert sanitize_filename("   ") == "unknown_file"
        assert sanitize_filename("CON") == "CON_file"  # Зарезервированное имя Windows
        assert sanitize_filename("PRN") == "PRN_file"
        assert sanitize_filename("AUX") == "AUX_file"
    
    def test_long_filename(self):
        """Тест длинного имени файла"""
        long_name = "a" * 300 + ".txt"
        result = sanitize_filename(long_name)
        assert len(result) <= 255  # Максимальная длина имени файла
        assert result.endswith(".txt")
    
    def test_none_filename(self):
        """Тест None в качестве имени файла"""
        assert sanitize_filename(None) == "unknown_file"


@pytest.mark.unit
class TestValidateFileType:
    """Тесты для функции validate_file_type"""
    
    def test_valid_text_file(self):
        """Тест валидного текстового файла"""
        content = b"This is a text file content"
        is_valid, error = validate_file_type(content, "test.txt")
        assert is_valid == True
        assert error is None
    
    def test_valid_pdf_file(self):
        """Тест валидного PDF файла"""
        # PDF файл начинается с %PDF
        content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog"
        is_valid, error = validate_file_type(content, "test.pdf")
        assert is_valid == True
        assert error is None
    
    def test_valid_json_file(self):
        """Тест валидного JSON файла"""
        content = b'{"key": "value", "number": 42}'
        is_valid, error = validate_file_type(content, "test.json")
        assert is_valid == True
        assert error is None
    
    def test_invalid_extension_mismatch(self):
        """Тест несоответствия расширения и содержимого"""
        # PDF содержимое с расширением .txt
        content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog"
        is_valid, error = validate_file_type(content, "test.txt")
        assert is_valid == False
        assert "not match" in error.lower()
    
    def test_unknown_file_type(self):
        """Тест неизвестного типа файла"""
        content = b"some binary content"
        is_valid, error = validate_file_type(content, "test.unknown")
        assert is_valid == True  # Неизвестные типы пропускаем
        assert error is None
    
    def test_empty_content(self):
        """Тест пустого содержимого"""
        content = b""
        is_valid, error = validate_file_type(content, "test.txt")
        assert is_valid == True  # Пустые файлы допускаются
        assert error is None
    
    def test_binary_content_with_text_extension(self):
        """Тест бинарного содержимого с текстовым расширением"""
        content = b"\x00\x01\x02\x03\x04\x05\x06\x07"
        is_valid, error = validate_file_type(content, "test.txt")
        assert is_valid == False
        assert error is not None
    
    @patch('app.utils.magic')
    def test_magic_library_not_available(self, mock_magic):
        """Тест когда библиотека magic недоступна"""
        mock_magic.side_effect = ImportError("No module named 'magic'")
        
        content = b"test content"
        is_valid, error = validate_file_type(content, "test.txt")
        assert is_valid == True  # Если magic недоступна, пропускаем проверку
        assert error is None


@pytest.mark.unit
class TestSetupLogging:
    """Тесты для функции setup_logging"""
    
    @patch('app.utils.structlog')
    def test_setup_logging_calls(self, mock_structlog):
        """Тест вызова настройки логирования"""
        setup_logging()
        
        # Проверяем, что structlog настраивается
        mock_structlog.configure.assert_called_once()
    
    @patch('app.utils.logging')
    def test_logging_level_setup(self, mock_logging):
        """Тест установки уровня логирования"""
        setup_logging()
        
        # Проверяем, что уровень логирования устанавливается
        mock_logging.basicConfig.assert_called_once()
    
    def test_setup_logging_no_exception(self):
        """Тест, что настройка логирования не выбрасывает исключений"""
        try:
            setup_logging()
        except Exception as e:
            pytest.fail(f"setup_logging raised an exception: {e}")
    
    def test_setup_logging_multiple_calls(self):
        """Тест множественных вызовов настройки логирования"""
        # Должно работать без ошибок при повторных вызовах
        setup_logging()
        setup_logging()
        setup_logging()
    
    @patch('app.utils.os.environ.get')
    def test_setup_logging_with_debug_env(self, mock_env_get):
        """Тест настройки логирования с переменной окружения DEBUG"""
        mock_env_get.return_value = "true"
        
        try:
            setup_logging()
        except Exception as e:
            pytest.fail(f"setup_logging with DEBUG env raised an exception: {e}") 