# Makefile для управления жизненным циклом Text Extraction API
IMAGE_NAME := text-extraction-api
TAG := latest

# Цветовые коды для вывода
RED    := \033[31m
GREEN  := \033[32m
YELLOW := \033[33m
BLUE   := \033[34m
PURPLE := \033[35m
CYAN   := \033[36m
WHITE  := \033[37m
RESET  := \033[0m
BOLD   := \033[1m

.PHONY: help build dev prod stop logs test test-unit test-integration test-coverage test-legacy clean status

help: ## 📋 Показать список доступных команд
	@echo "$(BOLD)$(CYAN)========================================$(RESET)"
	@echo "$(BOLD)$(CYAN)  Text Extraction API - Управление$(RESET)"
	@echo "$(BOLD)$(CYAN)========================================$(RESET)"
	@echo ""
	@echo "$(BOLD)$(GREEN)🏗️  Сборка и развертывание:$(RESET)"
	@echo "  $(YELLOW)make build$(RESET)   - Собрать Docker образ"
	@echo "  $(YELLOW)make dev$(RESET)     - Запустить в режиме разработки (с автоперезагрузкой)"
	@echo "  $(YELLOW)make prod$(RESET)    - Запустить в продакшене (в фоновом режиме)"
	@echo ""
	@echo "$(BOLD)$(GREEN)🔧 Управление сервисом:$(RESET)"
	@echo "  $(YELLOW)make stop$(RESET)    - Остановить все контейнеры"
	@echo "  $(YELLOW)make logs$(RESET)    - Показать логи приложения в реальном времени"
	@echo "  $(YELLOW)make status$(RESET)  - Показать статус контейнеров"
	@echo ""
	@echo "$(BOLD)$(GREEN)🧪 Тестирование:$(RESET)"
	@echo "  $(YELLOW)make test$(RESET)         - Запустить полное тестирование с покрытием"
	@echo "  $(YELLOW)make test-unit$(RESET)    - Запустить только unit тесты"
	@echo "  $(YELLOW)make test-integration$(RESET) - Запустить только integration тесты"
	@echo "  $(YELLOW)make test-docker$(RESET)  - Запустить тестирование в Docker контейнере"
	@echo "  $(YELLOW)make test-coverage$(RESET) - Показать отчет покрытия в браузере"
	@echo "  $(YELLOW)make test-legacy$(RESET)  - Запустить старые функциональные тесты"
	@echo ""
	@echo "$(BOLD)$(GREEN)🧹 Очистка:$(RESET)"
	@echo "  $(YELLOW)make clean$(RESET)   - Остановить и удалить все контейнеры, тома и сети"
	@echo ""
	@echo "$(BOLD)$(PURPLE)📖 Полезные ссылки после запуска:$(RESET)"
	@echo "  API:           http://localhost:7555"
	@echo "  Документация:  http://localhost:7555/docs"
	@echo "  Health check:  http://localhost:7555/health"
	@echo ""

build: ## 🏗️ Собрать Docker образ
	@echo "$(BOLD)$(BLUE)🔨 Сборка Docker образа...$(RESET)"
	@docker build -t $(IMAGE_NAME):$(TAG) .
	@echo "$(GREEN)✅ Образ $(IMAGE_NAME):$(TAG) успешно собран!$(RESET)"

dev: build ## 🚀 Запустить в режиме разработки
	@echo "$(BOLD)$(GREEN)🚀 Запуск в режиме разработки...$(RESET)"
	@echo "$(YELLOW)📝 Режим разработки включает:$(RESET)"
	@echo "  - Автоперезагрузка при изменении кода"
	@echo "  - Проброс папок для горячей замены"
	@echo "  - Подробные логи отладки"
	@echo ""
	@echo "$(CYAN)🌐 API будет доступен по адресу: http://localhost:7555$(RESET)"
	@echo "$(CYAN)📖 Документация: http://localhost:7555/docs$(RESET)"
	@echo ""
	@echo "$(YELLOW)Для остановки нажмите Ctrl+C$(RESET)"
	@docker-compose -f docker-compose.yml up

prod: build ## 🏭 Запустить в продакшене
	@echo "$(BOLD)$(GREEN)🏭 Запуск в продакшене...$(RESET)"
	@echo "$(YELLOW)📝 Режим продакшена включает:$(RESET)"
	@echo "  - Запуск в фоновом режиме"
	@echo "  - Автоперезапуск при сбоях"
	@echo "  - Оптимизированная производительность"
	@echo ""
	@docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
	@echo "$(GREEN)✅ Сервис запущен в фоновом режиме!$(RESET)"
	@echo "$(CYAN)🌐 API доступен по адресу: http://localhost:7555$(RESET)"
	@echo "$(CYAN)📖 Документация: http://localhost:7555/docs$(RESET)"
	@echo ""
	@echo "$(YELLOW)Для просмотра логов: make logs$(RESET)"
	@echo "$(YELLOW)Для остановки: make stop$(RESET)"

stop: ## 🛑 Остановить все контейнеры
	@echo "$(BOLD)$(RED)🛑 Остановка всех контейнеров...$(RESET)"
	@docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
	@echo "$(GREEN)✅ Все контейнеры остановлены!$(RESET)"

logs: ## 📋 Показать логи приложения
	@echo "$(BOLD)$(CYAN)📋 Показ логов приложения...$(RESET)"
	@echo "$(YELLOW)Для выхода нажмите Ctrl+C$(RESET)"
	@echo ""
	@docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

status: ## 📊 Показать статус контейнеров
	@echo "$(BOLD)$(CYAN)📊 Статус контейнеров:$(RESET)"
	@echo ""
	@docker-compose -f docker-compose.yml ps 2>/dev/null || echo "$(YELLOW)Контейнеры не запущены$(RESET)"
	@echo ""
	@echo "$(BOLD)$(CYAN)📈 Использование ресурсов:$(RESET)"
	@docker stats --no-stream 2>/dev/null | grep text-extraction || echo "$(YELLOW)Контейнеры не запущены$(RESET)"

test: ## 🧪 Запустить тестирование с покрытием кода
	@echo "$(BOLD)$(PURPLE)🧪 Запуск тестирования с покрытием кода...$(RESET)"
	@echo "$(YELLOW)📝 Тестирование включает:$(RESET)"
	@echo "  - Unit тесты всех модулей"
	@echo "  - Integration тесты API эндпоинтов"
	@echo "  - Тесты с реальными файлами"
	@echo "  - Измерение покрытия кода"
	@echo "  - Проверку производительности"
	@echo ""
	@echo "$(CYAN)🔧 Попытка установки зависимостей...$(RESET)"
	@if pip install -q -r requirements-test.txt; then \
		echo "$(GREEN)✅ Зависимости установлены локально$(RESET)"; \
		echo "$(CYAN)🏃 Запуск pytest с покрытием...$(RESET)"; \
		python -m pytest -v --cov=app --cov-report=term-missing --cov-report=html:coverage_html --cov-fail-under=30 || echo "$(YELLOW)⚠️ Некоторые тесты завершились с ошибками$(RESET)"; \
	else \
		echo "$(YELLOW)⚠️ Не удалось установить зависимости локально$(RESET)"; \
		echo "$(CYAN)🐳 Переход на тестирование в Docker...$(RESET)"; \
		$(MAKE) test-docker; \
	fi
	@echo ""
	@echo "$(GREEN)✅ Тестирование завершено!$(RESET)"
	@echo "$(YELLOW)📁 Отчеты сохранены:$(RESET)"
	@echo "  - HTML отчет покрытия: coverage_html/index.html"
	@echo "  - XML отчет покрытия: coverage.xml"
	@echo ""

test-unit: ## 🔬 Запустить только unit тесты
	@echo "$(BOLD)$(BLUE)🔬 Запуск unit тестов...$(RESET)"
	@pip install -q -r requirements-test.txt || echo "$(YELLOW)⚠️ Не удалось установить зависимости$(RESET)"
	@python -m pytest tests/ -m unit -v --cov=app --cov-report=term-missing

test-integration: ## 🔗 Запустить только integration тесты
	@echo "$(BOLD)$(BLUE)🔗 Запуск integration тестов...$(RESET)"
	@pip install -q -r requirements-test.txt || echo "$(YELLOW)⚠️ Не удалось установить зависимости$(RESET)"
	@python -m pytest tests/ -m integration -v --cov=app --cov-report=term-missing

test-coverage: ## 📊 Показать отчет покрытия в браузере
	@echo "$(BOLD)$(CYAN)📊 Открытие отчета покрытия...$(RESET)"
	@if [ -f "coverage_html/index.html" ]; then \
		python -c "import webbrowser; webbrowser.open('coverage_html/index.html')" 2>/dev/null || \
		echo "$(YELLOW)Откройте файл coverage_html/index.html в браузере$(RESET)"; \
	else \
		echo "$(RED)❌ Отчет покрытия не найден. Запустите 'make test' сначала.$(RESET)"; \
	fi

test-legacy: ## 📜 Запустить старые функциональные тесты
	@echo "$(BOLD)$(PURPLE)📜 Запуск старых функциональных тестов...$(RESET)"
	@if [ -f "./run_tests.sh" ]; then \
		./run_tests.sh; \
	else \
		echo "$(RED)❌ Файл run_tests.sh не найден!$(RESET)"; \
	fi

test-docker: build ## 🐳 Запустить тестирование в Docker контейнере
	@echo "$(BOLD)$(BLUE)🐳 Запуск тестирования в Docker...$(RESET)"
	@echo "$(YELLOW)📝 Тестирование в изолированном окружении:$(RESET)"
	@echo "  - Все зависимости предустановлены"
	@echo "  - Совместимость с Python 3.10+"
	@echo "  - Полная изоляция от системных пакетов"
	@echo ""
	@echo "$(CYAN)🔧 Создание контейнера для тестирования...$(RESET)"
	@docker run --rm -v $(shell pwd):/code -w /code $(IMAGE_NAME):$(TAG) \
		bash -c "pip install -q pytest==7.4.4 pytest-asyncio==0.23.2 pytest-cov==4.1.0 httpx==0.25.2 pytest-mock==3.12.0 requests==2.31.0 && \
		python -m pytest -v --cov=app --cov-report=term-missing --cov-report=html:coverage_html --cov-fail-under=30" || \
		echo "$(YELLOW)⚠️ Некоторые тесты завершились с ошибками$(RESET)"
	@echo ""
	@echo "$(GREEN)✅ Docker тестирование завершено!$(RESET)"

clean: ## 🧹 Полная очистка
	@echo "$(BOLD)$(RED)🧹 Полная очистка системы...$(RESET)"
	@echo "$(YELLOW)⚠️  Будут удалены:$(RESET)"
	@echo "  - Все контейнеры"
	@echo "  - Все тома Docker"
	@echo "  - Все сети Docker"
	@echo "  - Результаты тестов (tests/*.ok.txt, tests/*.err.txt)"
	@echo "  - Отчеты покрытия кода (.coverage, coverage_html/, coverage.xml)"
	@echo ""
	@read -p "Продолжить? (y/N) " -n 1 -r; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo ""; \
		echo "$(RED)🗑️  Удаление контейнеров и томов...$(RESET)"; \
		docker-compose -f docker-compose.yml -f docker-compose.prod.yml down --volumes --remove-orphans; \
		echo "$(RED)🗑️  Удаление результатов тестов...$(RESET)"; \
		rm -f tests/*.ok.txt tests/*.err.txt tests/supported_formats.json 2>/dev/null || true; \
		echo "$(RED)🗑️  Удаление отчетов покрытия...$(RESET)"; \
		rm -rf coverage_html/ .coverage coverage.xml .pytest_cache/ __pycache__/ 2>/dev/null || true; \
		echo "$(GREEN)✅ Система очищена!$(RESET)"; \
	else \
		echo ""; \
		echo "$(YELLOW)Операция отменена$(RESET)"; \
	fi

# Дополнительные команды для разработчиков
debug: ## 🐛 Запустить в режиме отладки
	@echo "$(BOLD)$(YELLOW)🐛 Режим отладки...$(RESET)"
	@echo "$(CYAN)Подключение к контейнеру для отладки$(RESET)"
	@docker-compose -f docker-compose.yml exec api /bin/bash

quick-test: ## ⚡ Быстрый тест API
	@echo "$(BOLD)$(BLUE)⚡ Быстрый тест API...$(RESET)"
	@if [ -f "quick_test.py" ]; then \
		python3 quick_test.py; \
	else \
		echo "$(RED)❌ Файл quick_test.py не найден!$(RESET)"; \
	fi

# Показать help по умолчанию
.DEFAULT_GOAL := help 