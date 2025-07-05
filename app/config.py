"""
Конфигурация приложения
"""

import os
from typing import List


class Settings:
    """Настройки приложения"""
    
    # Основные настройки
    VERSION: str = "1.6"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # Настройки API
    API_PORT: int = int(os.getenv("API_PORT", "7555"))
    
    # Настройки обработки файлов
    MAX_FILE_SIZE: int = 20 * 1024 * 1024  # 20 MB
    PROCESSING_TIMEOUT_SECONDS: int = int(os.getenv("PROCESSING_TIMEOUT_SECONDS", "300"))
    
    # Настройки OCR
    OCR_LANGUAGES: str = os.getenv("OCR_LANGUAGES", "rus+eng")
    
    # Поддерживаемые форматы
    SUPPORTED_FORMATS = {
        "images_ocr": ["jpg", "jpeg", "png", "tiff", "tif", "bmp", "gif"],
        "documents": ["doc", "docx", "pdf", "rtf", "odt"],
        "spreadsheets": ["csv", "xls", "xlsx", "ods"],
        "presentations": ["pptx", "ppt"],
        "structured_data": ["json", "xml", "yaml", "yml"],
        "other": ["txt", "html", "htm", "md", "markdown", "epub", "eml", "msg"]
    }
    
    @property
    def all_supported_extensions(self) -> List[str]:
        """Все поддерживаемые расширения файлов"""
        extensions = []
        for format_group in self.SUPPORTED_FORMATS.values():
            extensions.extend(format_group)
        return extensions


settings = Settings() 