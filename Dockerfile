# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    libreoffice \
    antiword \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /code

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY ./app /code/app

# Создаем пользователя для безопасности
RUN groupadd -r appuser && useradd -r -g appuser -m appuser && \
    chown -R appuser:appuser /code && \
    mkdir -p /home/appuser/.cache && \
    chown -R appuser:appuser /home/appuser
USER appuser

# Переменные окружения
ENV PYTHONPATH=/code
ENV PYTHONUNBUFFERED=1

# Открываем порт
EXPOSE 7555

# Команда по умолчанию
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7555"] 