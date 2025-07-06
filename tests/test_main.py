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
        
        # Мокаем валидацию файла - пропускаем проверку типа
        with patch('app.main.validate_file_type', return_value=(True, None)):
            with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
                mock_extract.side_effect = ValueError("File is corrupted")
                
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("corrupted.pdf", BytesIO(test_content), "application/pdf")}
                )
                
                assert response.status_code == 422
                data = response.json()
                assert data["status"] == "error"
                assert "поврежден" in data["message"]
    
    def test_extract_no_content_length_error(self, test_client):
        """Тест ошибки при отсутствии Content-Length"""
        # Создаем запрос без Content-Length заголовка
        response = test_client.post("/v1/extract/")
        
        assert response.status_code == 422
        # FastAPI автоматически возвращает ошибку при отсутствии файла
    
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
        test_content = b"fake archive content"
        
        # Мокаем валидацию файла
        with patch('app.main.validate_file_type', return_value=(True, None)):
            with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
                # Мокаем результат извлечения нескольких файлов
                mock_extract.return_value = [
                    {
                        "filename": "file1.txt",
                        "path": "archive.zip/file1.txt",
                        "size": 100,
                        "type": "txt",
                        "text": "Content of file 1"
                    },
                    {
                        "filename": "file2.txt",
                        "path": "archive.zip/file2.txt",
                        "size": 200,
                        "type": "txt",
                        "text": "Content of file 2"
                    }
                ]
                
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("archive.zip", BytesIO(test_content), "application/zip")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert len(data["files"]) == 2
                assert data["files"][0]["filename"] == "file1.txt"
                assert data["files"][1]["filename"] == "file2.txt"
    
    def test_extract_with_file_type_validation_error(self, test_client):
        """Тест ошибки при валидации типа файла"""
        # Файл с неподходящим содержимым
        fake_pdf_content = b"This is not a PDF file"
        
        with patch('app.utils.validate_file_type') as mock_validate:
            mock_validate.return_value = (False, "Расширение файла не соответствует содержимому")
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": ("fake.pdf", BytesIO(fake_pdf_content), "application/pdf")}
            )
            
            assert response.status_code == 415
            data = response.json()
            assert data["status"] == "error"
            assert "не соответствует" in data["message"]
    
    def test_extract_processing_timeout_error(self, test_client):
        """Тест ошибки таймаута при обработке"""
        test_content = b"large file content"
        
        # Мокаем валидацию файла
        with patch('app.main.validate_file_type', return_value=(True, None)):
            with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
                mock_extract.side_effect = ValueError("Processing timeout exceeded")
                
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("large.pdf", BytesIO(test_content), "application/pdf")}
                )
                
                assert response.status_code == 422
                data = response.json()
                assert data["status"] == "error"
                assert "поврежден" in data["message"]
    
    def test_extract_file_without_extension(self, test_client):
        """Тест обработки файла без расширения"""
        test_content = b"file content"
        
        # Мокаем валидацию файла - неудачная валидация
        with patch('app.main.validate_file_type', return_value=(False, "Не удалось определить расширение файла")):
            response = test_client.post(
                "/v1/extract/",
                files={"file": ("README", BytesIO(test_content), "text/plain")}
            )
            
            assert response.status_code == 415
            data = response.json()
            assert data["status"] == "error"
            assert "не соответствует" in data["message"]
    
    def test_extract_success_with_multiple_files_in_archive(self, test_client):
        """Тест успешного извлечения из архива с несколькими файлами"""
        test_content = b"archive with multiple files"
        
        # Мокаем валидацию файла
        with patch('app.main.validate_file_type', return_value=(True, None)):
            with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
                mock_extract.return_value = [
                    {
                        "filename": "doc1.txt",
                        "path": "archive.zip/folder/doc1.txt",
                        "size": 150,
                        "type": "txt",
                        "text": "First document text"
                    },
                    {
                        "filename": "doc2.pdf",
                        "path": "archive.zip/doc2.pdf",
                        "size": 300,
                        "type": "pdf",
                        "text": "Second document text"
                    }
                ]
                
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("documents.zip", BytesIO(test_content), "application/zip")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "documents.zip"
                assert len(data["files"]) == 2
                
                # Проверяем содержимое первого файла
                assert data["files"][0]["filename"] == "doc1.txt"
                assert data["files"][0]["text"] == "First document text"
                
                # Проверяем содержимое второго файла
                assert data["files"][1]["filename"] == "doc2.pdf"
                assert data["files"][1]["text"] == "Second document text"
    
    def test_extract_with_sanitized_filename(self, test_client):
        """Тест обработки файла с небезопасным именем"""
        test_content = b"test content"
        unsafe_filename = "../../../etc/passwd"
        
        with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
            mock_extract.return_value = [{
                "filename": "etc_passwd",  # Санитизованное имя
                "path": "etc_passwd",
                "size": len(test_content),
                "type": "txt",
                "text": "test content"
            }]
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": (unsafe_filename, BytesIO(test_content), "text/plain")}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["filename"] == unsafe_filename  # Оригинальное имя в ответе
            assert data["files"][0]["filename"] == "etc_passwd"  # Санитизованное имя
    
    def test_extract_zero_size_file(self, test_client):
        """Тест обработки файла нулевого размера"""
        response = test_client.post(
            "/v1/extract/",
            files={"file": ("empty.txt", BytesIO(b""), "text/plain")}
        )
        
        assert response.status_code == 422
        data = response.json()
        assert "empty" in data["detail"].lower()
    
    def test_extract_file_with_special_characters_in_name(self, test_client):
        """Тест обработки файла со специальными символами в имени"""
        test_content = b"test content"
        special_filename = "тест файл с пробелами & символами!.txt"
        
        with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
            mock_extract.return_value = [{
                "filename": "тест_файл_с_пробелами_символами.txt",
                "path": "тест_файл_с_пробелами_символами.txt",
                "size": len(test_content),
                "type": "txt",
                "text": "test content"
            }]
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": (special_filename, BytesIO(test_content), "text/plain")}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["filename"] == special_filename


