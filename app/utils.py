"""
Утилиты для приложения
"""

import logging
import sys
from typing import Optional
import os
import magic
import tempfile
import shutil
import glob
import time
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Настройка структурированного логирования"""
    
    # Создание форматтера для логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Настройка handler для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Настройка root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    
    # Настройка логгера для uvicorn
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.setLevel(logging.INFO)
    
    # Отключение дублирующихся логов
    uvicorn_logger.propagate = False


def get_file_extension(filename: str) -> Optional[str]:
    """Получение расширения файла"""
    if not filename or '.' not in filename:
        return None
    
    # Обработка составных расширений (tar.gz, tar.bz2, tar.xz)
    filename_lower = filename.lower()
    if filename_lower.endswith('.tar.gz') or filename_lower.endswith('.tgz'):
        return 'tar.gz'
    elif filename_lower.endswith('.tar.bz2') or filename_lower.endswith('.tbz2'):
        return 'tar.bz2'
    elif filename_lower.endswith('.tar.xz') or filename_lower.endswith('.txz'):
        return 'tar.xz'
    
    return filename.split('.')[-1].lower()


def is_supported_format(filename: str, supported_formats: dict) -> bool:
    """Проверка поддерживается ли формат файла"""
    extension = get_file_extension(filename)
    if not extension:
        return False
    
    for format_group in supported_formats.values():
        if extension in format_group:
            return True
    
    return False


def is_archive_format(filename: str, supported_formats: dict) -> bool:
    """Проверка, является ли файл архивом"""
    extension = get_file_extension(filename)
    if not extension:
        return False
    
    archives = supported_formats.get("archives", [])
    return extension in archives


def safe_filename(filename: str) -> str:
    """Безопасное имя файла для логов"""
    if not filename:
        return "unknown_file"
    
    # Удаляем потенциально опасные символы
    safe_chars = []
    for char in filename:
        if char.isalnum() or char in "._-":
            safe_chars.append(char)
        else:
            safe_chars.append('_')
    
    return ''.join(safe_chars) 


def sanitize_filename(filename: str) -> str:
    """Санитизация имени файла для безопасности"""
    if not filename:
        return "unknown_file"
    
    # Используем werkzeug для базовой санитизации
    secure_name = secure_filename(filename)
    
    # Если werkzeug удалил слишком много, возвращаем безопасное имя
    if not secure_name:
        return "sanitized_file"
    
    return secure_name


def validate_file_type(content: bytes, filename: str) -> tuple[bool, Optional[str]]:
    """
    Проверка соответствия расширения файла его содержимому
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if not content or not filename:
        return False, "Файл или имя файла отсутствуют"
    
    try:
        # Получаем расширение файла
        file_extension = get_file_extension(filename)
        if not file_extension:
            return False, "Не удалось определить расширение файла"
        
        # Определяем MIME-тип содержимого
        mime_type = magic.from_buffer(content, mime=True)
        
        # Словарь соответствия расширений и MIME-типов
        extension_to_mime = {
            # Изображения
            'jpg': ['image/jpeg'],
            'jpeg': ['image/jpeg'],
            'png': ['image/png'],
            'gif': ['image/gif', 'image/png'],  # Иногда GIF определяется как PNG
            'bmp': ['image/bmp', 'image/x-ms-bmp'],
            'tiff': ['image/tiff', 'image/png'],  # Иногда TIFF определяется как PNG
            'tif': ['image/tiff', 'image/png'],
            
            # Документы
            'pdf': ['application/pdf'],
            'doc': ['application/msword'],
            'docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
            'rtf': ['application/rtf', 'text/rtf'],
            'odt': ['application/vnd.oasis.opendocument.text'],
            
            # Таблицы
            'xls': ['application/vnd.ms-excel'],
            'xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
            'csv': ['text/csv', 'text/plain'],
            'ods': ['application/vnd.oasis.opendocument.spreadsheet'],
            
            # Презентации
            'ppt': ['application/vnd.ms-powerpoint'],
            'pptx': ['application/vnd.openxmlformats-officedocument.presentationml.presentation'],
            
            # Текстовые файлы
            'txt': ['text/plain'],
            'html': ['text/html'],
            'htm': ['text/html'],
            'md': ['text/plain', 'text/markdown'],
            'json': ['application/json', 'text/plain'],
            'xml': ['application/xml', 'text/xml'],
            'yaml': ['text/plain', 'application/x-yaml'],
            'yml': ['text/plain', 'application/x-yaml'],
            
            # Архивы
            'zip': ['application/zip'],
            'rar': ['application/vnd.rar'],
            '7z': ['application/x-7z-compressed'],
            'tar': ['application/x-tar'],
            'gz': ['application/gzip'],
            'bz2': ['application/x-bzip2'],
            'xz': ['application/x-xz'],
            
            # Исходный код (различные MIME-типы)
            'py': ['text/plain', 'text/x-script.python', 'text/x-python'],
            'js': ['text/plain', 'application/javascript', 'text/javascript'],
            'ts': ['text/plain', 'text/x-typescript', 'application/typescript'],
            'java': ['text/plain', 'text/x-java', 'text/x-java-source'],
            'c': ['text/plain', 'text/x-c', 'text/x-csrc'],
            'cpp': ['text/plain', 'text/x-c', 'text/x-c++', 'text/x-c++src'],
            'h': ['text/plain', 'text/x-c', 'text/x-chdr'],
            'cs': ['text/plain', 'text/x-c++', 'text/x-csharp'],
            'php': ['text/plain', 'text/x-php', 'application/x-php'],
            'rb': ['text/plain', 'text/x-ruby', 'application/x-ruby'],
            'go': ['text/plain', 'text/x-c', 'text/x-go'],
            'rs': ['text/plain', 'text/x-c', 'text/x-rust'],
            'swift': ['text/plain', 'text/x-c', 'text/x-swift'],
            'kt': ['text/plain', 'text/x-c', 'text/x-kotlin'],
            'scala': ['text/plain', 'text/x-scala'],
            'sql': ['text/plain', 'text/x-sql'],
            'sh': ['text/plain', 'text/x-shellscript', 'application/x-shellscript'],
            'css': ['text/css', 'text/plain'],
            'scss': ['text/plain', 'text/x-scss'],
            'sass': ['text/plain', 'text/x-sass'],
            'less': ['text/plain', 'text/x-less'],
            'ini': ['text/plain', 'text/x-ini'],
            'cfg': ['text/plain'],
            'conf': ['text/plain'],
            'config': ['text/plain'],
            'toml': ['text/plain', 'application/toml'],
            'properties': ['text/plain'],
            'dockerfile': ['text/plain'],
            'makefile': ['text/plain', 'text/x-makefile'],
            'gitignore': ['text/plain'],
            'bsl': ['text/plain'],
            'os': ['text/plain'],
        }
        
        # Получаем допустимые MIME-типы для расширения
        expected_mimes = extension_to_mime.get(file_extension, [])
        
        # Если расширение не в нашем словаре, считаем валидным
        if not expected_mimes:
            return True, None
        
        # Проверяем соответствие
        if mime_type in expected_mimes:
            return True, None
        
        # Особые случаи для текстовых файлов и исходного кода
        text_based_extensions = ['txt', 'md', 'py', 'js', 'java', 'c', 'cpp', 'h', 'cs', 'php', 'rb', 'go', 'rs', 'swift', 'kt', 'scala', 'sql', 'sh', 'ini', 'cfg', 'conf', 'config', 'toml', 'properties', 'dockerfile', 'makefile', 'gitignore', 'bsl', 'os', 'yaml', 'yml', 'ts', 'jsx', 'tsx', 'scss', 'sass', 'less', 'latex', 'tex', 'rst', 'adoc', 'asciidoc', 'jsonc', 'jsonl', 'ndjson']
        
        if mime_type == 'text/plain' and file_extension in text_based_extensions:
            return True, None
        
        # Особые случаи для различных MIME-типов исходного кода
        source_code_mimes = ['text/x-c', 'text/x-script.python', 'text/x-java', 'text/x-php', 'text/x-shellscript', 'text/x-c++', 'text/x-python', 'text/x-ruby', 'text/x-go', 'text/x-rust', 'text/x-swift', 'text/x-kotlin', 'text/x-scala', 'text/x-sql', 'text/x-scss', 'text/x-sass', 'text/x-less', 'text/x-ini', 'text/x-makefile', 'text/x-typescript', 'text/x-csrc', 'text/x-c++src', 'text/x-chdr', 'text/x-csharp', 'text/x-java-source', 'application/x-shellscript', 'application/javascript', 'text/javascript', 'text/css', 'application/x-php', 'application/x-ruby', 'application/toml', 'application/typescript']
        
        if mime_type in source_code_mimes and file_extension in text_based_extensions:
            return True, None
        
        return False, f"Расширение файла '.{file_extension}' не соответствует его содержимому (MIME-тип: {mime_type})"
        
    except Exception as e:
        # В случае ошибки определения MIME-типа, считаем файл невалидным (fail-closed)
        logger.warning(f"Ошибка при валидации файла {filename}: {str(e)}")
        return False, f"Не удалось определить тип файла: {str(e)}"


