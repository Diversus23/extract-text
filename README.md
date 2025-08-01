# Text Extraction API for RAG

[![CI/CD Pipeline](https://github.com/Diversus23/extract-text/workflows/CI/CD%20Pipeline/badge.svg)](https://github.com/Diversus23/extract-text/actions)
[![Coverage](https://img.shields.io/badge/coverage-60%25-brightgreen)](https://github.com/Diversus23/extract-text/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?logo=fastapi)](https://fastapi.tiangolo.com)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://docker.com)

API для извлечения текста из файлов различных форматов, предназначенный для создания векторных представлений (embeddings) в системах RAG (Retrieval-Augmented Generation).

## Особенности

- 🔧 **Широкая поддержка форматов**: PDF, DOCX, PPT, изображения, таблицы, исходный код и многое другое
- 💻 **Поддержка исходного кода**: Более 50 языков программирования и форматов конфигурации
- 🖼️ **OCR**: Распознавание текста на изображениях (русский и английский языки)
- 📦 **Обработка архивов**: Извлечение текста из файлов внутри архивов с таймаутом 300 секунд (ZIP, RAR, 7Z, TAR и др.)
- 🌐 **Веб-экстракция с JavaScript**: Извлечение текста с современных веб-страниц с поддержкой SPA и lazy loading (Playwright + Chromium)
- 🎭 **Base64 изображения**: Автоматическое извлечение и OCR встроенных base64-изображений из веб-страниц
- 🔄 **Умная lazy loading**: Безопасный скролл для активации ленивой загрузки с защитой от бесконечных лент
- 🚀 **Асинхронная обработка**: Неблокирующее выполнение с поддержкой множественных worker-процессов
- 📊 **Структурированный вывод**: Объединение текста из разных источников
- 🔒 **Безопасность**: Защита от path traversal, подделки типов файлов, DoS-атак и SSRF
- 🐳 **Docker**: Готовый к развертыванию контейнер
- 📝 **Автодокументация**: Swagger UI интерфейс
- 🧪 **Комплексное тестирование**: Unit, integration и функциональные тесты
- 💾 **Полное извлечение**: Полное извлечение из DOCX (с колонтитулами, сносками, комментариями) и PPTX (с заметками спикера)
- 📋 **Base64 поддержка**: Обработка файлов в формате base64 через JSON API для интеграции с системами

## Поддерживаемые форматы

### Документы
- PDF (с OCR для изображений)
- DOCX, DOC (полное извлечение включая колонтитулы, сноски, комментарии)
- ODT, RTF

### Презентации
- PPTX, PPT (полное извлечение включая заметки спикера)

### Таблицы
- XLSX, XLS, ODS
- CSV

### Изображения (OCR)
- JPG, JPEG, PNG
- TIFF, TIF, BMP, GIF
- WebP

### Архивы
- ZIP, RAR, 7Z
- TAR, GZ, BZ2, XZ
- TGZ, TBZ2, TXZ
- TAR.GZ, TAR.BZ2, TAR.XZ

### Исходный код и конфигурации
#### Языки программирования
- **Python**: `.py`, `.pyx`, `.pyi`, `.pyw`
- **JavaScript/TypeScript**: `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`
- **Java**: `.java`, `.jav`
- **C/C++**: `.c`, `.cpp`, `.cxx`, `.cc`, `.c++`, `.h`, `.hpp`, `.hxx`, `.h++`
- **C#**: `.cs`, `.csx`
- **PHP**: `.php`, `.php3`, `.php4`, `.php5`, `.phtml`
- **Ruby**: `.rb`, `.rbw`, `.rake`, `.gemspec`
- **Go**: `.go`, `.mod`, `.sum`
- **Rust**: `.rs`, `.rlib`
- **Swift**: `.swift`
- **Kotlin**: `.kt`, `.kts`
- **Scala**: `.scala`, `.sc`
- **R**: `.r`, `.rmd`
- **SQL**: `.sql`, `.ddl`, `.dml`
- **Shell**: `.sh`, `.bash`, `.zsh`, `.fish`, `.ksh`, `.csh`, `.tcsh`
- **PowerShell**: `.ps1`, `.psm1`, `.psd1`
- **Perl**: `.pl`, `.pm`, `.pod`, `.t`
- **Lua**: `.lua`
- **1C:Enterprise**: `.bsl`
- **OneScript**: `.os`

#### Конфигурационные файлы
- **Общие**: `.ini`, `.cfg`, `.conf`, `.config`, `.properties`
- **TOML**: `.toml`
- **YAML**: `.yaml`, `.yml`
- **JSON**: `.json`, `.jsonc`, `.jsonl`, `.ndjson`
- **XML**: `.xml`

#### Веб-технологии
- **CSS**: `.css`, `.scss`, `.sass`, `.less`, `.styl`
- **HTML**: `.html`, `.htm`

#### Разметка и документация
- **Markdown**: `.md`, `.markdown`
- **LaTeX**: `.tex`, `.latex`
- **reStructuredText**: `.rst`
- **AsciiDoc**: `.adoc`, `.asciidoc`

#### Специальные форматы
- **Docker**: `.dockerfile`, `.containerfile`
- **Makefile**: `.makefile`, `.mk`, `.mak`
- **Git**: `.gitignore`, `.gitattributes`, `.gitmodules`

### Электронная почта и книги
- **Email**: `.eml`, `.msg`
- **Электронные книги**: `.epub`

### Веб-страницы (новое в v1.10.0, улучшено в v1.10.1)
- **HTTP/HTTPS URL**: Извлечение текста непосредственно с веб-страниц
- **HTML-контент**: Автоматическое удаление разметки, скриптов и стилей
- **Изображения на странице**: OCR крупных изображений (>150x150 пикселей)
- **Base64 изображения**: Поддержка встроенных base64 изображений (data:image/...)
- **JavaScript рендеринг**: Полная поддержка SPA и динамического контента через Playwright
- **Lazy loading**: Автоматическая активация ленивой загрузки изображений с защитой от бесконечного скролла
- **Безопасность**: Защита от SSRF-атак, блокировка внутренних IP

### Текстовые файлы
- TXT

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
curl http://localhost:7555/v1/supported-formats
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

#### `GET /v1/supported-formats` - Поддерживаемые форматы
```bash
curl http://localhost:7555/v1/supported-formats
```

#### `POST /v1/extract/file` - Извлечение текста
```bash
curl -X POST \
  -F "file=@document.pdf" \
  http://localhost:7555/v1/extract/file
```

#### `POST /v1/extract/base64` - Извлечение текста из base64-файла
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "encoded_base64_file": "0J/RgNC40LLQtdGCINGN0YLQviDRgtC10LrRgdGCIQ==",
    "filename": "document.txt"
  }' \
  http://localhost:7555/v1/extract/base64
```

#### `POST /v1/extract/url` - Извлечение текста с веб-страниц и файлов по URL (новое в v1.10.0, расширено в v1.10.2, v1.10.3)

**Базовый запрос (для обратной совместимости):**
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/page",
    "user_agent": "Text Extraction Bot 1.0"
  }' \
  http://localhost:7555/v1/extract/url
```

**Расширенный запрос с настройками извлечения (новое в v1.10.2):**
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/spa-app",
    "extraction_options": {
      "enable_javascript": true,
      "js_render_timeout": 15,
      "web_page_delay": 2,
      "enable_lazy_loading_wait": false,
      "max_scroll_attempts": 0,
      "process_images": true,
      "max_images_per_page": 5,
      "web_page_timeout": 20
    }
  }' \
  http://localhost:7555/v1/extract/url
```

**Скачивание файла по URL (новое в v1.10.3):**
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/document.pdf"
  }' \
  http://localhost:7555/v1/extract/url
```

### Примеры ответов

#### Успешное извлечение (обычный файл)
```json
{
  "status": "success",
  "filename": "document.pdf",
  "files": [
    {
      "filename": "document.pdf",
      "path": "document.pdf",
      "size": 1024000,
      "type": "pdf",
      "text": "Извлеченный текст из документа..."
    }
  ]
}
```

#### Успешное извлечение (архив)
```json
{
  "status": "success",
  "filename": "documents.zip",
  "files": [
    {
      "filename": "document1.pdf",
      "path": "documents/document1.pdf",
      "size": 524288,
      "type": "pdf",
      "text": "Текст из первого документа..."
    },
    {
      "filename": "image1.jpg",
      "path": "documents/images/image1.jpg",
      "size": 102400,
      "type": "jpg",
      "text": "Распознанный текст с изображения..."
    }
  ]
}
```

#### Успешное извлечение (веб-страница, новое в v1.10.0)
```json
{
  "status": "success",
  "url": "https://example.com/news/article",
  "count": 3,
  "files": [
    {
      "filename": "page_content",
      "path": "https://example.com/news/article",
      "size": 45670,
      "type": "html",
      "text": "Заголовок статьи. Основной текст новости с подробным описанием события..."
    },
    {
      "filename": "photo1.jpg",
      "path": "https://example.com/images/photo1.jpg", 
      "size": 234567,
      "type": "jpg",
      "text": "Подпись к фотографии на изображении..."
    },
    {
      "filename": "chart.png",
      "path": "https://example.com/assets/chart.png",
      "size": 189432,
      "type": "png", 
      "text": "Данные с диаграммы: 2023 - 45%, 2024 - 67%"
    }
  ]
}
```

#### Успешное извлечение (скачанный файл по URL, новое в v1.10.3)
```json
{
  "status": "success",
  "url": "https://example.com/document.pdf",
  "count": 1,
  "files": [
    {
      "filename": "document.pdf",
      "path": "document.pdf",
      "size": 1024000,
      "type": "pdf",
      "text": "Извлеченный текст из скачанного PDF документа..."
    }
  ]
}
```

#### Успешное извлечение (скачанный архив по URL, новое в v1.10.3)
```json
{
  "status": "success",
  "url": "https://example.com/files.zip",
  "count": 2,
  "files": [
    {
      "filename": "document1.docx",
      "path": "files/document1.docx",
      "size": 524288,
      "type": "docx",
      "text": "Текст из первого документа в архиве..."
    },
    {
      "filename": "image1.jpg",
      "path": "files/images/image1.jpg",
      "size": 102400,
      "type": "jpg",
      "text": "Распознанный текст с изображения из архива..."
    }
  ]
}
```

#### Ошибка
```json
{
  "status": "error",
  "filename": "broken.pdf",
  "message": "Файл поврежден или формат не поддерживается."
}
```

### Коды ошибок

- `400` - Некорректный запрос (отсутствует Content-Length или неверный base64)
- `413` - Файл слишком большой (>20MB)
- `415` - Неподдерживаемый формат или несоответствие типа файла
- `422` - Поврежденный файл, пустой или защищенный паролем
- `504` - Превышен лимит времени обработки

### Настройки извлечения для веб-страниц (новое в v1.10.2)

API теперь поддерживает гибкие настройки извлечения текста с веб-страниц через параметр `extraction_options`. Все параметры **опциональны** и позволяют адаптировать процесс извлечения под конкретные требования.

#### Параметры настройки

**JavaScript и рендеринг:**
- `enable_javascript`: Включить Playwright для JS-рендеринга (по умолчанию: `false`)
- `js_render_timeout`: Таймаут JS-рендеринга в секундах (по умолчанию: `10`)
- `web_page_delay`: Задержка после JS в секундах (по умолчанию: `3`)

**Lazy Loading:**
- `enable_lazy_loading_wait`: Автоматический скролл для lazy loading (по умолчанию: `true`)
- `max_scroll_attempts`: Количество попыток скролла, 0 = без скролла (по умолчанию: `3`)

**Обработка изображений:**
- `process_images`: Обрабатывать изображения через OCR (по умолчанию: `true`)
- `enable_base64_images`: Обрабатывать base64 изображения (по умолчанию: `true`)
- `min_image_size_for_ocr`: Минимальный размер для OCR в пикселях (по умолчанию: `22500`)
- `max_images_per_page`: Максимум изображений на странице (по умолчанию: `20`)

**Таймауты:**
- `web_page_timeout`: Таймаут загрузки страницы в секундах (по умолчанию: `30`)
- `image_download_timeout`: Таймаут загрузки изображений в секундах (по умолчанию: `15`)

**Сетевые настройки:**
- `follow_redirects`: Следовать редиректам (по умолчанию: `true`)
- `max_redirects`: Максимум редиректов (только для requests)

**User-Agent:** Используется параметр `user_agent` на корневом уровне запроса.

#### Примеры использования

**Быстрое извлечение без lazy loading:**
```json
{
  "url": "https://news.example.com/article",
  "extraction_options": {
    "enable_lazy_loading_wait": false,
    "max_scroll_attempts": 0,
    "web_page_delay": 1,
    "web_page_timeout": 15
  }
}
```

**Только текст, без изображений:**
```json
{
  "url": "https://blog.example.com/post",
  "extraction_options": {
    "process_images": false,
    "enable_base64_images": false
  }
}
```

**Тщательная обработка SPA:**
```json
{
  "url": "https://spa.example.com",
  "extraction_options": {
    "enable_javascript": true,
    "js_render_timeout": 20,
    "web_page_delay": 5,
    "enable_lazy_loading_wait": true,
    "max_scroll_attempts": 5
  }
}
```

**Максимальная производительность:**
```json
{
  "url": "https://simple.example.com",
  "extraction_options": {
    "enable_javascript": false,
    "process_images": false,
    "web_page_timeout": 10
  }
}
```

### Выбор эндпоинта

**Используйте `/v1/extract/file`** когда:
- Загружаете файлы напрямую через форму или drag&drop
- Работаете с локальными файлами
- Интегрируетесь с файловыми системами

**Используйте `/v1/extract/base64`** когда:
- Файл уже закодирован в base64 в вашей системе
- Интегрируетесь с API, которые передают файлы в base64
- Работаете с микросервисной архитектурой через JSON
- Файл хранится в базе данных в виде base64

**Используйте `/v1/extract/url`** когда:
- Извлекаете текст напрямую с веб-страниц
- Работаете с современными веб-приложениями (SPA)
- Нужен контроль над процессом извлечения (JavaScript, lazy loading, изображения)
- **Скачиваете и обрабатываете файлы по URL (новое в v1.10.3)**
- Работаете с прямыми ссылками на документы, PDF, архивы и другие файлы
- Интегрируетесь с системами где файлы доступны через HTTP/HTTPS ссылки

### Примеры ошибок безопасности

```json
{
  "status": "error",
  "filename": "document.pdf",
  "message": "Отсутствует заголовок Content-Length. Пожалуйста, убедитесь, что размер файла указан в запросе."
}
```

```json
{
  "status": "error",
  "filename": "malicious.txt",
  "message": "Расширение файла не соответствует его содержимому. Возможная подделка типа файла."
}
```

## Безопасность

API включает несколько уровней защиты:

### 🛡️ Санитизация имен файлов
- Автоматическая очистка имен файлов от потенциально опасных символов
- Предотвращение атак типа path traversal (`../../../etc/passwd`)
- Использование безопасных имен для внутренней обработки

### 🔍 Проверка типов файлов
- Верификация соответствия расширения файла его реальному содержимому
- Использование MIME-типов для определения истинного формата
- Предотвращение загрузки исполняемых файлов под видом текстовых

### 🚫 Защита от DoS-атак
- Обязательная проверка наличия заголовка `Content-Length`
- Предотвращение загрузки файлов неизвестного размера
- Ограничение максимального размера файла (20MB)

### 🗜️ Защита от zip-бомб
- Ограничение размера распакованного содержимого архивов (100MB)
- Контроль глубины вложенности архивов (максимум 3 уровня)
- Изоляция процесса распаковки с таймаутом

### 📋 Логирование безопасности
- Детальное логирование всех попыток нарушения безопасности
- Предупреждения о подозрительной активности
- Трассировка потенциальных угроз

## Конфигурация

### Переменные окружения

```bash
# Порт API (по умолчанию: 7555)
API_PORT=7555

# Режим отладки
DEBUG=false

# Языки для OCR (по умолчанию: rus+eng)
OCR_LANGUAGES=rus+eng

# Таймаут обработки в секундах (по умолчанию: 300)
PROCESSING_TIMEOUT_SECONDS=300

# Количество ядер CPU (по умолчанию: 4)
# Используется для автоматического расчета WORKERS в продакшене
CPU_CORES=4

# Количество worker-процессов uvicorn (по умолчанию: 1)
# Для продакшена автоматически вычисляется: 2 * CPU_CORES + 1
WORKERS=1

# Максимальный размер файла в байтах (по умолчанию: 20MB)
MAX_FILE_SIZE=20971520

# Максимальный размер архива в байтах (по умолчанию: 20MB)
MAX_ARCHIVE_SIZE=20971520

# Максимальный размер распакованного содержимого (по умолчанию: 100MB)
MAX_EXTRACTED_SIZE=104857600

# Максимальная глубина вложенности архивов (по умолчанию: 3)
MAX_ARCHIVE_NESTING=3

# Настройки веб-экстрактора (новое в v1.10.0)
# Минимальный размер изображений для OCR в пикселях (по умолчанию: 150x150 = 22500)
MIN_IMAGE_SIZE_FOR_OCR=22500

# Максимальное количество изображений для обработки на странице (по умолчанию: 20)
MAX_IMAGES_PER_PAGE=20

# Таймаут загрузки веб-страницы в секундах (по умолчанию: 30)
WEB_PAGE_TIMEOUT=30

# Таймаут загрузки изображения в секундах (по умолчанию: 15)
IMAGE_DOWNLOAD_TIMEOUT=15

# User-Agent по умолчанию для веб-запросов
DEFAULT_USER_AGENT="Text Extraction Bot 1.0"

# Включить выполнение JavaScript (по умолчанию: false, требует дополнительных ресурсов)
ENABLE_JAVASCRIPT=false

# Заблокированные IP-диапазоны для защиты от SSRF
BLOCKED_IP_RANGES="127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,::1/128,fe80::/10"

# Настройки веб-экстрактора v1.10.1 (Playwright)
# Включить поддержку base64 изображений (по умолчанию: true)
ENABLE_BASE64_IMAGES=true

# Задержка после загрузки JavaScript в секундах (по умолчанию: 3)
WEB_PAGE_DELAY=3

# Включить ожидание lazy loading изображений (по умолчанию: true)
ENABLE_LAZY_LOADING_WAIT=true

# Отдельный таймаут для JS-рендеринга в секундах (по умолчанию: 10)
JS_RENDER_TIMEOUT=10

# Максимальное количество попыток скролла для lazy loading (по умолчанию: 3)
MAX_SCROLL_ATTEMPTS=3

# Новые настройки для определения типа контента и скачивания файлов (v1.10.3)
# Таймаут HEAD запроса для определения типа контента в секундах (по умолчанию: 10)
HEAD_REQUEST_TIMEOUT=10

# Таймаут скачивания файлов в секундах (по умолчанию: 60)
FILE_DOWNLOAD_TIMEOUT=60
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

# Сборка и развертывание
make build          # Собрать Docker образ
make dev            # Запустить в режиме разработки
make prod           # Запустить в продакшене

# Управление сервисом
make stop           # Остановить все контейнеры
make logs           # Показать логи приложения
make status         # Показать статус контейнеров

# Тестирование
make test           # Полное тестирование с покрытием
make test-unit      # Только unit тесты
make test-integration # Только integration тесты
make test-docker    # Тестирование в Docker
make test-coverage  # Показать отчет покрытия
make test-legacy    # Старые функциональные тесты

# Проверка кода
make install-linters # Установить инструменты для проверки кода
make lint           # Проверить код всеми линтерами
make lint-check     # Проверить код без исправлений
make format         # Автоформатирование кода (black + isort)

# Очистка
make clean          # Полная очистка системы
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

# Установка браузеров Playwright (новое в v1.10.1)
playwright install chromium

# Новые зависимости для веб-экстракции:
# v1.10.0: requests, beautifulsoup4, lxml, urllib3
# v1.10.1: playwright - для JS-рендеринга и lazy loading

# Запуск сервера разработки
uvicorn app.main:app --reload --host 0.0.0.0 --port 7555
```

### Структура проекта

```
├── app/
│   ├── __init__.py
│   ├── main.py           # Главный модуль FastAPI
│   ├── config.py         # Конфигурация
│   ├── extractors.py     # Извлечение текста из всех форматов
│   └── utils.py          # Утилиты (включая функции безопасности)
├── tests/                # Тестовые файлы (126+ файлов различных форматов)
├── docs/
│   └── TZ.md            # Техническое задание
├── requirements.txt      # Python зависимости
├── requirements-test.txt # Зависимости для тестирования
├── Dockerfile           # Docker образ с системными зависимостями
├── docker-compose.yml   # Разработка
├── docker-compose.prod.yml # Продакшен
├── Makefile            # Команды управления
├── run_tests.sh        # Скрипт legacy тестирования
├── CHANGELOG.md        # Журнал изменений
└── README.md           # Документация
```

## Тестирование

### Автоматическое тестирование

```bash
# Запуск всех тестов
make test

# Отдельные виды тестов
make test-unit         # Unit тесты
make test-integration  # Integration тесты
make test-docker       # Тестирование в Docker
```

### Система тестирования

**Современная система тестирования:**
- **Framework**: pytest + pytest-asyncio
- **Покрытие**: pytest-cov с минимальным порогом 60%
- **HTTP тесты**: httpx для тестирования API
- **Моки**: pytest-mock для внешних зависимостей
- **Типы тестов**: Unit, Integration, Real Files

**Структура тестов:**
```
tests/
├── conftest.py          # Общие фикстуры
├── test_config.py       # Тесты конфигурации
├── test_extractors.py   # Тесты извлечения текста
├── test_integration.py  # Integration тесты с реальными файлами
├── test_main.py         # Тесты API эндпоинтов
├── test_utils.py        # Тесты утилит
└── [126+ test files]    # Реальные файлы для тестирования
```

**Статистика тестирования:**
- **Всего тестов**: 120+
- **Покрытие кода**: 37%+ (требуется минимум 60%)
- **Поддерживаемые форматы**: 130+
- **Тестовые файлы**: 126+
- **Успешность**: 94.4% (119 из 126 файлов)

### Legacy функциональное тестирование

```bash
# Запуск старых функциональных тестов
make test-legacy
```

Скрипт `run_tests.sh`:
1. Проверяет доступность API
2. Тестирует все файлы из папки `tests/`
3. Создает файлы результатов:
   - `filename.ok.txt` - успешное извлечение
   - `filename.err.txt` - ошибки
4. Выводит статистику покрытия форматов

### Тестирование с реальными файлами

Новый класс `TestAllRealFiles` в `tests/test_integration.py`:
- Автоматически находит все файлы с поддерживаемыми расширениями
- Исключает служебные файлы и результаты тестов
- Отправляет файлы в API для проверки функциональности
- Предоставляет детальную статистику по типам файлов

## Интерактивная документация

После запуска API, документация доступна по адресам:

- **Swagger UI**: http://localhost:7555/docs
- **ReDoc**: http://localhost:7555/redoc

## Проверка качества кода

### Линтеры и форматирование

Проект использует современные инструменты для поддержания качества кода:

```bash
# Установка инструментов
make install-linters

# Автоформатирование кода
make format

# Проверка всеми линтерами
make lint

# Проверка без исправлений  
make lint-check
```

### Используемые инструменты

**Форматирование:**
- **Black**: Автоформатирование Python кода
- **isort**: Сортировка и организация импортов

**Проверка стиля:**
- **Flake8**: Проверка соответствия PEP 8 и поиск ошибок
- **MyPy**: Статическая проверка типов (опционально)

**Безопасность:**
- **Bandit**: Поиск уязвимостей в коде
- **Safety**: Проверка зависимостей на известные уязвимости

### Конфигурация

Настройки линтеров находятся в:
- `pyproject.toml` - конфигурация Black, isort, MyPy, pytest
- `.flake8` - настройки Flake8
- `requirements-lint.txt` - зависимости для проверки кода

### GitHub Actions

Проект включает полный CI/CD pipeline:
- **Линтинг**: Автоматическая проверка кода при каждом коммите
- **Тестирование**: Запуск тестов в Docker и на разных версиях Python  
- **Безопасность**: Проверка на уязвимости
- **Покрытие**: Генерация отчетов покрытия и загрузка в Codecov
- **Артефакты**: Сохранение отчетов для анализа

```bash
# Локальная проверка перед коммитом
make format    # Исправить форматирование
make lint      # Проверить все аспекты
make test      # Запустить тесты
```

## Мониторинг и логирование

### Структурированные логи

API ведет подробные логи:
- Входящие запросы с временными метками
- Время обработки каждого файла
- Ошибки с полным traceback
- Статистика извлечения (количество файлов, длина текста)
- Предупреждения безопасности

### Просмотр логов

```bash
# Docker логи
make logs

# Статус контейнеров
make status

# Или напрямую
docker-compose logs -f
```

## Производительность

### Ограничения

- **Максимальный размер файла**: 20 MB
- **Максимальный размер архива**: 20 MB
- **Максимальный размер распакованного содержимого**: 100 MB
- **Таймаут обработки**: 300 секунд (5 минут) для всех операций
- **Таймаут обработки архивов**: 300 секунд (5 минут) с принудительным завершением
- **Максимальная глубина вложенности архивов**: 3 уровня

### Оптимизация

- **Асинхронная обработка**: Все CPU-bound операции выполняются в отдельном пуле потоков
- **Неблокирующая архитектура**: Event loop не блокируется при обработке тяжелых файлов
- **Множественные worker-процессы**: Настраиваемое количество процессов для продакшена
- **Изоляция операций**: Сбой в одной операции не влияет на другие

**Рекомендации:**
- Используйте правильные форматы файлов
- Сжимайте изображения перед отправкой
- Для продакшена установите `WORKERS=9` (или 2 * количество ядер CPU + 1)
- Убедитесь в наличии заголовка Content-Length в запросах

### Статистика обработки

| Тип файла | Среднее время обработки | Особенности |
|-----------|------------------------|-------------|
| Текстовые файлы | <1мс | Автоопределение кодировки |
| Исходный код | <1мс | 50+ языков программирования |
| Изображения (OCR) | 100-500мс | Русский и английский |
| PDF документы | 50-200мс | С OCR для изображений |
| Office документы | 100-1000мс | Полное извлечение |
| DOCX документы | 100-800мс | Включая колонтитулы, сноски, комментарии |
| PPTX презентации | 100-600мс | Включая заметки спикера |
| Таблицы (большие) | 100-300мс | Все популярные форматы |
| Архивы | 200-2000мс | Таймаут 300 секунд |

## Архивы

### Поддерживаемые форматы архивов

- **ZIP**: Стандартный формат, быстрая обработка
- **RAR**: Требует библиотеку rarfile
- **7Z**: Требует библиотеку py7zr
- **TAR**: Включая сжатые варианты (GZ, BZ2, XZ)

### Обработка архивов

1. **Распаковка**: Архив распаковывается во временную папку
2. **Фильтрация**: Игнорируются системные файлы (.DS_Store, Thumbs.db)
3. **Обработка**: Каждый файл обрабатывается согласно его типу
4. **Объединение**: Результаты объединяются в единый ответ
5. **Очистка**: Временные файлы автоматически удаляются
6. **Таймаут**: Обработка архивов ограничена 300 секундами для предотвращения блокировки системы

### Безопасность архивов

- **Защита от zip-бомб**: Ограничение размера распакованного содержимого
- **Защита от path traversal**: Санитизация имен файлов в архивах
- **Контроль вложенности**: Максимум 3 уровня вложенности архивов
- **Изоляция процесса**: Распаковка в отдельном процессе с таймаутом
- **Таймаут обработки**: Принудительное завершение обработки архивов через 300 секунд

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
        - name: WORKERS
          value: "9"
        - name: OCR_LANGUAGES
          value: "rus+eng"
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
```

## Устранение проблем

### Частые проблемы

1. **OCR не работает**
   - Проверьте установку tesseract в Docker образе
   - Убедитесь в наличии языковых пакетов (rus+eng)

2. **Ошибки памяти**
   - Уменьшите размер файлов или архивов
   - Увеличьте лимиты контейнера
   - Уменьшите `MAX_EXTRACTED_SIZE`

3. **Таймауты**
   - Увеличьте `PROCESSING_TIMEOUT_SECONDS`
   - Уменьшите сложность входных файлов
   - Проверьте размер архивов
   - Обработка архивов автоматически завершается через 300 секунд

4. **Архивы не обрабатываются**
   - Убедитесь в наличии библиотек rarfile и py7zr
   - Проверьте размер архива и содержимого
   - Проверьте глубину вложенности
   - Обработка прекращается через 300 секунд (см. таймаут)

5. **Неполное извлечение текста**
   - DOCX: Теперь включает колонтитулы, сноски и комментарии
   - PPTX: Теперь включает заметки спикера
   - Проверьте версию API (должна быть 1.8.6+)

### Логи отладки

```bash
# Включение отладки
export DEBUG=true

# Просмотр подробных логов
make logs

# Проверка статуса
make status
```

### Диагностика

```bash
# Быстрая проверка API
curl http://localhost:7555/health

# Проверка поддерживаемых форматов
curl http://localhost:7555/v1/supported-formats

# Тестирование с простым файлом
curl -X POST -F "file=@tests/test.txt" http://localhost:7555/v1/extract/file
```

## Контрибуция

1. Форк репозитория
2. Создание ветки для фичи
3. Коммит изменений
4. Запуск тестов (`make test`)
5. Пуш в ветку
6. Создание Pull Request

## Лицензия

Этот проект лицензирован под MIT License - см. файл [LICENSE](LICENSE).

## Поддержка

Для вопросов и поддержки:
- GitHub Issues
- Техническая документация: `docs/TZ.md`

---

**Версия**: 1.10.5
**Разработчик**: Барилко Виталий
