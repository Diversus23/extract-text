"""Тесты для модуля конфигурации."""

import os
from unittest.mock import patch

import pytest

from app.config import Settings


@pytest.mark.unit
class TestSettings:
    """Тесты для класса Settings."""

    @patch.dict(os.environ, {}, clear=True)
    def test_default_settings(self):
        """Тест настроек по умолчанию (без переменных окружения)."""
        # Перезагружаем модуль для учета очищенных переменных окружения
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()

        assert settings.VERSION == "1.13.1"
        assert settings.API_PORT == 7555
        assert settings.MAX_FILE_SIZE == 20971520  # 20MB
        assert settings.PROCESSING_TIMEOUT_SECONDS == 300
        assert settings.OCR_LANGUAGES == "rus+eng"
        assert settings.WORKERS == 1  # Значение по умолчанию из config.py
        assert settings.MAX_ARCHIVE_SIZE == 20971520
        assert settings.MAX_EXTRACTED_SIZE == 104857600  # 100MB
        assert settings.MAX_ARCHIVE_NESTING == 3

    def test_supported_formats_structure(self):
        """Тест структуры поддерживаемых форматов."""
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
        """Тест содержимого поддерживаемых форматов."""
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
        assert "os" in formats["source_code"]  # OneScript
        assert "zip" in formats["archives"]
        assert "txt" in formats["other"]
        assert "html" in formats["other"]

    @patch.dict(os.environ, {"API_PORT": "8080"})
    def test_environment_variable_override(self):
        """Тест переопределения настроек через переменные окружения."""
        # Перезагружаем модуль для учета новых переменных окружения
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.API_PORT == 8080

    @patch.dict(os.environ, {"OCR_LANGUAGES": "eng+rus+deu"})
    def test_ocr_languages_override(self):
        """Тест переопределения языков OCR."""
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.OCR_LANGUAGES == "eng+rus+deu"

    @patch.dict(os.environ, {"WORKERS": "4"})
    def test_workers_override(self):
        """Тест переопределения количества workers."""
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.WORKERS == 4

    @patch.dict(os.environ, {"MAX_FILE_SIZE": "52428800"})  # 50MB
    def test_max_file_size_override(self):
        """Тест переопределения максимального размера файла."""
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.MAX_FILE_SIZE == 52428800

    @patch.dict(os.environ, {"PROCESSING_TIMEOUT_SECONDS": "600"})
    def test_timeout_override(self):
        """Тест переопределения таймаута обработки."""
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.PROCESSING_TIMEOUT_SECONDS == 600

    @patch.dict(os.environ, {"MAX_ARCHIVE_SIZE": "10485760"})  # 10MB
    def test_max_archive_size_override(self):
        """Тест переопределения максимального размера архива."""
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.MAX_ARCHIVE_SIZE == 10485760

    @patch.dict(os.environ, {"MAX_EXTRACTED_SIZE": "52428800"})  # 50MB
    def test_max_extracted_size_override(self):
        """Тест переопределения максимального размера распакованного архива."""
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.MAX_EXTRACTED_SIZE == 52428800

    @patch.dict(os.environ, {"MAX_ARCHIVE_NESTING": "5"})
    def test_max_archive_nesting_override(self):
        """Тест переопределения максимальной глубины вложенности архивов."""
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.MAX_ARCHIVE_NESTING == 5

    def test_all_formats_are_lowercase(self):
        """Тест, что все форматы записаны в нижнем регистре."""
        settings = Settings()

        for category, formats in settings.SUPPORTED_FORMATS.items():
            for format_ext in formats:
                assert (
                    format_ext.islower()
                ), f"Формат {format_ext} в категории {category} не в нижнем регистре"

    def test_no_duplicate_formats(self):
        """Тест, что нет дублирующихся форматов в разных категориях."""
        settings = Settings()
        all_formats = []

        for _category, formats in settings.SUPPORTED_FORMATS.items():
            all_formats.extend(formats)

        # Проверяем, что нет дубликатов
        assert len(all_formats) == len(
            set(all_formats)
        ), "Найдены дублирующиеся форматы"

    @patch.dict(os.environ, {}, clear=True)
    def test_web_extractor_default_settings(self):
        """Тест настроек веб-экстрактора по умолчанию."""
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()

        # Настройки v1.10.0
        assert settings.MIN_IMAGE_SIZE_FOR_OCR == 22500
        assert settings.MAX_IMAGES_PER_PAGE == 20
        assert settings.WEB_PAGE_TIMEOUT == 30
        assert settings.IMAGE_DOWNLOAD_TIMEOUT == 15
        assert settings.DEFAULT_USER_AGENT == "Text Extraction Bot 1.0"
        assert settings.ENABLE_JAVASCRIPT is False

        # Настройки v1.10.1 (Playwright)
        assert settings.ENABLE_BASE64_IMAGES is True
        assert settings.WEB_PAGE_DELAY == 3
        assert settings.ENABLE_LAZY_LOADING_WAIT is True
        assert settings.JS_RENDER_TIMEOUT == 10
        assert settings.MAX_SCROLL_ATTEMPTS == 3

    @patch.dict(
        os.environ,
        {
            "ENABLE_JAVASCRIPT": "true",
            "ENABLE_BASE64_IMAGES": "false",
            "WEB_PAGE_DELAY": "5",
            "JS_RENDER_TIMEOUT": "15",
            "MAX_SCROLL_ATTEMPTS": "5",
        },
    )
    def test_web_extractor_settings_override(self):
        """Тест переопределения настроек веб-экстрактора."""
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()

        assert settings.ENABLE_JAVASCRIPT is True
        assert settings.ENABLE_BASE64_IMAGES is False
        assert settings.WEB_PAGE_DELAY == 5
        assert settings.JS_RENDER_TIMEOUT == 15
        assert settings.MAX_SCROLL_ATTEMPTS == 5

    @patch.dict(os.environ, {"MIN_IMAGE_SIZE_FOR_OCR": "10000"})
    def test_min_image_size_override(self):
        """Тест переопределения минимального размера изображения для OCR."""
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.MIN_IMAGE_SIZE_FOR_OCR == 10000


