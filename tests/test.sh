#!/bin/bash

# Тестовый Shell скрипт для проверки извлечения текста
# Демонстрирует основные возможности bash

set -e  # Выход при ошибке

# Переменные
PROJECT_NAME="text-extraction-api"
VERSION="1.7.0"
LOG_FILE="/tmp/extraction.log"

# Функция для логирования
log_message() {
    local level="$1"
    local message="$2"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$level] $message" | tee -a "$LOG_FILE"
}

# Функция проверки зависимостей
check_dependencies() {
    log_message "INFO" "Проверка зависимостей..."
    
    local deps=("python3" "docker" "make" "curl")
    
    for dep in "${deps[@]}"; do
        if command -v "$dep" &> /dev/null; then
            log_message "INFO" "✅ $dep найден"
        else
            log_message "ERROR" "❌ $dep не найден"
            return 1
        fi
    done
}

# Основная функция развертывания
deploy_application() {
    log_message "INFO" "Начало развертывания $PROJECT_NAME v$VERSION"
    
    # Проверка зависимостей
    check_dependencies || exit 1
    
    # Создание директорий
    mkdir -p {logs,data,backups}
    
    # Обновление кода
    if [[ -d ".git" ]]; then
        git pull origin main
        log_message "INFO" "Код обновлен"
    fi
    
    # Сборка Docker образа
    docker build -t "$PROJECT_NAME:$VERSION" .
    log_message "INFO" "Docker образ собран"
    
    # Запуск тестов
    make test
    log_message "INFO" "Тесты пройдены"
    
    # Развертывание
    docker-compose up -d
    log_message "INFO" "Приложение развернуто"
    
    # Проверка здоровья
    sleep 5
    if curl -f http://localhost:7555/health; then
        log_message "INFO" "🎉 Развертывание успешно завершено!"
    else
        log_message "ERROR" "❌ Ошибка при развертывании"
        exit 1
    fi
}

# Обработка аргументов командной строки
case "${1:-}" in
    "deploy")
        deploy_application
        ;;
    "check")
        check_dependencies
        ;;
    "logs")
        tail -f "$LOG_FILE"
        ;;
    *)
        echo "Использование: $0 {deploy|check|logs}"
        echo "  deploy - развернуть приложение"
        echo "  check  - проверить зависимости"
        echo "  logs   - показать логи"
        exit 1
        ;;
esac 