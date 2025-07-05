#!/bin/tcsh

# Тестовый файл tcsh для проверки извлечения текста
# Демонстрирует основные возможности tcsh shell

# Установка основных переменных окружения
setenv PROJECT_NAME "text-extraction-api"
setenv API_VERSION "1.7"
setenv API_PORT "7555"
setenv LOG_LEVEL "INFO"
setenv MAX_WORKERS "4"

# Локальные переменные
set server_url = "http://localhost:${API_PORT}"
set log_file = "/tmp/tcsh_test.log"
set test_files_dir = "./tests"
set results_dir = "./results"

# Массив поддерживаемых форматов
set supported_formats = (pdf docx doc txt html md jpg jpeg png tiff py js ts java cpp bsl os)

# Функция для логирования
alias log_message 'echo "`date '+%Y-%m-%d %H:%M:%S'` [\!:1] \!:2*" | tee -a $log_file'

# Функция для проверки зависимостей
alias check_dependency 'which \!:1 >& /dev/null; if ($status == 0) then; echo "✅ \!:1 найден"; else; echo "❌ \!:1 не найден"; exit 1; endif'

# Функция для отправки HTTP запроса
send_http_request:
    set method = $1
    set url = $2
    set output_file = $3
    
    log_message "DEBUG" "Отправка $method запроса к $url"
    
    if ("$method" == "GET") then
        curl -s -X GET "$url" -o "$output_file"
    else if ("$method" == "POST") then
        curl -s -X POST "$url" -F "file=@$4" -o "$output_file"
    else
        log_message "ERROR" "Неизвестный HTTP метод: $method"
        exit 1
    endif
    
    if ($status == 0) then
        log_message "INFO" "HTTP запрос успешен"
        return 0
    else
        log_message "ERROR" "HTTP запрос неуспешен"
        return 1
    endif

# Функция для проверки API здоровья
check_api_health:
    log_message "INFO" "Проверка здоровья API"
    
    set temp_file = "/tmp/health_check.json"
    send_http_request "GET" "${server_url}/health" "$temp_file"
    
    if ($status == 0) then
        set health_status = `cat $temp_file | grep -o '"status":"[^"]*"' | cut -d'"' -f4`
        if ("$health_status" == "ok") then
            log_message "INFO" "API здоров"
            rm -f "$temp_file"
            return 0
        else
            log_message "ERROR" "API нездоров: $health_status"
            rm -f "$temp_file"
            return 1
        endif
    else
        log_message "ERROR" "Не удалось проверить здоровье API"
        return 1
    endif

# Функция для получения информации о API
get_api_info:
    log_message "INFO" "Получение информации о API"
    
    set temp_file = "/tmp/api_info.json"
    send_http_request "GET" "${server_url}/" "$temp_file"
    
    if ($status == 0) then
        set api_name = `cat $temp_file | grep -o '"api_name":"[^"]*"' | cut -d'"' -f4`
        set version = `cat $temp_file | grep -o '"version":"[^"]*"' | cut -d'"' -f4`
        
        log_message "INFO" "API: $api_name"
        log_message "INFO" "Версия: $version"
        
        rm -f "$temp_file"
        return 0
    else
        log_message "ERROR" "Не удалось получить информацию о API"
        return 1
    endif

# Функция для тестирования файла
test_file_extraction:
    set file_path = $1
    set file_name = $2
    
    log_message "INFO" "Тестирование файла: $file_name"
    
    if (! -f "$file_path") then
        log_message "WARNING" "Файл не найден: $file_path"
        return 1
    endif
    
    set temp_result = "/tmp/extract_result_${file_name}.json"
    send_http_request "POST" "${server_url}/v1/extract-text/" "$temp_result" "$file_path"
    
    if ($status == 0) then
        # Проверка наличия обязательных полей
        set has_text = `grep -c '"text"' "$temp_result"`
        set has_word_count = `grep -c '"word_count"' "$temp_result"`
        set has_char_count = `grep -c '"character_count"' "$temp_result"`
        
        if ($has_text > 0 && $has_word_count > 0 && $has_char_count > 0) then
            # Извлечение статистики
            set word_count = `cat $temp_result | grep -o '"word_count":[0-9]*' | cut -d':' -f2`
            set char_count = `cat $temp_result | grep -o '"character_count":[0-9]*' | cut -d':' -f2`
            
            log_message "INFO" "Файл $file_name успешно обработан"
            log_message "INFO" "Слов: $word_count, Символов: $char_count"
            
            # Сохранение результата
            if (! -d "$results_dir") then
                mkdir -p "$results_dir"
            endif
            
            cp "$temp_result" "${results_dir}/${file_name}.json"
            
            rm -f "$temp_result"
            return 0
        else
            log_message "ERROR" "Отсутствуют обязательные поля в ответе для $file_name"
            rm -f "$temp_result"
            return 1
        endif
    else
        log_message "ERROR" "Не удалось обработать файл $file_name"
        return 1
    endif

