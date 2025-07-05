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