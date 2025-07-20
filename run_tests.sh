#!/bin/bash

# Скрипт для тестирования API извлечения текста
set -e

API_URL="http://localhost:7555"
TESTS_DIR="./tests"

echo "=== Тестирование Text Extraction API ==="

# Проверка доступности API
echo "Проверка доступности API..."
if ! curl -s "$API_URL/health" | grep -q "ok"; then
    echo "❌ API недоступен. Убедитесь, что сервис запущен."
    echo "💡 Запустите сервис командой: make dev"
    exit 1
fi

echo "✅ API доступен"

# Получение поддерживаемых форматов
echo "Получение поддерживаемых форматов..."
if curl -s "$API_URL/v1/supported-formats" | jq . > "$TESTS_DIR/supported_formats.json" 2>/dev/null; then
    echo "✅ Поддерживаемые форматы сохранены в supported_formats.json"
else
    echo "⚠️ jq не установлен, пропускаем сохранение форматов"
fi

# Очистка предыдущих результатов тестов
echo "Очистка предыдущих результатов тестов..."
rm -f "$TESTS_DIR"/*.ok.txt "$TESTS_DIR"/*.err.txt

# Тестирование файлов
echo "Тестирование файлов из директории $TESTS_DIR..."

total_files=0
success_count=0
error_count=0

for file in "$TESTS_DIR"/*; do
    if [[ -f "$file" ]]; then
        filename=$(basename "$file")
        
        # Пропускаем служебные файлы
        if [[ "$filename" == "supported_formats.json" || "$filename" == *.ok.txt || "$filename" == *.err.txt ]]; then
            continue
        fi
        
        total_files=$((total_files + 1))
        
        echo "Тестирование: $filename"
        
        # Отправка файла на обработку с сохранением в временный файл
        temp_response=$(mktemp)
        http_code=$(curl -s -w "%{http_code}" -X POST \
            -F "file=@$file" \
            "$API_URL/v1/extract/file" \
            --output "$temp_response")
        
        # Чтение содержимого ответа
        body=$(cat "$temp_response")
        rm -f "$temp_response"
        
        if [[ "$http_code" -eq 200 ]]; then
            # Успешная обработка - сохраняем текст согласно ТЗ
            if command -v jq >/dev/null 2>&1; then
                echo "$body" | jq -r '.text' > "$TESTS_DIR/${filename}.ok.txt"
            else
                # Если jq нет, извлекаем текст простым способом (без sed для совместимости)
                echo "$body" > "$TESTS_DIR/${filename}.ok.txt"
            fi
            echo "✅ $filename - обработан успешно"
            success_count=$((success_count + 1))
        else
            # Ошибка обработки - сохраняем ошибку согласно ТЗ
            echo "$body" > "$TESTS_DIR/${filename}.err.txt"
            echo "❌ $filename - ошибка (HTTP $http_code)"
            error_count=$((error_count + 1))
        fi
    fi
done

echo ""
echo "=== Результаты тестирования ==="
echo "Всего файлов: $total_files"
echo "Успешно: $success_count"
echo "Ошибок: $error_count"

# Проверка покрытия поддерживаемых форматов
echo ""
echo "=== Проверка покрытия форматов ==="

if [[ -f "$TESTS_DIR/supported_formats.json" ]] && command -v jq >/dev/null 2>&1; then
    # Извлекаем все поддерживаемые расширения из API (из всех категорий)
    supported_extensions=($(jq -r '.[] | .[]' "$TESTS_DIR/supported_formats.json" 2>/dev/null | sort -u))
    
    # Собираем расширения всех тестовых файлов
    tested_extensions=()
    for file in "$TESTS_DIR"/*; do
        if [[ -f "$file" ]]; then
            filename=$(basename "$file")
            
            # Пропускаем служебные файлы
            if [[ "$filename" == "supported_formats.json" || "$filename" == *.ok.txt || "$filename" == *.err.txt ]]; then
                continue
            fi
            
            # Извлекаем расширение (может быть составным, например .image.pdf)
            if [[ "$filename" == *.* ]]; then
                extension="${filename##*.}"
                tested_extensions+=("$extension")
            fi
        fi
    done
    
    # Убираем дубликаты и сортируем
    tested_extensions=($(printf '%s\n' "${tested_extensions[@]}" | sort -u))
    
    # Находим непокрытые форматы
    uncovered_extensions=()
    for ext in "${supported_extensions[@]}"; do
        found=false
        for tested_ext in "${tested_extensions[@]}"; do
            if [[ "$ext" == "$tested_ext" ]]; then
                found=true
                break
            fi
        done
        if [[ "$found" == false ]]; then
            uncovered_extensions+=("$ext")
        fi
    done
    
    # Вычисляем процент покрытия
    if [[ ${#supported_extensions[@]} -gt 0 ]]; then
        covered_count=$(( ${#supported_extensions[@]} - ${#uncovered_extensions[@]} ))
        coverage_percent=$(( covered_count * 100 / ${#supported_extensions[@]} ))
    else
        coverage_percent=0
    fi
    
    echo "📊 Поддерживаемые форматы: ${#supported_extensions[@]}"
    echo "🧪 Протестированные форматы: ${#tested_extensions[@]}"
    echo "📈 Покрытие тестами: ${coverage_percent}%"
    
    if [[ ${#uncovered_extensions[@]} -eq 0 ]]; then
        echo "✅ Все поддерживаемые форматы покрыты тестами!"
    else
        echo "⚠️  Непокрытые форматы (${#uncovered_extensions[@]}):"
        for ext in "${uncovered_extensions[@]}"; do
            # Получаем категорию формата из API ответа
            category=$(jq -r --arg ext "$ext" 'to_entries[] | select(.value[] == $ext) | .key' "$TESTS_DIR/supported_formats.json" 2>/dev/null | head -1)
            if [[ -n "$category" && "$category" != "null" ]]; then
                echo "  🔸 .$ext ($category)"
            else
                echo "  🔸 .$ext"
            fi
        done
        echo ""
        echo "💡 Рекомендация: добавьте тестовые файлы для непокрытых форматов"
    fi
else
    echo "⚠️ Не удается проверить покрытие форматов (требуется jq и supported_formats.json)"
fi

echo ""
echo "📁 Результаты сохранены в папке tests/:"
if [[ $success_count -gt 0 ]]; then
    echo "  ✅ Успешные: tests/*.ok.txt"
fi
if [[ $error_count -gt 0 ]]; then
    echo "  ❌ Ошибки: tests/*.err.txt"
fi

if [[ $error_count -eq 0 ]]; then
    echo ""
    echo "🎉 Все тесты пройдены успешно!"
    exit 0
else
    echo ""
    echo "⚠️ Есть ошибки в тестах. Проверьте файлы *.err.txt в папке tests/"
    exit 1
fi 