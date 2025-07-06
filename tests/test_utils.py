"""
Unit тесты для модуля утилит
"""
import pytest
from unittest.mock import patch, Mock
import logging
import sys
from pathlib import Path

from app.utils import (
    get_file_extension, 
    sanitize_filename, 
    is_supported_format, 
    is_archive_format,
    safe_filename,
    validate_file_type,
    setup_logging
)


@pytest.mark.unit
class TestGetFileExtension:
    """Тесты для функции get_file_extension"""
    
    def test_simple_extension(self):
        """Тест простого расширения"""
        assert get_file_extension("document.pdf") == "pdf"
        assert get_file_extension("image.jpg") == "jpg"
        assert get_file_extension("data.csv") == "csv"
    
    def test_compound_extension(self):
        """Тест составного расширения"""
        assert get_file_extension("archive.tar.gz") == "tar.gz"
        assert get_file_extension("backup.tar.bz2") == "tar.bz2"
        assert get_file_extension("data.tar.xz") == "tar.xz"
        assert get_file_extension("file.tgz") == "tar.gz"
        assert get_file_extension("file.tbz2") == "tar.bz2"
        assert get_file_extension("file.txz") == "tar.xz"
    
    def test_multiple_dots(self):
        """Тест файлов с несколькими точками"""
        assert get_file_extension("file.name.txt") == "txt"
        assert get_file_extension("data.backup.json") == "json"
    
    def test_uppercase_extension(self):
        """Тест расширения в верхнем регистре"""
        assert get_file_extension("document.PDF") == "pdf"
        assert get_file_extension("IMAGE.JPG") == "jpg"
    
    def test_no_extension(self):
        """Тест файлов без расширения"""
        assert get_file_extension("README") is None
        assert get_file_extension("Makefile") is None
        assert get_file_extension("file_no_ext") is None
    
    def test_empty_filename(self):
        """Тест пустого имени файла"""
        assert get_file_extension("") is None
        assert get_file_extension("   ") is None
    
    def test_hidden_file(self):
        """Тест скрытого файла"""
        assert get_file_extension(".gitignore") == "gitignore"
        assert get_file_extension(".env") == "env"
        assert get_file_extension(".config.json") == "json"


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
        # werkzeug.secure_filename убирает пути и специальные символы
        assert sanitize_filename("../../../etc/passwd") == "etc_passwd"
        assert sanitize_filename("..\\..\\windows\\system32\\config") == "windowssystem32config"
        assert sanitize_filename("./malicious.exe") == "malicious.exe"
    
    def test_unicode_characters(self):
        """Тест обработки Unicode символов"""
        # Проверяем реальное поведение с Unicode
        result = sanitize_filename("файл_с_русскими_символами.txt")
        # werkzeug.secure_filename может обрабатывать Unicode по-разному
        assert result is not None
        assert len(result) > 0
    
    def test_empty_filename(self):
        """Тест обработки пустого имени файла"""
        assert sanitize_filename("") == "unknown_file"
        assert sanitize_filename("   ") == "sanitized_file"  # werkzeug.secure_filename удаляет пробелы
    
    def test_filename_with_slashes(self):
        """Тест обработки имен файлов со слешами"""
        # werkzeug.secure_filename по-разному обрабатывает прямые и обратные слеши
        assert sanitize_filename("path/to/file.txt") == "path_to_file.txt"
        assert sanitize_filename("path\\to\\file.txt") == "pathtofile.txt"
    
    def test_filename_with_special_chars(self):
        """Тест обработки специальных символов"""
        # werkzeug.secure_filename удаляет опасные символы
        result = sanitize_filename("file<>|.txt")
        assert result is not None
        # Проверяем, что опасные символы удалены
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result


