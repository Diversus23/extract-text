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

.PHONY: help build dev prod stop logs test clean status

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
	@echo "  $(YELLOW)make test$(RESET)    - Запустить полное тестирование API"
	@echo ""
	@echo "$(BOLD)$(GREEN)🧹 Очистка:$(RESET)"
	@echo "  $(YELLOW)make clean$(RESET)   - Остановить и удалить все контейнеры, тома и сети"
	@echo ""
	@echo "$(BOLD)$(PURPLE)📖 Полезные ссылки после запуска:$(RESET)"
	@echo "  API:           http://localhost:7555"
	@echo "  Документация:  http://localhost:7555/docs"
	@echo "  Health check:  http://localhost:7555/health"
	@echo ""