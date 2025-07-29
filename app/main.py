"""
Text Extraction API for RAG.

Главный модуль FastAPI приложения
"""

import asyncio
import base64
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.extractors import TextExtractor
from app.utils import (
    cleanup_recent_temp_files,
    cleanup_temp_files,
    sanitize_filename,
    setup_logging,
    validate_file_type,
)

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

# Константы для FastAPI аргументов
FILE_UPLOAD = File(...)

# Инициализация экстрактора текста
text_extractor = TextExtractor()


# Pydantic модели
class Base64FileRequest(BaseModel):
    """Модель для запроса обработки base64-файла."""

    encoded_base64_file: str = Field(
        "0J/RgNC40LLQtdGCINC80LjRgCEg0K3RgtC+INGC0LXRgdGCIGJhc2U2NArQntGH0LXQvdGMINC00LvQuNC90L3Ri9C5LCDRgSDQv9C10YDQtdC90L7RgdC+0Lwg0YHRgtGA0L7Qui4=",
        description="Файл в кодировке base64",
    )
    filename: str = Field("test.txt", description="Имя файла с расширением")


class ExtractionOptions(BaseModel):
    """Настройки извлечения текста для веб-страниц (новое в v1.10.2)."""

    # JavaScript и рендеринг
    enable_javascript: Optional[bool] = Field(
        True, description="Включить/выключить JavaScript рендеринг"
    )
    js_render_timeout: Optional[int] = Field(
        10, description="Таймаут JS-рендеринга в секундах"
    )
    web_page_delay: Optional[int] = Field(
        3, description="Задержка после загрузки JS в секундах"
    )

    # Lazy Loading
    enable_lazy_loading_wait: Optional[bool] = Field(
        True, description="Включить ожидание lazy loading"
    )
    max_scroll_attempts: Optional[int] = Field(
        3, description="Максимальное количество попыток скролла"
    )

    # Обработка изображений
    process_images: Optional[bool] = Field(
        True, description="Обрабатывать ли изображения через OCR"
    )
    enable_base64_images: Optional[bool] = Field(
        True, description="Обрабатывать ли base64 изображения"
    )
    min_image_size_for_ocr: Optional[int] = Field(
        22500, description="Минимальный размер изображения для OCR (пиксели)"
    )
    max_images_per_page: Optional[int] = Field(
        20, description="Максимальное количество изображений на странице"
    )

    # Таймауты
    web_page_timeout: Optional[int] = Field(
        30, description="Таймаут загрузки страницы в секундах"
    )
    image_download_timeout: Optional[int] = Field(
        15, description="Таймаут загрузки изображений в секундах"
    )

    # Сетевые настройки
    follow_redirects: Optional[bool] = Field(
        True, description="Следовать ли редиректам"
    )
    max_redirects: Optional[int] = Field(
        5, description="Максимальное количество редиректов"
    )


class URLRequest(BaseModel):
    """Модель для запроса обработки веб-страницы (обновлено в v1.10.2)."""

    url: str = Field(
        "https://habr.com/ru/companies/softonit/articles/911520/",
        description="URL веб-страницы для извлечения текста",
    )
    user_agent: Optional[str] = Field(
        "Text Extraction Bot 1.0",
        description="Пользовательский User-Agent (опционально, для обратной совместимости)",
    )
    extraction_options: Optional[ExtractionOptions] = Field(
        None, description="Настройки извлечения текста (опционально)"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager для FastAPI приложения."""
    logger.info(f"Запуск Text Extraction API v{settings.VERSION}")

    # Очистка временных файлов при старте
    cleanup_temp_files()

    yield

    # Graceful shutdown: корректно закрываем пул потоков
    logger.info("Завершение работы Text Extraction API")
    try:
        if hasattr(text_extractor, "_thread_pool"):
            logger.info("Закрытие пула потоков...")
            text_extractor._thread_pool.shutdown(wait=True)
            logger.info("Пул потоков успешно закрыт")
    except Exception as e:
        logger.warning(f"Ошибка при закрытии пула потоков: {str(e)}")

    # Финальная очистка временных файлов
    try:
        cleanup_temp_files()
    except Exception as e:
        logger.warning(f"Ошибка при финальной очистке: {str(e)}")


# Создание FastAPI приложения
app = FastAPI(
    title="Text Extraction API for RAG",
    description="API для извлечения текста из файлов различных форматов",
    version=settings.VERSION,
    lifespan=lifespan,
    license_info={"name": "MIT License", "url": "https://opensource.org/licenses/MIT"},
    contact={
        "name": "Барилко Виталий",
        "email": "support@softonit.ru",
        "url": "https://softonit.ru",
    },
)

# Добавление CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Middleware для логирования запросов."""
    start_time = time.time()

    logger.info(f"Запрос: {request.method} {request.url}")

    try:
        response = await call_next(request)
        process_time = time.time() - start_time

        logger.info(
            f"Ответ: {response.status_code} для {request.method} {request.url} "
            f"за {process_time:.3f}s"
        )
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            f"Ошибка обработки запроса {request.method} {request.url} "
            f"за {process_time:.3f}s: {str(e)}"
        )
        raise


