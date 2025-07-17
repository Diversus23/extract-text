"""
Тесты для модуля конфигурации
"""
import pytest
import os
from unittest.mock import patch

from app.config import Settings


@pytest.mark.unit
class TestSettings:
    """Тесты для класса Settings"""
    
    @patch.dict(os.environ, {}, clear=True)
    def test_default_settings(self):
        """Тест настроек по умолчанию (без переменных окружения)"""
        # Перезагружаем модуль для учета очищенных переменных окружения
        import importlib
        from app import config
        importlib.reload(config)
        settings = config.Settings()
        
        assert settings.VERSION == "1.8.8"
        assert settings.API_PORT == 7555
        assert settings.MAX_FILE_SIZE == 20971520  # 20MB
        assert settings.PROCESSING_TIMEOUT_SECONDS == 300
        assert settings.OCR_LANGUAGES == "rus+eng"
        assert settings.WORKERS == 1  # Значение по умолчанию из config.py
        assert settings.MAX_ARCHIVE_SIZE == 20971520
        assert settings.MAX_EXTRACTED_SIZE == 104857600  # 100MB
        assert settings.MAX_ARCHIVE_NESTING == 3
    
    def test_supported_formats_structure(self):
        """Тест структуры поддерживаемых форматов"""
        settings = Settings()
        
        assert isinstance(settings.SUPPORTED_FORMATS, dict)
        assert "images_ocr" in settings.SUPPORTED_FORMATS
        assert "documents" in settings.SUPPORTED_FORMATS
        assert "spreadsheets" in settings.SUPPORTED_FORMATS
        assert "presentations" in settings.SUPPORTED_FORMATS
        assert "structured_data" in settings.SUPPORTED_FORMATS
        assert "source_code" in settings.SUPPORTED_FORMATS
        assert "other" in settings.SUPPORTED_FORMATS
        assert "archives" in settings.SUPPORTED_FORMATS
    
    def test_supported_formats_content(self):
        """Тест содержимого поддерживаемых форматов"""
        settings = Settings()
        formats = settings.SUPPORTED_FORMATS
        
        # Проверяем, что ключевые форматы присутствуют
        assert "pdf" in formats["documents"]
        assert "docx" in formats["documents"]
        assert "jpg" in formats["images_ocr"]
        assert "png" in formats["images_ocr"]
        assert "xlsx" in formats["spreadsheets"]
        assert "csv" in formats["spreadsheets"]
        assert "json" in formats["structured_data"]
        assert "xml" in formats["structured_data"]
        assert "py" in formats["source_code"]
        assert "js" in formats["source_code"]
        assert "bsl" in formats["source_code"]  # 1C:Enterprise
        assert "os" in formats["source_code"]   # OneScript
        assert "zip" in formats["archives"]
        assert "txt" in formats["other"]
        assert "html" in formats["other"]
    
    @patch.dict(os.environ, {"API_PORT": "8080"})
    def test_environment_variable_override(self):
        """Тест переопределения настроек через переменные окружения"""
        # Перезагружаем модуль для учета новых переменных окружения
        import importlib
        from app import config
        importlib.reload(config)
        settings = config.Settings()
        assert settings.API_PORT == 8080
    
    @patch.dict(os.environ, {"OCR_LANGUAGES": "eng+rus+deu"})
    def test_ocr_languages_override(self):
        """Тест переопределения языков OCR"""
        import importlib
        from app import config
        importlib.reload(config)
        settings = config.Settings()
        assert settings.OCR_LANGUAGES == "eng+rus+deu"
    
    @patch.dict(os.environ, {"WORKERS": "4"})
    def test_workers_override(self):
        """Тест переопределения количества workers"""
        import importlib
        from app import config
        importlib.reload(config)
        settings = config.Settings()
        assert settings.WORKERS == 4
    
    @patch.dict(os.environ, {"MAX_FILE_SIZE": "52428800"})  # 50MB
    def test_max_file_size_override(self):
        """Тест переопределения максимального размера файла"""
        import importlib
        from app import config
        importlib.reload(config)
        settings = config.Settings()
        assert settings.MAX_FILE_SIZE == 52428800
    
    @patch.dict(os.environ, {"PROCESSING_TIMEOUT_SECONDS": "600"})
    def test_timeout_override(self):
        """Тест переопределения таймаута обработки"""
        import importlib
        from app import config
        importlib.reload(config)
        settings = config.Settings()
        assert settings.PROCESSING_TIMEOUT_SECONDS == 600
    
    @patch.dict(os.environ, {"MAX_ARCHIVE_SIZE": "10485760"})  # 10MB
    def test_max_archive_size_override(self):
        """Тест переопределения максимального размера архива"""
        import importlib
        from app import config
        importlib.reload(config)
        settings = config.Settings()
        assert settings.MAX_ARCHIVE_SIZE == 10485760
    
    @patch.dict(os.environ, {"MAX_EXTRACTED_SIZE": "52428800"})  # 50MB
    def test_max_extracted_size_override(self):
        """Тест переопределения максимального размера распакованного архива"""
        import importlib
        from app import config
        importlib.reload(config)
        settings = config.Settings()
        assert settings.MAX_EXTRACTED_SIZE == 52428800
    
    @patch.dict(os.environ, {"MAX_ARCHIVE_NESTING": "5"})
    def test_max_archive_nesting_override(self):
        """Тест переопределения максимальной глубины вложенности архивов"""
        import importlib
        from app import config
        importlib.reload(config)
        settings = config.Settings()
        assert settings.MAX_ARCHIVE_NESTING == 5
    
    def test_all_formats_are_lowercase(self):
        """Тест, что все форматы записаны в нижнем регистре"""
        settings = Settings()
        
        for category, formats in settings.SUPPORTED_FORMATS.items():
            for format_ext in formats:
                assert format_ext.islower(), f"Формат {format_ext} в категории {category} не в нижнем регистре"
    
    def test_no_duplicate_formats(self):
        """Тест, что нет дублирующихся форматов в разных категориях"""
        settings = Settings()
        all_formats = []
        
        for category, formats in settings.SUPPORTED_FORMATS.items():
            all_formats.extend(formats)
        
        # Проверяем, что нет дубликатов
        assert len(all_formats) == len(set(all_formats)), "Найдены дублирующиеся форматы" 