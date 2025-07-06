"""
Модуль для извлечения текста из файлов различных форматов
"""

import asyncio
import io
import logging
import zipfile
import tarfile
from typing import Optional, List, Dict, Any
import tempfile
import os
import shutil
import xml.etree.ElementTree as ET
import subprocess
import time
from pathlib import Path
from fastapi import BackgroundTasks
import concurrent.futures
import threading

# Импорты для архивов
try:
    import rarfile
except ImportError:
    rarfile = None

try:
    import py7zr
except ImportError:
    py7zr = None

# Импорты для различных форматов
try:
    import PyPDF2
    import pdfplumber
except ImportError:
    PyPDF2 = None
    pdfplumber = None

try:
    from docx import Document
except ImportError:
    Document = None

# Для .doc файлов используем antiword через subprocess
import subprocess

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None

try:
    from pptx import Presentation
except ImportError:
    Presentation = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import markdown
except ImportError:
    markdown = None

try:
    from odf.opendocument import load
    from odf.text import P
    from odf.teletype import extractText
except ImportError:
    load = None
    P = None
    extractText = None

try:
    from striprtf.striprtf import rtf_to_text
except ImportError:
    rtf_to_text = None

try:
    import yaml
except ImportError:
    yaml = None

from app.config import settings
from app.utils import get_file_extension, is_supported_format, is_archive_format

logger = logging.getLogger(__name__)


