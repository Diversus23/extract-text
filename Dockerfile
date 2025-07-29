# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    libreoffice \
    antiword \
    libmagic1 \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Создаем пользователя для безопасности раньше
RUN groupadd -r appuser && useradd -r -g appuser -m appuser

# Устанавливаем рабочую директорию
WORKDIR /code

# Изменяем владельца рабочей директории
RUN chown -R appuser:appuser /code

# Копируем файл зависимостей
COPY requirements.txt .
RUN chown appuser:appuser requirements.txt

# Переключаемся на пользователя для безопасной установки зависимостей
USER appuser

# Устанавливаем Python зависимости от непривилегированного пользователя
RUN pip install --no-cache-dir --upgrade --user pip && \
    pip install --no-cache-dir --user -r requirements.txt

# Переключаемся обратно на root для системных зависимостей Playwright
USER root

# Настраиваем PATH и устанавливаем системные зависимости для Playwright
ENV PATH=/home/appuser/.local/bin:$PATH
RUN PATH=/home/appuser/.local/bin:$PATH playwright install-deps chromium

# Копируем код приложения
COPY ./app /code/app

# Настраиваем права доступа
RUN chown -R appuser:appuser /code && \
    mkdir -p /home/appuser/.cache && \
    chown -R appuser:appuser /home/appuser

# Переключаемся на пользователя и устанавливаем Playwright браузер
USER appuser
RUN playwright install chromium

# Переменные окружения
ENV PYTHONPATH=/code
ENV PYTHONUNBUFFERED=1

# Открываем порт
EXPOSE 7555

# Команда по умолчанию
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7555"] 