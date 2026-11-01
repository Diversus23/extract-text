# Руководство для разработчиков

Добро пожаловать в проект Text Extraction API! Это руководство поможет вам настроить среду разработки и следовать принятым в проекте практикам.

## Быстрый старт для разработчиков

### 1. Клонирование и настройка

```bash
# Клонирование репозитория
git clone <repository-url>
cd extract-text

# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или venv\Scripts\activate  # Windows

# Установка всех зависимостей
pip3 install -r requirements.txt
pip3 install -r requirements-test.txt
pip3 install -r requirements-lint.txt

# Копирование переменных окружения
cp env_example .env
# Отредактируйте .env под ваши нужды
```

### 2. Установка системных зависимостей

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng
sudo apt-get install libreoffice-core antiword libmagic1
```

**macOS:**
```bash
brew install tesseract tesseract-lang
brew install libreoffice antiword libmagic
```

**Windows:**
Используйте Docker для разработки (рекомендуется). Нужен **Docker Compose v2.24.4+** (`docker compose version`; `docker-compose` v1 не подходит):
```bash
make dev  # Запуск в Docker
```

### 3. Проверка установки

```bash
# Быстрая проверка API
make quick-test

# Запуск тестов
make test

# Проверка линтерами
make lint
```

## Рабочий процесс разработки

### Перед началом работы

1. **Создайте ветку для фичи:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Установите pre-commit хуки (опционально):**
   ```bash
   pip3 install pre-commit
   pre-commit install
   ```

### Во время разработки

1. **Проверяйте код перед коммитом:**
   ```bash
   make format      # Автоформатирование
   make lint-check  # Строгая проверка
   make test        # Запуск тестов
   ```

2. **Пишите тесты для нового кода:**
   - Unit тесты в `tests/test_*.py`
   - Integration тесты для API эндпоинтов
   - Используйте маркеры: `@pytest.mark.unit`, `@pytest.mark.integration`

3. **Следуйте соглашениям:**
   - Используйте docstrings для функций и классов
   - Комментируйте сложную логику
   - Поддерживайте покрытие тестами >60%

### Перед отправкой PR

```bash
# Финальная проверка
make format      # Исправить форматирование
make lint        # Проверить все аспекты
make test        # Запустить тесты
make test-docker # Проверить в Docker

# Убедиться что все файлы добавлены
git add .
git commit -m "feat: описание изменений"
git push origin feature/your-feature-name
```

## Стандарты кода

### Python код

- **Стиль:** PEP 8 с автоформатированием через Black
- **Длина строки:** 88 символов (стандарт Black)
- **Импорты:** Сортировка через isort
- **Типизация:** Приветствуется, но не обязательна

### Документация

- **Docstrings:** Google стиль для функций и классов
- **Комментарии:** На русском языке, объясняют "почему", а не "что"
- **README:** Обновляется при изменении функциональности

### Git коммиты

Используйте Conventional Commits:
- `feat:` - новая функциональность
- `fix:` - исправление ошибок
- `docs:` - изменения в документации
- `style:` - форматирование, без изменений логики
- `refactor:` - рефакторинг без новых функций
- `test:` - добавление тестов
- `chore:` - обновление зависимостей, конфигурации

Примеры:
```
feat: добавить поддержку WebP изображений в OCR
fix: исправить обработку поврежденных PDF файлов
docs: обновить README с информацией о новых форматах
```

## Линтеры и автоматические проверки

### Настроенные инструменты

| Инструмент | Назначение | Команда |
|------------|------------|---------|
| Black | Автоформатирование | `black app/ tests/` |
| isort | Сортировка импортов | `isort app/ tests/` |
| Flake8 | Проверка PEP 8 | `flake8 app/ tests/` |
| MyPy | Проверка типов | `mypy app/` |
| Bandit | Безопасность | `bandit -r app/` |
| Safety | Уязвимости в зависимостях | `safety check` |

### Конфигурация

Настройки находятся в:
- `pyproject.toml` - Black, isort, MyPy, pytest
- `.flake8` - настройки Flake8
- `requirements-lint.txt` - версии инструментов

### Команды Makefile

```bash
# Установка линтеров
make install-linters

# Автоисправление
make format

# Полная проверка (с предупреждениями)
make lint

