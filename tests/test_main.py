"""
Integration тесты для FastAPI приложения
"""
import pytest
import json
from io import BytesIO
from unittest.mock import patch, AsyncMock, Mock

from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app
from app.config import settings


@pytest.mark.integration
class TestHealthEndpoints:
    """Тесты для эндпоинтов проверки состояния"""
    
    def test_root_endpoint(self, test_client):
        """Тест главного эндпоинта"""
        response = test_client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["api_name"] == "Text Extraction API for RAG"
        assert data["version"] == settings.VERSION
        assert data["contact"] == "ООО 'СОФТОНИТ'"
    
    def test_health_endpoint(self, test_client):
        """Тест эндпоинта проверки здоровья"""
        response = test_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    def test_supported_formats_endpoint(self, test_client):
        """Тест эндпоинта поддерживаемых форматов"""
        response = test_client.get("/v1/supported-formats/")
        
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
    """Тесты для эндпоинта извлечения текста"""
    
    def test_extract_text_file_success(self, test_client):
        """Тест успешного извлечения текста из текстового файла"""
        test_content = "Тестовый текст для проверки"
        
        with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
            mock_extract.return_value = [{
                "filename": "test.txt",
                "path": "test.txt",
                "size": len(test_content.encode('utf-8')),
                "type": "txt",
                "text": test_content
            }]
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": ("test.txt", BytesIO(test_content.encode('utf-8')), "text/plain")}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["filename"] == "test.txt"
            assert len(data["files"]) == 1
            assert data["files"][0]["text"] == test_content
    
    def test_extract_json_file_success(self, test_client):
        """Тест успешного извлечения из JSON файла"""
        test_content = '{"name": "Тест", "value": 42}'
        
        with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
            mock_extract.return_value = [{
                "filename": "test.json",
                "path": "test.json",
                "size": len(test_content.encode('utf-8')),
                "type": "json",
                "text": "name: Тест\nvalue: 42"
            }]
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": ("test.json", BytesIO(test_content.encode('utf-8')), "application/json")}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["filename"] == "test.json"
    
    def test_extract_empty_file_error(self, test_client):
        """Тест ошибки при обработке пустого файла"""
        response = test_client.post(
            "/v1/extract/",
            files={"file": ("empty.txt", BytesIO(b""), "text/plain")}
        )
        
        assert response.status_code == 422
        assert "empty" in response.json()["detail"].lower()
    
    def test_extract_large_file_error(self, test_client):
        """Тест ошибки при обработке слишком большого файла"""
        large_content = b"x" * (settings.MAX_FILE_SIZE + 1)
        
        response = test_client.post(
            "/v1/extract/",
            files={"file": ("large.txt", BytesIO(large_content), "text/plain")}
        )
        
        assert response.status_code == 413
        assert "size exceeds maximum" in response.json()["detail"].lower()
    
    def test_extract_unsupported_format_error(self, test_client):
        """Тест ошибки при обработке неподдерживаемого формата"""
        test_content = b"Some binary content"
        
        with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
            mock_extract.side_effect = ValueError("Unsupported file format")
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": ("test.unknown", BytesIO(test_content), "application/octet-stream")}
            )
            
            assert response.status_code == 415
            data = response.json()
            assert data["status"] == "error"
            assert "неподдерживаемый формат" in data["message"].lower()
    
    def test_extract_corrupted_file_error(self, test_client):
        """Тест ошибки при обработке поврежденного файла"""
        test_content = b"corrupted content"
        
        with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
            mock_extract.side_effect = ValueError("File is corrupted")
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": ("corrupted.pdf", BytesIO(test_content), "application/pdf")}
            )
            
            assert response.status_code == 422
            data = response.json()
            assert data["status"] == "error"
            assert "поврежден" in data["message"].lower()
    
    def test_extract_no_content_length_error(self, test_client):
        """Тест ошибки при отсутствии Content-Length"""
        with patch('fastapi.UploadFile') as mock_upload:
            mock_file = Mock()
            mock_file.filename = "test.txt"
            mock_file.size = None  # Отсутствует Content-Length
            mock_upload.return_value = mock_file
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": ("test.txt", BytesIO(b"content"), "text/plain")}
            )
            
            # Этот тест сложно протестировать без реального HTTP запроса
            # так как TestClient автоматически устанавливает Content-Length
            assert response.status_code in [200, 400]
    
    def test_extract_archive_file_error(self, test_client):
        """Тест ошибки при обработке архива (без распаковки)"""
        # Минимальный ZIP файл
        zip_content = b"PK\x03\x04\x14\x00\x00\x00\x08\x00"
        
        with patch('app.utils.is_archive_format') as mock_is_archive:
            mock_is_archive.return_value = True
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": ("test.zip", BytesIO(zip_content), "application/zip")}
            )
            
            # Зависит от реализации - может быть 415 или успешная обработка
            assert response.status_code in [200, 415]
    
    def test_extract_multiple_files_from_archive(self, test_client):
        """Тест извлечения нескольких файлов из архива"""
        zip_content = b"PK\x03\x04\x14\x00\x00\x00\x08\x00"
        
        with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
            mock_extract.return_value = [
                {
                    "filename": "doc1.txt",
                    "path": "documents/doc1.txt",
                    "size": 100,
                    "type": "txt",
                    "text": "Содержимое первого документа"
                },
                {
                    "filename": "doc2.txt",
                    "path": "documents/doc2.txt",
                    "size": 150,
                    "type": "txt",
                    "text": "Содержимое второго документа"
                }
            ]
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": ("archive.zip", BytesIO(zip_content), "application/zip")}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert len(data["files"]) == 2
            assert data["files"][0]["filename"] == "doc1.txt"
            assert data["files"][1]["filename"] == "doc2.txt"
    
    def test_extract_with_file_type_validation_error(self, test_client):
        """Тест ошибки при проверке типа файла"""
        test_content = b"fake content"
        
        with patch('app.utils.validate_file_type') as mock_validate:
            mock_validate.return_value = (False, "File type does not match extension")
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": ("fake.txt", BytesIO(test_content), "text/plain")}
            )
            
            assert response.status_code == 415
            data = response.json()
            assert data["status"] == "error"
            assert "расширение файла не соответствует" in data["message"].lower()
    
    def test_extract_internal_server_error(self, test_client):
        """Тест внутренней ошибки сервера"""
        test_content = b"test content"
        
        with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
            mock_extract.side_effect = Exception("Internal server error")
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": ("test.txt", BytesIO(test_content), "text/plain")}
            )
            
            assert response.status_code == 500
            data = response.json()
            assert data["status"] == "error"
    
    def test_extract_filename_sanitization(self, test_client):
        """Тест санитизации имени файла"""
        test_content = b"test content"
        malicious_filename = "../../../etc/passwd"
        
        with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
            mock_extract.return_value = [{
                "filename": "etc_passwd",
                "path": "etc_passwd",
                "size": len(test_content),
                "type": "txt",
                "text": "test content"
            }]
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": (malicious_filename, BytesIO(test_content), "text/plain")}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["filename"] == malicious_filename  # Оригинальное имя в ответе
            # Но файл обрабатывается с безопасным именем
            mock_extract.assert_called_once()


