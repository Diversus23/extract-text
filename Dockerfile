# Этап сборки (builder)
FROM python:3.11-slim AS builder

# Устанавливаем системные зависимости для сборки
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /code

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости в локальную директорию
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt

# Производственный этап (production)
FROM python:3.11-slim AS production

# Устанавливаем системные зависимости для работы приложения
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    libreoffice \
    antiword \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Создаем пользователя для безопасности
RUN groupadd -r appuser && useradd -r -g appuser -m appuser

# Устанавливаем рабочую директорию
WORKDIR /code

# Копируем Python пакеты из этапа сборки
COPY --from=builder /root/.local /home/appuser/.local

# Копируем код приложения
COPY ./app /code/app

# Устанавливаем права доступа
RUN chown -R appuser:appuser /code && \
    chown -R appuser:appuser /home/appuser

# Переключаемся на пользователя appuser
USER appuser

# Добавляем локальную папку пользователя в PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Переменные окружения
ENV PYTHONPATH=/code
ENV PYTHONUNBUFFERED=1

# Открываем порт
EXPOSE 7555

# Добавляем healthcheck для мониторинга работоспособности
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:7555/health || exit 1

# Команда по умолчанию
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7555"] 