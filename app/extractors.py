"""
Модуль для извлечения текста из файлов различных форматов
"""

import asyncio
import io
import logging
import zipfile
from typing import Optional, List
import tempfile
import os
import shutil
import xml.etree.ElementTree as ET

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
from app.utils import get_file_extension, is_supported_format

logger = logging.getLogger(__name__)


class TextExtractor:
    """Класс для извлечения текста из файлов различных форматов"""
    
    def __init__(self):
        self.ocr_languages = settings.OCR_LANGUAGES
        self.timeout = settings.PROCESSING_TIMEOUT_SECONDS
        
    async def extract_text(self, file_content: bytes, filename: str) -> str:
        """Основной метод извлечения текста"""
        
        # Проверка поддержки формата
        if not is_supported_format(filename, settings.SUPPORTED_FORMATS):
            raise ValueError(f"Unsupported file format: {filename}")
        
        # Проверка MIME-типа для безопасности
        if not self._check_mime_type(file_content, filename):
            logger.warning(f"MIME-тип файла {filename} не соответствует расширению")
            # Не блокируем, но предупреждаем
        
        extension = get_file_extension(filename)
        
        try:
            # Выполнение извлечения с таймаутом
            text = await asyncio.wait_for(
                self._extract_text_by_format(file_content, extension, filename),
                timeout=self.timeout
            )
            
            return text.strip() if text else ""
            
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
        
        if extension == "pdf":
            return await self._extract_from_pdf(content)
        elif extension in ["docx"]:
            return await self._extract_from_docx(content)
        elif extension in ["doc"]:
            return await self._extract_from_doc(content)
        elif extension in ["xls", "xlsx"]:
            return await self._extract_from_excel(content)
        elif extension in ["csv"]:
            return await self._extract_from_csv(content)
        elif extension in ["pptx"]:
            return await self._extract_from_pptx(content)
        elif extension in ["ppt"]:
            return await self._extract_from_ppt(content)
        elif extension in ["jpg", "jpeg", "png", "tiff", "tif", "bmp", "gif"]:
            return await self._extract_from_image(content)
        elif extension in source_code_extensions:
            return await self._extract_from_source_code(content, extension, filename)
        elif extension in ["txt"]:
            return await self._extract_from_txt(content)
        elif extension in ["html", "htm"]:
            return await self._extract_from_html(content)
        elif extension in ["md", "markdown"]:
            return await self._extract_from_markdown(content)
        elif extension in ["json"]:
            return await self._extract_from_json(content)
        elif extension in ["rtf"]:
            return await self._extract_from_rtf(content)
        elif extension in ["odt"]:
            return await self._extract_from_odt(content)
        elif extension in ["xml"]:
            return await self._extract_from_xml(content)
        elif extension in ["yaml", "yml"]:
            return await self._extract_from_yaml(content)
        elif extension in ["epub"]:
            return await self._extract_from_epub(content)
        elif extension in ["eml"]:
            return await self._extract_from_eml(content)
        elif extension in ["msg"]:
            return await self._extract_from_msg(content)
        else:
            # Попытка извлечения как обычный текст
            return await self._extract_from_txt(content)
    
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
    
    async def _extract_from_docx(self, content: bytes) -> str:
        """Извлечение текста из DOCX"""
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
    
    async def _extract_from_doc(self, content: bytes) -> str:
        """Извлечение текста из DOC через конвертацию в DOCX с помощью LibreOffice"""
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
                
                # Используем существующий метод для извлечения текста из DOCX
                text = await self._extract_from_docx(docx_content)
                
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
    
    async def _extract_from_excel(self, content: bytes) -> str:
        """Извлечение данных из Excel файлов"""
        if not pd:
            raise ImportError("pandas не установлен")
        
        try:
            excel_data = pd.read_excel(io.BytesIO(content), sheet_name=None)
            text_parts = []
            
            for sheet_name, df in excel_data.items():
                text_parts.append(f"[Лист: {sheet_name}]")
                # Конвертация в CSV формат
                csv_text = df.to_csv(index=False)
                text_parts.append(csv_text)
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке Excel: {str(e)}")
            raise ValueError(f"Error processing Excel: {str(e)}")
    
    async def _extract_from_csv(self, content: bytes) -> str:
        """Извлечение данных из CSV"""
        if not pd:
            raise ImportError("pandas не установлен")
        
        try:
            df = pd.read_csv(io.BytesIO(content))
            return df.to_csv(index=False)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке CSV: {str(e)}")
            raise ValueError(f"Error processing CSV: {str(e)}")
    
    async def _extract_from_pptx(self, content: bytes) -> str:
        """Извлечение текста из PPTX"""
        if not Presentation:
            raise ImportError("python-pptx не установлен")
        
        try:
            prs = Presentation(io.BytesIO(content))
            text_parts = []
            
            for slide_num, slide in enumerate(prs.slides, 1):
                slide_text = []
                slide_text.append(f"[Слайд {slide_num}]")
                
                # Текст из фигур
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        slide_text.append(shape.text)
                    
                    # Заметки спикера
                    if hasattr(shape, "notes_slide") and shape.notes_slide:
                        notes_text = shape.notes_slide.notes_text_frame.text
                        if notes_text.strip():
                            slide_text.append(f"[Заметки спикера]\n{notes_text}")
                
                if len(slide_text) > 1:  # Больше чем просто заголовок слайда
                    text_parts.append("\n".join(slide_text))
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке PPTX: {str(e)}")
            raise ValueError(f"Error processing PPTX: {str(e)}")
    
    async def _extract_from_ppt(self, content: bytes) -> str:
        """Извлечение текста из PPT через конвертацию в PPTX с помощью LibreOffice"""
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
                
                # Используем существующий метод для извлечения текста из PPTX
                text = await self._extract_from_pptx(pptx_content)
                
                return text
                
            finally:
                # Очищаем временные файлы
                os.unlink(temp_ppt_path)
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        except subprocess.TimeoutExpired:
            logger.error("LibreOffice conversion timeout")
            raise ValueError("PPT conversion timeout")
        except Exception as e:
            logger.error(f"Ошибка при обработке PPT: {str(e)}")
            raise ValueError(f"Error processing PPT: {str(e)}")
    
    async def _extract_from_image(self, content: bytes) -> str:
        """OCR изображения"""
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
    
    async def _extract_from_txt(self, content: bytes) -> str:
        """Извлечение текста из TXT файлов"""
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
    
    async def _extract_from_source_code(self, content: bytes, extension: str, filename: str) -> str:
        """Извлечение текста из файлов исходного кода"""
        try:
            # Попытка декодирования в разных кодировках
            text = None
            for encoding in ['utf-8', 'cp1251', 'latin-1']:
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
            
            header += "=" * 50 + "\n\n"
            
            # Возвращаем заголовок + содержимое файла
            return header + text
            
        except Exception as e:
            logger.error(f"Ошибка при обработке исходного кода {filename}: {str(e)}")
            raise ValueError(f"Error processing source code: {str(e)}")
    
    async def _extract_from_html(self, content: bytes) -> str:
        """Извлечение текста из HTML"""
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
    
    async def _extract_from_markdown(self, content: bytes) -> str:
        """Извлечение текста из Markdown"""
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
    
    async def _extract_from_json(self, content: bytes) -> str:
        """Извлечение текста из JSON"""
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
            
            string_values = extract_strings(data)
            return "\n".join(string_values)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке JSON: {str(e)}")
            raise ValueError(f"Error processing JSON: {str(e)}")
    
    async def _extract_from_rtf(self, content: bytes) -> str:
        """Извлечение текста из RTF"""
        if not rtf_to_text:
            raise ImportError("striprtf не установлен")
        
        try:
            # Декодирование RTF содержимого
            rtf_text = content.decode('utf-8', errors='replace')
            
            # Извлечение текста из RTF с помощью striprtf
            text = rtf_to_text(rtf_text)
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"Ошибка при обработке RTF: {str(e)}")
            raise ValueError(f"Error processing RTF: {str(e)}")
    
    async def _extract_from_xml(self, content: bytes) -> str:
        """Извлечение текста из XML"""
        try:
            # Декодирование XML содержимого
            xml_text = content.decode('utf-8', errors='replace')
            
            # Попытка использовать BeautifulSoup для лучшего парсинга
            if BeautifulSoup:
                soup = BeautifulSoup(xml_text, 'xml')
                
                # Извлечение всех текстовых элементов
                text_parts = []
                for element in soup.find_all():
                    if element.string and element.string.strip():
                        text_parts.append(f"{element.name}: {element.string.strip()}")
                
                # Если не найдено структурированных элементов, используем весь текст
                if not text_parts:
                    text_parts = [soup.get_text()]
                
                return "\n".join(text_parts)
            
            # Если BeautifulSoup не доступен, используем встроенный ElementTree
            root = ET.fromstring(xml_text)
            text_parts = []
            
            def extract_from_element(elem, path=""):
                """Рекурсивное извлечение текста из элементов XML"""
                element_path = f"{path}.{elem.tag}" if path else elem.tag
                
                if elem.text and elem.text.strip():
                    text_parts.append(f"{element_path}: {elem.text.strip()}")
                
                # Извлечение атрибутов
                for attr_name, attr_value in elem.attrib.items():
                    if attr_value.strip():
                        text_parts.append(f"{element_path}@{attr_name}: {attr_value}")
                
                # Рекурсивная обработка дочерних элементов
                for child in elem:
                    extract_from_element(child, element_path)
            
            extract_from_element(root)
            return "\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке XML: {str(e)}")
            raise ValueError(f"Error processing XML: {str(e)}")
    
    async def _extract_from_yaml(self, content: bytes) -> str:
        """Извлечение текста из YAML"""
        if not yaml:
            raise ImportError("PyYAML не установлен")
        
        try:
            # Декодирование YAML содержимого
            yaml_text = content.decode('utf-8', errors='replace')
            
            # Парсинг YAML
            data = yaml.safe_load(yaml_text)
            
            # Рекурсивное извлечение всех строковых значений
            def extract_strings(obj, path=""):
                strings = []
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        new_path = f"{path}.{key}" if path else str(key)
                        strings.extend(extract_strings(value, new_path))
                elif isinstance(obj, list):
                    for i, value in enumerate(obj):
                        new_path = f"{path}[{i}]" if path else f"[{i}]"
                        strings.extend(extract_strings(value, new_path))
                elif isinstance(obj, (str, int, float, bool)) and str(obj).strip():
                    strings.append(f"{path}: {obj}")
                return strings
            
            string_values = extract_strings(data)
            return "\n".join(string_values)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке YAML: {str(e)}")
            raise ValueError(f"Error processing YAML: {str(e)}")
    
    async def _extract_from_odt(self, content: bytes) -> str:
        """Извлечение текста из ODT"""
        if not load or not extractText:
            raise ImportError("odfpy не установлен")
        
        try:
            with tempfile.NamedTemporaryFile(suffix='.odt', delete=False) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            doc = load(temp_file_path)
            text_parts = []
            
            for paragraph in doc.getElementsByType(P):
                text = extractText(paragraph)
                if text.strip():
                    text_parts.append(text)
            
            os.unlink(temp_file_path)
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке ODT: {str(e)}")
            raise ValueError(f"Error processing ODT: {str(e)}")
    
    async def _extract_from_epub(self, content: bytes) -> str:
        """Извлечение текста из EPUB файлов"""
        if not BeautifulSoup:
            raise ImportError("beautifulsoup4 не установлен")
        
        try:
            # Ограничиваем размер распакованного содержимого (защита от zip-бомб)
            max_extract_size = 100 * 1024 * 1024  # 100 MB
            extracted_size = 0
            text_parts = []
            
            with zipfile.ZipFile(io.BytesIO(content), 'r') as zip_file:
                # Проверка на zip-бомбы
                for file_info in zip_file.infolist():
                    extracted_size += file_info.file_size
                    if extracted_size > max_extract_size:
                        raise ValueError("Archive too large - potential zip bomb")
                
                # Поиск HTML/XHTML файлов с контентом
                for file_info in zip_file.infolist():
                    if file_info.filename.endswith(('.html', '.xhtml', '.htm')):
                        # Исключаем служебные файлы и обрабатываем основной контент
                        if not file_info.filename.startswith('_static/') and not file_info.filename.startswith('META-INF/'):
                            try:
                                file_content = zip_file.read(file_info.filename)
                                html_text = file_content.decode('utf-8', errors='replace')
                                
                                # Извлекаем текст из HTML
                                soup = BeautifulSoup(html_text, 'html.parser')
                                
                                # Удаляем служебные теги
                                for script in soup(["script", "style", "head", "title", "meta", "link"]):
                                    script.decompose()
                                
                                # Извлекаем чистый текст
                                clean_text = soup.get_text()
                                
                                # Очищаем от лишних пробелов
                                lines = (line.strip() for line in clean_text.splitlines())
                                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                                chapter_text = '\n'.join(chunk for chunk in chunks if chunk)
                                
                                if chapter_text.strip():
                                    text_parts.append(chapter_text)
                                    
                            except Exception as e:
                                logger.warning(f"Ошибка при обработке файла {file_info.filename}: {str(e)}")
                                continue
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке EPUB: {str(e)}")
            raise ValueError(f"Error processing EPUB: {str(e)}")
    
    async def _extract_from_eml(self, content: bytes) -> str:
        """Извлечение текста из EML файлов (email)"""
        import email
        from email.policy import default
        
        try:
            # Парсинг EML содержимого
            msg = email.message_from_bytes(content, policy=default)
            
            text_parts = []
            
            # Заголовки
            text_parts.append("=== EMAIL HEADERS ===")
            for header in ['From', 'To', 'Subject', 'Date']:
                if msg.get(header):
                    text_parts.append(f"{header}: {msg.get(header)}")
            
            text_parts.append("\n=== EMAIL BODY ===")
            
            # Извлечение текста из тела письма
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            text_parts.append(part.get_content())
                        except Exception as e:
                            logger.warning(f"Ошибка при извлечении текста из части письма: {str(e)}")
                    elif part.get_content_type() == "text/html":
                        try:
                            html_content = part.get_content()
                            if BeautifulSoup:
                                soup = BeautifulSoup(html_content, 'html.parser')
                                text_parts.append(soup.get_text())
                            else:
                                text_parts.append(html_content)
                        except Exception as e:
                            logger.warning(f"Ошибка при извлечении HTML из части письма: {str(e)}")
            else:
                # Обычное письмо
                try:
                    text_parts.append(msg.get_content())
                except Exception as e:
                    logger.warning(f"Ошибка при извлечении содержимого письма: {str(e)}")
            
            return "\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке EML: {str(e)}")
            raise ValueError(f"Error processing EML: {str(e)}")
    
    async def _extract_from_msg(self, content: bytes) -> str:
        """Извлечение текста из MSG файлов (Outlook)"""
        import email
        import base64
        import re
        from email.policy import default
        
        try:
            # MSG файлы часто содержат embedded EML данные
            # Попробуем найти и извлечь EML части
            text_parts = []
            
            # Декодируем содержимое как текст для поиска структур
            try:
                text_content = content.decode('utf-8', errors='replace')
            except:
                text_content = content.decode('latin-1', errors='replace')
            
            # Ищем заголовки письма в стиле EML
            headers = {}
            email_body_parts = []
            
            # Поиск заголовков
            header_patterns = {
                'Subject': r'Subject:\s*(.+?)(?:\r?\n(?!\s)|$)',
                'From': r'From:\s*(.+?)(?:\r?\n(?!\s)|$)', 
                'To': r'To:\s*(.+?)(?:\r?\n(?!\s)|$)',
                'Date': r'Date:\s*(.+?)(?:\r?\n(?!\s)|$)'
            }
            
            for header_name, pattern in header_patterns.items():
                matches = re.findall(pattern, text_content, re.MULTILINE | re.IGNORECASE)
                if matches:
                    header_value = matches[0].strip()
                    
                    # Декодируем encoded-word заголовки (=?utf-8?b?...?=)
                    try:
                        if '=?' in header_value and '?=' in header_value:
                            # Используем email.header для декодирования
                            import email.header
                            decoded_parts = email.header.decode_header(header_value)
                            decoded_value = ''
                            for part, encoding in decoded_parts:
                                if isinstance(part, bytes):
                                    if encoding:
                                        decoded_value += part.decode(encoding)
                                    else:
                                        decoded_value += part.decode('utf-8', errors='replace')
                                else:
                                    decoded_value += part
                            headers[header_name] = decoded_value
                        else:
                            headers[header_name] = header_value
                    except:
                        headers[header_name] = header_value
            
            # Ищем base64 закодированный контент
            base64_pattern = r'Content-Transfer-Encoding:\s*base64\s*\r?\n(?:[^\r\n]*\r?\n)*?\r?\n([A-Za-z0-9+/\r\n=]+)'
            base64_matches = re.findall(base64_pattern, text_content, re.MULTILINE | re.IGNORECASE | re.DOTALL)
            
            # Также ищем отдельно стоящие base64 блоки (часто в MSG файлах)
            standalone_base64_pattern = r'\b([A-Za-z0-9+/]{20,}={0,2})\b'
            standalone_matches = re.findall(standalone_base64_pattern, text_content)
            
            # Объединяем все найденные base64 строки
            all_base64_candidates = base64_matches + standalone_matches
            
            for base64_data in all_base64_candidates:
                try:
                    # Очищаем base64 данные от переносов строк и пробелов
                    clean_base64 = re.sub(r'[\r\n\s]', '', base64_data)
                    
                    # Проверяем, что это действительно base64
                    if len(clean_base64) < 20 or len(clean_base64) % 4 > 2:
                        continue
                    
                    # Добавляем нужное количество padding
                    padding_needed = 4 - (len(clean_base64) % 4)
                    if padding_needed != 4:
                        clean_base64 += '=' * padding_needed
                    
                    decoded_bytes = base64.b64decode(clean_base64)
                    decoded_text = decoded_bytes.decode('utf-8', errors='replace')
                    
                    # Проверяем, что декодированный текст содержит читаемые символы
                    if decoded_text.strip() and len(decoded_text.strip()) > 5:
                        # Проверяем, что это не мусор (больше читаемых символов чем нечитаемых)
                        readable_chars = sum(1 for c in decoded_text if c.isprintable() or c.isspace())
                        if readable_chars > len(decoded_text) * 0.7:  # 70% читаемых символов
                            email_body_parts.append(decoded_text.strip())
                except Exception as e:
                    logger.warning(f"Ошибка при декодировании base64: {str(e)}")
                    continue
            
            # Ищем quoted-printable контент
            qp_pattern = r'Content-Transfer-Encoding:\s*quoted-printable\s*\r?\n\r?\n([^-]+?)(?=\r?\n--|\r?\nContent-|$)'
            qp_matches = re.findall(qp_pattern, text_content, re.MULTILINE | re.IGNORECASE | re.DOTALL)
            
            for qp_data in qp_matches:
                try:
                    import quopri
                    decoded_bytes = quopri.decodestring(qp_data.encode())
                    decoded_text = decoded_bytes.decode('utf-8', errors='replace')
                    if decoded_text.strip():
                        email_body_parts.append(decoded_text.strip())
                except Exception as e:
                    logger.warning(f"Ошибка при декодировании quoted-printable: {str(e)}")
                    continue
            
            # Ищем обычный текстовый контент
            text_pattern = r'Content-Type:\s*text/plain[^\r\n]*\r?\n(?:[^\r\n]*\r?\n)*?\r?\n([^-]+?)(?=\r?\n--|\r?\nContent-|$)'
            text_matches = re.findall(text_pattern, text_content, re.MULTILINE | re.IGNORECASE | re.DOTALL)
            
            for text_data in text_matches:
                clean_text = text_data.strip()
                if clean_text and len(clean_text) > 10:
                    email_body_parts.append(clean_text)
            
            # Формируем результат
            result_parts = []
            
            if headers:
                result_parts.append("=== EMAIL HEADERS ===")
                for header_name, header_value in headers.items():
                    result_parts.append(f"{header_name}: {header_value}")
                result_parts.append("")
            
            if email_body_parts:
                result_parts.append("=== EMAIL BODY ===")
                result_parts.extend(email_body_parts)
            
            # Если ничего не найдено, используем fallback метод
            if not result_parts:
                # Простая эвристика для извлечения читаемого текста
                lines = text_content.split('\n')
                readable_lines = []
                
                for line in lines:
                    # Пропускаем бинарные данные и служебную информацию
                    if len(line) > 10 and line.count('\x00') / len(line) < 0.3:
                        cleaned_line = ''.join(c for c in line if c.isprintable() or c.isspace())
                        if cleaned_line.strip() and not cleaned_line.startswith(('Content-', 'MIME-', '--')):
                            readable_lines.append(cleaned_line.strip())
                
                # Удаляем дубликаты и короткие строки
                unique_lines = []
                seen = set()
                for line in readable_lines:
                    if len(line) > 5 and line not in seen:
                        seen.add(line)
                        unique_lines.append(line)
                
                if unique_lines:
                    result_parts = unique_lines[:50]  # Ограничиваем количество строк
                else:
                    result_parts = ["Не удалось извлечь текстовое содержимое из MSG файла"]
            
            return "\n".join(result_parts)
                
        except Exception as e:
            logger.error(f"Ошибка при обработке MSG: {str(e)}")
            raise ValueError(f"Error processing MSG: {str(e)}")
    
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