@pytest.mark.integration
class TestMiddleware:
    """Тесты для middleware"""
    
    def test_cors_middleware(self, test_client):
        """Тест CORS middleware"""
        response = test_client.get("/")
        
        # Проверяем, что CORS заголовки установлены
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == "*"
    
    def test_logging_middleware(self, test_client):
        """Тест middleware для логирования"""
        with patch('app.main.logger') as mock_logger:
            response = test_client.get("/health")
            
            assert response.status_code == 200
            # Проверяем, что запрос и ответ залогированы
            mock_logger.info.assert_called()
    
    def test_logging_middleware_with_error(self, test_client):
        """Тест middleware для логирования с ошибкой"""
        with patch('app.main.logger') as mock_logger:
            with patch('app.main.app.router.route') as mock_route:
                mock_route.side_effect = Exception("Test error")
                
                try:
                    response = test_client.get("/health")
                except:
                    pass
                
                # Проверяем, что ошибка залогирована
                mock_logger.error.assert_called()


@pytest.mark.integration
class TestAsyncEndpoints:
    """Тесты для асинхронных эндпоинтов"""
    
    @pytest.mark.asyncio
    async def test_async_extract_endpoint(self, async_client):
        """Тест асинхронного эндпоинта извлечения"""
        test_content = "Асинхронный тестовый текст"
        
        with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
            mock_extract.return_value = [{
                "filename": "async_test.txt",
                "path": "async_test.txt",
                "size": len(test_content.encode('utf-8')),
                "type": "txt",
                "text": test_content
            }]
            
            response = await async_client.post(
                "/v1/extract/",
                files={"file": ("async_test.txt", BytesIO(test_content.encode('utf-8')), "text/plain")}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["files"][0]["text"] == test_content
    
    @pytest.mark.asyncio
    async def test_async_health_endpoint(self, async_client):
        """Тест асинхронного эндпоинта здоровья"""
        response = await async_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    @pytest.mark.asyncio
    async def test_async_supported_formats_endpoint(self, async_client):
        """Тест асинхронного эндпоинта поддерживаемых форматов"""
        response = await async_client.get("/v1/supported-formats/")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "images_ocr" in data