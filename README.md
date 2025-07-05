# Text Extraction API for RAG

API для извлечения текста из файлов различных форматов, предназначенный для создания векторных представлений (embeddings) в системах RAG (Retrieval-Augmented Generation).

## Особенности

- 🔧 **Широкая поддержка форматов**: PDF, DOCX, PPT, изображения, таблицы и многое другое
- 🖼️ **OCR**: Распознавание текста на изображениях (русский и английский языки)
- 🚀 **Высокая производительность**: Асинхронная обработка с таймаутами
- 📊 **Структурированный вывод**: Объединение текста из разных источников
- 🐳 **Docker**: Готовый к развертыванию контейнер
- 📝 **Автодокументация**: Swagger UI интерфейс
- 🔄 **Гибкая настройка**: Переменные окружения

## Поддерживаемые форматы

### Документы
- PDF (с OCR для изображений)
- DOCX, DOC
- ODT, RTF

### Презентации
- PPTX, PPT (включая заметки спикера)

### Таблицы
- XLSX, XLS, ODS
- CSV

### Изображения (OCR)
- JPG, JPEG, PNG
- TIFF, TIF, BMP, GIF

### Прочие
- TXT, HTML, HTM
- MD, Markdown
- JSON, EPUB, EML, MSG

## Быстрый старт

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd text-extraction-api
```

### 2. Запуск в Docker (рекомендуется)

```bash
# Сборка и запуск в режиме разработки
make dev

# Или для продакшена
make prod
```

### 3. Проверка работы

```bash
# Проверка статуса
curl http://localhost:7555/health

# Получение поддерживаемых форматов
curl http://localhost:7555/v1/supported-formats/
```

## Использование API

### Эндпоинты

#### `GET /` - Информация о API
```bash
curl http://localhost:7555/
```

#### `GET /health` - Проверка состояния
```bash
curl http://localhost:7555/health
```

#### `GET /v1/supported-formats/` - Поддерживаемые форматы
```bash
curl http://localhost:7555/v1/supported-formats/
```

#### `POST /v1/extract/` - Извлечение текста
```bash
curl -X POST \
  -F "file=@document.pdf" \
  http://localhost:7555/v1/extract/
```

### Примеры ответов

#### Успешное извлечение
```json
{
  "status": "success",
  "filename": "document.pdf",
  "text": "Извлеченный текст из документа..."
}
```

#### Ошибка
```json
{
  "status": "error",
  "filename": "broken.pdf",
  "message": "File is corrupted or format is not supported."
}
```

### Коды ошибок

- `413` - Файл слишком большой (>20MB)
- `415` - Неподдерживаемый формат
- `422` - Поврежденный файл или пустой
- `504` - Превышен лимит времени обработки

## Конфигурация

### Переменные окружения

```bash
# Порт API (по умолчанию: 7555)
API_PORT=7555

# Режим отладки
DEBUG=true

# Языки для OCR (по умолчанию: rus+eng)
OCR_LANGUAGES=rus+eng

# Таймаут обработки в секундах (по умолчанию: 300)
PROCESSING_TIMEOUT_SECONDS=300

# Уровень логирования
LOG_LEVEL=INFO
```

### Настройка .env файла

```bash
cp env_example .env
# Отредактируйте .env под ваши нужды
```

## Команды управления

### Makefile команды

```bash
# Помощь
make help

# Сборка образа
make build

# Запуск в режиме разработки
make dev

# Запуск в продакшене
make prod

# Остановка
make stop

# Просмотр логов
make logs

# Тестирование
make test

# Очистка
make clean
```

### Docker Compose команды

```bash
# Разработка
docker-compose up

# Продакшен
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Остановка
docker-compose down
```

## Разработка

### Локальная разработка

```bash
# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows

# Установка зависимостей
pip install -r requirements.txt

# Запуск сервера разработки
uvicorn app.main:app --reload --host 0.0.0.0 --port 7555
```

### Структура проекта

```
├── app/
│   ├── __init__.py
│   ├── main.py           # Главный модуль FastAPI
│   ├── config.py         # Конфигурация
│   ├── extractors.py     # Извлечение текста
│   └── utils.py          # Утилиты
├── tests/                # Тестовые файлы
├── docs/                 # Документация
├── requirements.txt      # Python зависимости
├── Dockerfile           # Docker образ
├── docker-compose.yml   # Разработка
├── docker-compose.prod.yml # Продакшен
├── Makefile            # Команды управления
├── run_tests.sh        # Скрипт тестирования
└── README.md           # Документация
```

## Тестирование

### Автоматическое тестирование

```bash
# Запуск тестов
make test

# Или напрямую
./run_tests.sh
```

Скрипт тестирования:
1. Проверяет доступность API
2. Тестирует все файлы из папки `tests/`
3. Создает файлы результатов:
   - `filename.ok.txt` - успешное извлечение
   - `filename.err.txt` - ошибки

### Ручное тестирование

```bash
# Тестирование PDF
curl -X POST -F "file=@tests/sample.pdf" http://localhost:7555/v1/extract/

# Тестирование изображения
curl -X POST -F "file=@tests/sample.jpg" http://localhost:7555/v1/extract/

# Тестирование DOCX
curl -X POST -F "file=@tests/sample.docx" http://localhost:7555/v1/extract/
```

## Интерактивная документация

После запуска API, документация доступна по адресам:

- **Swagger UI**: http://localhost:7555/docs
- **ReDoc**: http://localhost:7555/redoc

## Мониторинг и логирование

### Структурированные логи

API ведет подробные логи:
- Входящие запросы
- Время обработки
- Ошибки с traceback
- Статистика извлечения

### Просмотр логов

```bash
# Docker логи
make logs

# Или напрямую
docker-compose logs -f
```

## Производительность

### Ограничения

- **Максимальный размер файла**: 20 MB
- **Таймаут обработки**: 300 секунд (5 минут)
- **Одновременная обработка**: Асинхронная

### Оптимизация

- Используйте правильные форматы файлов
- Сжимайте изображения перед отправкой
- Избегайте чрезмерно сложных PDF с множеством изображений

## Развертывание

### Docker (рекомендуется)

```bash
# Сборка
docker build -t text-extraction-api .

# Запуск
docker run -p 7555:7555 text-extraction-api
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: text-extraction-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: text-extraction-api
  template:
    metadata:
      labels:
        app: text-extraction-api
    spec:
      containers:
      - name: api
        image: text-extraction-api:latest
        ports:
        - containerPort: 7555
        env:
        - name: API_PORT
          value: "7555"
        - name: OCR_LANGUAGES
          value: "rus+eng"
```

## Устранение проблем

### Частые проблемы

1. **OCR не работает**
   - Проверьте установку tesseract
   - Убедитесь в наличии языковых пакетов

2. **Ошибки памяти**
   - Уменьшите размер файлов
   - Увеличьте лимиты контейнера

3. **Таймауты**
   - Увеличьте `PROCESSING_TIMEOUT_SECONDS`
   - Оптимизируйте входные файлы

### Логи отладки

```bash
# Включение отладки
export DEBUG=true

# Просмотр подробных логов
docker-compose logs -f api
```

## Контрибуция

1. Форк репозитория
2. Создание ветки для фичи
3. Коммит изменений
4. Пуш в ветку
5. Создание Pull Request

## Лицензия

Этот проект лицензирован под MIT License - см. файл [LICENSE](LICENSE).

## Поддержка

Для вопросов и поддержки:
- GitHub Issues
- Email: support@example.com

---

**Версия**: 1.5  
**Разработчик**: ООО "СОФТОНИТ"  
**Дата**: 2024 