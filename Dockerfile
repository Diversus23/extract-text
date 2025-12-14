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

# Устанавливаем Python зависимости от root (стандартная практика в Docker)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Устанавливаем замещающие пакеты для зависимостей Playwright
RUN apt-get update && apt-get install -y \
    fonts-unifont \
    fonts-liberation \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем системные зависимости для Playwright (без проблемных пакетов)
RUN playwright install-deps chromium || true && \
    apt-get update && apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Копируем код приложения
COPY ./app /code/app

# Настраиваем права доступа
RUN chown -R appuser:appuser /code && \
    mkdir -p /home/appuser/.cache && \
    chown -R appuser:appuser /home/appuser

# Переключаемся на пользователя для безопасного запуска приложения
USER appuser

# Устанавливаем Playwright браузер от пользователя
RUN playwright install chromium

# Переменные окружения
ENV PYTHONPATH=/code
ENV PYTHONUNBUFFERED=1

# Открываем порт
EXPOSE 7555

# Команда по умолчанию
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7555"] 