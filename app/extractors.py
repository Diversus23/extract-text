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
            # Это упрощенная реализация - в реальности нужно более сложное извлечение изображений
            return ""
        except Exception as e:
            logger.warning(f"Ошибка OCR: {str(e)}")
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
        """Извлечение текста из DOC (старый формат Word)"""
        # Для DOC файлов нужен более сложный подход
        # Можно использовать python-docx2txt или antiword
        raise ValueError("DOC format not fully supported yet")
    
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
        """Извлечение текста из PPT (старый формат PowerPoint)"""
        raise ValueError("PPT format not fully supported yet")
    
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