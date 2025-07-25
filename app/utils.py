"""Утилиты для приложения."""

import glob
import logging
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

import magic
from werkzeug.utils import secure_filename

from .config import settings

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Настройка структурированного логирования."""
    # Создание форматтера для логов
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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
    """Получение расширения файла."""
    if not filename or "." not in filename:
        return None

    # Обработка составных расширений (tar.gz, tar.bz2, tar.xz)
    filename_lower = filename.lower()
    if filename_lower.endswith(".tar.gz") or filename_lower.endswith(".tgz"):
        return "tar.gz"
    elif filename_lower.endswith(".tar.bz2") or filename_lower.endswith(".tbz2"):
        return "tar.bz2"
    elif filename_lower.endswith(".tar.xz") or filename_lower.endswith(".txz"):
        return "tar.xz"

    return filename.split(".")[-1].lower()


def is_supported_format(filename: str, supported_formats: dict) -> bool:
    """Проверка поддерживается ли формат файла."""
    extension = get_file_extension(filename)
    if not extension:
        return False

    for format_group in supported_formats.values():
        if extension in format_group:
            return True

    return False


def is_archive_format(filename: str, supported_formats: dict) -> bool:
    """Проверка, является ли файл архивом."""
    extension = get_file_extension(filename)
    if not extension:
        return False

    archives = supported_formats.get("archives", [])
    return extension in archives


def safe_filename(filename: str) -> str:
    """Безопасное имя файла для логов."""
    if not filename:
        return "unknown_file"

    # Удаляем потенциально опасные символы
    safe_chars = []
    for char in filename:
        if char.isalnum() or char in "._-":
            safe_chars.append(char)
        else:
            safe_chars.append("_")

    return "".join(safe_chars)


def sanitize_filename(filename: str) -> str:
    """
    Санитизация имени файла для безопасности с поддержкой кириллицы.

    Удаляет опасные символы для path traversal атак, но сохраняет кириллические символы
    """
    if not filename:
        return "unknown_file"

    # Удаляем опасные символы для path traversal
    filename = filename.replace("..", "").replace("/", "").replace("\\", "")

    # Удаляем другие потенциально опасные символы
    dangerous_chars = ["<", ">", ":", '"', "|", "?", "*", "\0"]
    for char in dangerous_chars:
        filename = filename.replace(char, "")

    # Удаляем управляющие символы
    filename = "".join(char for char in filename if ord(char) >= 32)

    # Удаляем начальные и конечные пробелы и точки
    filename = filename.strip(" .")

    # Если после очистки файл пустой, возвращаем безопасное имя
    if not filename:
        return "sanitized_file"

    # Ограничиваем длину имени файла (максимум 255 символов для большинства ФС)
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        # Сохраняем расширение и обрезаем имя
        max_name_length = 255 - len(ext)
        filename = name[:max_name_length] + ext

    return filename


def validate_file_type(content: bytes, filename: str) -> tuple[bool, Optional[str]]:
    """
    Проверка соответствия расширения файла его содержимому.

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
            "jpg": ["image/jpeg"],
            "jpeg": ["image/jpeg"],
            "png": ["image/png"],
            "gif": ["image/gif", "image/png"],  # Иногда GIF определяется как PNG
            "bmp": ["image/bmp", "image/x-ms-bmp"],
            "tiff": ["image/tiff", "image/png"],  # Иногда TIFF определяется как PNG
            "tif": ["image/tiff", "image/png"],
            # Документы
            "pdf": ["application/pdf"],
            "doc": ["application/msword"],
            "docx": [
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ],
            "rtf": ["application/rtf", "text/rtf"],
            "odt": ["application/vnd.oasis.opendocument.text"],
            # Таблицы
            "xls": ["application/vnd.ms-excel"],
            "xlsx": [
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ],
            "csv": ["text/csv", "text/plain"],
            "ods": ["application/vnd.oasis.opendocument.spreadsheet"],
            # Презентации
            "ppt": ["application/vnd.ms-powerpoint"],
            "pptx": [
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ],
            # Текстовые файлы
            "txt": ["text/plain"],
            "html": ["text/html"],
            "htm": ["text/html"],
            "md": ["text/plain", "text/markdown"],
            "json": ["application/json", "text/plain"],
            "xml": ["application/xml", "text/xml"],
            "yaml": ["text/plain", "application/x-yaml"],
            "yml": ["text/plain", "application/x-yaml"],
            # Архивы
            "zip": ["application/zip"],
            "rar": ["application/vnd.rar"],
            "7z": ["application/x-7z-compressed"],
            "tar": ["application/x-tar"],
            "gz": ["application/gzip"],
            "bz2": ["application/x-bzip2"],
            "xz": ["application/x-xz"],
            # Исходный код (различные MIME-типы)
            "py": ["text/plain", "text/x-script.python", "text/x-python"],
            "js": ["text/plain", "application/javascript", "text/javascript"],
            "ts": ["text/plain", "text/x-typescript", "application/typescript"],
            "java": ["text/plain", "text/x-java", "text/x-java-source"],
            "c": ["text/plain", "text/x-c", "text/x-csrc"],
            "cpp": ["text/plain", "text/x-c", "text/x-c++", "text/x-c++src"],
            "h": ["text/plain", "text/x-c", "text/x-chdr"],
            "cs": ["text/plain", "text/x-c++", "text/x-csharp"],
            "php": ["text/plain", "text/x-php", "application/x-php"],
            "rb": ["text/plain", "text/x-ruby", "application/x-ruby"],
            "go": ["text/plain", "text/x-c", "text/x-go"],
            "rs": ["text/plain", "text/x-c", "text/x-rust"],
            "swift": ["text/plain", "text/x-c", "text/x-swift"],
            "kt": ["text/plain", "text/x-c", "text/x-kotlin"],
            "scala": ["text/plain", "text/x-scala"],
            "sql": ["text/plain", "text/x-sql"],
            "sh": ["text/plain", "text/x-shellscript", "application/x-shellscript"],
            "css": ["text/css", "text/plain"],
            "scss": ["text/plain", "text/x-scss"],
            "sass": ["text/plain", "text/x-sass"],
            "less": ["text/plain", "text/x-less"],
            "ini": ["text/plain", "text/x-ini"],
            "cfg": ["text/plain"],
            "conf": ["text/plain"],
            "config": ["text/plain"],
            "toml": ["text/plain", "application/toml"],
            "properties": ["text/plain"],
            "dockerfile": ["text/plain"],
            "makefile": ["text/plain", "text/x-makefile"],
            "gitignore": ["text/plain"],
            "bsl": ["text/plain"],
            "os": ["text/plain"],
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
        text_based_extensions = [
            "txt",
            "md",
            "py",
            "js",
            "java",
            "c",
            "cpp",
            "h",
            "cs",
            "php",
            "rb",
            "go",
            "rs",
            "swift",
            "kt",
            "scala",
            "sql",
            "sh",
            "ini",
            "cfg",
            "conf",
            "config",
            "toml",
            "properties",
            "dockerfile",
            "makefile",
            "gitignore",
            "bsl",
            "os",
            "yaml",
            "yml",
            "ts",
            "jsx",
            "tsx",
            "scss",
            "sass",
            "less",
            "latex",
            "tex",
            "rst",
            "adoc",
            "asciidoc",
            "jsonc",
            "jsonl",
            "ndjson",
        ]

        if mime_type == "text/plain" and file_extension in text_based_extensions:
            return True, None

        # Особые случаи для различных MIME-типов исходного кода
        source_code_mimes = [
            "text/x-c",
            "text/x-script.python",
            "text/x-java",
            "text/x-php",
            "text/x-shellscript",
            "text/x-c++",
            "text/x-python",
            "text/x-ruby",
            "text/x-go",
            "text/x-rust",
            "text/x-swift",
            "text/x-kotlin",
            "text/x-scala",
            "text/x-sql",
            "text/x-scss",
            "text/x-sass",
            "text/x-less",
            "text/x-ini",
            "text/x-makefile",
            "text/x-typescript",
            "text/x-csrc",
            "text/x-c++src",
            "text/x-chdr",
            "text/x-csharp",
            "text/x-java-source",
            "application/x-shellscript",
            "application/javascript",
            "text/javascript",
            "text/css",
            "application/x-php",
            "application/x-ruby",
            "application/toml",
            "application/typescript",
        ]

        if mime_type in source_code_mimes and file_extension in text_based_extensions:
            return True, None

        return (
            False,
            f"Расширение файла '.{file_extension}' не соответствует его содержимому (MIME-тип: {mime_type})",
        )

    except Exception as e:
        # В случае ошибки определения MIME-типа, считаем файл невалидным (fail-closed)
        logger.warning(f"Ошибка при валидации файла {filename}: {str(e)}")
        return False, f"Не удалось определить тип файла: {str(e)}"


