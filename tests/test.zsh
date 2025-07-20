#!/bin/zsh

# Тестовый файл Z shell для проверки извлечения текста
# Демонстрирует продвинутые возможности zsh

# Включение расширенных возможностей zsh
setopt EXTENDED_GLOB
setopt AUTO_CD
setopt CORRECT
setopt APPEND_HISTORY
setopt SHARE_HISTORY
setopt HIST_IGNORE_DUPS

# Автозагрузка функций
autoload -U colors && colors
autoload -U zmv
autoload -U compinit && compinit

# Конфигурация проекта
typeset -r PROJECT_NAME="text-extraction-api"
typeset -r API_VERSION="1.7"
typeset -r API_PORT=${API_PORT:-7555}
typeset -r API_HOST=${API_HOST:-localhost}
typeset -r LOG_LEVEL=${LOG_LEVEL:-INFO}

# Производные переменные
typeset -r API_BASE_URL="http://${API_HOST}:${API_PORT}"
typeset -r LOG_FILE="/tmp/zsh_test_$(date +%Y%m%d_%H%M%S).log"
typeset -r TEST_FILES_DIR="./tests"
typeset -r RESULTS_DIR="./results"

# Ассоциативный массив для статистики
typeset -A test_stats
test_stats[total]=0
test_stats[passed]=0
test_stats[failed]=0
test_stats[skipped]=0

# Массив поддерживаемых форматов
typeset -a supported_formats=(
    pdf docx doc txt html md rtf odt
    jpg jpeg png tiff tif bmp gif
    xls xlsx csv ods
    pptx ppt
    json xml yaml yml
    py pyx pyi pyw js jsx ts tsx mjs cjs
    java jav c cpp cxx cc "c++" h hpp hxx "h++"
    cs csx php php3 php4 php5 phtml
    rb rbw rake gemspec go mod sum
    rs rlib swift kt kts scala sc
    r R rmd Rmd sql ddl dml
    sh bash zsh fish ksh csh tcsh
    ps1 psm1 psd1 pl pm pod t lua
    bsl os ini cfg conf toml
    css scss sass less styl
    tex latex dockerfile makefile gitignore
)

# Цветовые константы
typeset -r RED=$'\e[31m'
typeset -r GREEN=$'\e[32m'
typeset -r YELLOW=$'\e[33m'
typeset -r BLUE=$'\e[34m'
typeset -r MAGENTA=$'\e[35m'
typeset -r CYAN=$'\e[36m'
typeset -r WHITE=$'\e[37m'
typeset -r RESET=$'\e[0m'

# Функция для цветного вывода
print_colored() {
    local color=$1
    local message=$2
    printf "${color}%s${RESET}\n" "$message"
}

# Функция для логирования с поддержкой уровней
log_message() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local log_entry="${timestamp} [${level}] ${message}"
    
    # Цветной вывод в консоль
    case $level in
        ERROR)   print_colored "$RED" "$log_entry" ;;
        WARNING) print_colored "$YELLOW" "$log_entry" ;;
        INFO)    print_colored "$GREEN" "$log_entry" ;;
        DEBUG)   print_colored "$CYAN" "$log_entry" ;;
        *)       print_colored "$WHITE" "$log_entry" ;;
    esac
    
    # Запись в лог-файл
    echo "$log_entry" >> "$LOG_FILE"
}

# Функция для проверки зависимостей
check_dependencies() {
    local -a dependencies=(curl jq grep sed awk)
    local -i missing_deps=0
    
    log_message "INFO" "Проверка зависимостей..."
    
    for dep in "${dependencies[@]}"; do
        if command -v "$dep" >/dev/null 2>&1; then
            log_message "DEBUG" "✅ $dep найден"
        else
            log_message "ERROR" "❌ $dep не найден"
            ((missing_deps++))
        fi
    done
    
    if ((missing_deps > 0)); then
        log_message "ERROR" "Отсутствуют необходимые зависимости: $missing_deps"
        return 1
    fi
    
    return 0
}

# Функция для отправки HTTP запросов
send_http_request() {
    local method=$1
    local endpoint=$2
    local file_path=${3:-}
    local timeout=${4:-30}
    
    local url="${API_BASE_URL}${endpoint}"
    local response_file="/tmp/response_$$.json"
    
    log_message "DEBUG" "Отправка $method запроса к $url"
    
    local curl_cmd="curl -s -w '%{http_code}' -o '$response_file' -m $timeout"
    
    case $method in
        GET)
            curl_cmd+=" -X GET '$url'"
            ;;
        POST)
            if [[ -n "$file_path" ]]; then
                curl_cmd+=" -X POST -F 'file=@$file_path' '$url'"
            else
                log_message "ERROR" "Для POST запроса требуется файл"
                return 1
            fi
            ;;
        *)
            log_message "ERROR" "Неподдерживаемый HTTP метод: $method"
            return 1
            ;;
    esac
    
    local http_code=$(eval "$curl_cmd")
    local response_content=$(cat "$response_file" 2>/dev/null || echo "{}")
    
    # Создание результата
    local result_json=$(jq -n \
        --arg code "$http_code" \
        --argjson content "$response_content" \
        '{http_code: $code, content: $content}')
    
    echo "$result_json"
    rm -f "$response_file"
    
    return 0
}

