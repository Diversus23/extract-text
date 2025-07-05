/**
 * Тестовый файл Java для проверки извлечения текста из исходного кода
 * 
 * @author Test Author
 * @version 1.0
 */

import java.util.*;
import java.util.stream.Collectors;

public class TextProcessor {
    
    private final String language;
    private final boolean caseSensitive;
    private final Map<String, Integer> wordFrequency;
    
    /**
     * Конструктор класса TextProcessor
     * 
     * @param language Язык обработки текста
     * @param caseSensitive Учитывать ли регистр символов
     */
    public TextProcessor(String language, boolean caseSensitive) {
        this.language = language;
        this.caseSensitive = caseSensitive;
        this.wordFrequency = new HashMap<>();
    }
    
    /**
     * Конструктор по умолчанию
     */
    public TextProcessor() {
        this("ru", false);
    }
    
    /**
     * Обрабатывает входной текст и подсчитывает частоту слов
     * 
     * @param text Входной текст для обработки
     * @return Результат обработки текста
     */
    public ProcessingResult processText(String text) {
        if (text == null || text.trim().isEmpty()) {
            return new ProcessingResult("Пустой текст", 0, Collections.emptyMap());
        }
        
        // Подготовка текста
        String processedText = caseSensitive ? text : text.toLowerCase();
        
        // Разделение на слова
        String[] words = processedText.split("\\s+");
        
        // Подсчёт частоты слов
        for (String word : words) {
            // Очистка от знаков препинания
            String cleanWord = word.replaceAll("[^\\w\\u0400-\\u04FF]", "");
            if (!cleanWord.isEmpty()) {
                wordFrequency.merge(cleanWord, 1, Integer::sum);
            }
        }
        
        return new ProcessingResult(
            "Текст обработан успешно",
            words.length,
            new HashMap<>(wordFrequency)
        );
    }
    
    /**
     * Получает наиболее часто встречающиеся слова
     * 
     * @param limit Максимальное количество слов
     * @return Список наиболее частых слов
     */
    public List<Map.Entry<String, Integer>> getTopWords(int limit) {
        return wordFrequency.entrySet()
            .stream()
            .sorted(Map.Entry.<String, Integer>comparingByValue().reversed())
            .limit(limit)
            .collect(Collectors.toList());
    }
    
    /**
     * Очищает статистику обработки
     */
    public void clearStatistics() {
        wordFrequency.clear();
    }
    
    /**
     * Получает текущий язык обработки
     * 
     * @return Язык обработки
     */
    public String getLanguage() {
        return language;
    }
    
    /**
     * Класс для хранения результата обработки текста
     */
    public static class ProcessingResult {
        private final String message;
        private final int wordCount;
        private final Map<String, Integer> wordFrequency;
        
        public ProcessingResult(String message, int wordCount, Map<String, Integer> wordFrequency) {
            this.message = message;
            this.wordCount = wordCount;
            this.wordFrequency = wordFrequency;
        }
        
        public String getMessage() { return message; }
        public int getWordCount() { return wordCount; }
        public Map<String, Integer> getWordFrequency() { return wordFrequency; }
        
        @Override
        public String toString() {
            return String.format("ProcessingResult{message='%s', wordCount=%d, uniqueWords=%d}", 
                message, wordCount, wordFrequency.size());
        }
    }
    
    /**
     * Основной метод для тестирования функциональности
     * 
     * @param args Аргументы командной строки
     */
    public static void main(String[] args) {
        System.out.println("=== Тестирование TextProcessor ===");
        
        TextProcessor processor = new TextProcessor("ru", false);
        
        // Тестовые тексты
        String[] testTexts = {
            "Привет, мир! Это тестовый текст для обработки на Java.",
            "Hello, World! This is a test text for Java processing.",
            "Анализ текста Java приложением с подсчётом частоты слов"
        };
        
        for (int i = 0; i < testTexts.length; i++) {
            System.out.println("\nТест " + (i + 1) + ":");
            System.out.println("Текст: \"" + testTexts[i] + "\"");
            
            ProcessingResult result = processor.processText(testTexts[i]);
            System.out.println("Результат: " + result);
        }
        
        // Показать топ-10 наиболее частых слов
        System.out.println("\nТоп-10 наиболее частых слов:");
        List<Map.Entry<String, Integer>> topWords = processor.getTopWords(10);
        topWords.forEach(entry -> 
            System.out.println(entry.getKey() + ": " + entry.getValue())
        );
    }
} 