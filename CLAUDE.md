# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Назначение проекта

Text Extraction API — FastAPI-сервис на Python 3.12+, извлекающий текст из 130+ форматов файлов (PDF, Office, изображения с OCR, архивы, исходный код, веб-страницы) для последующей загрузки в векторные БД систем RAG. Развёртывание — Docker, порт 7555. Языки общения с пользователем: русский (включая комментарии в коде, сообщения коммитов и логи).

## Команды разработки

Все основные операции через `make` (см. `Makefile`):

```bash
# Разработка / запуск
make up               # dev-режим (docker compose v2, hot reload, foreground)
make prod-up          # prod-режим (git pull → stop → up -d с docker-compose.prod.yml)
make stop / make down # остановить контейнеры
make logs             # docker compose logs -f
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

Compose — v2 (`docker compose`, переменная `COMPOSE` в `Makefile`). Имя проекта не задаём: v1 и v2 берут его из имени директории (`extract-text`), поэтому v2 видит контейнеры, созданные прежним v1; при другом имени фиксированные `container_name` дают конфликт имён. Prod-сервер — Ubuntu 24.04 с `docker.io` 29: Compose ставится как `apt install docker-compose-v2` (2.24.6); v1 там падает с `KeyError: 'id'` в `watch_events`. Установка и миграция — в README, раздел «Docker Compose команды».

CI (`.github/workflows/ci.yml`) запускает `lint` → `test-docker` → matrix на Python 3.12/3.13 → security (pip-audit) → docker build. Линтер блокирующий, MyPy — `continue-on-error`. Минимум — Python 3.12 (поднято с 3.10 в v1.11.0).

Локальный запуск без Docker: `uvicorn app.main:app --reload --host 0.0.0.0 --port 7555`. Требует системных зависимостей: `tesseract-ocr` (+ `tesseract-ocr-rus`, `tesseract-ocr-eng`), `libreoffice`, `antiword`, `libmagic1`, и `playwright install chromium`.

## Архитектура

### Слои приложения

```
app/
├── main.py        # FastAPI: эндпоинты /v1/extract/*, /v1/transcribe, /v1/audio/transcriptions, /v1/chat/completions; lifespan, middleware, Pydantic-модели
├── chat_completions.py  # POST /v1/chat/completions: разбор запроса, content-блоки, ответ (без импорта app.main)
├── chat_ingress.py      # ASGI-предохранитель chat/completions: доступ и Content-Length до чтения тела
├── extractors.py  # TextExtractor: единая точка извлечения по расширению (~3300 строк)
├── config.py      # Settings (env-vars), SUPPORTED_FORMATS, MIME_TO_EXTENSION, VERSION
├── transcription.py  # /v1/transcribe: ffprobe/ffmpeg → GigaAM v3 (onnx-asr) + silero VAD, сегменты, говорящие по каналам
└── utils.py       # sanitize_filename, validate_file_type, cleanup_temp_files, setup_logging
```

### Ключевой инвариант: всё CPU-bound выполняется в threadpool с таймаутом

Эндпоинты `/v1/extract/{file,base64,url}` (а `file` и `/v1/chat/completions` через общую `_extract_document`) оборачивают вызов `text_extractor.extract_text(...)` в `asyncio.wait_for(run_in_threadpool(...), timeout=settings.PROCESSING_TIMEOUT_SECONDS)` (300 сек по умолчанию). Это критично — event loop не должен блокироваться. Любой новый extractor должен оставаться синхронным и не делать `asyncio.run` внутри. У `TextExtractor` есть собственный `_thread_pool` (max_workers=4), корректно закрываемый в `lifespan` shutdown.

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

### Расшифровка аудио (`/v1/transcribe`, v1.12.3)

Лимит `MAX_AUDIO_FILE_SIZE` применяется и в middleware, и в эндпоинте независимо от `MAX_FILE_SIZE` для документов.

Аудио определяется по содержимому, имя и Content-Type клиента не определяют обработчик. ffprobe использует `format_whitelist` и `protocol_whitelist=file`; ffmpeg получает определённый демуксер явно. `filename` сохраняется, `detected_format` возвращает канонический формат. Проверка MIME используется только для уточнения ошибки неудачного зондирования.

Контур: `app/transcription_ingress.py` проверяет доступ, Content-Length и размер до разбора multipart, затем асинхронно занимает слот через `Transcriber.reserve`; очередь ограничена `TRANSCRIPTION_MAX_QUEUE_SIZE`. Слот передаётся заданию в отдельном пуле аудио и удерживается до фактического завершения потока, включая отмену HTTP-запроса. В `app/transcription.py` файл пишется как `input`; ffprobe/ffmpeg работают без shell, с `-protocol_whitelist file`. Отмена проверяется между этапами и пакетами VAD, таймауты подпроцессов ограничены общим дедлайном. Обе модели грузятся офлайн из `MODELS_DIR` и прогреваются при старте: основная GigaAM RNN-T с VAD и резервная CTC int8 для пустых речевых сегментов. Нераспознанные сегменты сохраняют тайм-коды; `text_status` — `ok`, `partial`, `unrecognized` или `no_speech`. Готовность — `GET /health?check=transcription`. Стерео распознаётся по каналам, для моно `speaker=null`. В prod сервис `api-audio` использует один воркер и порт 7556; у сервиса документов `ENABLE_TRANSCRIPTION=false`, и он пересылает `/v1/transcribe` в `api-audio` (`app/transcription_proxy.py`, `TRANSCRIPTION_UPSTREAM_URL`), так что клиенту достаточно порта 7555. Пересылка потоковая; ответ клиенту нужен всегда, даже при его обрыве (`499`), иначе `BaseHTTPMiddleware` в `main.py` падает с «No response returned». Полный контракт — в `README.md` и `docs/TZ.md`. Интеграция со стороны 1С — отдельная задача.

### Безопасность (обязательно учитывать при правках)

- `validate_file_type` (`utils.py`) сверяет расширение с реальным MIME через `python-magic` — несоответствие даёт 415 без обработки.
- Для `.zip` с MIME `application/octet-stream` валидатор дополнительно открывает центральный каталог через `zipfile.ZipFile`, не распаковывая данные. Конкретный несовпадающий MIME не переопределяется; поврежденный ZIP отклоняется. Ограничения распаковки остаются в extractor.
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

### OpenAI-совместимая транскрибация (1.14.0) и каталог моделей (1.15.0)

`app/openai_compat.py` содержит формат ошибок, каталог моделей и представления ответа (`json`, `verbose_json`, `text`). С 1.15.0 каталог публикует `softonit/extracttext` (всегда; вход `file`) и `softonit/<TRANSCRIPTION_MODEL>` (по доступности транскрибации): префикс `PUBLIC_MODEL_PREFIX` добавляется в коде, `TRANSCRIPTION_MODEL` остаётся именем каталога весов, новых env нет. Идентификатор модели извлечения обязан содержать `extract` (1С по подстроке ставит флаг `text_extraction`; закреплено тестом). Транскрибация принимает публичный и прежний id (`is_transcription_model`), `POST /v1/extract/file` принимает необязательное поле `model` (`validate_extraction_model`, чужая → 404 в формате `{status, filename, message}` до чтения файла). `api` и `api-audio` обновляются одним релизом: `model` пересылается в `api-audio` verbatim. Новые `/v1/models` и `/v1/audio/transcriptions` зарегистрированы отдельным роутером; старый `/v1/transcribe` использует тот же `_run_transcription` и сохраняет прежний ответ. На всех `/v1` доступны Bearer и X-API-Key (приоритет у непустого X-API-Key), проверка общая в `app/auth.py`. Ingress и прокси обслуживают оба пути, выбирая формат ошибок по пути; все ограничения до multipart и удержание слота после отмены остаются обязательными. Полный контракт и пример OpenAI SDK — в README.md, нормативное дополнение — в docs/TZ.md.

### Извлечение через POST /v1/chat/completions (1.16.0)

`openai_router` обслуживает `POST /v1/chat/completions` (модель `softonit/extracttext`; одна file-часть сообщения, `file_data` = `data:<mime>;base64,...`). Ответ — не потоковый `chat.completion`, а `content` собран как `"\n".join("--- FILE: {filename.strip()} ---\n{text}")` по `files[]` результата извлечения (блок есть и у единственного файла; элемент без `text` пропускается). Общая логика извлечения вынесена в `_extract_document(content, original_filename)` в `app/main.py` (должна оставаться там: тесты прежних маршрутов патчат `app.main.validate_file_type` и `TextExtractor.extract_text`); ошибки передаются как `ExtractionError(status, message, legacy_detail, internal)`: `/v1/extract/file` показывает их побайтно как раньше (в том числе 422 для непредвиденного исключения), новый маршрут - в конверте OpenAI (непредвиденное исключение - 500 `internal_error`). Чистые функции разбора и сборки - в `app/chat_completions.py` (без импорта `app.main`). Лимит тела `chat_body_limit() = ceil(MAX_FILE_SIZE/3)*4 + 256 КиБ` проверяется дважды: `ChatBodyGuardMiddleware` (`app/chat_ingress.py`) - доступ и `Content-Length` до чтения тела, `read_limited_body` - потоковый подсчёт при чтении (ложный Content-Length не обходит лимит). Все ошибки маршрута - в конверте OpenAI (`/v1/chat/completions` входит в `OPENAI_PATHS`; для 405 добавлен код `method_not_allowed`). `file_data` и base64 в логи не писать. Новых env нет; маршрут обслуживает контейнер `api`. Контракт - в README.md, нормативное дополнение - в docs/TZ.md («Дополнение 1.16.0»).
