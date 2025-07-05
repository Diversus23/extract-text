/**
 * Тестовый файл JavaScript для проверки извлечения текста из исходного кода
 */

const fs = require('fs');
const path = require('path');

class TextAnalyzer {
    constructor(options = {}) {
        this.language = options.language || 'en';
        this.caseSensitive = options.caseSensitive || false;
        this.processedWords = new Set();
    }

    /**
     * Анализирует текст и возвращает статистику
     * @param {string} text - Входной текст для анализа
     * @returns {Object} Объект со статистикой
     */
    analyzeText(text) {
        if (!text || typeof text !== 'string') {
            return { error: 'Invalid text input' };
        }

        // Разделение на слова
        const words = text.toLowerCase().split(/\s+/);
        const wordCount = words.length;
        const uniqueWords = new Set(words);

        // Сохранение обработанных слов
        words.forEach(word => this.processedWords.add(word));

        return {
            totalWords: wordCount,
            uniqueWords: uniqueWords.size,
            averageWordLength: this.calculateAverageWordLength(words),
            language: this.language,
            timestamp: new Date().toISOString()
        };
    }

    /**
     * Вычисляет среднюю длину слова
     * @param {Array} words - Массив слов
     * @returns {number} Средняя длина слова
     */
    calculateAverageWordLength(words) {
        if (words.length === 0) return 0;
        
        const totalLength = words.reduce((sum, word) => sum + word.length, 0);
        return Math.round((totalLength / words.length) * 100) / 100;
    }

    /**
     * Получает все обработанные слова
     * @returns {Array} Массив уникальных слов
     */
    getProcessedWords() {
        return Array.from(this.processedWords);
    }

    /**
     * Очищает кэш обработанных слов
     */
    clearCache() {
        this.processedWords.clear();
    }
}

// Основная функция для тестирования
function main() {
    console.log('=== Тестирование TextAnalyzer ===');
    
    const analyzer = new TextAnalyzer({ language: 'ru' });
    
    // Тестовые тексты
    const testTexts = [
        'Привет, мир! Это тестовый текст.',
        'Hello, World! This is a test text.',
        'Анализ текста на русском и английском языках'
    ];

    testTexts.forEach((text, index) => {
        console.log(`\nТест ${index + 1}:`);
        console.log(`Текст: "${text}"`);
        
        const result = analyzer.analyzeText(text);
        console.log('Результат анализа:', JSON.stringify(result, null, 2));
    });

    // Показать все обработанные слова
    console.log('\nВсе обработанные слова:');
    console.log(analyzer.getProcessedWords());
}

// Запуск, если файл выполняется напрямую
if (require.main === module) {
    main();
}

module.exports = TextAnalyzer; 