@pytest.mark.unit
class TestTranscriptionSettings:
    """Тесты настроек транскрибации аудио."""

    @patch.dict(os.environ, {}, clear=True)
    def test_transcription_defaults(self):
        """Значения по умолчанию для транскрибации."""
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()

        assert settings.AUDIO_FORMATS == [
            "mp3",
            "wav",
            "ogg",
            "opus",
            "flac",
            "m4a",
            "aac",
            "wma",
            "amr",
        ]
        assert settings.ENABLE_TRANSCRIPTION is True
        assert settings.TRANSCRIPTION_MODEL == "gigaam-v3-e2e-rnnt"
        assert settings.TRANSCRIPTION_QUANTIZATION == ""
        assert settings.MODELS_DIR == "/opt/models"
        assert settings.MAX_AUDIO_DURATION_SECONDS == 1800
        assert settings.TRANSCRIPTION_TIMEOUT_SECONDS == 900
        assert settings.TRANSCRIPTION_MAX_CONCURRENCY == 1
        assert settings.TRANSCRIPTION_QUEUE_WAIT_SECONDS == 30
        assert settings.TRANSCRIPTION_THREADS == (os.cpu_count() or 1)
        assert settings.TRANSCRIPTION_VAD_MIN_SILENCE_MS == 500
        assert settings.TRANSCRIPTION_VAD_SPEECH_PAD_MS == 300

    @patch.dict(
        os.environ,
        {
            "MAX_AUDIO_DURATION_SECONDS": "60",
            "ENABLE_TRANSCRIPTION": "false",
            "TRANSCRIPTION_MAX_CONCURRENCY": "2",
            "TRANSCRIPTION_QUANTIZATION": "int8",
        },
    )
    def test_transcription_env_overrides(self):
        """Переопределение настроек транскрибации через окружение."""
        import importlib

        from app import config

        importlib.reload(config)
        settings = config.Settings()

        assert settings.MAX_AUDIO_DURATION_SECONDS == 60
        assert settings.ENABLE_TRANSCRIPTION is False
        assert settings.TRANSCRIPTION_MAX_CONCURRENCY == 2
        assert settings.TRANSCRIPTION_QUANTIZATION == "int8"

    @pytest.mark.parametrize(
        ("env", "expected"),
        [
            ({"TRANSCRIPTION_THREADS": "3"}, 3),
            ({"TRANSCRIPTION_THREADS": "3", "AUDIO_CPUS": "8"}, 3),
            ({"AUDIO_CPUS": "6"}, 6),
            ({"AUDIO_CPUS": "2.5"}, 2),
            ({"AUDIO_CPUS": "0.5"}, 1),
            ({"TRANSCRIPTION_THREADS": "", "AUDIO_CPUS": "6"}, 6),
        ],
    )
    def test_transcription_threads_fall_back_to_audio_cpus(self, env, expected):
        """Потоки: TRANSCRIPTION_THREADS, иначе лимит CPU api-audio (AUDIO_CPUS)."""
        import importlib

        from app import config

        with patch.dict(os.environ, env, clear=True):
            importlib.reload(config)
            assert config.Settings().TRANSCRIPTION_THREADS == expected

    @patch.dict(os.environ, {}, clear=True)
    def test_transcription_upstream_url_is_empty_by_default(self):
        """Без адреса api-audio проксирование выключено."""
        import importlib

        from app import config

        importlib.reload(config)

        assert config.Settings().TRANSCRIPTION_UPSTREAM_URL == ""

    @patch.dict(os.environ, {"TRANSCRIPTION_UPSTREAM_URL": " http://api-audio:7556/ "})
    def test_transcription_upstream_url_is_normalized(self):
        """Пробелы и завершающий слэш убираются, чтобы путь склеивался корректно."""
        import importlib

        from app import config

        importlib.reload(config)

        assert config.Settings().TRANSCRIPTION_UPSTREAM_URL == "http://api-audio:7556"

    def test_audio_formats_not_in_supported_formats(self):
        """Аудио-расширения не должны попадать в SUPPORTED_FORMATS."""
        settings = Settings()
        supported = set(sum(settings.SUPPORTED_FORMATS.values(), []))

        assert set(settings.AUDIO_FORMATS).isdisjoint(supported)
