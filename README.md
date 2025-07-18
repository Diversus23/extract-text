# Text Extraction API for RAG

API для извлечения текста из файлов различных форматов, предназначенный для создания векторных представлений (embeddings) в системах RAG (Retrieval-Augmented Generation).

## Особенности

- 🔧 **Широкая поддержка форматов**: PDF, DOCX, PPT, изображения, таблицы, исходный код и многое другое
- 💻 **Поддержка исходного кода**: Более 50 языков программирования и форматов конфигурации
- 🖼️ **OCR**: Распознавание текста на изображениях (русский и английский языки)
- 📦 **Обработка архивов**: Извлечение текста из файлов внутри архивов с таймаутом 300 секунд (ZIP, RAR, 7Z, TAR и др.)
- 🚀 **Асинхронная обработка**: Неблокирующее выполнение с поддержкой множественных worker-процессов
- 📊 **Структурированный вывод**: Объединение текста из разных источников
- 🔒 **Безопасность**: Защита от path traversal, подделки типов файлов и DoS-атак
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

#### `POST /v1/extract-base64/` - Извлечение текста из base64-файла
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "encoded_base64_file": "0J/RgNC40LLQtdGCINGN0YLQviDRgtC10LrRgdGCIQ==",
    "filename": "document.txt"
  }' \
  http://localhost:7555/v1/extract-base64/
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

### Выбор эндпоинта

**Используйте `/v1/extract/`** когда:
- Загружаете файлы напрямую через форму или drag&drop
- Работаете с локальными файлами
- Интегрируетесь с файловыми системами

**Используйте `/v1/extract-base64/`** когда:
- Файл уже закодирован в base64 в вашей системе
- Интегрируетесь с API, которые передают файлы в base64
- Работаете с микросервисной архитектурой через JSON
- Файл хранится в базе данных в виде base64

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

# Количество worker-процессов uvicorn (по умолчанию: 1)
# Для продакшена рекомендуется: 2 * (количество ядер CPU) + 1
WORKERS=1

# Максимальный размер файла в байтах (по умолчанию: 20MB)
MAX_FILE_SIZE=20971520

# Максимальный размер архива в байтах (по умолчанию: 20MB)
MAX_ARCHIVE_SIZE=20971520

# Максимальный размер распакованного содержимого (по умолчанию: 100MB)
MAX_EXTRACTED_SIZE=104857600

# Максимальная глубина вложенности архивов (по умолчанию: 3)
MAX_ARCHIVE_NESTING=3
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
- **Покрытие**: pytest-cov с минимальным порогом 30%
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
- **Покрытие кода**: 37%+ (выше минимального порога 30%)
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
curl http://localhost:7555/v1/supported-formats/

# Тестирование с простым файлом
curl -X POST -F "file=@tests/test.txt" http://localhost:7555/v1/extract/
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

**Версия**: 1.8.9
**Разработчик**: ООО "СОФТОНИТ"
