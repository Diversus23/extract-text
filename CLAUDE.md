# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Назначение проекта

Text Extraction API — FastAPI-сервис на Python 3.12+, извлекающий текст из 130+ форматов файлов (PDF, Office, изображения с OCR, архивы, исходный код, веб-страницы) для последующей загрузки в векторные БД систем RAG. Развёртывание — Docker, порт 7555. Языки общения с пользователем: русский (включая комментарии в коде, сообщения коммитов и логи).

## Команды разработки

Все основные операции через `make` (см. `Makefile`):

```bash
# Разработка / запуск
make up               # dev-режим (docker-compose, hot reload, foreground)
make prod-up          # prod-режим (git pull → stop → up -d с docker-compose.prod.yml)
make stop / make down # остановить контейнеры
make logs             # docker-compose logs -f
make debug            # exec /bin/bash в dev-контейнер

# Тестирование (минимальный порог покрытия --cov-fail-under=60)
make test             # pytest локально, fallback на test-docker
make test-unit        # pytest -m unit
make test-integration # pytest -m integration
make test-docker      # pytest внутри контейнера (изолированное окружение)
make test-legacy      # ./run_tests.sh — функциональные тесты, требуют запущенный API

# Один тест
python -m pytest tests/test_main.py::TestClassName::test_method_name -v

# Линтеры (Black, isort, Flake8, MyPy, Bandit, Safety)
make format           # автоисправление: isort + black
make lint-check       # CI-режим: только проверка, без исправлений
make lint             # все линтеры с предупреждениями (включая bandit/safety)
```

CI (`.github/workflows/ci.yml`) запускает `lint` → `test-docker` → matrix на Python 3.12/3.13 → security (pip-audit) → docker build. Линтер блокирующий, MyPy — `continue-on-error`. Минимум — Python 3.12 (поднято с 3.10 в v1.11.0).

Локальный запуск без Docker: `uvicorn app.main:app --reload --host 0.0.0.0 --port 7555`. Требует системных зависимостей: `tesseract-ocr` (+ `tesseract-ocr-rus`, `tesseract-ocr-eng`), `libreoffice`, `antiword`, `libmagic1`, и `playwright install chromium`.

## Архитектура

### Слои приложения

```
app/
├── main.py        # FastAPI: 4 эндпоинта, lifespan, middleware, Pydantic-модели
├── extractors.py  # TextExtractor: единая точка извлечения по расширению (~3300 строк)
├── config.py      # Settings (env-vars), SUPPORTED_FORMATS, MIME_TO_EXTENSION, VERSION
└── utils.py       # sanitize_filename, validate_file_type, cleanup_temp_files, setup_logging
```

### Ключевой инвариант: всё CPU-bound выполняется в threadpool с таймаутом

Эндпоинты `/v1/extract/{file,base64,url}` оборачивают вызов `text_extractor.extract_text(...)` в `asyncio.wait_for(run_in_threadpool(...), timeout=settings.PROCESSING_TIMEOUT_SECONDS)` (300 сек по умолчанию). Это критично — event loop не должен блокироваться. Любой новый extractor должен оставаться синхронным и не делать `asyncio.run` внутри. У `TextExtractor` есть собственный `_thread_pool` (max_workers=4), корректно закрываемый в `lifespan` shutdown.

### Маршрутизация по форматам в `extractors.py`

`TextExtractor.extract_text()` → `is_archive_format` → распаковка с защитой от zip-бомб (3 уровня вложенности, 100 MB лимит) → рекурсивная обработка содержимого. Иначе `_extract_text_by_format()` ищет метод в:
1. `_get_extraction_methods_mapping()` — точное соответствие расширения (pdf, docx, doc, csv, pptx, ppt, txt, json, rtf, odt, xml, epub, eml, msg).
2. `_get_group_extraction_methods()` — группы (xls/xlsx, изображения, html/htm, md/markdown, yaml/yml).
3. `source_code` группа из `SUPPORTED_FORMATS` → единый обработчик `_extract_from_source_code_sync` с заголовком `[Язык: ..., Файл: ..., Строк: ...]`.

При добавлении нового формата: 1) добавить расширение в `SUPPORTED_FORMATS` (`config.py`), 2) реализовать `_extract_from_<format>_sync(self, content: bytes) -> str`, 3) зарегистрировать в `_get_extraction_methods_mapping` или `_get_group_extraction_methods`.

### Конвертация старых офисных форматов

`.doc` → `.docx` и `.ppt` → `.pptx` через `subprocess` LibreOffice headless. Эти пути требуют установленной системной зависимости и используют ограничения памяти (`MAX_LIBREOFFICE_MEMORY=1.5GB`) через `resource.setrlimit` в Linux (см. `utils.py`).