@app.get("/")
async def root() -> Dict[str, str]:
    """Информация о API."""
    return {
        "api_name": "Text Extraction API for RAG",
        "version": settings.VERSION,
        "contact": "Барилко Виталий",
    }


@app.get("/health")
async def health() -> Dict[str, str]:
    """Проверка состояния API."""
    return {"status": "ok"}


@app.get("/v1/supported-formats")
async def supported_formats() -> Dict[str, list]:
    """Поддерживаемые форматы файлов."""
    return settings.SUPPORTED_FORMATS


@app.post("/v1/extract/file")
async def extract_text(file: UploadFile = FILE_UPLOAD):
    """Извлечение текста из файла."""
    try:
        # Санитизация имени файла
        original_filename = file.filename or "unknown_file"
        safe_filename_for_processing = sanitize_filename(original_filename)

        logger.info(f"Получен файл для обработки: {original_filename}")

        # Проверка наличия размера файла (защита от DoS)
        if file.size is None:
            logger.warning(
                f"Файл {original_filename} не содержит заголовок Content-Length"
            )
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Отсутствует заголовок Content-Length. Пожалуйста, убедитесь, что размер файла указан в запросе.",
                },
            )

        # Проверка размера файла
        if file.size > settings.MAX_FILE_SIZE:
            logger.warning(
                f"Файл {original_filename} слишком большой: {file.size} bytes"
            )
            raise HTTPException(
                status_code=413, detail="File size exceeds maximum allowed size"
            )

        # Чтение содержимого файла
        content = await file.read()

        # Проверка на пустой файл
        if not content:
            logger.warning(f"Файл {original_filename} пуст")
            raise HTTPException(status_code=422, detail="File is empty")

        # Проверка соответствия расширения файла его содержимому
        is_valid, validation_error = validate_file_type(content, original_filename)
        if not is_valid:
            logger.warning(
                f"Файл {original_filename} не прошел проверку типа: {validation_error}"
            )
            return JSONResponse(
                status_code=415,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Расширение файла не соответствует его содержимому. Возможная подделка типа файла.",
                },
            )

        # Извлечение текста - КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: выполняем в пуле потоков с таймаутом
        start_time = time.time()
        try:
            extracted_files = await asyncio.wait_for(
                run_in_threadpool(
                    text_extractor.extract_text, content, safe_filename_for_processing
                ),
                timeout=settings.PROCESSING_TIMEOUT_SECONDS,  # 300 секунд согласно ТЗ п.5.1
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Таймаут обработки файла {original_filename}: превышен лимит {settings.PROCESSING_TIMEOUT_SECONDS} секунд"
            )
            return JSONResponse(
                status_code=504,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": f"Обработка файла превысила установленный лимит времени ({settings.PROCESSING_TIMEOUT_SECONDS} секунд).",
                },
            )
        finally:
            # Дополнительная очистка временных файлов после обработки
            try:
                cleanup_recent_temp_files()
            except Exception as cleanup_error:
                logger.warning(
                    f"Ошибка при очистке временных файлов: {str(cleanup_error)}"
                )

        process_time = time.time() - start_time

        # Подсчет общей длины текста
        total_text_length = sum(
            len(file_data.get("text", "")) for file_data in extracted_files
        )

        logger.info(
            f"Текст успешно извлечен из {original_filename} за {process_time:.3f}s. "
            f"Обработано файлов: {len(extracted_files)}, общая длина текста: {total_text_length} символов"
        )

        return {
            "status": "success",
            "filename": original_filename,
            "count": len(extracted_files),
            "files": extracted_files,
        }

    except HTTPException:
        raise
    except ValueError as e:
        error_msg = str(e)
        if "Unsupported file format" in error_msg:
            logger.warning(f"Неподдерживаемый формат файла: {original_filename}")
            return JSONResponse(
                status_code=415,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Неподдерживаемый формат файла.",
                },
            )
        else:
            logger.error(
                f"Ошибка при обработке файла {original_filename}: {error_msg}",
                exc_info=True,
            )
            return JSONResponse(
                status_code=422,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Файл поврежден или формат не поддерживается.",
                },
            )
    except Exception as e:
        # Определяем имя файла для логирования
        filename_for_error = getattr(file, "filename", "unknown_file") or "unknown_file"
        logger.error(
            f"Ошибка при обработке файла {filename_for_error}: {str(e)}", exc_info=True
        )
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "filename": filename_for_error,
                "message": "Файл поврежден или формат не поддерживается.",
            },
        )


@app.post("/v1/extract/base64")
async def extract_text_base64(request: Base64FileRequest):
    """Извлечение текста из base64-файла."""
    try:
        # Санитизация имени файла
        original_filename = request.filename
        safe_filename_for_processing = sanitize_filename(original_filename)

        logger.info(f"Получен base64-файл для обработки: {original_filename}")

        # Декодирование base64
        try:
            content = base64.b64decode(request.encoded_base64_file)
        except Exception as e:
            logger.warning(
                f"Ошибка декодирования base64 для файла {original_filename}: {str(e)}"
            )
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Неверный формат base64. Убедитесь, что файл корректно закодирован в base64.",
                },
            )

        # Проверка размера файла
        file_size = len(content)
        if file_size > settings.MAX_FILE_SIZE:
            logger.warning(
                f"Файл {original_filename} слишком большой: {file_size} bytes"
            )
            raise HTTPException(
                status_code=413, detail="File size exceeds maximum allowed size"
            )

        # Проверка на пустой файл
        if not content:
            logger.warning(f"Файл {original_filename} пуст")
            raise HTTPException(status_code=422, detail="File is empty")

        # Проверка соответствия расширения файла его содержимому
        is_valid, validation_error = validate_file_type(content, original_filename)
        if not is_valid:
            logger.warning(
                f"Файл {original_filename} не прошел проверку типа: {validation_error}"
            )
            return JSONResponse(
                status_code=415,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Расширение файла не соответствует его содержимому. Возможная подделка типа файла.",
                },
            )

        # Извлечение текста - выполняем в пуле потоков с таймаутом
        start_time = time.time()
        try:
            extracted_files = await asyncio.wait_for(
                run_in_threadpool(
                    text_extractor.extract_text, content, safe_filename_for_processing
                ),
                timeout=settings.PROCESSING_TIMEOUT_SECONDS,  # 300 секунд согласно ТЗ п.5.1
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Таймаут обработки файла {original_filename}: превышен лимит {settings.PROCESSING_TIMEOUT_SECONDS} секунд"
            )
            return JSONResponse(
                status_code=504,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": f"Обработка файла превысила установленный лимит времени ({settings.PROCESSING_TIMEOUT_SECONDS} секунд).",
                },
            )
        finally:
            # Дополнительная очистка временных файлов после обработки base64-файла
            try:
                cleanup_recent_temp_files()
            except Exception as cleanup_error:
                logger.warning(
                    f"Ошибка при очистке временных файлов: {str(cleanup_error)}"
                )

        process_time = time.time() - start_time

        # Подсчет общей длины текста
        total_text_length = sum(
            len(file_data.get("text", "")) for file_data in extracted_files
        )

        logger.info(
            f"Текст успешно извлечен из base64-файла {original_filename} за {process_time:.3f}s. "
            f"Обработано файлов: {len(extracted_files)}, общая длина текста: {total_text_length} символов"
        )

        return {
            "status": "success",
            "filename": original_filename,
            "count": len(extracted_files),
            "files": extracted_files,
        }

    except HTTPException:
        raise
    except ValueError as e:
        error_msg = str(e)
        if "Unsupported file format" in error_msg:
            logger.warning(f"Неподдерживаемый формат файла: {original_filename}")
            return JSONResponse(
                status_code=415,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Неподдерживаемый формат файла.",
                },
            )
        else:
            logger.error(
                f"Ошибка при обработке файла {original_filename}: {error_msg}",
                exc_info=True,
            )
            return JSONResponse(
                status_code=422,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Файл поврежден или формат не поддерживается.",
                },
            )
    except Exception as e:
        logger.error(
            f"Ошибка при обработке base64-файла {original_filename}: {str(e)}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "filename": original_filename,
                "message": "Файл поврежден или формат не поддерживается.",
            },
        )


