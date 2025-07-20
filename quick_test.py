#!/usr/bin/env python3
"""
Быстрый тест API для извлечения текста
"""

import requests
import json
import os
import sys

API_URL = "http://localhost:7555"

def test_api():
    """Тестирование основных эндпоинтов API"""
    
    print("=== Тестирование Text Extraction API ===")
    
    # Тест 1: Проверка health
    print("\n1. Проверка health...")
    try:
        response = requests.get(f"{API_URL}/health")
        if response.status_code == 200:
            print("✅ Health check OK")
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ API недоступен: {e}")
        return False
    
    # Тест 2: Информация о API
    print("\n2. Информация о API...")
    try:
        response = requests.get(f"{API_URL}/")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API Name: {data.get('api_name')}")
            print(f"✅ Version: {data.get('version')}")
        else:
            print(f"❌ API info failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error getting API info: {e}")
    
    # Тест 3: Поддерживаемые форматы
    print("\n3. Поддерживаемые форматы...")
    try:
        response = requests.get(f"{API_URL}/v1/supported-formats")
        if response.status_code == 200:
            data = response.json()
            print("✅ Поддерживаемые форматы:")
            for category, formats in data.items():
                print(f"  {category}: {', '.join(formats)}")
        else:
            print(f"❌ Formats failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error getting formats: {e}")
    
    # Тест 4: Извлечение текста из простого файла
    print("\n4. Тестирование извлечения текста...")
    test_file = "tests/text.txt"
    
    if os.path.exists(test_file):
        try:
            with open(test_file, 'rb') as f:
                files = {'file': f}
                response = requests.post(f"{API_URL}/v1/extract/file", files=files)
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ Файл обработан: {data.get('filename')}")
                    print(f"✅ Извлечено символов: {len(data.get('text', ''))}")
                    print(f"✅ Первые 100 символов: {data.get('text', '')[:100]}...")
                else:
                    print(f"❌ Extract failed: {response.status_code}")
                    print(f"Response: {response.text}")
        except Exception as e:
            print(f"❌ Error extracting text: {e}")
    else:
        print(f"❌ Test file {test_file} not found")
    
    print("\n=== Тестирование завершено ===")
    return True

if __name__ == "__main__":
    success = test_api()
    sys.exit(0 if success else 1) 