# Функция для тестирования ошибок
test_error_handling:
    log_message "INFO" "Тестирование обработки ошибок"
    
    # Создание файла неподдерживаемого формата
    set unsupported_file = "/tmp/test.unsupported"
    echo "Тестовый контент" > "$unsupported_file"
    
    set temp_result = "/tmp/error_test.json"
    send_http_request "POST" "${server_url}/v1/extract-text/" "$temp_result" "$unsupported_file"
    
    if ($status != 0) then
        log_message "INFO" "Неподдерживаемый формат корректно отклонен"
        rm -f "$unsupported_file" "$temp_result"
        return 0
    else
        log_message "ERROR" "Неподдерживаемый формат не был отклонен"
        rm -f "$unsupported_file" "$temp_result"
        return 1
    endif

# Главная функция выполнения тестов
main:
    log_message "INFO" "Запуск тестирования API извлечения текста"
    log_message "INFO" "Проект: $PROJECT_NAME, Версия: $API_VERSION"
    
    # Проверка зависимостей
    log_message "INFO" "Проверка зависимостей..."
    check_dependency curl
    check_dependency grep
    check_dependency cut
    
    # Проверка здоровья API
    check_api_health
    if ($status != 0) then
        log_message "ERROR" "API недоступен"
        exit 1
    endif
    
    # Получение информации о API
    get_api_info
    
    # Тестирование файлов
    log_message "INFO" "Начинаем тестирование файлов..."
    
    set total_tests = 0
    set passed_tests = 0
    
    foreach format ($supported_formats)
        set test_file = "${test_files_dir}/test.${format}"
        if (-f "$test_file") then
            @ total_tests++
            test_file_extraction "$test_file" "test.${format}"
            if ($status == 0) then
                @ passed_tests++
            endif
        endif
    end
    
    # Тестирование обработки ошибок
    @ total_tests++
    test_error_handling
    if ($status == 0) then
        @ passed_tests++
    endif
    
    # Подведение итогов
    log_message "INFO" "Тестирование завершено"
    log_message "INFO" "Пройдено тестов: $passed_tests из $total_tests"
    
    if ($passed_tests == $total_tests) then
        log_message "INFO" "🎉 Все тесты пройдены успешно!"
        exit 0
    else
        @ failed_tests = $total_tests - $passed_tests
        log_message "ERROR" "❌ Провалено тестов: $failed_tests"
        exit 1
    endif

# Обработка аргументов командной строки
if ($#argv == 0) then
    # Запуск основных тестов
    main
else
    switch ($1)
        case "health":
            check_api_health
            breaksw
        case "info":
            get_api_info
            breaksw
        case "test":
            if ($#argv >= 2) then
                test_file_extraction "$2" "`basename $2`"
            else
                echo "Использование: $0 test <файл>"
                exit 1
            endif
            breaksw
        case "help":
            echo "Использование: $0 [команда] [аргументы]"
            echo "Команды:"
            echo "  health     - проверить здоровье API"
            echo "  info       - получить информацию о API"
            echo "  test <файл> - протестировать конкретный файл"
            echo "  help       - показать эту справку"
            echo "  (пустая)   - запустить все тесты"
            breaksw
        default:
            echo "Неизвестная команда: $1"
            echo "Используйте '$0 help' для получения справки"
            exit 1
            breaksw
    endsw
endif 