# Функция для проверки здоровья API
check_api_health() {
    log_message "INFO" "Проверка здоровья API"
    
    local response=$(send_http_request "GET" "/health")
    local http_code=$(echo "$response" | jq -r '.http_code')
    
    if [[ "$http_code" == "200" ]]; then
        local status=$(echo "$response" | jq -r '.content.status // empty')
        if [[ "$status" == "ok" ]]; then
            log_message "INFO" "API здоров"
            return 0
        else
            log_message "ERROR" "API нездоров: $status"
            return 1
        fi
    else
        log_message "ERROR" "API недоступен (HTTP $http_code)"
        return 1
    fi
}

# Функция для получения информации о API
get_api_info() {
    log_message "INFO" "Получение информации о API"
    
    local response=$(send_http_request "GET" "/")
    local http_code=$(echo "$response" | jq -r '.http_code')
    
    if [[ "$http_code" == "200" ]]; then
        local api_name=$(echo "$response" | jq -r '.content.api_name // "Unknown"')
        local version=$(echo "$response" | jq -r '.content.version // "Unknown"')
        local contact=$(echo "$response" | jq -r '.content.contact // "Unknown"')
        
        log_message "INFO" "API: $api_name"
        log_message "INFO" "Версия: $version"
        log_message "INFO" "Контакт: $contact"
        
        return 0
    else
        log_message "ERROR" "Не удалось получить информацию о API (HTTP $http_code)"
        return 1
    fi
}

# Функция для получения поддерживаемых форматов
get_supported_formats() {
    log_message "INFO" "Получение поддерживаемых форматов"
    
    local response=$(send_http_request "GET" "/v1/supported-formats")
    local http_code=$(echo "$response" | jq -r '.http_code')
    
    if [[ "$http_code" == "200" ]]; then
        local formats=$(echo "$response" | jq -r '.content | keys | join(", ")')
        log_message "INFO" "Поддерживаемые категории: $formats"
        
        # Проверка наличия category source_code
        local has_source_code=$(echo "$response" | jq -r '.content.source_code // empty')
        if [[ -n "$has_source_code" ]]; then
            local source_formats=$(echo "$response" | jq -r '.content.source_code | join(", ")')
            log_message "INFO" "Исходный код: $source_formats"
        fi
        
        return 0
    else
        log_message "ERROR" "Не удалось получить поддерживаемые форматы (HTTP $http_code)"
        return 1
    fi
}

# Функция для тестирования файла
test_file_extraction() {
    local file_path=$1
    local file_name=$(basename "$file_path")
    
    log_message "INFO" "Тестирование файла: $file_name"
    
    ((test_stats[total]++))
    
    if [[ ! -f "$file_path" ]]; then
        log_message "WARNING" "Файл не найден: $file_path"
        ((test_stats[skipped]++))
        return 2
    fi
    
    local file_size=$(stat -c%s "$file_path" 2>/dev/null || stat -f%z "$file_path" 2>/dev/null || echo 0)
    log_message "DEBUG" "Размер файла: $file_size байт"
    
    local response=$(send_http_request "POST" "/v1/extract-text/" "$file_path")
    local http_code=$(echo "$response" | jq -r '.http_code')
    
    if [[ "$http_code" == "200" ]]; then
        local content=$(echo "$response" | jq -r '.content')
        
        # Проверка обязательных полей
        local text=$(echo "$content" | jq -r '.text // empty')
        local word_count=$(echo "$content" | jq -r '.word_count // 0')
        local char_count=$(echo "$content" | jq -r '.character_count // 0')
        
        if [[ -n "$text" && "$word_count" -gt 0 ]]; then
            log_message "INFO" "Файл $file_name успешно обработан"
            log_message "INFO" "Слов: $word_count, Символов: $char_count"
            
            # Сохранение результата
            [[ ! -d "$RESULTS_DIR" ]] && mkdir -p "$RESULTS_DIR"
            echo "$content" > "${RESULTS_DIR}/${file_name}.json"
            
            ((test_stats[passed]++))
            return 0
        else
            log_message "ERROR" "Некорректный ответ для файла $file_name"
            ((test_stats[failed]++))
            return 1
        fi
    else
        log_message "ERROR" "Ошибка обработки файла $file_name (HTTP $http_code)"
        ((test_stats[failed]++))
        return 1
    fi
}