def cleanup_temp_files() -> None:
    """
    Очистка временных файлов при старте приложения.

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
            "tmp*.yml",
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
                except OSError as e:
                    logger.warning(
                        f"Не удалось удалить временный файл {temp_file}: {str(e)}"
                    )

        # Поиск и удаление временных папок
        temp_dirs_patterns = ["tmp*", "extract_*", "temp_*"]

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
                    except OSError as e:
                        logger.warning(
                            f"Не удалось удалить временную папку {temp_dir_path}: {str(e)}"
                        )

        if files_removed > 0 or dirs_removed > 0:
            logger.info(
                f"Очистка временных файлов завершена. Удалено файлов: {files_removed}, папок: {dirs_removed}"
            )
        else:
            logger.info(
                "Очистка временных файлов завершена. Старые временные файлы не найдены."
            )

    except Exception as e:
        logger.error(f"Ошибка при очистке временных файлов: {str(e)}", exc_info=True)


def cleanup_recent_temp_files() -> None:
    """
    Немедленная очистка временных файлов текущего процесса.

    Удаляет временные файлы, созданные в последние 10 минут
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
            "tmp*.yml",
            "tmp*.png",
            "tmp*.jpg",
            "tmp*.jpeg",
            "tmp*.tiff",
            "tmp*.tif",
            "tmp*.bmp",
            "tmp*.gif",
        ]

        files_removed = 0
        current_time = time.time()

        # Поиск и удаление недавних временных файлов (младше 10 минут)
        for pattern in patterns:
            full_pattern = os.path.join(temp_dir, pattern)
            for temp_file in glob.glob(full_pattern):
                try:
                    # Проверяем, что файл младше 10 минут (600 секунд)
                    file_age = os.path.getmtime(temp_file)

                    if current_time - file_age <= 600:  # 10 минут
                        os.unlink(temp_file)
                        files_removed += 1
                        logger.debug(f"Удален недавний временный файл: {temp_file}")
                except OSError as e:
                    logger.debug(
                        f"Не удалось удалить временный файл {temp_file}: {str(e)}"
                    )

        # Поиск и удаление недавних временных папок
        temp_dirs_patterns = ["tmp*", "extract_*", "temp_*"]
        dirs_removed = 0

        for pattern in temp_dirs_patterns:
            full_pattern = os.path.join(temp_dir, pattern)
            for temp_dir_path in glob.glob(full_pattern):
                if os.path.isdir(temp_dir_path):
                    try:
                        # Проверяем, что папка младше 10 минут
                        dir_age = os.path.getmtime(temp_dir_path)

                        if current_time - dir_age <= 600:  # 10 минут
                            shutil.rmtree(temp_dir_path, ignore_errors=True)
                            dirs_removed += 1
                            logger.debug(
                                f"Удалена недавняя временная папка: {temp_dir_path}"
                            )
                    except OSError as e:
                        logger.debug(
                            f"Не удалось удалить временную папку {temp_dir_path}: {str(e)}"
                        )

        if files_removed > 0 or dirs_removed > 0:
            logger.info(
                f"Очистка недавних временных файлов завершена. Удалено файлов: {files_removed}, папок: {dirs_removed}"
            )

    except Exception as e:
        logger.warning(f"Ошибка при очистке недавних временных файлов: {str(e)}")