@pytest.mark.unit
class TestValidateFileType:
    """Тесты для функции validate_file_type"""
    
    def test_valid_pdf_file(self):
        """Тест валидного PDF файла"""
        # Простой PDF заголовок
        pdf_content = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'
        
        with patch('app.utils.magic.from_buffer', return_value='application/pdf'):
            is_valid, error = validate_file_type(pdf_content, "document.pdf")
            assert is_valid is True
            assert error is None
    
    def test_invalid_extension_mismatch(self):
        """Тест несоответствия расширения содержимому"""
        # Текстовый контент с PDF расширением
        text_content = b'This is plain text, not PDF'
        
        with patch('app.utils.magic.from_buffer', return_value='text/plain'):
            is_valid, error = validate_file_type(text_content, "document.pdf")
            assert is_valid is False
            assert error is not None
            assert "не соответствует" in error
    
    def test_text_file_valid(self):
        """Тест валидного текстового файла"""
        text_content = b'This is a text file'
        
        with patch('app.utils.magic.from_buffer', return_value='text/plain'):
            is_valid, error = validate_file_type(text_content, "file.txt")
            assert is_valid is True
            assert error is None
    
    def test_source_code_file_valid(self):
        """Тест валидного файла исходного кода"""
        python_content = b'print("Hello, World!")'
        
        with patch('app.utils.magic.from_buffer', return_value='text/plain'):
            is_valid, error = validate_file_type(python_content, "script.py")
            assert is_valid is True
            assert error is None
    
    def test_empty_content(self):
        """Тест пустого содержимого"""
        is_valid, error = validate_file_type(b'', "file.txt")
        assert is_valid is False
        assert error is not None
        assert "отсутствуют" in error
    
    def test_empty_filename(self):
        """Тест пустого имени файла"""
        is_valid, error = validate_file_type(b'content', "")
        assert is_valid is False
        assert error is not None
        assert "отсутствуют" in error
    
    def test_no_extension(self):
        """Тест файла без расширения"""
        is_valid, error = validate_file_type(b'content', "README")
        assert is_valid is False
        assert error is not None
        assert "расширение" in error
    
    def test_magic_library_not_available(self):
        """Тест когда magic library недоступна"""
        with patch('app.utils.magic.from_buffer', side_effect=Exception("Magic not available")):
            is_valid, error = validate_file_type(b'content', "file.txt")
            assert is_valid is False  # Fail-closed стратегия при ошибке
            assert "Не удалось определить тип файла" in error


@pytest.mark.unit
class TestSetupLogging:
    """Тесты для функции setup_logging"""
    
    def test_setup_logging_calls(self):
        """Тест вызова setup_logging"""
        with patch('logging.getLogger') as mock_get_logger:
            with patch('logging.StreamHandler') as mock_stream_handler:
                with patch('logging.Formatter') as mock_formatter:
                    mock_root_logger = Mock()
                    mock_uvicorn_logger = Mock()
                    mock_get_logger.side_effect = [mock_root_logger, mock_uvicorn_logger]
                    
                    setup_logging()
                    
                    # Проверяем что логгеры настроены
                    mock_root_logger.setLevel.assert_called_with(logging.INFO)
                    mock_uvicorn_logger.setLevel.assert_called_with(logging.INFO)
                    assert mock_uvicorn_logger.propagate is False
    
    def test_logging_level_setup(self):
        """Тест настройки уровней логирования"""
        with patch('logging.getLogger') as mock_get_logger:
            with patch('logging.StreamHandler'):
                with patch('logging.Formatter'):
                    mock_root_logger = Mock()
                    mock_uvicorn_logger = Mock()
                    mock_get_logger.side_effect = [mock_root_logger, mock_uvicorn_logger]
                    
                    setup_logging()
                    
                    # Проверяем уровни логирования
                    mock_root_logger.setLevel.assert_called_with(logging.INFO)
                    mock_uvicorn_logger.setLevel.assert_called_with(logging.INFO)


@pytest.mark.unit
class TestFormatSupportFunctions:
    """Тесты для функций проверки поддержки форматов"""
    
    def test_is_supported_format(self):
        """Тест проверки поддержки формата"""
        supported_formats = {
            "text": ["txt", "md"],
            "pdf": ["pdf"],
            "archives": ["zip", "tar"]
        }
        
        assert is_supported_format("document.pdf", supported_formats) is True
        assert is_supported_format("readme.txt", supported_formats) is True
        assert is_supported_format("archive.zip", supported_formats) is True
        assert is_supported_format("unknown.xyz", supported_formats) is False
    
    def test_is_archive_format(self):
        """Тест проверки архивного формата"""
        supported_formats = {
            "text": ["txt", "md"],
            "pdf": ["pdf"],
            "archives": ["zip", "tar", "gz"]
        }
        
        assert is_archive_format("archive.zip", supported_formats) is True
        assert is_archive_format("backup.tar", supported_formats) is True
        assert is_archive_format("data.gz", supported_formats) is True
        assert is_archive_format("document.pdf", supported_formats) is False
        assert is_archive_format("readme.txt", supported_formats) is False
    
    def test_safe_filename(self):
        """Тест безопасного имени файла"""
        assert safe_filename("document.pdf") == "document.pdf"
        assert safe_filename("file with spaces.txt") == "file_with_spaces.txt"
        assert safe_filename("file@#$%^&*()name.txt") == "file_________name.txt"
        assert safe_filename("") == "unknown_file"
        # Проверяем реальное поведение с кириллицей
        result = safe_filename("файл.txt")
        assert result is not None
        assert len(result) > 0 