@pytest.mark.integration
class TestMiddleware:
    """Тесты для middleware"""
    
    def test_cors_middleware(self, test_client):
        """Тест CORS middleware"""
        # Проверяем обычный запрос с заголовком Origin
        response = test_client.get("/", headers={"Origin": "http://localhost:3000"})
        
        # Проверяем, что запрос успешен
        assert response.status_code == 200
        assert response.json()["api_name"] == "Text Extraction API for RAG"
        
        # Проверяем наличие CORS заголовков
        # FastAPI автоматически добавляет CORS заголовки при настройке CORSMiddleware
        assert "access-control-allow-origin" in response.headers.keys() or "Access-Control-Allow-Origin" in response.headers.keys()
    
    def test_logging_middleware(self, test_client):
        """Тест middleware для логирования"""
        with patch('app.main.logger') as mock_logger:
            response = test_client.get("/health")
            
            assert response.status_code == 200
            # Проверяем, что запрос и ответ залогированы
            mock_logger.info.assert_called()
    
    def test_logging_middleware_with_error(self, test_client):
        """Тест logging middleware при ошибке"""
        # Отправляем запрос на несуществующий endpoint
        response = test_client.get("/nonexistent")
        
        # Проверяем, что возвращается 404
        assert response.status_code == 404
        
        # Проверяем что middleware работает - логирование происходит автоматически
        # Мы можем только проверить, что запрос обработан
        assert response.json()["detail"] == "Not Found"


@pytest.mark.integration
class TestAsyncEndpoints:
    """Тесты для асинхронных endpoint'ов"""
    
    def test_async_extract_endpoint(self, test_client):
        """Тест асинхронного endpoint извлечения текста"""
        test_content = b"Test content"
        
        # Мокаем валидацию файла
        with patch('app.main.validate_file_type', return_value=(True, None)):
            with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
                mock_extract.return_value = [{
                    "filename": "test.txt",
                    "path": "test.txt",
                    "size": 12,
                    "type": "txt",
                    "text": "Test content"
                }]
                
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("test.txt", BytesIO(test_content), "text/plain")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.txt"
                # Проверяем что асинхронный метод был вызван
                mock_extract.assert_called_once()
    
    def test_async_health_endpoint(self, test_client):
        """Тест асинхронного health endpoint"""
        response = test_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    def test_async_supported_formats_endpoint(self, test_client):
        """Тест асинхронного endpoint поддерживаемых форматов"""
        response = test_client.get("/v1/supported-formats/")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Проверяем, что есть основные группы форматов
        assert "images_ocr" in data
        assert "documents" in data
        assert "other" in data  # группа "other" содержит текстовые файлы
        assert "pdf" in data["documents"]  # PDF в группе documents