# Функция для тестирования обработки ошибок
test_error_handling() {
    log_message "INFO" "Тестирование обработки ошибок"
    
    ((test_stats[total]++))
    
    # Создание файла неподдерживаемого формата
    local unsupported_file="/tmp/test_unsupported_$$.unknown"
    echo "Тестовый контент неподдерживаемого формата" > "$unsupported_file"
    
    local response=$(send_http_request "POST" "/v1/extract-text/" "$unsupported_file")
    local http_code=$(echo "$response" | jq -r '.http_code')
    
    rm -f "$unsupported_file"
    
    if [[ "$http_code" == "415" ]]; then
        log_message "INFO" "Неподдерживаемый формат корректно отклонен"
        ((test_stats[passed]++))
        return 0
    else
        log_message "ERROR" "Неподдерживаемый формат не был отклонен (HTTP $http_code)"
        ((test_stats[failed]++))
        return 1
    fi
}

# Функция для создания отчета
generate_report() {
    log_message "INFO" "Создание отчета о тестировании"
    
    local report_file="${RESULTS_DIR}/test_report.json"
    [[ ! -d "$RESULTS_DIR" ]] && mkdir -p "$RESULTS_DIR"
    
    local report=$(jq -n \
        --arg timestamp "$(date -Iseconds)" \
        --arg project "$PROJECT_NAME" \
        --arg version "$API_VERSION" \
        --arg total "${test_stats[total]}" \
        --arg passed "${test_stats[passed]}" \
        --arg failed "${test_stats[failed]}" \
        --arg skipped "${test_stats[skipped]}" \
        --arg log_file "$LOG_FILE" \
        '{
            timestamp: $timestamp,
            project: $project,
            version: $version,
            statistics: {
                total: ($total | tonumber),
                passed: ($passed | tonumber),
                failed: ($failed | tonumber),
                skipped: ($skipped | tonumber)
            },
            log_file: $log_file
        }')
    
    echo "$report" > "$report_file"
    log_message "INFO" "Отчет сохранен в: $report_file"
}

# Главная функция тестирования
main() {
    log_message "INFO" "Запуск тестирования API извлечения текста"
    log_message "INFO" "Проект: $PROJECT_NAME, Версия: $API_VERSION"
    log_message "INFO" "API URL: $API_BASE_URL"
    
    # Проверка зависимостей
    check_dependencies || {
        log_message "ERROR" "Не удалось проверить зависимости"
        return 1
    }
    
    # Проверка здоровья API
    check_api_health || {
        log_message "ERROR" "API недоступен"
        return 1
    }
    
    # Получение информации о API
    get_api_info
    get_supported_formats
    
    # Тестирование файлов
    log_message "INFO" "Начинаем тестирование файлов..."
    
    for format in "${supported_formats[@]}"; do
        local test_file="${TEST_FILES_DIR}/test.${format}"
        test_file_extraction "$test_file"
    done
    
    # Тестирование обработки ошибок
    test_error_handling
    
    # Создание отчета
    generate_report
    
    # Подведение итогов
    log_message "INFO" "Тестирование завершено"
    log_message "INFO" "Всего тестов: ${test_stats[total]}"
    log_message "INFO" "Пройдено: ${test_stats[passed]}"
    log_message "INFO" "Провалено: ${test_stats[failed]}"
    log_message "INFO" "Пропущено: ${test_stats[skipped]}"
    
    if ((test_stats[failed] == 0)); then
        log_message "INFO" "🎉 Все тесты пройдены успешно!"
        return 0
    else
        log_message "ERROR" "❌ Некоторые тесты провалены"
        return 1
    fi
}

# Обработка аргументов командной строки
case "${1:-}" in
    health)
        check_api_health
        ;;
    info)
        get_api_info
        ;;
    formats)
        get_supported_formats
        ;;
    test)
        if [[ -n "${2:-}" ]]; then
            test_file_extraction "$2"
        else
            echo "Использование: $0 test <файл>"
            exit 1
        fi
        ;;
    help)
        cat << EOF
Использование: $0 [команда] [аргументы]

Команды:
  health     - проверить здоровье API
  info       - получить информацию о API
  formats    - получить поддерживаемые форматы
  test <файл> - протестировать конкретный файл
  help       - показать эту справку
  (пустая)   - запустить все тесты

Переменные окружения:
  API_HOST   - хост API (по умолчанию: localhost)
  API_PORT   - порт API (по умолчанию: 7555)
  LOG_LEVEL  - уровень логирования (по умолчанию: INFO)
EOF
        ;;
    *)
        main
        ;;
esac 