def run_subprocess_with_limits(
    command: list,
    timeout: int = 30,
    memory_limit: Optional[int] = None,
    capture_output: bool = True,
    text: bool = True,
    **kwargs,
) -> subprocess.CompletedProcess:
    """
    Запуск подпроцесса с ограничениями ресурсов.

    Args:
        command: Команда для выполнения
        timeout: Таймаут в секундах
        memory_limit: Ограничение памяти в байтах (None для использования настроек по умолчанию)
        capture_output: Захватывать ли вывод
        text: Использовать ли текстовый режим
        **kwargs: Дополнительные параметры для subprocess.run

    Returns:
        subprocess.CompletedProcess: Результат выполнения

    Raises:
        subprocess.TimeoutExpired: При превышении таймаута
        subprocess.CalledProcessError: При ошибке выполнения
        MemoryError: При превышении лимита памяти
    """
    if not settings.ENABLE_RESOURCE_LIMITS:
        # Если ограничения отключены, используем стандартный запуск
        return subprocess.run(
            command, timeout=timeout, capture_output=capture_output, text=text, **kwargs
        )

    # Определяем лимит памяти
    if memory_limit is None:
        memory_limit = settings.MAX_SUBPROCESS_MEMORY

    def preexec_fn():
        """Функция для установки ограничений ресурсов перед выполнением."""
        try:
            # Устанавливаем ограничение на использование виртуальной памяти
            resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))

            # Устанавливаем ограничение на размер данных
            resource.setrlimit(resource.RLIMIT_DATA, (memory_limit, memory_limit))

            # Устанавливаем ограничение на время CPU (в секундах)
            resource.setrlimit(resource.RLIMIT_CPU, (timeout * 2, timeout * 2))

            logger.debug(
                f"Установлены ограничения ресурсов: память={memory_limit}, CPU={timeout * 2}"
            )

        except Exception as e:
            logger.warning(f"Не удалось установить ограничения ресурсов: {e}")

    try:
        # Запускаем процесс с ограничениями
        result = subprocess.run(
            command,
            timeout=timeout,
            capture_output=capture_output,
            text=text,
            preexec_fn=preexec_fn,
            **kwargs,
        )

        return result

    except subprocess.TimeoutExpired:
        logger.error(f"Процесс превысил таймаут {timeout}s: {' '.join(command)}")
        raise
    except subprocess.CalledProcessError as e:
        # Проверяем, не была ли ошибка связана с превышением лимита памяти
        if e.returncode == 137:  # SIGKILL, часто означает превышение лимита памяти
            logger.error(
                f"Процесс превысил лимит памяти {memory_limit} байт: {' '.join(command)}"
            )
            raise MemoryError(f"Subprocess exceeded memory limit: {memory_limit} bytes")
        else:
            logger.error(
                f"Процесс завершился с ошибкой {e.returncode}: {' '.join(command)}"
            )
            raise
    except Exception as e:
        logger.error(f"Ошибка при выполнении процесса: {' '.join(command)}, {str(e)}")
        raise


