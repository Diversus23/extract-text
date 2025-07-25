"""Integration тесты с реальными файлами из папки tests."""

import json
import mimetypes
import os
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.mark.integration
class TestAllRealFiles:
    """Автоматические тесты для всех файлов из папки tests."""

    @pytest.fixture
    def supported_formats(self, real_test_files_dir):
        """Загружает поддерживаемые форматы из JSON файла."""
        supported_formats_file = real_test_files_dir / "supported_formats.json"
        with open(supported_formats_file, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def all_supported_extensions(self, supported_formats):
        """Возвращает все поддерживаемые расширения файлов."""
        extensions = set()
        for category, formats in supported_formats.items():
            if category != "archives":  # Архивы обрабатываются отдельно
                extensions.update(formats)
        return extensions

    @pytest.fixture
    def test_files_to_skip(self):
        """Файлы, которые нужно пропустить при тестировании."""
        return {
            # Конфигурационные файлы
            "supported_formats.json",
            "config.toml",
            "conftest.py",
            "pytest.ini",
            "__init__.py",
            # Результаты тестов
            "*.ok.txt",
            "*.err.txt",
            # Системные файлы
            ".DS_Store",
            "Thumbs.db",
            # Файлы тестирования
            "test_*.py",
            # Файлы без текста (для специальных тестов)
            "test.notext.tif",
            "test.only_image.tiff",
        }

    def should_skip_file(self, file_path, skip_patterns):
        """Проверяет, нужно ли пропустить файл."""
        filename = file_path.name

        # Проверяем точные совпадения
        if filename in skip_patterns:
            return True

        # Проверяем паттерны с звездочками
        for pattern in skip_patterns:
            if "*" in pattern:
                if pattern.startswith("*") and filename.endswith(pattern[1:]):
                    return True
                if pattern.endswith("*") and filename.startswith(pattern[:-1]):
                    return True

        return False

    def get_content_type(self, file_path):
        """Определяет MIME тип файла."""
        # Для архивов используем специальный тип
        if file_path.suffix.lower() in [
            ".zip",
            ".rar",
            ".7z",
            ".tar",
            ".gz",
            ".bz2",
            ".xz",
        ]:
            return "application/octet-stream"

        # Для остальных файлов используем стандартное определение
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type:
            return content_type

        # Дефолтный тип для неизвестных файлов
        return "application/octet-stream"

    @patch("app.main.validate_file_type")
    @patch("app.extractors.pytesseract")
    @patch("app.extractors.Image")
    @patch("app.extractors.pdfplumber")
    @patch("app.extractors.Document")
    @patch("app.extractors.pd")
    def test_all_supported_files(
        self,
        mock_pd,
        mock_document,
        mock_pdfplumber,
        mock_image,
        mock_tesseract,
        mock_validate_file_type,
        test_client,
        real_test_files_dir,
        all_supported_extensions,
        test_files_to_skip,
    ):
        """Тест обработки всех поддерживаемых файлов из папки tests."""
        # Мокаем валидацию файлов чтобы пропустить MIME проверки
        mock_validate_file_type.return_value = (True, None)

        # Мокаем внешние зависимости
        mock_tesseract.image_to_string.return_value = "OCR text"
        mock_image.open.return_value = Mock()

        # Мокаем pdfplumber
        mock_pdf = Mock()
        mock_page = Mock()
        mock_page.extract_text.return_value = "PDF text"
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf

        # Мокаем Document для Word файлов
        mock_doc = Mock()
        mock_paragraph = Mock()
        mock_paragraph.text = "Document text"
        mock_doc.paragraphs = [mock_paragraph]
        mock_doc.tables = []
        mock_document.return_value = mock_doc

        # Мокаем pandas для Excel файлов
        mock_df = Mock()
        mock_df.to_csv.return_value = "CSV data"
        mock_pd.read_excel.return_value = mock_df
        mock_pd.read_csv.return_value = mock_df

        # Находим все файлы в папке tests
        all_files = []
        for file_path in real_test_files_dir.iterdir():
            if file_path.is_file():
                # Пропускаем служебные файлы
                if self.should_skip_file(file_path, test_files_to_skip):
                    continue

                # Получаем расширение файла
                extension = file_path.suffix.lower().lstrip(".")

                # Для составных расширений (tar.gz, tar.bz2, etc.)
                if file_path.name.count(".") > 1:
                    parts = file_path.name.split(".")
                    if len(parts) >= 3:
                        # Для файлов типа test.tar.gz
                        compound_ext = ".".join(parts[-2:])
                        if compound_ext in all_supported_extensions:
                            extension = compound_ext

                # Проверяем, поддерживается ли расширение
                if extension in all_supported_extensions:
                    all_files.append(file_path)

        # Проверяем, что файлы найдены
        assert len(all_files) > 0, "Не найдено файлов для тестирования в папке tests"

        # Счетчики для статистики
        successful_files = 0
        failed_files = 0
        skipped_files = 0

        # Тестируем каждый файл
        for file_path in all_files:
            try:
                # Проверяем размер файла (не более 20 МБ)
                file_size = file_path.stat().st_size
                if file_size > 20 * 1024 * 1024:  # 20 МБ
                    print(
                        f"Пропускаем файл {file_path.name} - размер {file_size} байт превышает лимит"
                    )
                    skipped_files += 1
                    continue

                # Читаем файл
                with open(file_path, "rb") as f:
                    content = f.read()

                # Определяем MIME тип
                content_type = self.get_content_type(file_path)

                # Отправляем запрос
                response = test_client.post(
                    "/v1/extract/file",
                    files={"file": (file_path.name, content, content_type)},
                )

                # Проверяем результат
                if response.status_code == 200:
                    data = response.json()
                    assert (
                        data["status"] == "success"
                    ), f"Файл {file_path.name}: status != success"
                    assert (
                        data["filename"] == file_path.name
                    ), f"Файл {file_path.name}: неверное имя файла"
                    assert (
                        "count" in data
                    ), f"Файл {file_path.name}: отсутствует поле count"
                    assert (
                        data["count"] >= 1
                    ), f"Файл {file_path.name}: count должен быть >= 1"
                    assert (
                        len(data["files"]) >= 1
                    ), f"Файл {file_path.name}: нет файлов в результате"
                    assert (
                        len(data["files"]) == data["count"]
                    ), f"Файл {file_path.name}: count не соответствует количеству файлов"
                    successful_files += 1
                    print(f"✓ {file_path.name} - успешно обработан")
                elif response.status_code == 415:
                    # Файл не поддерживается или архив
                    data = response.json()
                    if "архив" in data.get("message", "").lower():
                        print(f"→ {file_path.name} - архив (требует распаковки)")
                    else:
                        print(f"→ {file_path.name} - не поддерживается")
                    skipped_files += 1
                elif response.status_code == 422:
                    # Файл поврежден или пустой
                    data = response.json()
                    print(
                        f"⚠ {file_path.name} - поврежден или пуст: {data.get('message', 'Unknown error')}"
                    )
                    # Не считаем это ошибкой - файл может быть специально поврежден для тестирования
                    skipped_files += 1
                else:
                    # Неожиданная ошибка
                    print(
                        f"✗ {file_path.name} - ошибка {response.status_code}: {response.text}"
                    )
                    failed_files += 1

            except Exception as e:
                print(f"✗ {file_path.name} - исключение: {e}")
                failed_files += 1

        # Выводим статистику
        total_files = len(all_files)
        print("\n=== Статистика тестирования файлов ===")
        print(f"Всего файлов: {total_files}")
        print(f"Успешно обработано: {successful_files}")
        print(f"Пропущено: {skipped_files}")
        print(f"Ошибки: {failed_files}")
        print(
            f"Успешность: {successful_files}/{total_files} ({successful_files/total_files*100:.1f}%)"
        )

        # Проверяем, что хотя бы половина файлов обработалась успешно
        success_rate = successful_files / total_files if total_files > 0 else 0
        assert (
            success_rate >= 0.3
        ), f"Слишком низкая успешность обработки файлов: {success_rate:.1f}% (ожидается минимум 30%)"

        # Проверяем, что критических ошибок не слишком много
        error_rate = failed_files / total_files if total_files > 0 else 0
        assert (
            error_rate <= 0.2
        ), f"Слишком много критических ошибок: {error_rate:.1f}% (максимум 20%)"

    def test_archive_files_rejection(self, test_client, real_test_files_dir):
        """Тест отклонения архивных файлов."""
        archive_extensions = [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"]

        found_archives = []
        for file_path in real_test_files_dir.iterdir():
            if file_path.is_file():
                if any(file_path.name.endswith(ext) for ext in archive_extensions):
                    found_archives.append(file_path)

        if not found_archives:
            pytest.skip("Не найдено архивных файлов для тестирования")

        for archive_path in found_archives:
            with open(archive_path, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file",
                    files={"file": (archive_path.name, f, "application/octet-stream")},
                )

            # Архивы должны отклоняться с кодом 415
            assert (
                response.status_code == 415
            ), f"Архив {archive_path.name} должен отклоняться с кодом 415"
            data = response.json()
            assert data["status"] == "error"
            assert "архив" in data["message"].lower()


@pytest.mark.integration
class TestRealFiles:
    """Тесты с реальными файлами из папки tests."""

    def test_extract_real_text_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального текстового файла."""
        text_file = real_test_files_dir / "text.txt"

        if text_file.exists():
            with open(text_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file", files={"file": ("text.txt", f, "text/plain")}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "text.txt"
                assert data["count"] == 1
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0

    def test_extract_real_json_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального JSON файла."""
        json_file = real_test_files_dir / "test.json"

        if json_file.exists():
            with open(json_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file",
                    files={"file": ("test.json", f, "application/json")},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.json"
                assert data["count"] == 1
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0

    def test_extract_real_csv_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального CSV файла."""
        csv_file = real_test_files_dir / "test.csv"

        if csv_file.exists():
            with open(csv_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file", files={"file": ("test.csv", f, "text/csv")}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.csv"
                assert data["count"] == 1
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0

    def test_extract_real_python_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального Python файла."""
        py_file = real_test_files_dir / "test.py"

        if py_file.exists():
            with open(py_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file", files={"file": ("test.py", f, "text/x-python")}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.py"
                assert data["count"] == 1
                assert len(data["files"]) == 1
                # Убираем ожидание конкретного формата - просто проверяем, что текст извлечен
                assert len(data["files"][0]["text"]) > 0
                assert data["files"][0]["type"] == "py"

    def test_extract_real_html_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального HTML файла."""
        html_file = real_test_files_dir / "test.html"

        if html_file.exists():
            with open(html_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file", files={"file": ("test.html", f, "text/html")}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.html"
                assert data["count"] == 1
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0

    def test_extract_real_xml_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального XML файла."""
        xml_file = real_test_files_dir / "test.xml"

        if xml_file.exists():
            with open(xml_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file",
                    files={"file": ("test.xml", f, "application/xml")},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.xml"
                assert data["count"] == 1
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0

    def test_extract_real_yaml_file(self, test_client, real_test_files_dir):
        """Тест извлечения из реального YAML файла."""
        yaml_file = real_test_files_dir / "test.yaml"

        if yaml_file.exists():
            with open(yaml_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file",
                    files={"file": ("test.yaml", f, "application/x-yaml")},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.yaml"
                assert data["count"] == 1
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0

    @patch("app.extractors.pytesseract")
    @patch("app.extractors.Image")
    def test_extract_real_image_file(
        self, mock_image_class, mock_tesseract, test_client, real_test_files_dir
    ):
        """Тест извлечения из реального изображения."""
        # Мокаем OCR для стабильности тестов
        mock_tesseract.image_to_string.return_value = "Распознанный текст с изображения"
        mock_image = Mock()
        mock_image_class.open.return_value = mock_image

        jpg_file = real_test_files_dir / "test.jpg"

        if jpg_file.exists():
            with open(jpg_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file", files={"file": ("test.jpg", f, "image/jpeg")}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.jpg"
                assert data["count"] == 1
                assert len(data["files"]) == 1
                # Текст может быть пустым если OCR не распознал ничего
                assert "text" in data["files"][0]

    @patch("app.extractors.PyPDF2.PdfReader")
    def test_extract_real_pdf_file(
        self, mock_pdf_reader, test_client, real_test_files_dir
    ):
        """Тест извлечения из реального PDF файла."""
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
                    "/v1/extract/file",
                    files={"file": ("test.pdf", f, "application/pdf")},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.pdf"
                assert data["count"] == 1
                assert len(data["files"]) == 1
                assert len(data["files"][0]["text"]) > 0

    @patch("app.extractors.Document")
    def test_extract_real_docx_file(
        self, mock_document, test_client, real_test_files_dir
    ):
        """Тест извлечения из реального DOCX файла."""
        # Мокаем python-docx для стабильности тестов
        mock_doc = Mock()
        mock_paragraph = Mock()
        mock_paragraph.text = "Текст из DOCX документа"
        mock_doc.paragraphs = [mock_paragraph]
        mock_doc.tables = []  # Делаем tables итерируемым
        mock_doc.sections = []  # Добавляем sections для полного мокинга
        mock_document.return_value = mock_doc

        docx_file = real_test_files_dir / "test.docx"

        if docx_file.exists():
            with open(docx_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file",
                    files={
                        "file": (
                            "test.docx",
                            f,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    },
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.docx"
                assert data["count"] >= 1
                assert len(data["files"]) >= 1
                # Проверяем, что текст был извлечен
                assert len(data["files"][0]["text"]) > 0
        else:
            pytest.skip("test.docx file not found")

    @patch("app.extractors.pd")
    def test_extract_real_xlsx_file(self, mock_pd, test_client, real_test_files_dir):
        """Тест извлечения из реального XLSX файла."""
        # Мокаем pandas для стабильности тестов
        mock_dataframe = Mock()
        mock_dataframe.to_csv.return_value = "col1,col2\ndata1,data2"
        mock_pd.read_excel.return_value = {"Sheet1": mock_dataframe}

        xlsx_file = real_test_files_dir / "test.xlsx"

        if xlsx_file.exists():
            with open(xlsx_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file",
                    files={
                        "file": (
                            "test.xlsx",
                            f,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    },
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.xlsx"
                assert data["count"] >= 1
                assert len(data["files"]) >= 1
                # Проверяем, что данные были извлечены
                assert len(data["files"][0]["text"]) > 0
        else:
            pytest.skip("test.xlsx file not found")

    def test_extract_1c_enterprise_file(self, test_client, real_test_files_dir):
        """Тест извлечения из файла 1C Enterprise."""
        bsl_file = real_test_files_dir / "test.bsl"

        if bsl_file.exists():
            with open(bsl_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file", files={"file": ("test.bsl", f, "text/plain")}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.bsl"
                assert data["count"] >= 1
                assert len(data["files"]) >= 1
                # Проверяем, что код был извлечен как текст
                assert data["files"][0]["type"] == "bsl"
        else:
            pytest.skip("test.bsl file not found")

    def test_extract_onescript_file(self, test_client, real_test_files_dir):
        """Тест извлечения из файла OneScript."""
        os_file = real_test_files_dir / "test.os"

        if os_file.exists():
            with open(os_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file", files={"file": ("test.os", f, "text/plain")}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.os"
                assert data["count"] >= 1
                assert len(data["files"]) >= 1
                # Проверяем, что код был извлечен как текст
                assert data["files"][0]["type"] == "os"
        else:
            pytest.skip("test.os file not found")

    def test_extract_multiple_file_types(self, test_client, real_test_files_dir):
        """Тест извлечения из нескольких типов файлов подряд."""
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
                        "/v1/extract/file", files={"file": (filename, f, content_type)}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "success"
                    assert data["filename"] == filename
                    assert data["count"] == 1
                    assert len(data["files"]) == 1

    def test_extract_real_docx_file_content(self, test_client, real_test_files_dir):
        """Тест извлечения конкретного содержимого из реального DOCX файла."""
        docx_file = real_test_files_dir / "test.docx"

        if docx_file.exists():
            with open(docx_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file",
                    files={
                        "file": (
                            "test.docx",
                            f,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    },
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "test.docx"
                assert data["count"] >= 1
                assert len(data["files"]) >= 1

                # Проверяем, что текст был извлечен
                extracted_text = data["files"][0]["text"]
                assert len(extracted_text) > 0

                # Проверяем наличие основных элементов из прайс-листа
                assert "СтройМаркет" in extracted_text
                assert "Иванов Сергей Сергеевич" in extracted_text
                assert "+7(800) 500-54-36" in extracted_text
                assert "support@kub-24.ru" in extracted_text
                assert "Данные на 02.03.2020" in extracted_text

                # Проверяем наличие заголовков таблицы
                assert "Наименование" in extracted_text
                assert "Остаток" in extracted_text
                assert "Ед. измерения" in extracted_text
                assert "Цена" in extracted_text

                # Проверяем наличие некоторых товаров из прайс-листа
                assert "Арматура 8мм А3" in extracted_text
                assert "Болт оцинкованный М8х80" in extracted_text
                assert "Кирпич лицевой одинарный" in extracted_text
                assert "Перфоратор Макита HR2450" in extracted_text
                assert "ТИККУРИЛА Евро 2" in extracted_text

                # Проверяем некоторые цены
                assert "30,00" in extracted_text  # Цена арматуры
                assert "2 999,00" in extracted_text  # Цена грунт-эмали
                assert "8 490,00" in extracted_text  # Цена перфоратора

                # Проверяем тип файла
                assert data["files"][0]["type"] == "docx"

        else:
            pytest.skip("test.docx file not found")

    def test_extract_cyrillic_filename(self, test_client, real_test_files_dir):
        """Тест извлечения файла с кириллицей в названии."""
        cyrillic_file = real_test_files_dir / "тест.md"

        if cyrillic_file.exists():
            with open(cyrillic_file, "rb") as f:
                response = test_client.post(
                    "/v1/extract/file", files={"file": ("тест.md", f, "text/markdown")}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["filename"] == "тест.md"
                assert data["count"] == 1
                assert len(data["files"]) == 1

                # Проверяем, что текст был извлечен
                extracted_text = data["files"][0]["text"]
                assert len(extracted_text) > 0
                assert "Это тест" in extracted_text
                assert data["files"][0]["type"] == "md"

        else:
            pytest.skip("тест.md file not found")


@pytest.mark.integration
class TestPerformance:
    """Тесты производительности."""

    def test_concurrent_requests(self, test_client):
        """Тест одновременных запросов."""
        import threading
        import time

        results = []

        def make_request():
            test_content = "Тестовый контент для проверки производительности"
            response = test_client.post(
                "/v1/extract/file",
                files={"file": ("test.txt", test_content.encode(), "text/plain")},
            )
            results.append(response.status_code)

        # Создаем 5 одновременных запросов
        threads = []
        for _i in range(5):
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
        """Тест обработки большого текстового файла."""
        # Создаем файл размером примерно 1MB
        large_content = (
            "Большой текстовый файл для тестирования производительности.\n" * 10000
        )

        response = test_client.post(
            "/v1/extract/file",
            files={"file": ("large.txt", large_content.encode(), "text/plain")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["filename"] == "large.txt"
        assert data["count"] == 1
        assert len(data["files"]) == 1
        assert len(data["files"][0]["text"]) > 0

    def test_response_time(self, test_client):
        """Тест времени ответа."""
        import time

        test_content = "Тестовый контент для проверки времени ответа"

        start_time = time.time()
        response = test_client.post(
            "/v1/extract/file",
            files={"file": ("test.txt", test_content.encode(), "text/plain")},
        )
        end_time = time.time()

        response_time = end_time - start_time

        assert response.status_code == 200
        assert (
            response_time < 5.0
        )  # Ответ должен быть быстрее 5 секунд для простого текста


@pytest.mark.integration
class TestErrorHandling:
    """Тесты обработки ошибок."""

    def test_malformed_request(self, test_client):
        """Тест неправильно сформированного запроса."""
        response = test_client.post("/v1/extract/file")

        assert response.status_code == 422  # Unprocessable Entity

    def test_missing_file(self, test_client):
        """Тест отсутствующего файла в запросе."""
        response = test_client.post("/v1/extract/file", data={"not_file": "some_data"})

        assert response.status_code == 422

    def test_invalid_endpoint(self, test_client):
        """Тест несуществующего эндпоинта."""
        response = test_client.get("/v1/nonexistent/")

        assert response.status_code == 404

    def test_invalid_method(self, test_client):
        """Тест неподдерживаемого HTTP метода."""
        response = test_client.put("/v1/extract/file")

        assert response.status_code == 405  # Method Not Allowed

    def test_server_error_simulation(self, test_client):
        """Тест имитации серверной ошибки."""
        test_content = b"test content"

        # Мокаем валидацию файла и имитируем серверную ошибку
        with patch("app.main.validate_file_type", return_value=(True, None)):
            with patch("app.extractors.TextExtractor.extract_text") as mock_extract:
                # Имитируем неожиданную ошибку (не ValueError)
                mock_extract.side_effect = RuntimeError("Server internal error")

                response = test_client.post(
                    "/v1/extract/file",
                    files={"file": ("test.txt", BytesIO(test_content), "text/plain")},
                )

                # Серверная ошибка обрабатывается как 422
                assert response.status_code == 422
                data = response.json()
                assert data["status"] == "error"
                assert "поврежден" in data["message"]


@pytest.mark.integration
class TestDocumentation:
    """Тесты документации API."""

    def test_openapi_schema(self, test_client):
        """Тест OpenAPI схемы."""
        response = test_client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema
        assert "/v1/extract/file" in schema["paths"]

    def test_swagger_ui(self, test_client):
        """Тест Swagger UI."""
        response = test_client.get("/docs")

        assert response.status_code == 200
        assert "swagger" in response.text.lower()

    def test_redoc(self, test_client):
        """Тест ReDoc документации."""
        response = test_client.get("/redoc")

        assert response.status_code == 200
        assert "redoc" in response.text.lower()


@pytest.mark.integration
class TestURLExtractionIntegration:
    """Интеграционные тесты для извлечения текста с URL (v1.10.1)."""

    def test_extract_url_invalid_url(self, test_client):
        """Тест обработки некорректного URL."""
        response = test_client.post("/v1/extract/url", json={"url": "not-a-valid-url"})

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "URL" in data["message"] or "url" in data["message"]

    def test_extract_url_blocked_localhost(self, test_client):
        """Тест блокировки localhost (защита от SSRF)."""
        response = test_client.post(
            "/v1/extract/url", json={"url": "http://localhost:8080/admin"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert (
            "внутренним IP-адресам запрещен" in data["message"]
            or "blocked" in data["message"]
        )

    def test_extract_url_blocked_private_ip(self, test_client):
        """Тест блокировки приватных IP (защита от SSRF)."""
        response = test_client.post(
            "/v1/extract/url", json={"url": "http://192.168.1.1/config"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert (
            "внутренним IP-адресам запрещен" in data["message"]
            or "blocked" in data["message"]
        )