### Веб-экстракция (`/v1/extract/url`)

Двухрежимная: `requests` + BeautifulSoup для статики; Playwright (Chromium) для JS-рендеринга, lazy loading (защита от бесконечного скролла через `MAX_SCROLL_ATTEMPTS`), base64-изображений. Параметры передаются через Pydantic-модель `ExtractionOptions` (см. `app/main.py:54`) и переопределяют дефолты из `config.py`. Отдельная защита от SSRF: `BLOCKED_IP_RANGES` и `BLOCKED_HOSTNAMES`. Если URL ведёт на файл (определяется HEAD-запросом, `HEAD_REQUEST_TIMEOUT`), он скачивается и обрабатывается как обычный файл.

### Безопасность (обязательно учитывать при правках)

- `validate_file_type` (`utils.py`) сверяет расширение с реальным MIME через `python-magic` — несоответствие даёт 415 без обработки.
- `sanitize_filename` (через werkzeug `secure_filename` + кастомная логика) защищает от path traversal — всегда применяется до записи на диск.
- `MAX_FILE_SIZE` (20 MB) проверяется до чтения тела для `/file`; для `/base64` — после декодирования.
- Для `/file` обязателен заголовок `Content-Length` (защита от DoS) — иначе 400.
- Архивы изолируются ограничением `MAX_EXTRACTED_SIZE`, `MAX_ARCHIVE_NESTING`, обработка ограничена 300 секундами с принудительным завершением.

### HTTP-коды ответов

`200` — успех (JSON со `status: success`, массивом `files[]` с `filename/path/size/type/text`); `400` — отсутствует Content-Length / некорректный URL / некорректный base64; `413` — превышен `MAX_FILE_SIZE`; `415` — формат не поддерживается / mismatch расширения и MIME; `422` — повреждённый/пустой/защищённый файл; `504` — таймаут обработки. Ошибки возвращаются как `JSONResponse` с полем `status: "error"` (НЕ через `raise HTTPException` — клиент полагается на структуру `{status, filename|url, message}`).

## Версионирование и обязательные обновления

- Источник истины версии — `app/config.py:Settings.VERSION`. **При любом изменении функциональности** обновлять её и добавлять запись в `CHANGELOG.md` с заголовком `## [X.Y.Z] - YYYY-MM-DD` (текущая дата через `date +%Y-%m-%d`).
- `docs/TZ.md` — техническое задание; держать в актуальном состоянии при изменении контрактов API или поддерживаемых форматов (правило из `.cursor/rules/python.mdc`).
- `README.md` обновлять при изменении публичного API или списка форматов.
- Коммиты — Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `style:`).

## Стиль и тесты

- Black 88 символов, isort профиль `black`, `known_first_party = ["app"]`, Flake8 `max-complexity=20`. Перед PR — `make format && make lint-check && make test`.
- Маркеры pytest: `@pytest.mark.unit` (быстрые, с моками — `mock_tesseract`, `mock_libreoffice` из `conftest.py`) и `@pytest.mark.integration` (через `TestClient`/`AsyncClient` с реальными файлами из `tests/test.*`). `asyncio_mode = "auto"`.
- `tests/conftest.py` содержит фикстуры `test_client`, `async_client`, `text_extractor`, `temp_dir`, генераторы простых файлов (`sample_text_file`, `sample_python_file`, …) и `settings_override` для подмены настроек.
- В `tests/` лежат 126+ реальных файлов (`test.pdf`, `test.docx`, `test.bsl` и т.д.) — `TestAllRealFiles` в `test_integration.py` автоматически прогоняет их через API. **Не удалять** случайно при чистке (см. `make clean` — он специально исключает их шаблоном).
- Артефакты `tests/*.ok.txt`, `tests/*.err.txt`, `tests/supported_formats.json` создаются `run_tests.sh` и должны игнорироваться (см. `.flake8` exclude).

## Конфигурация через env

Все настройки читаются через `os.getenv` в `app/config.py`. Шаблон — `env_example` → `.env`. Ключевые переменные: `API_PORT` (7555), `WORKERS` (prod: `2*CPU_CORES+1`), `OCR_LANGUAGES` (`rus+eng`), `PROCESSING_TIMEOUT_SECONDS` (300), `MAX_FILE_SIZE` (20MB), `ENABLE_JAVASCRIPT` (false по умолчанию для безопасности), `BLOCKED_IP_RANGES`, `BLOCKED_HOSTNAMES`. Ограничения памяти подпроцессов: `MAX_SUBPROCESS_MEMORY` (1GB), `MAX_LIBREOFFICE_MEMORY` (1.5GB), `MAX_TESSERACT_MEMORY` (512MB) — применяются только если `ENABLE_RESOURCE_LIMITS=true`.
