"""
Integration тесты с реальными файлами из папки tests
"""
import pytest
import os
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings


@pytest.mark.integration
class TestRealFiles:
    """Тесты с реальными файлами из папки tests"""
    
    def test_extract_real_text_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального текстового файла"""
        text_file = real_test_files_dir / "text.txt"
        
        if text_file.exists():
            with open(text_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("text.txt", f, "text/plain")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "text.txt"
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0
    
    def test_extract_real_json_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального JSON файла"""
        json_file = real_test_files_dir / "test.json"
        
        if json_file.exists():
            with open(json_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("test.json", f, "application/json")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.json"
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0
    
    def test_extract_real_csv_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального CSV файла"""
        csv_file = real_test_files_dir / "test.csv"
        
        if csv_file.exists():
            with open(csv_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("test.csv", f, "text/csv")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.csv"
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0
    
    def test_extract_real_python_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального Python файла"""
        py_file = real_test_files_dir / "test.py"
        
        if py_file.exists():
            with open(py_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("test.py", f, "text/x-python")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.py"
                assert len(data["files"]) == 1
                assert "Язык программирования: Python" in data["files"][0]["text"]
    
    def test_extract_real_html_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального HTML файла"""
        html_file = real_test_files_dir / "test.html"
        
        if html_file.exists():
            with open(html_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("test.html", f, "text/html")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.html"
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0
    
    def test_extract_real_xml_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального XML файла"""
        xml_file = real_test_files_dir / "test.xml"
        
        if xml_file.exists():
            with open(xml_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("test.xml", f, "application/xml")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.xml"
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0
    
    def test_extract_real_yaml_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального YAML файла"""
        yaml_file = real_test_files_dir / "test.yaml"
        
        if yaml_file.exists():
            with open(yaml_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("test.yaml", f, "application/x-yaml")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.yaml"
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0
    
    @patch('app.extractors.pytesseract.image_to_string')
    def test_extract_real_image_file(self, mock_tesseract, test_client, real_test_files_dir):
        """Тест извлечения из реального изображения"""
        # Мокаем OCR для стабильности тестов
        mock_tesseract.return_value = "Распознанный текст с изображения"
        
        jpg_file = real_test_files_dir / "test.jpg"
        
        if jpg_file.exists():
            with open(jpg_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("test.jpg", f, "image/jpeg")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.jpg"
                assert len(data["files"]) == 1
                # Текст может быть пустым если OCR не распознал ничего
                assert "text" in data["files"][0]
    
    @patch('app.extractors.PyPDF2.PdfReader')
    def test_extract_real_pdf_file(self, mock_pdf_reader, test_client, real_test_files_dir):
        """Тест извлечения из реального PDF файла"""
        # Мокаем PyPDF2 для стабильности тестов
        mock_reader = Mock()
        mock_page = Mock()
        mock_page.extract_text.return_value = "Текст из PDF документа"
        mock_reader.pages = [mock_page]
        mock_pdf_reader.return_value = mock_reader
        
        pdf_file = real_test_files_dir / "test.pdf"
        
        if pdf_file.exists():
            with open(pdf_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("test.pdf", f, "application/pdf")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.pdf"
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0
    
    @patch('app.extractors.Document')
    def test_extract_real_docx_file(self, mock_document, test_client, real_test_files_dir):
        """Тест извлечения из реального DOCX файла"""
        # Мокаем python-docx для стабильности тестов
        mock_doc = Mock()
        mock_paragraph = Mock()
        mock_paragraph.text = "Текст из DOCX документа"
        mock_doc.paragraphs = [mock_paragraph]
        mock_document.return_value = mock_doc
        
        docx_file = real_test_files_dir / "test.docx"
        
        if docx_file.exists():
            with open(docx_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.docx"
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0
    
    @patch('app.extractors.pandas.read_excel')
    def test_extract_real_xlsx_file(self, mock_read_excel, test_client, real_test_files_dir):
        """Тест извлечения из реального XLSX файла"""
        # Мокаем pandas для стабильности тестов
        mock_df = Mock()
        mock_df.to_csv.return_value = "Столбец1,Столбец2\nЗначение1,Значение2"
        mock_read_excel.return_value = {"Sheet1": mock_df}
        
        xlsx_file = real_test_files_dir / "test.xlsx"
        
        if xlsx_file.exists():
            with open(xlsx_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.xlsx"
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0
    
    def test_extract_1c_enterprise_file(self, test_client, real_test_files_dir):
        """Тест извлечения из файла 1C:Enterprise"""
        bsl_file = real_test_files_dir / "test.bsl"
        
        if bsl_file.exists():
            with open(bsl_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("test.bsl", f, "text/plain")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.bsl"
                assert len(data["files"]) == 1
                assert "Язык программирования: 1C:Enterprise" in data["files"][0]["text"]
    
    def test_extract_onescript_file(self, test_client, real_test_files_dir):
        """Тест извлечения из файла OneScript"""
        os_file = real_test_files_dir / "test.os"
        
        if os_file.exists():
            with open(os_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/",
                    files={"file": ("test.os", f, "text/plain")}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.os"
                assert len(data["files"]) == 1
                assert "Язык программирования: OneScript" in data["files"][0]["text"]
    
    def test_extract_multiple_file_types(self, test_client, real_test_files_dir):
        """Тест извлечения из нескольких типов файлов подряд"""
        test_files = [
            ("text.txt", "text/plain"),
            ("test.json", "application/json"),
            ("test.py", "text/x-python"),
            ("test.html", "text/html"),
        ]
        
        for filename, content_type in test_files:
            file_path = real_test_files_dir / filename
            
            if file_path.exists():
                with open(file_path, "rb") as f:
                    response = test_client.post(
                        "/v1/extract/",
                        files={"file": (filename, f, content_type)}
                    )
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "success"
                    assert data["filename"] == filename
                    assert len(data["files"]) == 1


@pytest.mark.integration
class TestPerformance:
    """Тесты производительности"""
    
    def test_concurrent_requests(self, test_client):
        """Тест одновременных запросов"""
        import threading
        import time
        
        results = []
        
        def make_request():
            test_content = "Тестовый контент для проверки производительности"
            response = test_client.post(
                "/v1/extract/",
                files={"file": ("test.txt", test_content.encode(), "text/plain")}
            )
            results.append(response.status_code)
        
        # Создаем 5 одновременных запросов
        threads = []
        for i in range(5):
            t = threading.Thread(target=make_request)
            threads.append(t)
            t.start()
        
        # Ждем завершения всех потоков
        for t in threads:
            t.join()
        
        # Проверяем, что все запросы выполнены успешно
        assert len(results) == 5
        assert all(status == 200 for status in results)
    
    def test_large_text_file(self, test_client):
        """Тест обработки большого текстового файла"""
        # Создаем файл размером примерно 1MB
        large_content = "Большой текстовый файл для тестирования производительности.\n" * 10000
        
        response = test_client.post(
            "/v1/extract/",
            files={"file": ("large.txt", large_content.encode(), "text/plain")}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["filename"] == "large.txt"
        assert len(data["files"]) == 1
        assert len(data["files"][0]["text"]) > 0
    
    def test_response_time(self, test_client):
        """Тест времени ответа"""
        import time
        
        test_content = "Тестовый контент для проверки времени ответа"
        
        start_time = time.time()
        response = test_client.post(
            "/v1/extract/",
            files={"file": ("test.txt", test_content.encode(), "text/plain")}
        )
        end_time = time.time()
        
        response_time = end_time - start_time
        
        assert response.status_code == 200
        assert response_time < 5.0  # Ответ должен быть быстрее 5 секунд для простого текста


@pytest.mark.integration
class TestErrorHandling:
    """Тесты обработки ошибок"""
    
    def test_malformed_request(self, test_client):
        """Тест неправильно сформированного запроса"""
        response = test_client.post("/v1/extract/")
        
        assert response.status_code == 422  # Unprocessable Entity
    
    def test_missing_file(self, test_client):
        """Тест отсутствующего файла в запросе"""
        response = test_client.post(
            "/v1/extract/",
            data={"not_file": "some_data"}
        )
        
        assert response.status_code == 422
    
    def test_invalid_endpoint(self, test_client):
        """Тест несуществующего эндпоинта"""
        response = test_client.get("/v1/nonexistent/")
        
        assert response.status_code == 404
    
    def test_invalid_method(self, test_client):
        """Тест неподдерживаемого HTTP метода"""
        response = test_client.put("/v1/extract/")
        
        assert response.status_code == 405  # Method Not Allowed
    
    def test_server_error_simulation(self, test_client):
        """Тест симуляции ошибки сервера"""
        with patch('app.extractors.TextExtractor.extract_text') as mock_extract:
            mock_extract.side_effect = Exception("Simulated server error")
            
            response = test_client.post(
                "/v1/extract/",
                files={"file": ("test.txt", b"test content", "text/plain")}
            )
            
            assert response.status_code == 500
            data = response.json()
            assert data["status"] == "error"


@pytest.mark.integration
class TestDocumentation:
    """Тесты документации API"""
    
    def test_openapi_schema(self, test_client):
        """Тест OpenAPI схемы"""
        response = test_client.get("/openapi.json")
        
        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema
        assert "/v1/extract/" in schema["paths"]
    
    def test_swagger_ui(self, test_client):
        """Тест Swagger UI"""
        response = test_client.get("/docs")
        
        assert response.status_code == 200
        assert "swagger" in response.text.lower()
    
    def test_redoc(self, test_client):
        """Тест ReDoc документации"""
        response = test_client.get("/redoc")
        
        assert response.status_code == 200
        assert "redoc" in response.text.lower() 