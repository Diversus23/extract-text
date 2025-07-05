"""
Утилиты для приложения
"""

import logging
import sys
from typing import Optional
import os


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