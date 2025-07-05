"""
Text Extraction API for RAG
Главный модуль FastAPI приложения
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import logging
from typing import Dict, Any
import time
from contextlib import asynccontextmanager

from app.config import settings
from app.extractors import TextExtractor
from app.utils import setup_logging

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

# Инициализация экстрактора текста
text_extractor = TextExtractor()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager для FastAPI приложения"""
    logger.info(f"Запуск Text Extraction API v{settings.VERSION}")
    yield
    logger.info("Завершение работы Text Extraction API")

# Создание FastAPI приложения
app = FastAPI(
    title="Text Extraction API for RAG",
    description="API для извлечения текста из файлов различных форматов",
    version=settings.VERSION,
    lifespan=lifespan
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
        "contact": "ООО 'СОФТОНИТ'"
    }


@app.get("/health")
async def health() -> Dict[str, str]:
    """Проверка состояния API"""
    return {"status": "ok"}


@app.get("/v1/supported-formats/")
async def supported_formats() -> Dict[str, list]:
    """Поддерживаемые форматы файлов"""
    return settings.SUPPORTED_FORMATS


@app.post("/v1/extract/")
async def extract_text(file: UploadFile = File(...)):
    """Извлечение текста из файла"""
    try:
        logger.info(f"Получен файл для обработки: {file.filename}")
        
        # Проверка размера файла
        if file.size and file.size > settings.MAX_FILE_SIZE:
            logger.warning(f"Файл {file.filename} слишком большой: {file.size} bytes")
            raise HTTPException(
                status_code=413,
                detail="File size exceeds maximum allowed size"
            )
        
        # Чтение содержимого файла
        content = await file.read()
        
        # Проверка на пустой файл
        if not content:
            logger.warning(f"Файл {file.filename} пуст")
            raise HTTPException(
                status_code=422,
                detail="File is empty"
            )
        
        # Извлечение текста
        start_time = time.time()
        extracted_text = await text_extractor.extract_text(content, file.filename)
        process_time = time.time() - start_time
        
        logger.info(
            f"Текст успешно извлечен из {file.filename} за {process_time:.3f}s. "
            f"Длина текста: {len(extracted_text)} символов"
        )
        
        return {
            "status": "success",
            "filename": file.filename,
            "text": extracted_text
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при обработке файла {file.filename}: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "filename": file.filename,
                "message": "File is corrupted or format is not supported."
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