class TextExtractor:
    """Класс для извлечения текста из файлов различных форматов"""
    
    def __init__(self):
        self.ocr_languages = settings.OCR_LANGUAGES
        self.timeout = settings.PROCESSING_TIMEOUT_SECONDS
        # Создаем пул потоков для CPU-bound операций
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        
    async def extract_text(self, file_content: bytes, filename: str) -> List[Dict[str, Any]]:
        """Основной метод извлечения текста"""
        
        # Проверка, является ли файл архивом
        if is_archive_format(filename, settings.SUPPORTED_FORMATS):
            return await self._extract_from_archive(file_content, filename)
        
        # Проверка поддержки формата
        if not is_supported_format(filename, settings.SUPPORTED_FORMATS):
            raise ValueError(f"Unsupported file format: {filename}")
        
        # Проверка MIME-типа для безопасности (синхронная операция)
        loop = asyncio.get_event_loop()
        is_valid_mime = await loop.run_in_executor(
            self._thread_pool,
            self._check_mime_type,
            file_content,
            filename
        )
        
        if not is_valid_mime:
            logger.warning(f"MIME-тип файла {filename} не соответствует расширению")
            # Не блокируем, но предупреждаем
        
        extension = get_file_extension(filename)
        
        try:
            # Выполнение извлечения с таймаутом в отдельном потоке
            text = await asyncio.wait_for(
                self._extract_text_by_format(file_content, extension, filename),
                timeout=self.timeout
            )
            
            # Возвращаем массив с одним элементом для единообразия
            return [{
                "filename": filename,
                "path": filename,
                "size": len(file_content),
                "type": extension,
                "text": text.strip() if text else ""
            }]
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout при обработке файла {filename}")
            raise ValueError("Processing timeout exceeded")
        except Exception as e:
            logger.error(f"Ошибка при извлечении текста из {filename}: {str(e)}")
            raise ValueError(f"Error extracting text: {str(e)}")
    
    async def _extract_text_by_format(self, content: bytes, extension: str, filename: str) -> str:
        """Извлечение текста в зависимости от формата"""
        
        # Проверяем, является ли файл исходным кодом
        source_code_extensions = settings.SUPPORTED_FORMATS.get("source_code", [])
        
        loop = asyncio.get_event_loop()
        
        if extension == "pdf":
            return await loop.run_in_executor(self._thread_pool, self._extract_from_pdf_sync, content)
        elif extension in ["docx"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_docx_sync, content)
        elif extension in ["doc"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_doc_sync, content)
        elif extension in ["xls", "xlsx"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_excel_sync, content)
        elif extension in ["csv"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_csv_sync, content)
        elif extension in ["pptx"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_pptx_sync, content)
        elif extension in ["ppt"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_ppt_sync, content)
        elif extension in ["jpg", "jpeg", "png", "tiff", "tif", "bmp", "gif"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_image_sync, content)
        elif extension in source_code_extensions:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_source_code_sync, content, extension, filename)
        elif extension in ["txt"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_txt_sync, content)
        elif extension in ["html", "htm"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_html_sync, content)
        elif extension in ["md", "markdown"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_markdown_sync, content)
        elif extension in ["json"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_json_sync, content)
        elif extension in ["rtf"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_rtf_sync, content)
        elif extension in ["odt"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_odt_sync, content)
        elif extension in ["xml"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_xml_sync, content)
        elif extension in ["yaml", "yml"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_yaml_sync, content)
        elif extension in ["epub"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_epub_sync, content)
        elif extension in ["eml"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_eml_sync, content)
        elif extension in ["msg"]:
            return await loop.run_in_executor(self._thread_pool, self._extract_from_msg_sync, content)
        else:
            # Попытка извлечения как обычный текст
            return await loop.run_in_executor(self._thread_pool, self._extract_from_txt_sync, content)
    
    def _extract_from_pdf_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из PDF"""
        if not pdfplumber:
            raise ImportError("pdfplumber не установлен")
        
        text_parts = []
        
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            with pdfplumber.open(temp_file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    # Извлечение текста со страницы
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"[Страница {page_num}]\n{page_text}")
                    
                    # Извлечение изображений и OCR
                    if page.images:
                        text_parts.append("--- OCR ---")
                        for img_idx, img in enumerate(page.images):
                            try:
                                # Попытка извлечения изображения и OCR
                                image_text = self._ocr_from_pdf_image_sync(page, img)
                                if image_text.strip():
                                    text_parts.append(f"[Изображение {img_idx + 1}]\n{image_text}")
                            except Exception as e:
                                logger.warning(f"Ошибка OCR изображения {img_idx + 1}: {str(e)}")
                        text_parts.append("---")
            
            os.unlink(temp_file_path)
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке PDF: {str(e)}")
            raise ValueError(f"Error processing PDF: {str(e)}")
    
    async def _extract_from_pdf(self, content: bytes) -> str:
        """Извлечение текста из PDF"""
        if not pdfplumber:
            raise ImportError("pdfplumber не установлен")
        
        text_parts = []
        
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            with pdfplumber.open(temp_file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    # Извлечение текста со страницы
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"[Страница {page_num}]\n{page_text}")
                    
                    # Извлечение изображений и OCR
                    if page.images:
                        text_parts.append("--- OCR ---")
                        for img_idx, img in enumerate(page.images):
                            try:
                                # Попытка извлечения изображения и OCR
                                image_text = await self._ocr_from_pdf_image(page, img)
                                if image_text.strip():
                                    text_parts.append(f"[Изображение {img_idx + 1}]\n{image_text}")
                            except Exception as e:
                                logger.warning(f"Ошибка OCR изображения {img_idx + 1}: {str(e)}")
                        text_parts.append("---")
            
            os.unlink(temp_file_path)
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке PDF: {str(e)}")
            raise ValueError(f"Error processing PDF: {str(e)}")
    
    def _ocr_from_pdf_image_sync(self, page, img_info) -> str:
        """Синхронный OCR изображения из PDF"""
        if not pytesseract or not Image:
            return ""
        
        try:
            # Получаем координаты изображения
            x0, y0, x1, y1 = img_info['x0'], img_info['y0'], img_info['x1'], img_info['y1']
            
            # Обрезаем область изображения из всей страницы
            cropped_bbox = (x0, y0, x1, y1)
            cropped_page = page.crop(cropped_bbox)
            
            # Конвертируем обрезанную область в изображение с высоким разрешением
            img_pil = cropped_page.to_image(resolution=300)
            
            # Применяем OCR к извлеченному изображению
            text = pytesseract.image_to_string(img_pil, lang=self.ocr_languages)
            
            return text.strip() if text else ""
            
        except Exception as e:
            logger.warning(f"Ошибка OCR изображения: {str(e)}")
            # Альтернативный подход - рендерим всю страницу и обрезаем
            try:
                # Конвертируем всю страницу в изображение PIL
                page_image = page.to_image(resolution=300)
                pil_image = page_image.original  # Получаем PIL изображение
                
                # Вычисляем координаты в пикселях (учитывая resolution=300)
                scale = 300 / 72  # PDF обычно 72 DPI, мы рендерим в 300 DPI
                pixel_bbox = (
                    int(x0 * scale),
                    int(y0 * scale), 
                    int(x1 * scale),
                    int(y1 * scale)
                )
                
                # Обрезаем область изображения
                cropped_img = pil_image.crop(pixel_bbox)
                
                # Применяем OCR
                text = pytesseract.image_to_string(cropped_img, lang=self.ocr_languages)
                
                return text.strip() if text else ""
                
            except Exception as e2:
                logger.warning(f"Альтернативная попытка OCR также не удалась: {str(e2)}")
                return ""
    
    async def _ocr_from_pdf_image(self, page, img_info) -> str:
        """OCR изображения из PDF"""
        if not pytesseract or not Image:
            return ""
        
        try:
            # Получаем координаты изображения
            x0, y0, x1, y1 = img_info['x0'], img_info['y0'], img_info['x1'], img_info['y1']
            
            # Обрезаем область изображения из всей страницы
            cropped_bbox = (x0, y0, x1, y1)
            cropped_page = page.crop(cropped_bbox)
            
            # Конвертируем обрезанную область в изображение с высоким разрешением
            img_pil = cropped_page.to_image(resolution=300)
            
            # Применяем OCR к извлеченному изображению
            text = pytesseract.image_to_string(img_pil, lang=self.ocr_languages)
            
            return text.strip() if text else ""
            
        except Exception as e:
            logger.warning(f"Ошибка OCR изображения: {str(e)}")
            # Альтернативный подход - рендерим всю страницу и обрезаем
            try:
                # Конвертируем всю страницу в изображение PIL
                page_image = page.to_image(resolution=300)
                pil_image = page_image.original  # Получаем PIL изображение
                
                # Вычисляем координаты в пикселях (учитывая resolution=300)
                scale = 300 / 72  # PDF обычно 72 DPI, мы рендерим в 300 DPI
                pixel_bbox = (
                    int(x0 * scale),
                    int(y0 * scale), 
                    int(x1 * scale),
                    int(y1 * scale)
                )
                
                # Обрезаем область изображения
                cropped_img = pil_image.crop(pixel_bbox)
                
                # Применяем OCR
                text = pytesseract.image_to_string(cropped_img, lang=self.ocr_languages)
                
                return text.strip() if text else ""
                
            except Exception as e2:
                logger.warning(f"Альтернативная попытка OCR также не удалась: {str(e2)}")
                return ""
    
    def _extract_from_docx_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из DOCX"""
        if not Document:
            raise ImportError("python-docx не установлен")
        
        try:
            doc = Document(io.BytesIO(content))
            text_parts = []
            
            # Основной текст
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text_parts.append(paragraph.text)
            
            # Таблицы
            for table in doc.tables:
                table_text = []
                for row in table.rows:
                    row_text = []
                    for cell in row.cells:
                        row_text.append(cell.text.strip())
                    table_text.append("\t".join(row_text))
                
                if table_text:
                    text_parts.append("\n".join(table_text))
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке DOCX: {str(e)}")
            raise ValueError(f"Error processing DOCX: {str(e)}")
    
    def _extract_from_doc_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из DOC через конвертацию в DOCX с помощью LibreOffice"""
        if not Document:
            raise ImportError("python-docx не установлен")
        
        try:
            # Создаем временные файлы
            with tempfile.NamedTemporaryFile(suffix='.doc', delete=False) as temp_doc:
                temp_doc.write(content)
                temp_doc_path = temp_doc.name
            
            # Создаем временную директорию для вывода
            temp_dir = tempfile.mkdtemp()
            
            try:
                # Конвертируем .doc в .docx с помощью LibreOffice
                result = subprocess.run([
                    'libreoffice', '--headless', '--convert-to', 'docx',
                    '--outdir', temp_dir, temp_doc_path
                ], capture_output=True, text=True, timeout=30)
                
                if result.returncode != 0:
                    logger.error(f"LibreOffice conversion failed: {result.stderr}")
                    raise ValueError("Failed to convert DOC to DOCX")
                
                # Находим сконвертированный файл
                doc_filename = os.path.splitext(os.path.basename(temp_doc_path))[0]
                docx_path = os.path.join(temp_dir, f"{doc_filename}.docx")
                
                if not os.path.exists(docx_path):
                    raise ValueError("Converted DOCX file not found")
                
                # Читаем сконвертированный DOCX файл
                with open(docx_path, 'rb') as docx_file:
                    docx_content = docx_file.read()
                
                # Используем синхронный метод для извлечения текста из DOCX
                text = self._extract_from_docx_sync(docx_content)
                
                return text
                
            finally:
                # Очищаем временные файлы
                os.unlink(temp_doc_path)
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        except subprocess.TimeoutExpired:
            logger.error("LibreOffice conversion timeout")
            raise ValueError("DOC conversion timeout")
        except Exception as e:
            logger.error(f"Ошибка при обработке DOC: {str(e)}")
            raise ValueError(f"Error processing DOC: {str(e)}")
    
    def _extract_from_excel_sync(self, content: bytes) -> str:
        """Синхронное извлечение данных из Excel файлов"""
        if not pd:
            raise ImportError("pandas не установлен")
        
        try:
            excel_data = pd.read_excel(io.BytesIO(content), sheet_name=None)
            text_parts = []
            
            for sheet_name, df in excel_data.items():
                text_parts.append(f"[Лист: {sheet_name}]")
                text_parts.append(df.to_csv(index=False))
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке Excel: {str(e)}")
            raise ValueError(f"Error processing Excel: {str(e)}")
    
    def _extract_from_csv_sync(self, content: bytes) -> str:
        """Синхронное извлечение данных из CSV файлов"""
        if not pd:
            raise ImportError("pandas не установлен")
        
        try:
            df = pd.read_csv(io.BytesIO(content))
            return df.to_csv(index=False)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке CSV: {str(e)}")
            raise ValueError(f"Error processing CSV: {str(e)}")
    
    def _extract_from_pptx_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из PPTX"""
        if not Presentation:
            raise ImportError("python-pptx не установлен")
        
        try:
            prs = Presentation(io.BytesIO(content))
            text_parts = []
            
            for slide_num, slide in enumerate(prs.slides, 1):
                slide_text = []
                slide_text.append(f"[Слайд {slide_num}]")
                
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        slide_text.append(shape.text)
                
                if len(slide_text) > 1:  # Больше чем просто заголовок слайда
                    text_parts.append("\n".join(slide_text))
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке PPTX: {str(e)}")
            raise ValueError(f"Error processing PPTX: {str(e)}")
    
    def _extract_from_ppt_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из PPT через конвертацию в PPTX с помощью LibreOffice"""
        if not Presentation:
            raise ImportError("python-pptx не установлен")
        
        try:
            # Создаем временные файлы
            with tempfile.NamedTemporaryFile(suffix='.ppt', delete=False) as temp_ppt:
                temp_ppt.write(content)
                temp_ppt_path = temp_ppt.name
            
            # Создаем временную директорию для вывода
            temp_dir = tempfile.mkdtemp()
            
            try:
                # Конвертируем .ppt в .pptx с помощью LibreOffice
                result = subprocess.run([
                    'libreoffice', '--headless', '--convert-to', 'pptx',
                    '--outdir', temp_dir, temp_ppt_path
                ], capture_output=True, text=True, timeout=30)
                
                if result.returncode != 0:
                    logger.error(f"LibreOffice conversion failed: {result.stderr}")
                    raise ValueError("Failed to convert PPT to PPTX")
                
                # Находим сконвертированный файл
                ppt_filename = os.path.splitext(os.path.basename(temp_ppt_path))[0]
                pptx_path = os.path.join(temp_dir, f"{ppt_filename}.pptx")
                
                if not os.path.exists(pptx_path):
                    raise ValueError("Converted PPTX file not found")
                
                # Читаем сконвертированный PPTX файл
                with open(pptx_path, 'rb') as pptx_file:
                    pptx_content = pptx_file.read()
                
                # Используем синхронный метод для извлечения текста из PPTX
                text = self._extract_from_pptx_sync(pptx_content)
                
                return text
                
            finally:
                # Очищаем временные файлы
                os.unlink(temp_ppt_path)
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        except subprocess.TimeoutExpired:
            logger.error("LibreOffice conversion timeout")
            raise ValueError("PPT conversion timeout")
        except Exception as e:
            logger.error(f"Ошибка при обработке PPT: {str(e)}")
            raise ValueError(f"Error processing PPT: {str(e)}")
    
    def _extract_from_txt_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из TXT файлов"""
        try:
            # Попытка декодирования в разных кодировках
            for encoding in ['utf-8', 'cp1251', 'latin-1']:
                try:
                    return content.decode(encoding)
                except UnicodeDecodeError:
                    continue
            
            # Если не удалось декодировать, используем замещение символов
            return content.decode('utf-8', errors='replace')
            
        except Exception as e:
            logger.error(f"Ошибка при обработке TXT: {str(e)}")
            raise ValueError(f"Error processing TXT: {str(e)}")
    
    def _extract_from_source_code_sync(self, content: bytes, extension: str, filename: str) -> str:
        """Синхронное извлечение текста из файлов исходного кода"""
        try:
            # Попытка декодирования в разных кодировках
            text = None
            for encoding in ['utf-8', 'cp1251', 'latin-1', 'koi8-r', 'windows-1251', 'cp866']:
                try:
                    text = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if text is None:
                # Если не удалось декодировать, используем замещение символов
                text = content.decode('utf-8', errors='replace')
            
            # Определение языка программирования по расширению
            language_map = {
                # Python
                'py': 'Python', 'pyx': 'Python', 'pyi': 'Python', 'pyw': 'Python',
                # JavaScript/TypeScript
                'js': 'JavaScript', 'jsx': 'JavaScript', 'ts': 'TypeScript', 'tsx': 'TypeScript',
                'mjs': 'JavaScript', 'cjs': 'JavaScript',
                # Java
                'java': 'Java', 'jav': 'Java',
                # C/C++
                'c': 'C', 'cpp': 'C++', 'cxx': 'C++', 'cc': 'C++', 'c++': 'C++',
                'h': 'C Header', 'hpp': 'C++ Header', 'hxx': 'C++ Header', 'h++': 'C++ Header',
                # C#
                'cs': 'C#', 'csx': 'C#',
                # PHP
                'php': 'PHP', 'php3': 'PHP', 'php4': 'PHP', 'php5': 'PHP', 'phtml': 'PHP',
                # Ruby
                'rb': 'Ruby', 'rbw': 'Ruby', 'rake': 'Ruby', 'gemspec': 'Ruby',
                # Go
                'go': 'Go', 'mod': 'Go Module', 'sum': 'Go Sum',
                # Rust
                'rs': 'Rust', 'rlib': 'Rust Library',
                # Swift
                'swift': 'Swift',
                # Kotlin
                'kt': 'Kotlin', 'kts': 'Kotlin Script',
                # Scala
                'scala': 'Scala', 'sc': 'Scala',
                # R
                'r': 'R', 'R': 'R', 'rmd': 'R Markdown', 'Rmd': 'R Markdown',
                # SQL
                'sql': 'SQL', 'ddl': 'SQL DDL', 'dml': 'SQL DML',
                # Shell
                'sh': 'Shell', 'bash': 'Bash', 'zsh': 'Zsh', 'fish': 'Fish',
                'ksh': 'Ksh', 'csh': 'Csh', 'tcsh': 'Tcsh',
                # PowerShell
                'ps1': 'PowerShell', 'psm1': 'PowerShell Module', 'psd1': 'PowerShell Data',
                # Perl
                'pl': 'Perl', 'pm': 'Perl Module', 'pod': 'Perl Documentation', 't': 'Perl Test',
                # Lua
                'lua': 'Lua',
                # 1C and OneScript
                'bsl': '1C:Enterprise', 'os': 'OneScript',
                # Configuration files
                'ini': 'INI Config', 'cfg': 'Config', 'conf': 'Config',
                'config': 'Config', 'toml': 'TOML', 'properties': 'Properties',
                # Web
                'css': 'CSS', 'scss': 'SCSS', 'sass': 'Sass', 'less': 'Less', 'styl': 'Stylus',
                # Markup
                'tex': 'LaTeX', 'latex': 'LaTeX', 'rst': 'reStructuredText',
                'adoc': 'AsciiDoc', 'asciidoc': 'AsciiDoc',
                # Data
                'jsonl': 'JSON Lines', 'ndjson': 'NDJSON', 'jsonc': 'JSON with Comments',
                # Docker
                'dockerfile': 'Dockerfile', 'containerfile': 'Containerfile',
                # Makefile
                'makefile': 'Makefile', 'mk': 'Makefile', 'mak': 'Makefile',
                # Git
                'gitignore': 'Git Ignore', 'gitattributes': 'Git Attributes',
                'gitmodules': 'Git Modules'
            }
            
            language = language_map.get(extension.lower(), 'Source Code')
            
            # Формирование заголовка с информацией о файле
            header = f"=== {language} File: {filename} ===\n"
            
            # Добавление информации о количестве строк
            lines = text.split('\n')
            line_count = len(lines)
            header += f"Lines: {line_count}\n"
            
            # Если файл слишком длинный, добавляем предупреждение
            if line_count > 1000:
                header += f"Warning: Large file with {line_count} lines\n"
            
            # Возвращаем заголовок + содержимое файла
            return header + "=" * 50 + "\n" + text
            
        except Exception as e:
            logger.error(f"Ошибка при обработке исходного кода {filename}: {str(e)}")
            raise ValueError(f"Error processing source code: {str(e)}")
    
    def _extract_from_html_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из HTML"""
        if not BeautifulSoup:
            raise ImportError("beautifulsoup4 не установлен")
        
        try:
            text = content.decode('utf-8', errors='replace')
            soup = BeautifulSoup(text, 'html.parser')
            
            # Удаление script и style тегов
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Получение текста
            text = soup.get_text()
            
            # Очистка от лишних пробелов
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            return '\n'.join(chunk for chunk in chunks if chunk)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке HTML: {str(e)}")
            raise ValueError(f"Error processing HTML: {str(e)}")
    
    def _extract_from_markdown_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из Markdown"""
        try:
            text = content.decode('utf-8', errors='replace')
            
            if markdown:
                # Конвертация в HTML и извлечение текста
                html = markdown.markdown(text)
                if BeautifulSoup:
                    soup = BeautifulSoup(html, 'html.parser')
                    return soup.get_text()
            
            # Если markdown не установлен, возвращаем как есть
            return text
            
        except Exception as e:
            logger.error(f"Ошибка при обработке Markdown: {str(e)}")
            raise ValueError(f"Error processing Markdown: {str(e)}")
    
    def _extract_from_json_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из JSON"""
        import json
        
        try:
            text = content.decode('utf-8', errors='replace')
            data = json.loads(text)
            
            # Рекурсивное извлечение всех строковых значений
            def extract_strings(obj, path=""):
                strings = []
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        new_path = f"{path}.{key}" if path else key
                        strings.extend(extract_strings(value, new_path))
                elif isinstance(obj, list):
                    for i, value in enumerate(obj):
                        new_path = f"{path}[{i}]" if path else f"[{i}]"
                        strings.extend(extract_strings(value, new_path))
                elif isinstance(obj, str):
                    if obj.strip():
                        strings.append(f"{path}: {obj}")
                return strings
            
            strings = extract_strings(data)
            return "\n".join(strings)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке JSON: {str(e)}")
            raise ValueError(f"Error processing JSON: {str(e)}")
    
    def _extract_from_rtf_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из RTF"""
        if not rtf_to_text:
            raise ImportError("striprtf не установлен")
        
        try:
            text = content.decode('utf-8', errors='replace')
            plain_text = rtf_to_text(text)
            return plain_text
            
        except Exception as e:
            logger.error(f"Ошибка при обработке RTF: {str(e)}")
            raise ValueError(f"Error processing RTF: {str(e)}")
    
    def _extract_from_xml_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из XML"""
        try:
            text = content.decode('utf-8', errors='replace')
            root = ET.fromstring(text)
            
            # Рекурсивное извлечение всех элементов и атрибутов
            def extract_from_element(elem, path=""):
                strings = []
                
                current_path = f"{path}.{elem.tag}" if path else elem.tag
                
                # Добавляем текст элемента
                if elem.text and elem.text.strip():
                    strings.append(f"{current_path}: {elem.text.strip()}")
                
                # Добавляем атрибуты
                for attr_name, attr_value in elem.attrib.items():
                    if attr_value.strip():
                        strings.append(f"{current_path}@{attr_name}: {attr_value}")
                
                # Рекурсивно обрабатываем дочерние элементы
                for child in elem:
                    strings.extend(extract_from_element(child, current_path))
                
                return strings
            
            strings = extract_from_element(root)
            return "\n".join(strings)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке XML: {str(e)}")
            raise ValueError(f"Error processing XML: {str(e)}")
    
    def _extract_from_yaml_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из YAML"""
        if not yaml:
            raise ImportError("PyYAML не установлен")
        
        try:
            text = content.decode('utf-8', errors='replace')
            data = yaml.safe_load(text)
            
            # Рекурсивное извлечение всех строковых значений
            def extract_strings(obj, path=""):
                strings = []
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        new_path = f"{path}.{key}" if path else key
                        strings.extend(extract_strings(value, new_path))
                elif isinstance(obj, list):
                    for i, value in enumerate(obj):
                        new_path = f"{path}[{i}]" if path else f"[{i}]"
                        strings.extend(extract_strings(value, new_path))
                elif isinstance(obj, str):
                    if obj.strip():
                        strings.append(f"{path}: {obj}")
                return strings
            
            strings = extract_strings(data)
            return "\n".join(strings)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке YAML: {str(e)}")
            raise ValueError(f"Error processing YAML: {str(e)}")
    
    def _extract_from_odt_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из ODT"""
        if not load:
            raise ImportError("odfpy не установлен")
        
        try:
            with tempfile.NamedTemporaryFile(suffix='.odt', delete=False) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            doc = load(temp_file_path)
            text_parts = []
            
            # Извлечение всех текстовых элементов
            for p in doc.getElementsByType(P):
                text = extractText(p)
                if text.strip():
                    text_parts.append(text)
            
            os.unlink(temp_file_path)
            
            return "\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке ODT: {str(e)}")
            raise ValueError(f"Error processing ODT: {str(e)}")
    
    def _extract_from_epub_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из EPUB"""
        if not BeautifulSoup:
            raise ImportError("beautifulsoup4 не установлен")
        
        try:
            text_parts = []
            extracted_size = 0
            
            with zipfile.ZipFile(io.BytesIO(content), 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    # Ограничиваем размер распакованного содержимого
                    if extracted_size + file_info.file_size > settings.MAX_EXTRACTED_SIZE:
                        logger.warning(f"Достигнут лимит размера распакованного содержимого EPUB")
                        break
                    
                    if file_info.filename.endswith(('.html', '.xhtml', '.htm')):
                        try:
                            html_content = zip_ref.read(file_info.filename)
                            html_text = html_content.decode('utf-8', errors='replace')
                            
                            # Парсинг HTML
                            soup = BeautifulSoup(html_text, 'html.parser')
                            
                            # Удаление script и style тегов
                            for script in soup(["script", "style"]):
                                script.decompose()
                            
                            # Извлечение текста
                            text = soup.get_text()
                            if text.strip():
                                text_parts.append(text.strip())
                            
                            extracted_size += file_info.file_size
                            
                        except Exception as e:
                            logger.warning(f"Ошибка при обработке файла {file_info.filename}: {e}")
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке EPUB: {str(e)}")
            raise ValueError(f"Error processing EPUB: {str(e)}")
    
    def _extract_from_eml_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из EML"""
        import email
        from email.header import decode_header
        
        try:
            # Попытка декодирования в разных кодировках
            msg_text = None
            for encoding in ['utf-8', 'cp1251', 'latin-1']:
                try:
                    msg_text = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if msg_text is None:
                msg_text = content.decode('utf-8', errors='replace')
            
            msg = email.message_from_string(msg_text)
            text_parts = []
            
            # Извлечение заголовков
            headers = ['From', 'To', 'Subject', 'Date']
            for header in headers:
                value = msg.get(header)
                if value:
                    # Декодирование заголовка
                    decoded_parts = decode_header(value)
                    decoded_value = ''
                    for part, encoding in decoded_parts:
                        if isinstance(part, bytes):
                            if encoding:
                                decoded_value += part.decode(encoding)
                            else:
                                decoded_value += part.decode('utf-8', errors='replace')
                        else:
                            decoded_value += part
                    
                    text_parts.append(f"{header}: {decoded_value}")
            
            text_parts.append("---")
            
            # Извлечение тела письма
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type in ['text/plain', 'text/html']:
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                # Определение кодировки
                                charset = part.get_content_charset() or 'utf-8'
                                try:
                                    body_text = payload.decode(charset)
                                except UnicodeDecodeError:
                                    body_text = payload.decode('utf-8', errors='replace')
                                
                                # Обработка HTML
                                if content_type == 'text/html' and BeautifulSoup:
                                    soup = BeautifulSoup(body_text, 'html.parser')
                                    body_text = soup.get_text()
                                
                                if body_text.strip():
                                    text_parts.append(body_text)
                        except Exception as e:
                            logger.warning(f"Ошибка при обработке части письма: {e}")
            else:
                # Простое письмо
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        charset = msg.get_content_charset() or 'utf-8'
                        try:
                            body_text = payload.decode(charset)
                        except UnicodeDecodeError:
                            body_text = payload.decode('utf-8', errors='replace')
                        
                        if body_text.strip():
                            text_parts.append(body_text)
                except Exception as e:
                    logger.warning(f"Ошибка при обработке тела письма: {e}")
            
            if text_parts:
                return "\n".join(text_parts)
            else:
                return "Не удалось извлечь читаемый текст из EML файла"
                 
        except Exception as e:
            logger.error(f"Ошибка при обработке EML: {str(e)}")
            raise ValueError(f"Error processing EML: {str(e)}")
    
    def _extract_from_msg_sync(self, content: bytes) -> str:
        """Синхронное извлечение текста из MSG"""
        try:
            # Простая эвристика для MSG файлов
            # MSG файлы содержат текст в Unicode и могут содержать различные блоки данных
            
            # Попытка найти текстовые данные в файле
            text_parts = []
            
            # Конвертация в строку и поиск читаемых фрагментов
            try:
                # Попытка декодирования как UTF-16 (часто используется в MSG)
                text = content.decode('utf-16le', errors='ignore')
                
                # Фильтрация и очистка
                lines = text.split('\n')
                clean_lines = []
                
                for line in lines:
                    # Убираем нулевые байты и управляющие символы
                    clean_line = ''.join(char for char in line if ord(char) >= 32 or char in '\t\n\r')
                    clean_line = clean_line.strip()
                    
                    # Пропускаем слишком короткие или бессмысленные строки
                    if len(clean_line) > 3 and not clean_line.startswith(('_', '\x00')):
                        # Проверяем, что строка содержит буквы
                        if any(c.isalpha() for c in clean_line):
                            clean_lines.append(clean_line)
                
                # Удаление дубликатов и объединение
                unique_lines = []
                seen = set()
                for line in clean_lines:
                    if line not in seen and len(line) > 5:  # Минимальная длина
                        unique_lines.append(line)
                        seen.add(line)
                
                if unique_lines:
                    text_parts.extend(unique_lines)
                
            except Exception as e:
                logger.warning(f"Ошибка при декодировании UTF-16: {e}")
            
            # Альтернативный подход - поиск ASCII текста
            try:
                # Извлечение ASCII текста
                ascii_text = content.decode('ascii', errors='ignore')
                lines = ascii_text.split('\n')
                
                for line in lines:
                    clean_line = line.strip()
                    if len(clean_line) > 10 and any(c.isalpha() for c in clean_line):
                        if clean_line not in text_parts:
                            text_parts.append(clean_line)
                
            except Exception as e:
                logger.warning(f"Ошибка при извлечении ASCII: {e}")
            
            if text_parts:
                return "\n".join(text_parts)
            else:
                return "Не удалось извлечь читаемый текст из MSG файла"
                 
        except Exception as e:
            logger.error(f"Ошибка при обработке MSG: {str(e)}")
            raise ValueError(f"Error processing MSG: {str(e)}")
    
    def _extract_from_image_sync(self, content: bytes) -> str:
        """Синхронный OCR изображения"""
        if not pytesseract or not Image:
            raise ImportError("pytesseract или PIL не установлены")
        
        try:
            image = Image.open(io.BytesIO(content))
            # OCR на русском и английском языках
            text = pytesseract.image_to_string(image, lang=self.ocr_languages)
            return text.strip()
            
        except Exception as e:
            logger.error(f"Ошибка при OCR изображения: {str(e)}")
            raise ValueError(f"Error processing image: {str(e)}")
    
    def _check_mime_type(self, content: bytes, filename: str) -> bool:
        """Проверка MIME-типа файла для предотвращения подделки расширений"""
        import mimetypes
        
        try:
            # Определяем MIME-тип по содержимому (первые байты)
            mime_signatures = {
                b'\x50\x4B\x03\x04': ['application/zip', 'application/epub+zip', 'application/vnd.openxmlformats'],
                b'\x50\x4B\x07\x08': ['application/zip', 'application/epub+zip'],
                b'\x50\x4B\x05\x06': ['application/zip', 'application/epub+zip'],
                b'%PDF': ['application/pdf'],
                b'\xD0\xCF\x11\xE0': ['application/msword', 'application/vnd.ms-excel', 'application/vnd.ms-powerpoint'],
                b'\x89PNG': ['image/png'],
                b'\xFF\xD8\xFF': ['image/jpeg'],
                b'GIF8': ['image/gif'],
                b'BM': ['image/bmp'],
                b'II*\x00': ['image/tiff'],
                b'MM\x00*': ['image/tiff'],
                b'<!DOCTYPE': ['text/html'],
                b'<html': ['text/html'],
                b'<?xml': ['text/xml', 'application/xml'],
            }
            
            # Проверяем сигнатуру файла
            file_start = content[:10]
            detected_mime = None
            
            for signature, mime_types in mime_signatures.items():
                if file_start.startswith(signature):
                    detected_mime = mime_types[0]
                    break
            
            # Определяем ожидаемый MIME-тип по расширению
            expected_mime, _ = mimetypes.guess_type(filename)
            
            # Если не можем определить MIME-тип, разрешаем
            if not detected_mime or not expected_mime:
                return True
                
            # Проверяем соответствие
            return detected_mime in mime_signatures.get(file_start[:4], [expected_mime])
            
        except Exception as e:
            logger.warning(f"Ошибка при проверке MIME-типа: {str(e)}")
            return True  # В случае ошибки разрешаем обработку

    async def _extract_from_archive(self, content: bytes, filename: str, nesting_level: int = 0) -> List[Dict[str, Any]]:
        """Безопасное извлечение файлов из архива"""
        
        # Проверка глубины вложенности
        if nesting_level >= settings.MAX_ARCHIVE_NESTING:
            logger.warning(f"Превышена максимальная глубина вложенности архивов: {filename}")
            raise ValueError("Maximum archive nesting level exceeded")
        
        # Проверка размера архива
        if len(content) > settings.MAX_ARCHIVE_SIZE:
            logger.warning(f"Архив {filename} слишком большой: {len(content)} байт")
            raise ValueError("Archive size exceeds maximum allowed size")
        
        extension = get_file_extension(filename)
        logger.info(f"Обработка архива {filename} (тип: {extension}, размер: {len(content)} байт)")
        
        extracted_files = []
        
        # Создаем временную директорию для безопасной работы
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            archive_path = temp_path / f"archive_{int(time.time())}.{extension}"
            
            try:
                # Записываем архив во временный файл
                with open(archive_path, 'wb') as f:
                    f.write(content)
                
                # Извлекаем файлы в зависимости от типа архива
                extract_dir = temp_path / "extracted"
                extract_dir.mkdir(exist_ok=True)
                
                if extension == "zip":
                    extracted_files = await self._extract_zip_files(archive_path, extract_dir, filename, nesting_level)
                elif extension in ["tar", "gz", "bz2", "xz", "tar.gz", "tar.bz2", "tar.xz", "tgz", "tbz2", "txz"]:
                    extracted_files = await self._extract_tar_files(archive_path, extract_dir, filename, nesting_level)
                elif extension == "rar":
                    extracted_files = await self._extract_rar_files(archive_path, extract_dir, filename, nesting_level)
                elif extension == "7z":
                    extracted_files = await self._extract_7z_files(archive_path, extract_dir, filename, nesting_level)
                else:
                    raise ValueError(f"Unsupported archive format: {extension}")
                
                logger.info(f"Успешно обработано {len(extracted_files)} файлов из архива {filename}")
                return extracted_files
                
            except Exception as e:
                logger.error(f"Ошибка при обработке архива {filename}: {str(e)}")
                raise ValueError(f"Error processing archive: {str(e)}")
    
    async def _extract_zip_files(self, archive_path: Path, extract_dir: Path, archive_name: str, nesting_level: int) -> List[Dict[str, Any]]:
        """Извлечение файлов из ZIP-архива"""
        extracted_files = []
        total_size = 0
        
        try:
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                # Проверяем размер распакованных файлов
                for info in zip_ref.infolist():
                    if info.is_dir():
                        continue
                    total_size += info.file_size
                    
                    if total_size > settings.MAX_EXTRACTED_SIZE:
                        raise ValueError("Extracted files size exceeds maximum allowed size (zip bomb protection)")
                
                # Извлекаем файлы
                for info in zip_ref.infolist():
                    if info.is_dir():
                        continue
                    
                    # Санитизируем имя файла
                    safe_filename = self._sanitize_archive_filename(info.filename)
                    if not safe_filename:
                        continue
                    
                    # Фильтруем системные файлы
                    if self._is_system_file(safe_filename):
                        continue
                    
                    # Создаем безопасный путь для извлечения
                    safe_path = extract_dir / safe_filename
                    safe_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    try:
                        # Извлекаем файл
                        with zip_ref.open(info) as source, open(safe_path, 'wb') as target:
                            shutil.copyfileobj(source, target)
                        
                        # Обрабатываем файл
                        file_content = safe_path.read_bytes()
                        file_result = await self._process_extracted_file(
                            file_content, safe_filename, safe_path.name, archive_name, nesting_level
                        )
                        
                        if file_result:
                            extracted_files.extend(file_result)
                            
                    except Exception as e:
                        logger.warning(f"Ошибка при обработке файла {safe_filename} из архива {archive_name}: {str(e)}")
                        continue
                
        except zipfile.BadZipFile:
            raise ValueError("Invalid ZIP file")
        
        return extracted_files
    
    async def _extract_tar_files(self, archive_path: Path, extract_dir: Path, archive_name: str, nesting_level: int) -> List[Dict[str, Any]]:
        """Извлечение файлов из TAR-архива"""
        extracted_files = []
        total_size = 0
        
        try:
            with tarfile.open(archive_path, 'r:*') as tar_ref:
                # Проверяем размер распакованных файлов
                for member in tar_ref.getmembers():
                    if member.isfile():
                        total_size += member.size
                        
                        if total_size > settings.MAX_EXTRACTED_SIZE:
                            raise ValueError("Extracted files size exceeds maximum allowed size (tar bomb protection)")
                
                # Извлекаем файлы
                for member in tar_ref.getmembers():
                    if not member.isfile():
                        continue
                    
                    # Санитизируем имя файла
                    safe_filename = self._sanitize_archive_filename(member.name)
                    if not safe_filename:
                        continue
                    
                    # Фильтруем системные файлы
                    if self._is_system_file(safe_filename):
                        continue
                    
                    # Создаем безопасный путь для извлечения
                    safe_path = extract_dir / safe_filename
                    safe_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    try:
                        # Извлекаем файл
                        with tar_ref.extractfile(member) as source, open(safe_path, 'wb') as target:
                            if source:
                                shutil.copyfileobj(source, target)
                        
                        # Обрабатываем файл
                        file_content = safe_path.read_bytes()
                        file_result = await self._process_extracted_file(
                            file_content, safe_filename, safe_path.name, archive_name, nesting_level
                        )
                        
                        if file_result:
                            extracted_files.extend(file_result)
                            
                    except Exception as e:
                        logger.warning(f"Ошибка при обработке файла {safe_filename} из архива {archive_name}: {str(e)}")
                        continue
                
        except tarfile.TarError:
            raise ValueError("Invalid TAR file")
        
        return extracted_files
    
    async def _extract_rar_files(self, archive_path: Path, extract_dir: Path, archive_name: str, nesting_level: int) -> List[Dict[str, Any]]:
        """Извлечение файлов из RAR-архива"""
        if not rarfile:
            raise ValueError("RAR support not available. Install rarfile library.")
        
        extracted_files = []
        total_size = 0
        
        try:
            with rarfile.RarFile(archive_path, 'r') as rar_ref:
                # Проверяем размер распакованных файлов
                for info in rar_ref.infolist():
                    if info.is_dir():
                        continue
                    total_size += info.file_size
                    
                    if total_size > settings.MAX_EXTRACTED_SIZE:
                        raise ValueError("Extracted files size exceeds maximum allowed size (rar bomb protection)")
                
                # Извлекаем файлы
                for info in rar_ref.infolist():
                    if info.is_dir():
                        continue
                    
                    # Санитизируем имя файла
                    safe_filename = self._sanitize_archive_filename(info.filename)
                    if not safe_filename:
                        continue
                    
                    # Фильтруем системные файлы
                    if self._is_system_file(safe_filename):
                        continue
                    
                    # Создаем безопасный путь для извлечения
                    safe_path = extract_dir / safe_filename
                    safe_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    try:
                        # Извлекаем файл
                        with rar_ref.open(info) as source, open(safe_path, 'wb') as target:
                            shutil.copyfileobj(source, target)
                        
                        # Обрабатываем файл
                        file_content = safe_path.read_bytes()
                        file_result = await self._process_extracted_file(
                            file_content, safe_filename, safe_path.name, archive_name, nesting_level
                        )
                        
                        if file_result:
                            extracted_files.extend(file_result)
                            
                    except Exception as e:
                        logger.warning(f"Ошибка при обработке файла {safe_filename} из архива {archive_name}: {str(e)}")
                        continue
                
        except rarfile.RarError:
            raise ValueError("Invalid RAR file")
        
        return extracted_files
    
    async def _extract_7z_files(self, archive_path: Path, extract_dir: Path, archive_name: str, nesting_level: int) -> List[Dict[str, Any]]:
        """Извлечение файлов из 7Z-архива"""
        if not py7zr:
            raise ValueError("7Z support not available. Install py7zr library.")
        
        extracted_files = []
        total_size = 0
        
        try:
            with py7zr.SevenZipFile(archive_path, 'r') as sz_ref:
                # Проверяем размер распакованных файлов
                for info in sz_ref.list():
                    if info.is_dir:
                        continue
                    total_size += info.uncompressed
                    
                    if total_size > settings.MAX_EXTRACTED_SIZE:
                        raise ValueError("Extracted files size exceeds maximum allowed size (7z bomb protection)")
                
                # Извлекаем файлы
                sz_ref.extractall(extract_dir)
                
                # Обрабатываем извлеченные файлы
                for root, dirs, files in os.walk(extract_dir):
                    for file in files:
                        file_path = Path(root) / file
                        relative_path = file_path.relative_to(extract_dir)
                        
                        # Санитизируем имя файла
                        safe_filename = self._sanitize_archive_filename(str(relative_path))
                        if not safe_filename:
                            continue
                        
                        # Фильтруем системные файлы
                        if self._is_system_file(safe_filename):
                            continue
                        
                        try:
                            # Обрабатываем файл
                            file_content = file_path.read_bytes()
                            file_result = await self._process_extracted_file(
                                file_content, safe_filename, file_path.name, archive_name, nesting_level
                            )
                            
                            if file_result:
                                extracted_files.extend(file_result)
                                
                        except Exception as e:
                            logger.warning(f"Ошибка при обработке файла {safe_filename} из архива {archive_name}: {str(e)}")
                            continue
                
        except py7zr.Bad7zFile:
            raise ValueError("Invalid 7Z file")
        
        return extracted_files
    
    async def _process_extracted_file(self, content: bytes, filename: str, basename: str, archive_name: str, nesting_level: int) -> Optional[List[Dict[str, Any]]]:
        """Обработка извлеченного файла"""
        try:
            # Если файл является архивом, рекурсивно обрабатываем его
            if is_archive_format(basename, settings.SUPPORTED_FORMATS):
                return await self._extract_from_archive(content, basename, nesting_level + 1)
            
            # Если файл поддерживается, извлекаем текст
            if is_supported_format(basename, settings.SUPPORTED_FORMATS):
                extension = get_file_extension(basename)
                text = await self._extract_text_by_format(content, extension, basename)
                
                return [{
                    "filename": basename,
                    "path": f"{archive_name}/{filename}",
                    "size": len(content),
                    "type": extension,
                    "text": text.strip() if text else ""
                }]
            
            return None
            
        except Exception as e:
            logger.warning(f"Ошибка при обработке файла {filename}: {str(e)}")
            return None
    
    def _sanitize_archive_filename(self, filename: str) -> str:
        """Санитизация имени файла из архива"""
        if not filename:
            return ""
        
        # Удаляем опасные пути
        filename = filename.replace('..', '').replace('\\', '/').strip('/')
        
        # Проверяем на абсолютные пути
        if filename.startswith('/'):
            filename = filename[1:]
        
        # Удаляем пустые части пути
        parts = [part for part in filename.split('/') if part and part != '.']
        
        if not parts:
            return ""
        
        return '/'.join(parts)
    
    def _is_system_file(self, filename: str) -> bool:
        """Проверка, является ли файл системным"""
        system_files = [
            '.DS_Store', 'Thumbs.db', '.git/', '.svn/', '.hg/',
            '__MACOSX/', '.localized', 'desktop.ini', 'folder.ini'
        ]
        
        filename_lower = filename.lower()
        for system_file in system_files:
            if system_file in filename_lower:
                return True
        
        return False