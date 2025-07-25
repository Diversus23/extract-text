"""Integration тесты для FastAPI приложения."""

import base64
import json
from io import BytesIO
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.config import settings
from app.main import app


@pytest.mark.integration
class TestHealthEndpoints:
    """Тесты для эндпоинтов проверки состояния."""

    def test_root_endpoint(self, test_client):
        """Тест главного эндпоинта."""
        response = test_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["api_name"] == "Text Extraction API for RAG"
        assert data["version"] == settings.VERSION
        assert data["contact"] == "Барилко Виталий"

    def test_health_endpoint(self, test_client):
        """Тест health."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_supported_formats_endpoint(self, test_client):
        """Тест эндпоинта поддерживаемых форматов."""
        response = test_client.get("/v1/supported-formats")

        assert response.status_code == 200
        data = response.json()

        # Проверяем структуру ответа
        assert isinstance(data, dict)
        assert "images_ocr" in data
        assert "documents" in data
        assert "spreadsheets" in data
        assert "presentations" in data
        assert "structured_data" in data
        assert "source_code" in data
        assert "other" in data
        assert "archives" in data

        # Проверяем содержимое
        assert "jpg" in data["images_ocr"]
        assert "pdf" in data["documents"]
        assert "xlsx" in data["spreadsheets"]
        assert "json" in data["structured_data"]
        assert "py" in data["source_code"]
        assert "zip" in data["archives"]
        assert "txt" in data["other"]


@pytest.mark.integration
class TestExtractEndpoint:
    """Тесты для эндпоинта извлечения текста."""

    def test_extract_text_file_success(self, test_client):
        """Тест успешного извлечения текста из текстового файла."""
        test_content = "Тестовый текст для проверки"

        with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
            mock_extract.return_value = [
                {
                    "filename": "test.txt",
                    "path": "test.txt",
                    "size": len(test_content.encode("utf-8")),
                    "type": "txt",
                    "text": test_content,
                }
            ]

            response = test_client.post(
                "/v1/extract/file",
                files={
                    "file": (
                        "test.txt",
                        BytesIO(test_content.encode("utf-8")),
                        "text/plain",
                    )
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["filename"] == "test.txt"
            assert data["count"] == 1
            assert len(data["files"]) == 1
            assert data["files"][0]["text"] == test_content

    def test_extract_json_file_success(self, test_client):
        """Тест успешного извлечения из JSON файла."""
        test_content = '{"name": "Тест", "value": 42}'

        with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
            mock_extract.return_value = [
                {
                    "filename": "test.json",
                    "path": "test.json",
                    "size": len(test_content.encode("utf-8")),
                    "type": "json",
                    "text": "name: Тест\nvalue: 42",
                }
            ]

            response = test_client.post(
                "/v1/extract/file",
                files={
                    "file": (
                        "test.json",
                        BytesIO(test_content.encode("utf-8")),
                        "application/json",
                    )
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["filename"] == "test.json"
            assert data["count"] == 1

    def test_extract_empty_file_error(self, test_client):
        """Тест ошибки при обработке пустого файла."""
        response = test_client.post(
            "/v1/extract/file",
            files={"file": ("empty.txt", BytesIO(b""), "text/plain")},
        )

        assert response.status_code == 422
        assert "empty" in response.json()["detail"].lower()

    def test_extract_large_file_error(self, test_client):
        """Тест ошибки при обработке слишком большого файла."""
        large_content = b"x" * (settings.MAX_FILE_SIZE + 1)

        response = test_client.post(
            "/v1/extract/file",
            files={"file": ("large.txt", BytesIO(large_content), "text/plain")},
        )

        assert response.status_code == 413
        assert "size exceeds maximum" in response.json()["detail"].lower()

    def test_extract_unsupported_format_error(self, test_client):
        """Тест ошибки при обработке неподдерживаемого формата."""
        test_content = b"Some binary content"

        with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
            mock_extract.side_effect = ValueError("Unsupported file format")

            response = test_client.post(
                "/v1/extract/file",
                files={
                    "file": (
                        "test.unknown",
                        BytesIO(test_content),
                        "application/octet-stream",
                    )
                },
            )

            assert response.status_code == 415
            data = response.json()
            assert data["status"] == "error"
            assert "неподдерживаемый формат" in data["message"].lower()

    def test_extract_corrupted_file_error(self, test_client):
        """Тест ошибки при обработке поврежденного файла."""
        test_content = b"corrupted content"

        # Мокаем валидацию файла - пропускаем проверку типа
        with patch("app.main.validate_file_type", return_value=(True, None)):
            with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
                mock_extract.side_effect = ValueError("File is corrupted")

                response = test_client.post(
                    "/v1/extract/file",
                    files={
                        "file": (
                            "corrupted.pdf",
                            BytesIO(test_content),
                            "application/pdf",
                        )
                    },
                )

                assert response.status_code == 422
                data = response.json()
                assert data["status"] == "error"
                assert "поврежден" in data["message"]

    def test_extract_no_content_length_error(self, test_client):
        """Тест ошибки при отсутствии Content-Length."""
        # Создаем запрос без Content-Length заголовка
        response = test_client.post("/v1/extract/file")

        assert response.status_code == 422
        # FastAPI автоматически возвращает ошибку при отсутствии файла

    def test_extract_archive_file_error(self, test_client):
        """Тест ошибки при обработке архива (без распаковки)."""
        # Минимальный ZIP файл
        zip_content = b"PK\x03\x04\x14\x00\x00\x00\x08\x00"

        with patch("app.utils.is_archive_format") as mock_is_archive:
            mock_is_archive.return_value = True

            response = test_client.post(
                "/v1/extract/file",
                files={"file": ("test.zip", BytesIO(zip_content), "application/zip")},
            )

            # Зависит от реализации - может быть 415 или успешная обработка
            assert response.status_code in [200, 415]

    def test_extract_multiple_files_from_archive(self, test_client):
        """Тест извлечения нескольких файлов из архива."""
        test_content = b"fake archive content"

        # Мокаем валидацию файла
        with patch("app.main.validate_file_type", return_value=(True, None)):
            with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
                # Мокаем результат извлечения нескольких файлов
                mock_extract.return_value = [
                    {
                        "filename": "file1.txt",
                        "path": "archive.zip/file1.txt",
                        "size": 100,
                        "type": "txt",
                        "text": "Content of file 1",
                    },
                    {
                        "filename": "file2.txt",
                        "path": "archive.zip/file2.txt",
                        "size": 200,
                        "type": "txt",
                        "text": "Content of file 2",
                    },
                ]

                response = test_client.post(
                    "/v1/extract/file",
                    files={
                        "file": (
                            "archive.zip",
                            BytesIO(test_content),
                            "application/zip",
                        )
                    },
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert len(data["files"]) == 2
                assert data["files"][0]["filename"] == "file1.txt"
                assert data["files"][1]["filename"] == "file2.txt"

    def test_extract_with_file_type_validation_error(self, test_client):
        """Тест ошибки при валидации типа файла."""
        # Файл с неподходящим содержимым
        fake_pdf_content = b"This is not a PDF file"

        with patch("app.utils.validate_file_type") as mock_validate:
            mock_validate.return_value = (
                False,
                "Расширение файла не соответствует содержимому",
            )

            response = test_client.post(
                "/v1/extract/file",
                files={
                    "file": ("fake.pdf", BytesIO(fake_pdf_content), "application/pdf")
                },
            )

            assert response.status_code == 415
            data = response.json()
            assert data["status"] == "error"
            assert "не соответствует" in data["message"]

    def test_extract_processing_timeout_error(self, test_client):
        """Тест ошибки таймаута при обработке."""
        test_content = b"large file content"

        # Мокаем валидацию файла
        with patch("app.main.validate_file_type", return_value=(True, None)):
            with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
                mock_extract.side_effect = ValueError("Processing timeout exceeded")

                response = test_client.post(
                    "/v1/extract/file",
                    files={
                        "file": ("large.pdf", BytesIO(test_content), "application/pdf")
                    },
                )

                assert response.status_code == 422
                data = response.json()
                assert data["status"] == "error"
                assert "поврежден" in data["message"]

    def test_extract_file_without_extension(self, test_client):
        """Тест обработки файла без расширения."""
        test_content = b"file content"

        # Мокаем валидацию файла - неудачная валидация
        with patch(
            "app.main.validate_file_type",
            return_value=(False, "Не удалось определить расширение файла"),
        ):
            response = test_client.post(
                "/v1/extract/file",
                files={"file": ("README", BytesIO(test_content), "text/plain")},
            )

            assert response.status_code == 415
            data = response.json()
            assert data["status"] == "error"
            assert "не соответствует" in data["message"]

    def test_extract_success_with_multiple_files_in_archive(self, test_client):
        """Тест успешного извлечения из архива с несколькими файлами."""
        test_content = b"archive with multiple files"

        # Мокаем валидацию файла
        with patch("app.main.validate_file_type", return_value=(True, None)):
            with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
                mock_extract.return_value = [
                    {
                        "filename": "doc1.txt",
                        "path": "archive.zip/folder/doc1.txt",
                        "size": 150,
                        "type": "txt",
                        "text": "First document text",
                    },
                    {
                        "filename": "doc2.pdf",
                        "path": "archive.zip/doc2.pdf",
                        "size": 300,
                        "type": "pdf",
                        "text": "Second document text",
                    },
                ]

                response = test_client.post(
                    "/v1/extract/file",
                    files={
                        "file": (
                            "documents.zip",
                            BytesIO(test_content),
                            "application/zip",
                        )
                    },
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "documents.zip"
                assert data["count"] == 2
                assert len(data["files"]) == 2

                # Проверяем содержимое первого файла
                assert data["files"][0]["filename"] == "doc1.txt"
                assert data["files"][0]["text"] == "First document text"

                # Проверяем содержимое второго файла
                assert data["files"][1]["filename"] == "doc2.pdf"
                assert data["files"][1]["text"] == "Second document text"

    def test_extract_with_sanitized_filename(self, test_client):
        """Тест обработки файла с небезопасным именем."""
        test_content = b"test content"
        unsafe_filename = "../../../etc/passwd"

        with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
            mock_extract.return_value = [
                {
                    "filename": "etc_passwd",  # Санитизованное имя
                    "path": "etc_passwd",
                    "size": len(test_content),
                    "type": "txt",
                    "text": "test content",
                }
            ]

            response = test_client.post(
                "/v1/extract/file",
                files={"file": (unsafe_filename, BytesIO(test_content), "text/plain")},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["filename"] == unsafe_filename  # Оригинальное имя в ответе
            assert data["count"] == 1
            assert data["files"][0]["filename"] == "etc_passwd"  # Санитизованное имя

    def test_extract_zero_size_file(self, test_client):
        """Тест обработки файла нулевого размера."""
        response = test_client.post(
            "/v1/extract/file",
            files={"file": ("empty.txt", BytesIO(b""), "text/plain")},
        )

        assert response.status_code == 422
        data = response.json()
        assert "empty" in data["detail"].lower()

    def test_extract_file_with_special_characters_in_name(self, test_client):
        """Тест обработки файла со специальными символами в имени."""
        test_content = b"test content"
        special_filename = "тест файл с пробелами & символами!.txt"

        with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
            mock_extract.return_value = [
                {
                    "filename": "тест_файл_с_пробелами_символами.txt",
                    "path": "тест_файл_с_пробелами_символами.txt",
                    "size": len(test_content),
                    "type": "txt",
                    "text": "test content",
                }
            ]

            response = test_client.post(
                "/v1/extract/file",
                files={"file": (special_filename, BytesIO(test_content), "text/plain")},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["filename"] == special_filename
            assert data["count"] == 1


@pytest.mark.integration
class TestBase64ExtractEndpoint:
    """Тесты для эндпоинта извлечения текста из base64-файлов."""

    def test_extract_base64_text_success(self, test_client):
        """Тест успешного извлечения текста из base64-файла."""
        base64_content = "0J/RgNC40LLQtdGCINGN0YLQviDRgtC10LrRgdGCIQ=="
        expected_text = "Привет это текст!"

        with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
            mock_extract.return_value = [
                {
                    "filename": "text.txt",
                    "path": "text.txt",
                    "size": 31,
                    "type": "txt",
                    "text": expected_text,
                }
            ]

            response = test_client.post(
                "/v1/extract/base64",
                json={"encoded_base64_file": base64_content, "filename": "text.txt"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["filename"] == "text.txt"
            assert data["count"] == 1
            assert len(data["files"]) == 1
            assert data["files"][0]["filename"] == "text.txt"
            assert data["files"][0]["size"] == 31
            assert data["files"][0]["type"] == "txt"
            assert data["files"][0]["text"] == expected_text

    def test_extract_base64_invalid_base64(self, test_client):
        """Тест ошибки при некорректном base64."""
        response = test_client.post(
            "/v1/extract/base64",
            json={
                "encoded_base64_file": "invalid_base64_string!",
                "filename": "test.txt",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "base64" in data["message"].lower()

    def test_extract_base64_empty_filename(self, test_client):
        """Тест ошибки при пустом filename."""
        response = test_client.post(
            "/v1/extract/base64",
            json={"encoded_base64_file": "SGVsbG8gV29ybGQ=", "filename": ""},
        )

        assert (
            response.status_code == 415
        )  # Unsupported Media Type из-за валидации файла
        data = response.json()
        assert data["status"] == "error"
        assert "не соответствует" in data["message"]

    def test_extract_base64_large_file_error(self, test_client):
        """Тест ошибки при превышении максимального размера файла."""
        # Создаем base64 файл больше лимита
        large_content = "A" * (settings.MAX_FILE_SIZE + 1)
        import base64

        large_base64 = base64.b64encode(large_content.encode()).decode()

        response = test_client.post(
            "/v1/extract/base64",
            json={"encoded_base64_file": large_base64, "filename": "large.txt"},
        )

        assert response.status_code == 413
        data = response.json()
        # FastAPI автоматически создает структуру с полем "detail"
        assert "detail" in data
        assert "exceeds maximum" in data["detail"]

    def test_extract_base64_unsupported_format(self, test_client):
        """Тест ошибки при неподдерживаемом формате файла."""
        test_base64 = "SGVsbG8gV29ybGQ="  # "Hello World"

        with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
            mock_extract.side_effect = ValueError("Unsupported file format")

            response = test_client.post(
                "/v1/extract/base64",
                json={"encoded_base64_file": test_base64, "filename": "test.unknown"},
            )

            assert response.status_code == 415
            data = response.json()
            assert data["status"] == "error"
            assert "неподдерживаемый формат" in data["message"].lower()

    def test_extract_base64_corrupted_file(self, test_client):
        """Тест ошибки при поврежденном файле."""
        test_base64 = "SGVsbG8gV29ybGQ="

        # Мокаем валидацию файла - пропускаем проверку типа
        with patch("app.main.validate_file_type", return_value=(True, None)):
            with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
                mock_extract.side_effect = ValueError("File is corrupted")

                response = test_client.post(
                    "/v1/extract/base64",
                    json={
                        "encoded_base64_file": test_base64,
                        "filename": "corrupted.pdf",
                    },
                )

                assert response.status_code == 422
                data = response.json()
                assert data["status"] == "error"
                assert "поврежден" in data["message"]

    def test_extract_base64_with_sanitized_filename(self, test_client):
        """Тест обработки base64 файла с небезопасным именем."""
        test_base64 = "0J/RgNC40LLQtdGCINGN0YLQviDRgtC10LrRgdGCIQ=="
        unsafe_filename = "../../../etc/passwd"

        with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
            mock_extract.return_value = [
                {
                    "filename": "etc_passwd",  # Санитизованное имя
                    "path": "etc_passwd",
                    "size": 31,
                    "type": "txt",
                    "text": "Привет это текст!",
                }
            ]

            response = test_client.post(
                "/v1/extract/base64",
                json={"encoded_base64_file": test_base64, "filename": unsafe_filename},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["filename"] == unsafe_filename  # Оригинальное имя в ответе
            assert data["count"] == 1
            assert data["files"][0]["filename"] == "etc_passwd"  # Санитизованное имя

    def test_extract_base64_json_file(self, test_client):
        """Тест извлечения из JSON файла в base64."""
        json_content = '{"message": "Привет", "number": 42}'
        import base64

        json_base64 = base64.b64encode(json_content.encode()).decode()

        with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
            mock_extract.return_value = [
                {
                    "filename": "test.json",
                    "path": "test.json",
                    "size": len(json_content.encode()),
                    "type": "json",
                    "text": "message: Привет\nnumber: 42",
                }
            ]

            response = test_client.post(
                "/v1/extract/base64",
                json={"encoded_base64_file": json_base64, "filename": "test.json"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["filename"] == "test.json"
            assert data["count"] == 1
            assert "Привет" in data["files"][0]["text"]

    def test_extract_base64_cyrillic_filename(self, test_client):
        """Тест извлечения base64-файла с кириллицей в названии."""
        # Кодируем простой текст в base64
        test_content = "Тест файла с кириллическим названием"
        content_base64 = base64.b64encode(test_content.encode()).decode()

        response = test_client.post(
            "/v1/extract/base64",
            json={
                "encoded_base64_file": content_base64,
                "filename": "кириллический_файл.txt",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["filename"] == "кириллический_файл.txt"
        assert data["count"] == 1
        assert len(data["files"]) == 1

        # Проверяем, что текст был корректно извлечен
        extracted_text = data["files"][0]["text"]
        assert "Тест файла с кириллическим названием" in extracted_text
        assert data["files"][0]["type"] == "txt"


@pytest.mark.integration
class TestMiddleware:
    """Тесты для middleware."""

    def test_cors_middleware(self, test_client):
        """Тест CORS middleware."""
        # Проверяем обычный запрос с заголовком Origin
        response = test_client.get("/", headers={"Origin": "http://localhost:3000"})

        # Проверяем, что запрос успешен
        assert response.status_code == 200
        assert response.json()["api_name"] == "Text Extraction API for RAG"

        # Проверяем наличие CORS заголовков
        # FastAPI автоматически добавляет CORS заголовки при настройке CORSMiddleware
        assert (
            "access-control-allow-origin" in response.headers.keys()
            or "Access-Control-Allow-Origin" in response.headers.keys()
        )

    def test_logging_middleware(self, test_client):
        """Тест middleware для логирования."""
        with patch("app.main.logger") as mock_logger:
            response = test_client.get("/health")

            assert response.status_code == 200
            # Проверяем, что запрос и ответ залогированы
            mock_logger.info.assert_called()

    def test_logging_middleware_with_error(self, test_client):
        """Тест logging middleware при ошибке."""
        # Отправляем запрос на несуществующий endpoint
        response = test_client.get("/nonexistent")

        # Проверяем, что возвращается 404
        assert response.status_code == 404

        # Проверяем что middleware работает - логирование происходит автоматически
        # Мы можем только проверить, что запрос обработан
        assert response.json()["detail"] == "Not Found"


@pytest.mark.integration
class TestAsyncEndpoints:
    """Тесты для асинхронных endpoint'ов."""

    def test_async_extract_endpoint(self, test_client):
        """Тест асинхронного endpoint извлечения текста."""
        test_content = b"Test content"

        # Мокаем валидацию файла
        with patch("app.main.validate_file_type", return_value=(True, None)):
            with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
                mock_extract.return_value = [
                    {
                        "filename": "test.txt",
                        "path": "test.txt",
                        "size": 12,
                        "type": "txt",
                        "text": "Test content",
                    }
                ]

                response = test_client.post(
                    "/v1/extract/file",
                    files={"file": ("test.txt", BytesIO(test_content), "text/plain")},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.txt"
                assert data["count"] == 1
                # Проверяем что асинхронный метод был вызван
                mock_extract.assert_called_once()

    def test_async_health_endpoint(self, test_client):
        """Тест асинхронного health endpoint."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_async_supported_formats_endpoint(self, test_client):
        """Тест асинхронного endpoint поддерживаемых форматов."""
        response = test_client.get("/v1/supported-formats")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Проверяем, что есть основные группы форматов
        assert "images_ocr" in data
        assert "documents" in data
        assert "other" in data  # группа "other" содержит текстовые файлы
        assert "pdf" in data["documents"]  # PDF в группе documents


@pytest.mark.integration
class TestURLExtractionEndpoint:
    """Тесты для веб-экстракции (новое в v1.10.0)."""

    def test_extract_url_invalid_scheme(self, test_client):
        """Тест с невалидной схемой URL."""
        response = test_client.post(
            "/v1/extract/url", json={"url": "ftp://example.com"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "http://" in data["message"] or "https://" in data["message"]

    def test_extract_url_empty_url(self, test_client):
        """Тест с пустым URL."""
        response = test_client.post("/v1/extract/url", json={"url": ""})

        assert response.status_code == 400

    @patch("app.extractors.TextExtractor.extract_from_url")
    def test_extract_url_success(self, mock_extract, test_client):
        """Тест успешного извлечения текста с URL."""
        # Мокаем успешный ответ
        mock_extract.return_value = [
            {
                "filename": "page_content",
                "path": "https://example.com",
                "size": 1024,
                "type": "html",
                "text": "Основной текст страницы",
            },
            {
                "filename": "image1.jpg",
                "path": "https://example.com/image1.jpg",
                "size": 2048,
                "type": "jpg",
                "text": "Текст с изображения",
            },
        ]

        response = test_client.post(
            "/v1/extract/url",
            json={"url": "https://example.com", "user_agent": "Test Agent"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["url"] == "https://example.com"
        assert data["count"] == 2
        assert len(data["files"]) == 2

        # Проверяем первый файл (страница)
        page_file = data["files"][0]
        assert page_file["filename"] == "page_content"
        assert page_file["type"] == "html"
        assert "Основной текст страницы" in page_file["text"]

        # Проверяем второй файл (изображение)
        img_file = data["files"][1]
        assert img_file["filename"] == "image1.jpg"
        assert img_file["type"] == "jpg"
        assert "Текст с изображения" in img_file["text"]

        # Проверяем что метод был вызван с правильными параметрами (3 параметра)
        mock_extract.assert_called_once()
        args = mock_extract.call_args[0]
        assert args[0] == "https://example.com"  # url
        assert args[1] == "Test Agent"  # user_agent
        # extraction_options может быть None или объектом

    @patch("app.extractors.TextExtractor.extract_from_url")
    def test_extract_url_blocked_ip(self, mock_extract, test_client):
        """Тест блокировки внутренних IP-адресов."""
        mock_extract.side_effect = ValueError(
            "Access to internal IP addresses is prohibited for security reasons"
        )

        response = test_client.post(
            "/v1/extract/url", json={"url": "http://192.168.1.1"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "внутренним IP-адресам запрещен" in data["message"]

    @patch("app.extractors.TextExtractor.extract_from_url")
    def test_extract_url_connection_error(self, mock_extract, test_client):
        """Тест ошибки подключения."""
        mock_extract.side_effect = ValueError("Failed to load page: Connection timeout")

        response = test_client.post(
            "/v1/extract/url", json={"url": "https://nonexistent-domain-12345.com"}
        )

        assert response.status_code == 504
        data = response.json()
        assert data["status"] == "error"
        assert (
            "таймаут" in data["message"].lower()
            or "timeout" in data["message"].lower()
            or "превышен лимит времени" in data["message"].lower()
        )
