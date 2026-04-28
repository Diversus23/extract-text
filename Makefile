SHELL := /bin/bash
# Makefile для управления жизненным циклом Text Extraction API
IMAGE_NAME := text-extraction-api
TAG := latest


.PHONY: help build up prod-up down stop logs test test-unit test-integration test-coverage test-legacy clean status lint format lint-check install-linters

help: ## 📋 Показать список доступных команд
	@echo "================================================"
	@echo "  Text Extraction API - Управление"
	@echo "================================================"
	@echo ""
	@echo "🏗️  Сборка и развертывание:"
	@echo "  make build   - Собрать Docker образ"
	@echo "  make up      - Запустить в режиме разработки (с автоперезагрузкой)"
	@echo "  make prod-up - Запустить в продакшене (в фоновом режиме)"
	@echo ""
	@echo "🔧 Управление сервисом:"
	@echo "  make down    - Остановить все контейнеры"
	@echo "  make stop    - Остановить все контейнеры (алиас для down)"
	@echo "  make logs    - Показать логи приложения в реальном времени"
	@echo "  make status  - Показать статус контейнеров"
	@echo ""
	@echo "🧪 Тестирование:"
	@echo "  make test         - Запустить полное тестирование с покрытием"
	@echo "  make test-unit    - Запустить только unit тесты"
	@echo "  make test-integration - Запустить только integration тесты"
	@echo "  make test-docker  - Запустить тестирование в Docker контейнере"
	@echo "  make test-coverage - Показать отчет покрытия в браузере"
	@echo "  make test-legacy  - Запустить старые функциональные тесты"
	@echo ""
	@echo "🔍 Проверка кода:"
	@echo "  make install-linters - Установить инструменты для проверки кода"
	@echo "  make lint        - Проверить код всеми линтерами"
	@echo "  make lint-check  - Проверить код без исправлений"
	@echo "  make format      - Автоформатирование кода (black + isort)"
	@echo ""
	@echo "🧹 Очистка:"
	@echo "  make clean   - Остановить и удалить все контейнеры, тома и сети"
	@echo ""
	@echo "📖 Полезные ссылки после запуска:"
	@echo "  API:           http://localhost:7555"
	@echo "  Документация:  http://localhost:7555/docs"
	@echo "  Health check:  http://localhost:7555/health"
	@echo ""

build: ## 🏗️ Собрать Docker образ
	@echo "🔨 Сборка Docker образа..."
	@docker build -t $(IMAGE_NAME):$(TAG) .
	@echo "✅ Образ $(IMAGE_NAME):$(TAG) успешно собран!"

up: build ## 🚀 Запустить в режиме разработки
	@echo "🚀 Запуск в режиме разработки..."
	@echo "📝 Режим разработки включает:"
	@echo "  - Автоперезагрузка при изменении кода"
	@echo "  - Проброс папок для горячей замены"
	@echo "  - Подробные логи отладки"
	@echo ""
	@echo "🌐 API будет доступен по адресу: http://localhost:7555"
	@echo "📖 Документация: http://localhost:7555/docs"
	@echo ""
	@echo "Для остановки нажмите Ctrl+C"
	@docker-compose -f docker-compose.yml up

prod-up: build ## 🏭 Запустить в продакшене
	@echo "🔄 Обновление репозитория..."
	@git pull
	@echo "✅ Репозиторий обновлен!"
	@make stop
	@echo "🏭 Запуск в продакшене..."
	@echo "📝 Режим продакшена включает:"
	@echo "  - Запуск в фоновом режиме"
	@echo "  - Автоперезапуск при сбоях"
	@echo "  - Оптимизированная производительность"
	@echo ""
	@docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
	@echo "✅ Сервис запущен в фоновом режиме!"
	@echo "🌐 API доступен по адресу: http://localhost:7555"
	@echo "📖 Документация: http://localhost:7555/docs"
	@echo ""
	@echo "Для просмотра логов: make logs"
	@echo "Для остановки: make stop"

down: ## 🛑 Остановить все контейнеры
	@echo "🛑 Остановка всех контейнеров..."
	@docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
	@echo "✅ Все контейнеры остановлены!"

stop: down ## 🛑 Остановить все контейнеры (алиас для down)