# Строгая проверка (для CI)
make lint-check
```

## Тестирование

### Структура тестов

```
tests/
├── conftest.py          # Общие фикстуры
├── test_main.py         # API тесты
├── test_extractors.py   # Тесты логики извлечения
├── test_utils.py        # Тесты утилит
├── test_config.py       # Тесты конфигурации
├── test_integration.py  # Integration тесты
└── [test files]         # Реальные файлы для тестов
```

### Виды тестов

1. **Unit тесты** (`@pytest.mark.unit`):
   - Тестируют отдельные функции
   - Используют моки для внешних зависимостей
   - Быстрые (<1с на тест)

2. **Integration тесты** (`@pytest.mark.integration`):
   - Тестируют API эндпоинты
   - Работают с реальными файлами
   - Проверяют взаимодействие компонентов

3. **Legacy тесты** (`run_tests.sh`):
   - Функциональное тестирование всех форматов
   - Работает с запущенным API
   - Создает `.ok.txt` и `.err.txt` файлы

### Команды тестирования

```bash
make test               # Все тесты с покрытием
make test-unit          # Только unit тесты
make test-integration   # Только integration тесты
make test-docker        # Тесты в Docker
make test-coverage      # Просмотр отчета покрытия
make test-legacy        # Legacy функциональные тесты
```

### Написание тестов

```python
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.integration
async def test_extract_pdf():
    """Тест извлечения текста из PDF файла."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        with open("tests/test.pdf", "rb") as f:
            response = await client.post(
                "/v1/extract/file",
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["files"]) > 0
        assert data["files"][0]["text"].strip() != ""

@pytest.mark.unit
def test_sanitize_filename():
    """Тест санитизации имен файлов."""
    from app.utils import sanitize_filename
    
    assert sanitize_filename("../../../etc/passwd") == "etc_passwd"
    assert sanitize_filename("normal_file.pdf") == "normal_file.pdf"
```

## CI/CD Pipeline

### GitHub Actions

Проект использует автоматизированный pipeline с 5 этапами:

1. **Линтинг** - проверка качества кода
2. **Docker тесты** - тестирование в изолированной среде  
3. **Matrix тесты** - тестирование на Python 3.10, 3.11, 3.12
4. **Безопасность** - проверка уязвимостей
5. **Сборка** - проверка Docker образа

### Отчеты и артефакты

- **Покрытие кода:** автоматически загружается в Codecov
- **Отчеты безопасности:** сохраняются как артефакты
- **Бейджи:** отображаются в README

### Локальная имитация CI

```bash
# Имитация этапа линтинга
make lint-check

# Имитация тестирования
make test-docker

# Полная проверка перед PR
make format && make lint && make test && make test-docker
```

## Отладка и разработка

### Запуск в режиме разработки

```bash
# С автоперезагрузкой (Docker)
make dev

# Локально с автоперезагрузкой
uvicorn app.main:app --reload --host 0.0.0.0 --port 7555

# Подключение к контейнеру для отладки
make debug
```

### Полезные эндпоинты

- **API**: http://localhost:7555/
- **Документация**: http://localhost:7555/docs
- **Health check**: http://localhost:7555/health
- **Поддерживаемые форматы**: http://localhost:7555/v1/supported-formats

### Логирование

```python
import structlog
logger = structlog.get_logger()

# В коде
logger.info("Начало обработки файла", filename=filename, size=file_size)
logger.warning("Файл слишком большой", filename=filename, size=file_size, limit=MAX_SIZE)
logger.error("Ошибка обработки", filename=filename, error=str(e))
```

### Профилирование

```bash
# Анализ производительности
python -m cProfile -o profile.stats quick_test.py
python -c "import pstats; pstats.Stats('profile.stats').sort_stats('cumulative').print_stats(20)"
```

## Часто встречающиеся проблемы

### 1. Проблемы с зависимостями

```bash
# Переустановка всех зависимостей
pip3 install --force-reinstall -r requirements.txt
pip3 install --force-reinstall -r requirements-test.txt
pip3 install --force-reinstall -r requirements-lint.txt
```

### 2. Ошибки линтеров

```bash
# Автоисправление большинства проблем
make format

# Игнорирование конкретной ошибки
# В коде: # noqa: E501 (конкретная ошибка)
# В файле: # flake8: noqa (весь файл)
```

### 3. Проблемы с тестами

```bash
# Запуск конкретного теста
pytest tests/test_main.py::test_health_check -v

# Запуск с отладкой
pytest tests/test_main.py::test_health_check -v -s --pdb

# Очистка кэша pytest
pytest --cache-clear
```

### 4. Docker проблемы

```bash
# Полная пересборка
make clean && make build

# Логи контейнера
make logs

# Подключение к контейнеру
docker exec -it extract-text-api-1 /bin/bash
```

Проблемы с Docker Compose (нужен v2.24.4 или новее, установка описана в README):

- `unknown shorthand flag: 'f' in -f` при `make down` или `make prod-up` — не установлен плагин Compose v2. На Ubuntu 24.04 с `docker.io`: `sudo apt install docker-compose-v2`, затем `docker compose version`.
- `KeyError: 'id'` в `watch_events` — запущен устаревший `docker-compose` v1. Используйте `docker compose` (через `make` это делается автоматически).
- `container name ... is already in use` после перехода с v1 — выполните один раз `docker rm -f extract-text-prod extract-text-audio-prod` и повторите `make prod-up`.

## Внесение вклада

1. **Fork репозиторий** на GitHub
2. **Создайте ветку** для вашей фичи
3. **Напишите код** следуя стандартам проекта
4. **Добавьте тесты** для нового функционала
5. **Проверьте** все линтеры и тесты
6. **Отправьте Pull Request** с описанием изменений

### Чек-лист для PR

- [ ] Код отформатирован (`make format`)
- [ ] Все линтеры проходят (`make lint-check`)
- [ ] Тесты проходят (`make test`)
- [ ] Покрытие не упало (>60%)
- [ ] Добавлены тесты для нового функционала
- [ ] Обновлена документация (если нужно)
- [ ] Commit messages следуют Conventional Commits

## Контакты

Если у вас есть вопросы:
- Создайте Issue в GitHub
- Посмотрите документацию в `docs/TZ.md`
- Проверьте существующие Issues и PR

---

**Спасибо за ваш вклад в проект!** 🚀 