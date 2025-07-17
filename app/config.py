"""
Конфигурация приложения
"""

import os
from typing import List


class Settings:
    """Настройки приложения"""
    
    # Основные настройки
    VERSION: str = "1.8.8"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # Настройки API
    API_PORT: int = int(os.getenv("API_PORT", "7555"))
    
    # Настройки обработки файлов
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", str(20 * 1024 * 1024)))  # 20 MB
    PROCESSING_TIMEOUT_SECONDS: int = int(os.getenv("PROCESSING_TIMEOUT_SECONDS", "300"))
    
    # Настройки управления ресурсами дочерних процессов
    # Максимальное потребление памяти дочерними процессами (в байтах)
    MAX_SUBPROCESS_MEMORY: int = int(os.getenv("MAX_SUBPROCESS_MEMORY", str(1024 * 1024 * 1024)))  # 1 GB
    
    # Максимальное потребление памяти для LibreOffice (в байтах)
    MAX_LIBREOFFICE_MEMORY: int = int(os.getenv("MAX_LIBREOFFICE_MEMORY", str(1536 * 1024 * 1024)))  # 1.5 GB
    
    # Максимальное потребление памяти для Tesseract (в байтах)
    MAX_TESSERACT_MEMORY: int = int(os.getenv("MAX_TESSERACT_MEMORY", str(512 * 1024 * 1024)))  # 512 MB
    
    # Максимальное разрешение для OCR изображений (пиксели)
    MAX_OCR_IMAGE_PIXELS: int = int(os.getenv("MAX_OCR_IMAGE_PIXELS", str(50 * 1024 * 1024)))  # 50 MP
    
    # Включить/выключить ограничения ресурсов
    ENABLE_RESOURCE_LIMITS: bool = os.getenv("ENABLE_RESOURCE_LIMITS", "true").lower() == "true"
    
    # Настройки OCR
    OCR_LANGUAGES: str = os.getenv("OCR_LANGUAGES", "rus+eng")
    
    # Настройки производительности
    WORKERS: int = int(os.getenv("WORKERS", "1"))
    
    # Настройки архивов
    MAX_ARCHIVE_SIZE: int = int(os.getenv("MAX_ARCHIVE_SIZE", "20971520"))  # 20 MB
    MAX_EXTRACTED_SIZE: int = int(os.getenv("MAX_EXTRACTED_SIZE", "104857600"))  # 100 MB
    MAX_ARCHIVE_NESTING: int = int(os.getenv("MAX_ARCHIVE_NESTING", "3"))
    
    # Поддерживаемые форматы
    SUPPORTED_FORMATS = {
        "images_ocr": ["jpg", "jpeg", "png", "tiff", "tif", "bmp", "gif"],
        "documents": ["doc", "docx", "pdf", "rtf", "odt"],
        "spreadsheets": ["csv", "xls", "xlsx", "ods"],
        "presentations": ["pptx", "ppt"],
        "structured_data": ["json", "xml", "yaml", "yml"],
        "source_code": [
            # Python
            "py", "pyx", "pyi", "pyw",
            # JavaScript/TypeScript
            "js", "jsx", "ts", "tsx", "mjs", "cjs",
            # Java
            "java", "jav",
            # C/C++
            "c", "cpp", "cxx", "cc", "c++", "h", "hpp", "hxx", "h++",
            # C#
            "cs", "csx",
            # PHP
            "php", "php3", "php4", "php5", "phtml",
            # Ruby
            "rb", "rbw", "rake", "gemspec",
            # Go
            "go", "mod", "sum",
            # Rust
            "rs", "rlib",
            # Swift
            "swift",
            # Kotlin
            "kt", "kts",
            # Scala
            "scala", "sc",
            # R
            "r", "rmd",
            # SQL
            "sql", "ddl", "dml",
            # Shell/Bash
            "sh", "bash", "zsh", "fish", "ksh", "csh", "tcsh",
            # PowerShell
            "ps1", "psm1", "psd1",
            # Perl
            "pl", "pm", "pod", "t",
            # Lua
            "lua",
            # 1C and OneScript
            "bsl", "os",
            # Configuration files
            "ini", "cfg", "conf", "config", "toml", "properties",
            # Web
            "css", "scss", "sass", "less", "styl",
            # Markup
            "tex", "latex", "rst", "adoc", "asciidoc",
            # Data formats
            "jsonl", "ndjson", "jsonc",
            # Docker
            "dockerfile", "containerfile",
            # Makefile
            "makefile", "mk", "mak",
            # Git
            "gitignore", "gitattributes", "gitmodules"
        ],
        "other": ["txt", "html", "htm", "md", "markdown", "epub", "eml", "msg"],
        "archives": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "tbz2", "txz", "tar.gz", "tar.bz2", "tar.xz"]
    }
    
    @property
    def all_supported_extensions(self) -> List[str]:
        """Все поддерживаемые расширения файлов"""
        extensions = []
        for format_group in self.SUPPORTED_FORMATS.values():
            extensions.extend(format_group)
        return extensions


settings = Settings() 