def validate_image_for_ocr(image_content: bytes) -> tuple[bool, Optional[str]]:
    """
    Валидация изображения перед OCR для предотвращения DoS атак.

    Args:
        image_content: Содержимое изображения

    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    try:
        import io

        from PIL import Image

        # Открываем изображение без полной загрузки в память
        with Image.open(io.BytesIO(image_content)) as img:
            # Проверяем разрешение
            width, height = img.size
            total_pixels = width * height

            if total_pixels > settings.MAX_OCR_IMAGE_PIXELS:
                return (
                    False,
                    f"Изображение слишком большое: {total_pixels} пикселей (макс: {settings.MAX_OCR_IMAGE_PIXELS})",
                )

            # Проверяем формат
            if img.format not in ["JPEG", "PNG", "TIFF", "BMP", "GIF"]:
                return False, f"Неподдерживаемый формат изображения: {img.format}"

            # Проверяем количество каналов (защита от сложных изображений)
            if hasattr(img, "mode"):
                if img.mode not in ["L", "RGB", "RGBA", "P"]:
                    return False, f"Неподдерживаемый цветовой режим: {img.mode}"

            logger.debug(
                f"Валидация изображения пройдена: {width}x{height}, {img.format}, {img.mode}"
            )
            return True, None

    except Exception as e:
        logger.error(f"Ошибка при валидации изображения: {str(e)}")
        return False, f"Не удалось обработать изображение: {str(e)}"


def get_memory_usage() -> Dict[str, Any]:
    """
    Получение информации об использовании памяти.

    Returns:
        Dict[str, Any]: Информация о памяти
    """
    try:
        import psutil

        # Информация о системе
        memory = psutil.virtual_memory()

        # Информация о текущем процессе
        process = psutil.Process(os.getpid())
        process_memory = process.memory_info()

        return {
            "system_total": memory.total,
            "system_available": memory.available,
            "system_used": memory.used,
            "system_percent": memory.percent,
            "process_rss": process_memory.rss,
            "process_vms": process_memory.vms,
            "process_percent": process.memory_percent(),
        }
    except ImportError:
        logger.warning("psutil не установлен, информация о памяти недоступна")
        return {}
    except Exception as e:
        logger.error(f"Ошибка при получении информации о памяти: {e}")
        return {}


def get_extension_from_mime(
    content_type: str, supported_formats: dict
) -> Optional[str]:
    """
    Определение расширения файла по MIME-типу с учетом поддерживаемых форматов.

    Args:
        content_type: MIME-тип из заголовка Content-Type
        supported_formats: Словарь поддерживаемых форматов из settings.SUPPORTED_FORMATS

    Returns:
        Optional[str]: Расширение файла или None, если тип не поддерживается
    """
    if not content_type:
        return None

    content_type = content_type.lower().strip()

    # Получаем список поддерживаемых расширений изображений
    supported_image_formats = supported_formats.get("images_ocr", [])

    # Маппинг MIME-типов к расширениям
    mime_mapping = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
        "image/bmp": "bmp",
        "image/tiff": "tiff",
        "image/tif": "tif",
    }

    # Ищем соответствие MIME-типа среди поддерживаемых форматов
    for mime, ext in mime_mapping.items():
        if mime in content_type and ext in supported_image_formats:
            return ext

    # Если точного соответствия нет, проверяем частичные совпадения
    if "jpeg" in content_type or "jpg" in content_type:
        return "jpg" if "jpg" in supported_image_formats else None
    elif "png" in content_type:
        return "png" if "png" in supported_image_formats else None
    elif "webp" in content_type:
        return "webp" if "webp" in supported_image_formats else None
    elif "gif" in content_type:
        return "gif" if "gif" in supported_image_formats else None
    elif "bmp" in content_type:
        return "bmp" if "bmp" in supported_image_formats else None
    elif "tiff" in content_type or "tif" in content_type:
        return (
            "tiff"
            if "tiff" in supported_image_formats
            else "tif" if "tif" in supported_image_formats else None
        )

    # Если MIME-тип не поддерживается, возвращаем None
    return None


def decode_base64_image(base64_data: str) -> Optional[bytes]:
    """
    Декодирование base64 изображения из data URI.

    Args:
        base64_data: Строка в формате data:image/jpeg;base64,/9j/4AAQ...

    Returns:
        Optional[bytes]: Декодированные байты изображения или None при ошибке
    """
    try:
        # Проверяем формат data URI
        if not base64_data.startswith("data:image/"):
            return None

        # Извлекаем base64 часть после запятой
        if "," not in base64_data:
            return None

        base64_part = base64_data.split(",", 1)[1]

        # Декодируем base64
        import base64

        return base64.b64decode(base64_part)

    except Exception as e:
        logger.warning(f"Ошибка декодирования base64 изображения: {str(e)}")
        return None


def extract_mime_from_base64_data_uri(data_uri: str) -> Optional[str]:
    """
    Извлечение MIME-типа из data URI.

    Args:
        data_uri: Строка в формате data:image/jpeg;base64,/9j/4AAQ...

    Returns:
        Optional[str]: MIME-тип (например, 'image/jpeg') или None при ошибке
    """
    try:
        if not data_uri.startswith("data:"):
            return None

        # Извлекаем часть до точки с запятой
        if ";" not in data_uri:
            return None

        mime_part = data_uri.split(";")[0]
        mime_type = mime_part.replace("data:", "")

        return mime_type if mime_type.startswith("image/") else None

    except Exception as e:
        logger.warning(f"Ошибка извлечения MIME-типа из data URI: {str(e)}")
        return None
