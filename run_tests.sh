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
curl -s "$API_URL/v1/supported-formats/" | jq . > "$TESTS_DIR/supported_formats.json" 2>/dev/null || echo "⚠️ jq не установлен, пропускаем сохранение форматов"

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
            "$API_URL/v1/extract/" \
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