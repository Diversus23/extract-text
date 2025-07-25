"""Общие фикстуры для тестирования Text Extraction API."""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, Generator
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.config import settings
from app.extractors import TextExtractor
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Создает event loop для сессии тестирования."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_client():
    """Создает тестовый клиент для FastAPI."""
    return TestClient(app)


@pytest.fixture
async def async_client():
    """Создает асинхронный HTTP клиент для тестирования."""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def text_extractor():
    """Создает экземпляр TextExtractor для тестирования."""
    return TextExtractor()


@pytest.fixture
def temp_dir():
    """Создает временную директорию для тестов."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_text_file(temp_dir):
    """Создает временный текстовый файл для тестов."""
    file_path = temp_dir / "test.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("Тестовый текст для проверки\nВторая строка\nТретья строка")
    return file_path


@pytest.fixture
def sample_json_file(temp_dir):
    """Создает временный JSON файл для тестов."""
    file_path = temp_dir / "test.json"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write('{"name": "Тест", "description": "Тестовое описание", "count": 42}')
    return file_path


@pytest.fixture
def sample_csv_file(temp_dir):
    """Создает временный CSV файл для тестов."""
    file_path = temp_dir / "test.csv"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("Название,Цена,Количество\nТовар 1,100,5\nТовар 2,200,3")
    return file_path


@pytest.fixture
def sample_python_file(temp_dir):
    """Создает временный Python файл для тестов."""
    file_path = temp_dir / "test.py"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(
            """#!/usr/bin/env python3
# -*- coding: utf-8 -*-
\"\"\"
Тестовый Python файл
\"\"\"

def hello_world():
    \"\"\"Приветствие мира\"\"\"
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()
"""
        )
    return file_path


@pytest.fixture
def sample_html_file(temp_dir):
    """Создает временный HTML файл для тестов."""
    file_path = temp_dir / "test.html"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(
            """<!DOCTYPE html>
<html>
<head>
    <title>Тестовая страница</title>
</head>
<body>
    <h1>Заголовок</h1>
    <p>Тестовый параграф с <strong>жирным</strong> текстом.</p>
    <ul>
        <li>Элемент списка 1</li>
        <li>Элемент списка 2</li>
    </ul>
</body>
</html>"""
        )
    return file_path


@pytest.fixture
def sample_xml_file(temp_dir):
    """Создает временный XML файл для тестов."""
    file_path = temp_dir / "test.xml"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(
            """<?xml version="1.0" encoding="UTF-8"?>
<root>
    <item id="1">
        <name>Товар 1</name>
        <price>100</price>
    </item>
    <item id="2">
        <name>Товар 2</name>
        <price>200</price>
    </item>
</root>"""
        )
    return file_path


@pytest.fixture
def sample_yaml_file(temp_dir):
    """Создает временный YAML файл для тестов."""
    file_path = temp_dir / "test.yaml"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(
            """name: Тестовый проект
version: 1.0.0
description: Описание тестового проекта
dependencies:
  - python: ">=3.10"
  - fastapi: "^0.111.0"
config:
  debug: true
  port: 8000
"""
        )
    return file_path


@pytest.fixture
def real_test_files_dir():
    """Путь к реальным тестовым файлам."""
    return Path(__file__).parent


@pytest.fixture
def mock_tesseract():
    """Мокает pytesseract для тестирования OCR."""
    with patch("pytesseract.image_to_string") as mock_ocr:
        mock_ocr.return_value = "Распознанный текст с изображения"
        yield mock_ocr


@pytest.fixture
def mock_libreoffice():
    """Мокает subprocess для LibreOffice."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        yield mock_run


@pytest.fixture
def settings_override():
    """Создает переопределенные настройки для тестов."""
    original_settings = {}

    def override(**kwargs):
        for key, value in kwargs.items():
            if hasattr(settings, key):
                original_settings[key] = getattr(settings, key)
                setattr(settings, key, value)

    yield override

    # Восстанавливаем исходные настройки
    for key, value in original_settings.items():
        setattr(settings, key, value)


@pytest.fixture
def uploaded_file_mock():
    """Создает мок для UploadFile."""

    def create_upload_file(
        filename: str, content: bytes, content_type: str = "text/plain"
    ):
        file_mock = Mock()
        file_mock.filename = filename
        file_mock.size = len(content)
        file_mock.content_type = content_type
        file_mock.read = Mock(return_value=content)
        return file_mock

    return create_upload_file


# Параметризованные фикстуры для тестирования различных форматов
@pytest.fixture(
    params=[
        ("test.txt", "text/plain"),
        ("test.json", "application/json"),
        ("test.csv", "text/csv"),
        ("test.py", "text/x-python"),
        ("test.html", "text/html"),
        ("test.xml", "application/xml"),
        ("test.yaml", "application/x-yaml"),
    ]
)
def text_format_file(request, temp_dir):
    """Параметризованная фикстура для создания файлов разных текстовых форматов."""
    filename, content_type = request.param
    file_path = temp_dir / filename

    content_map = {
        "test.txt": "Простой текстовый файл",
        "test.json": '{"test": "json content"}',
        "test.csv": "col1,col2\\nval1,val2",
        "test.py": "print('hello')",
        "test.html": "<html><body>Test</body></html>",
        "test.xml": "<root><item>test</item></root>",
        "test.yaml": "key: value\\nlist:\\n  - item1\\n  - item2",
    }

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content_map[filename])

    return file_path, content_type