logs: ## 📋 Показать логи приложения
	@echo "📋 Показ логов приложения..."
	@echo "Для выхода нажмите Ctrl+C"
	@echo ""
	@docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

status: ## 📊 Показать статус контейнеров
	@echo "📊 Статус контейнеров:"
	@echo ""
	@docker-compose -f docker-compose.yml ps 2>/dev/null || echo "Контейнеры не запущены"
	@echo ""
	@echo "📈 Использование ресурсов:"
	@docker stats --no-stream 2>/dev/null | grep text-extraction || echo "Контейнеры не запущены"

test: ## 🧪 Запустить тестирование с покрытием кода
	@echo "🧪 Запуск тестирования с покрытием кода..."
	@echo "📝 Тестирование включает:"
	@echo "  - Unit тесты всех модулей"
	@echo "  - Integration тесты API эндпоинтов"
	@echo "  - Тесты с реальными файлами"
	@echo "  - Измерение покрытия кода"
	@echo "  - Проверку производительности"
	@echo ""
	@echo "🔧 Попытка установки зависимостей..."
	@if python3 -m pip install -q -r requirements-test.txt; then \
		echo "✅ Зависимости установлены локально"; \
		echo "🏃 Запуск pytest с покрытием..."; \
		python -m pytest -v --cov=app --cov-report=term-missing --cov-report=html:coverage_html --cov-fail-under=60 || echo "⚠️ Некоторые тесты завершились с ошибками"; \
	else \
		echo "⚠️ Не удалось установить зависимости локально"; \
		echo "🐳 Переход на тестирование в Docker..."; \
		$(MAKE) test-docker; \
	fi
	@echo ""
	@echo "✅ Тестирование завершено!"
	@echo "📁 Отчеты сохранены:"
	@echo "  - HTML отчет покрытия: coverage_html/index.html"
	@echo "  - XML отчет покрытия: coverage.xml"
	@echo ""

test-unit: ## 🔬 Запустить только unit тесты
	@echo "🔬 Запуск unit тестов..."
	@python3 -m pip install -q -r requirements-test.txt || echo "⚠️ Не удалось установить зависимости"
	@python -m pytest tests/ -m unit -v --cov=app --cov-report=term-missing

test-integration: ## 🔗 Запустить только integration тесты
	@echo "🔗 Запуск integration тестов..."
	@python3 -m pip install -q -r requirements-test.txt || echo "⚠️ Не удалось установить зависимости"
	@python -m pytest tests/ -m integration -v --cov=app --cov-report=term-missing

test-coverage: ## 📊 Показать отчет покрытия в браузере
	@echo "📊 Открытие отчета покрытия..."
	@if [ -f "coverage_html/index.html" ]; then \
		python -c "import webbrowser; webbrowser.open('coverage_html/index.html')" 2>/dev/null || \
		echo "Откройте файл coverage_html/index.html в браузере"; \
	else \
		echo "❌ Отчет покрытия не найден. Запустите 'make test' сначала."; \
	fi

test-legacy: ## 📜 Запустить старые функциональные тесты
	@echo "📜 Запуск старых функциональных тестов..."
	@if [ -f "./run_tests.sh" ]; then \
		./run_tests.sh; \
	else \
		echo "❌ Файл run_tests.sh не найден!"; \
	fi

test-docker: build ## 🐳 Запустить тестирование в Docker контейнере
	@echo "🐳 Запуск тестирования в Docker..."
	@echo "📝 Тестирование в изолированном окружении:"
	@echo "  - Все зависимости предустановлены"
	@echo "  - Совместимость с Python 3.12+"
	@echo "  - Полная изоляция от системных пакетов"
	@echo ""
	@echo "🔧 Создание контейнера для тестирования..."
	@docker run --rm -v $(shell pwd):/code -w /code $(IMAGE_NAME):$(TAG) \
		bash -c "python3 -m pip install -q -r requirements-test.txt && \
		python -m pytest -v --cov=app --cov-report=term-missing --cov-report=html:coverage_html --cov-report=xml:coverage.xml --cov-fail-under=55" || \
		echo "⚠️ Некоторые тесты завершились с ошибками"
	@echo ""
	@echo "✅ Docker тестирование завершено!"

