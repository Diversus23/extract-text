"""
Text Extraction API for RAG
Главный модуль FastAPI приложения
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
import uvicorn
import os
import logging
import asyncio
import base64
from typing import Dict, Any
import time
from contextlib import asynccontextmanager

from app.config import settings
from app.extractors import TextExtractor
from app.utils import setup_logging, sanitize_filename, validate_file_type, cleanup_temp_files, cleanup_recent_temp_files

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

# Инициализация экстрактора текста
text_extractor = TextExtractor()

# Pydantic модели
class Base64FileRequest(BaseModel):
    """Модель для запроса обработки base64-файла"""
    encoded_base64_file: str = Field(..., description="Файл в кодировке base64")
    filename: str = Field(..., description="Имя файла с расширением")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager для FastAPI приложения"""
    logger.info(f"Запуск Text Extraction API v{settings.VERSION}")
    
    # Очистка временных файлов при старте
    cleanup_temp_files()
    
    yield
    logger.info("Завершение работы Text Extraction API")

# Создание FastAPI приложения
app = FastAPI(
    title="Text Extraction API for RAG",
    description="API для извлечения текста из файлов различных форматов",
    version=settings.VERSION,
    lifespan=lifespan,
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT"
    },
    contact={
        "name": "Барилко Виталий",
        "email": "support@softonit.ru",
        "url": "https://softonit.ru"
    }
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
    """Middleware для логирования запросов"""
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
    """Информация о API"""
    return {
        "api_name": "Text Extraction API for RAG",
        "version": settings.VERSION,
        "contact": "Барилко Виталий"
    }


@app.get("/health")
async def health() -> Dict[str, str]:
    """Проверка состояния API"""
    return {"status": "ok"}


@app.get("/v1/supported-formats")
async def supported_formats() -> Dict[str, list]:
    """Поддерживаемые форматы файлов"""
    return settings.SUPPORTED_FORMATS


@app.post("/v1/extract/file")
async def extract_text(file: UploadFile = File(...)):
    """Извлечение текста из файла"""
    try:
        # Санитизация имени файла
        original_filename = file.filename or "unknown_file"
        safe_filename_for_processing = sanitize_filename(original_filename)
        
        logger.info(f"Получен файл для обработки: {original_filename}")
        
        # Проверка наличия размера файла (защита от DoS)
        if file.size is None:
            logger.warning(f"Файл {original_filename} не содержит заголовок Content-Length")
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Отсутствует заголовок Content-Length. Пожалуйста, убедитесь, что размер файла указан в запросе."
                }
            )
        
        # Проверка размера файла
        if file.size > settings.MAX_FILE_SIZE:
            logger.warning(f"Файл {original_filename} слишком большой: {file.size} bytes")
            raise HTTPException(
                status_code=413,
                detail="File size exceeds maximum allowed size"
            )
        
        # Чтение содержимого файла
        content = await file.read()
        
        # Проверка на пустой файл
        if not content:
            logger.warning(f"Файл {original_filename} пуст")
            raise HTTPException(
                status_code=422,
                detail="File is empty"
            )
        
        # Проверка соответствия расширения файла его содержимому
        is_valid, validation_error = validate_file_type(content, original_filename)
        if not is_valid:
            logger.warning(f"Файл {original_filename} не прошел проверку типа: {validation_error}")
            return JSONResponse(
                status_code=415,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Расширение файла не соответствует его содержимому. Возможная подделка типа файла."
                }
            )
        
        # Извлечение текста - КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: выполняем в пуле потоков с таймаутом
        start_time = time.time()
        try:
            extracted_files = await asyncio.wait_for(
                run_in_threadpool(
                    text_extractor.extract_text, content, safe_filename_for_processing
                ),
                timeout=settings.PROCESSING_TIMEOUT_SECONDS  # 300 секунд согласно ТЗ п.5.1
            )
        except asyncio.TimeoutError:
            logger.error(f"Таймаут обработки файла {original_filename}: превышен лимит {settings.PROCESSING_TIMEOUT_SECONDS} секунд")
            return JSONResponse(
                status_code=504,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": f"Обработка файла превысила установленный лимит времени ({settings.PROCESSING_TIMEOUT_SECONDS} секунд)."
                }
            )
        finally:
            # Дополнительная очистка временных файлов после обработки
            try:
                cleanup_recent_temp_files()
            except Exception as cleanup_error:
                logger.warning(f"Ошибка при очистке временных файлов: {str(cleanup_error)}")
        
        process_time = time.time() - start_time
        
        # Подсчет общей длины текста
        total_text_length = sum(len(file_data.get("text", "")) for file_data in extracted_files)
        
        logger.info(
            f"Текст успешно извлечен из {original_filename} за {process_time:.3f}s. "
            f"Обработано файлов: {len(extracted_files)}, общая длина текста: {total_text_length} символов"
        )
        
        return {
            "status": "success",
            "filename": original_filename,
            "count": len(extracted_files),
            "files": extracted_files
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
                    "message": "Неподдерживаемый формат файла."
                }
            )
        else:
            logger.error(f"Ошибка при обработке файла {original_filename}: {error_msg}", exc_info=True)
            return JSONResponse(
                status_code=422,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Файл поврежден или формат не поддерживается."
                }
            )
    except Exception as e:
        # Определяем имя файла для логирования
        filename_for_error = getattr(file, 'filename', 'unknown_file') or 'unknown_file'
        logger.error(f"Ошибка при обработке файла {filename_for_error}: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "filename": filename_for_error,
                "message": "Файл поврежден или формат не поддерживается."
            }
        )