@app.post("/v1/extract/url")
async def extract_text_from_url(request: URLRequest):
    """Извлечение текста с веб-страницы (обновлено в v1.10.2)."""
    url = request.url.strip()

    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    # Проверка валидности URL
    if not url.startswith(("http://", "https://")):
        logger.warning(f"Некорректный URL: {url}")
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "url": url,
                "message": "URL должен начинаться с http:// или https://",
            },
        )

    logger.info(f"Начало извлечения текста с URL: {url}")

    # Используем user_agent из корневого уровня
    user_agent = request.user_agent

    try:
        # Извлечение текста в пуле потоков с таймаутом
        start_time = time.time()
        try:
            extracted_files = await asyncio.wait_for(
                run_in_threadpool(
                    text_extractor.extract_from_url,
                    url,
                    user_agent,
                    request.extraction_options,
                ),
                timeout=settings.PROCESSING_TIMEOUT_SECONDS,  # 300 секунд
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Таймаут обработки URL {url}: превышен лимит {settings.PROCESSING_TIMEOUT_SECONDS} секунд"
            )
            return JSONResponse(
                status_code=504,
                content={
                    "status": "error",
                    "url": url,
                    "message": f"Обработка веб-страницы превысила установленный лимит времени ({settings.PROCESSING_TIMEOUT_SECONDS} секунд).",
                },
            )

        process_time = time.time() - start_time

        # Подсчет общей длины текста
        total_text_length = sum(
            len(file_data.get("text", "")) for file_data in extracted_files
        )

        logger.info(
            f"Текст успешно извлечен с URL {url} за {process_time:.3f}s. "
            f"Обработано файлов: {len(extracted_files)}, общая длина текста: {total_text_length} символов"
        )

        return {
            "status": "success",
            "url": url,
            "count": len(extracted_files),
            "files": extracted_files,
        }

    except ValueError as e:
        error_msg = str(e)

        # Определяем тип ошибки для правильного HTTP-кода
        if "internal IP" in error_msg.lower() or "prohibited" in error_msg.lower():
            logger.warning(f"Запрос к заблокированному URL {url}: {error_msg}")
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "url": url,
                    "message": "Доступ к внутренним IP-адресам запрещен из соображений безопасности.",
                },
            )
        elif "timeout" in error_msg.lower():
            logger.warning(f"Таймаут загрузки URL {url}: {error_msg}")
            return JSONResponse(
                status_code=504,
                content={
                    "status": "error",
                    "url": url,
                    "message": "Не удалось загрузить страницу: превышен лимит времени ожидания.",
                },
            )
        elif "connection" in error_msg.lower() or "failed to load" in error_msg.lower():
            logger.warning(f"Ошибка подключения к URL {url}: {error_msg}")
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "url": url,
                    "message": f"Не удалось загрузить страницу: {error_msg}",
                },
            )
        else:
            logger.error(f"Ошибка при обработке URL {url}: {error_msg}")
            return JSONResponse(
                status_code=422,
                content={
                    "status": "error",
                    "url": url,
                    "message": f"Ошибка парсинга HTML: {error_msg}",
                },
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке URL {url}: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "url": url,
                "message": f"Ошибка обработки веб-страницы: {str(e)}",
            },
        )


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.API_PORT,
        log_level="info",
        reload=settings.DEBUG,
    )