# Команды для проверки кода
install-linters: ## 🛠️ Установить инструменты для проверки кода
	@echo "🛠️ Установка инструментов для проверки кода..."
	@python3 -m pip install --upgrade pip
	@python3 -m pip install -r requirements-lint.txt
	@echo "✅ Инструменты установлены!"

lint: install-linters ## 🔍 Проверить код всеми линтерами
	@echo "🔍 Проверка кода всеми линтерами..."
	@echo ""
	@echo "🎨 Проверка форматирования с Black..."
	@python3 -m black --check --diff app/ tests/ || echo "⚠️ Найдены проблемы форматирования"
	@echo ""
	@echo "📏 Проверка стиля кода с Flake8..."
	@python3 -m flake8 app/ tests/ || echo "⚠️ Найдены нарушения стиля кода"
	@echo ""
	@echo "🔤 Проверка сортировки импортов с isort..."
	@python3 -m isort --check-only --diff app/ tests/ || echo "⚠️ Импорты не отсортированы"
	@echo ""
	@echo "🔎 Проверка типов с MyPy..."
	@python3 -m mypy app/ --ignore-missing-imports --no-strict-optional || echo "⚠️ Найдены проблемы типизации"
	@echo ""
	@echo "🛡️ Проверка безопасности с Bandit..."
	@python3 -m bandit -r app/ || echo "⚠️ Найдены потенциальные уязвимости"
	@echo ""
	@echo "🔒 Проверка зависимостей с Safety..."
	@python3 -m safety check || echo "⚠️ Найдены уязвимые зависимости"
	@echo ""
	@echo "✅ Проверка кода завершена!"

lint-check: install-linters ## 🔍 Проверить код без исправлений
	@echo "🔍 Проверка кода без автоисправлений..."
	@echo ""
	@echo "🎨 Black (только проверка)..."
	@python3 -m black --check app/ tests/
	@echo ""
	@echo "📏 Flake8..."
	@python3 -m flake8 app/ tests/
	@echo ""
	@echo "🔤 isort (только проверка)..."
	@python3 -m isort --check-only app/ tests/
	@echo ""
	@echo "✅ Проверка завершена!"

format: install-linters ## 🎨 Автоформатирование кода
	@echo "🎨 Автоформатирование кода..."
	@echo ""
	@echo "🔤 Сортировка импортов с isort..."
	@python3 -m isort app/ tests/
	@echo ""
	@echo "🎨 Форматирование с Black..."
	@python3 -m black app/ tests/
	@echo ""
	@echo "✅ Форматирование завершено!"

clean: ## 🧹 Полная очистка
	@echo "🧹 Полная очистка системы..."
	@echo "⚠️  Будут удалены:"
	@echo "  - Все контейнеры"
	@echo "  - Все тома Docker"
	@echo "  - Все сети Docker"
	@echo "  - Результаты тестов (tests/*.ok.txt, tests/*.err.txt)"
	@echo "  - Отчеты покрытия кода (.coverage, coverage_html/, coverage.xml)"
	@echo ""
	@read -p "Продолжить? (y/N) " -n 1 -r; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo ""; \
		echo "🗑️  Удаление контейнеров и томов..."; \
		docker-compose -f docker-compose.yml -f docker-compose.prod.yml down --volumes --remove-orphans; \
		echo "🗑️  Удаление результатов тестов..."; \
		rm -f tests/*.ok.txt tests/*.err.txt tests/supported_formats.json 2>/dev/null || true; \
		echo "🗑️  Удаление отчетов покрытия..."; \
		rm -rf coverage_html/ .coverage coverage.xml .pytest_cache/ __pycache__/ 2>/dev/null || true; \
		echo "✅ Система очищена!"; \
	else \
		echo ""; \
		echo "Операция отменена"; \
	fi

# Дополнительные команды для разработчиков
debug: ## 🐛 Запустить в режиме отладки
	@echo "🐛 Режим отладки..."
	@echo "Подключение к контейнеру для отладки"
	@docker-compose -f docker-compose.yml exec api /bin/bash

quick-test: ## ⚡ Быстрый тест API
	@echo "⚡ Быстрый тест API..."
	@if [ -f "quick_test.py" ]; then \
		python3 quick_test.py; \
	else \
		echo "❌ Файл quick_test.py не найден!"; \
	fi

# Показать help по умолчанию
.DEFAULT_GOAL := help 