def cleanup_temp_files() -> None:
    """
    Очистка временных файлов при старте приложения
    Удаляет временные файлы, которые могли остаться после предыдущих запусков
    """
    try:
        # Получаем системную папку для временных файлов
        temp_dir = tempfile.gettempdir()
        
        # Паттерны для поиска временных файлов нашего приложения
        patterns = [
            "tmp*.pdf",
            "tmp*.doc",
            "tmp*.docx", 
            "tmp*.ppt",
            "tmp*.pptx",
            "tmp*.odt",
            "tmp*.xlsx",
            "tmp*.xls",
            "tmp*.csv",
            "tmp*.txt",
            "tmp*.zip",
            "tmp*.rar",
            "tmp*.7z",
            "tmp*.tar",
            "tmp*.gz",
            "tmp*.bz2",
            "tmp*.xz",
            "tmp*.html",
            "tmp*.htm",
            "tmp*.xml",
            "tmp*.json",
            "tmp*.yaml",
            "tmp*.yml"
        ]
        
        files_removed = 0
        
        # Поиск и удаление временных файлов
        for pattern in patterns:
            full_pattern = os.path.join(temp_dir, pattern)
            for temp_file in glob.glob(full_pattern):
                try:
                    # Проверяем, что файл старше 1 часа (3600 секунд)
                    file_age = os.path.getmtime(temp_file)
                    current_time = time.time()
                    
                    if current_time - file_age > 3600:
                        os.unlink(temp_file)
                        files_removed += 1
                        logger.debug(f"Удален временный файл: {temp_file}")
                except (OSError, IOError) as e:
                    logger.warning(f"Не удалось удалить временный файл {temp_file}: {str(e)}")
        
        # Поиск и удаление временных папок
        temp_dirs_patterns = [
            "tmp*",
            "extract_*",
            "temp_*"
        ]
        
        dirs_removed = 0
        
        for pattern in temp_dirs_patterns:
            full_pattern = os.path.join(temp_dir, pattern)
            for temp_dir_path in glob.glob(full_pattern):
                if os.path.isdir(temp_dir_path):
                    try:
                        # Проверяем, что папка старше 1 часа
                        dir_age = os.path.getmtime(temp_dir_path)
                        current_time = time.time()
                        
                        if current_time - dir_age > 3600:
                            shutil.rmtree(temp_dir_path, ignore_errors=True)
                            dirs_removed += 1
                            logger.debug(f"Удалена временная папка: {temp_dir_path}")
                    except (OSError, IOError) as e:
                        logger.warning(f"Не удалось удалить временную папку {temp_dir_path}: {str(e)}")
        
        if files_removed > 0 or dirs_removed > 0:
            logger.info(f"Очистка временных файлов завершена. Удалено файлов: {files_removed}, папок: {dirs_removed}")
        else:
            logger.info("Очистка временных файлов завершена. Старые временные файлы не найдены.")
            
    except Exception as e:
        logger.error(f"Ошибка при очистке временных файлов: {str(e)}", exc_info=True)