@app.post("/v1/extract/base64")
async def extract_text_base64(request: Base64FileRequest):
    """Извлечение текста из base64-файла"""
    try:
        # Санитизация имени файла
        original_filename = request.filename
        safe_filename_for_processing = sanitize_filename(original_filename)
        
        logger.info(f"Получен base64-файл для обработки: {original_filename}")
        
        # Декодирование base64
        try:
            content = base64.b64decode(request.encoded_base64_file)
        except Exception as e:
            logger.warning(f"Ошибка декодирования base64 для файла {original_filename}: {str(e)}")
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Неверный формат base64. Убедитесь, что файл корректно закодирован в base64."
                }
            )
        
        # Проверка размера файла
        file_size = len(content)
        if file_size > settings.MAX_FILE_SIZE:
            logger.warning(f"Файл {original_filename} слишком большой: {file_size} bytes")
            raise HTTPException(
                status_code=413,
                detail="File size exceeds maximum allowed size"
            )
        
        # Проверка на пустой файл
        if not content:
            logger.warning(f"Файл {original_filename} пуст")
            raise HTTPException(
                status_code=422,
                detail="File is empty"
            )
        
        # Проверка соответствия расширения файла его содержимому
        is_valid, validation_error = validate_file_type(content, original_filename)
        if not is_valid:
            logger.warning(f"Файл {original_filename} не прошел проверку типа: {validation_error}")
            return JSONResponse(
                status_code=415,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Расширение файла не соответствует его содержимому. Возможная подделка типа файла."
                }
            )
        
        # Извлечение текста - выполняем в пуле потоков с таймаутом
        start_time = time.time()
        try:
            extracted_files = await asyncio.wait_for(
                run_in_threadpool(
                    text_extractor.extract_text, content, safe_filename_for_processing
                ),
                timeout=settings.PROCESSING_TIMEOUT_SECONDS  # 300 секунд согласно ТЗ п.5.1
            )
        except asyncio.TimeoutError:
            logger.error(f"Таймаут обработки файла {original_filename}: превышен лимит {settings.PROCESSING_TIMEOUT_SECONDS} секунд")
            return JSONResponse(
                status_code=504,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": f"Обработка файла превысила установленный лимит времени ({settings.PROCESSING_TIMEOUT_SECONDS} секунд)."
                }
            )
        finally:
            # Дополнительная очистка временных файлов после обработки base64-файла
            try:
                cleanup_recent_temp_files()
            except Exception as cleanup_error:
                logger.warning(f"Ошибка при очистке временных файлов: {str(cleanup_error)}")
        
        process_time = time.time() - start_time
        
        # Подсчет общей длины текста
        total_text_length = sum(len(file_data.get("text", "")) for file_data in extracted_files)
        
        logger.info(
            f"Текст успешно извлечен из base64-файла {original_filename} за {process_time:.3f}s. "
            f"Обработано файлов: {len(extracted_files)}, общая длина текста: {total_text_length} символов"
        )
        
        return {
            "status": "success",
            "filename": original_filename,
            "count": len(extracted_files),
            "files": extracted_files
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
                    "message": "Неподдерживаемый формат файла."
                }
            )
        else:
            logger.error(f"Ошибка при обработке файла {original_filename}: {error_msg}", exc_info=True)
            return JSONResponse(
                status_code=422,
                content={
                    "status": "error",
                    "filename": original_filename,
                    "message": "Файл поврежден или формат не поддерживается."
                }
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке base64-файла {original_filename}: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "filename": original_filename,
                "message": "Файл поврежден или формат не поддерживается."
            }
        )


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.API_PORT,
        log_level="info",
        reload=settings.DEBUG
    ) 