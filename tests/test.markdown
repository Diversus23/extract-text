# Тестовый Markdown файл

## Заголовок второго уровня

Это **тестовый** файл для проверки работы парсера Markdown в API извлечения текста.

### Список элементов

- Первый элемент списка
- Второй элемент списка
- Третий элемент с *курсивом*

### Нумерованный список

1. Первый пункт
2. Второй пункт
3. Третий пункт

### Таблица

| Формат | Поддержка | Описание |
|--------|----------|----------|
| .md | ✅ | Markdown файлы |
| .pdf | ✅ | PDF документы |
| .txt | ✅ | Текстовые файлы |

### Код

```python
def extract_text_from_markdown(file_path):
    """Извлечение текста из Markdown файла"""
    return "Извлеченный текст"
```

### Ссылка

Подробная документация доступна на [GitHub](https://github.com/example/repo).

### Цитата

> Markdown — это облегчённый язык разметки, созданный с целью обозначения форматирования в простом тексте.

### Заключение

Этот файл содержит различные элементы Markdown для тестирования API извлечения текста.

# Быстрый старт

## Вариант 1: Docker (Рекомендуется)

```bash
# Сборка образа
docker build -t file-processing-api .

# Запуск контейнера
docker run -d -p 8000:8000 --name file-api file-processing-api

# Проверка работы
curl http://localhost:8000/health
```

## Вариант 2: Docker Compose

```bash
# Запуск
docker-compose up -d --build

# Остановка
docker-compose down
```

## Вариант 3: Локальный запуск

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск приложения
python main.py
```

## Скрипт управления

```bash
# Просмотр доступных команд
python manage.py help

# Примеры использования
python manage.py build     # Сборка Docker образа
python manage.py docker    # Запуск Docker контейнера
python manage.py test      # Тестирование API
python manage.py logs      # Просмотр логов
```

## Тестирование API

```bash
# Автоматические тесты
python test_api.py

# Ручное тестирование
curl -X POST "http://localhost:8000/v1/extract/" \
  -F "file=@example.pdf"
```

## Документация API

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc 