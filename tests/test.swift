/**
 * Тестовый Swift файл для проверки извлечения текста
 * Демонстрирует основные возможности языка Swift
 */

import Foundation
import Combine

// MARK: - Протоколы

protocol TextProcessor {
    var name: String { get }
    var version: String { get }
    
    func process(_ text: String) async throws -> ProcessingResult
    func processAsync(_ text: String, completion: @escaping (Result<ProcessingResult, Error>) -> Void)
}

protocol TextAnalyzer {
    func analyze(_ text: String) -> TextAnalysis
}

// MARK: - Структуры и классы

struct ProcessingResult {
    let originalText: String
    let processedText: String
    let wordCount: Int
    let characterCount: Int
    let language: String
    let confidence: Double
    let processingTime: TimeInterval
    
    var statistics: String {
        """
        Статистика обработки:
        - Слов: \(wordCount)
        - Символов: \(characterCount)
        - Язык: \(language)
        - Уверенность: \(String(format: "%.2f%%", confidence * 100))
        - Время обработки: \(String(format: "%.3f", processingTime))с
        """
    }
}

struct TextAnalysis {
    let sentenceCount: Int
    let paragraphCount: Int
    let averageWordLength: Double
    let readabilityScore: Double
    
    var description: String {
        """
        Анализ текста:
        - Предложений: \(sentenceCount)
        - Абзацев: \(paragraphCount)
        - Средняя длина слова: \(String(format: "%.1f", averageWordLength))
        - Читаемость: \(String(format: "%.2f", readabilityScore))
        """
    }
}

// MARK: - Перечисления

enum SupportedLanguage: String, CaseIterable {
    case russian = "ru"
    case english = "en"
    case german = "de"
    case french = "fr"
    case spanish = "es"
    
    var displayName: String {
        switch self {
        case .russian: return "Русский"
        case .english: return "English"
        case .german: return "Deutsch"
        case .french: return "Français"
        case .spanish: return "Español"
        }
    }
}

enum ProcessingError: Error, LocalizedError {
    case emptyText
    case invalidEncoding
    case processingFailed(String)
    case timeout
    
    var errorDescription: String? {
        switch self {
        case .emptyText:
            return "Текст не может быть пустым"
        case .invalidEncoding:
            return "Неверная кодировка текста"
        case .processingFailed(let message):
            return "Ошибка обработки: \(message)"
        case .timeout:
            return "Превышено время ожидания"
        }
    }
}

// MARK: - Основной класс

class AdvancedTextProcessor: TextProcessor, TextAnalyzer {
    
    // MARK: - Свойства
    
    let name: String
    let version: String
    private let processingQueue = DispatchQueue(label: "text.processing", qos: .userInitiated)
    private let cancellables = Set<AnyCancellable>()
    
    // Computed properties
    var supportedLanguages: [SupportedLanguage] {
        return SupportedLanguage.allCases
    }
    
    var isProcessing: Bool {
        return _isProcessing
    }
    
    // Private properties
    private var _isProcessing = false
    private let timeout: TimeInterval = 30.0
    
    // MARK: - Инициализация
    
    init(name: String = "Advanced Text Processor", version: String = "1.0.0") {
        self.name = name
        self.version = version
    }
    
    // MARK: - Публичные методы
    
    func process(_ text: String) async throws -> ProcessingResult {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw ProcessingError.emptyText
        }
        
        let startTime = Date()
        _isProcessing = true
        
        defer {
            _isProcessing = false
        }
        
        do {
            // Нормализация текста
            let normalizedText = normalizeText(text)
            
            // Определение языка
            let language = await detectLanguage(normalizedText)
            
            // Обработка текста
            let processedText = await processText(normalizedText, language: language)
            
            // Подсчет статистики
            let wordCount = countWords(in: processedText)
            let characterCount = processedText.count
            
            // Вычисление уверенности
            let confidence = calculateConfidence(for: processedText, language: language)
            
            let processingTime = Date().timeIntervalSince(startTime)
            
            return ProcessingResult(
                originalText: text,
                processedText: processedText,
                wordCount: wordCount,
                characterCount: characterCount,
                language: language.displayName,
                confidence: confidence,
                processingTime: processingTime
            )
            
        } catch {
            throw ProcessingError.processingFailed(error.localizedDescription)
        }
    }
    
    func processAsync(_ text: String, completion: @escaping (Result<ProcessingResult, Error>) -> Void) {
        Task {
            do {
                let result = try await process(text)
                completion(.success(result))
            } catch {
                completion(.failure(error))
            }
        }
    }
    
    func analyze(_ text: String) -> TextAnalysis {
        let sentences = text.components(separatedBy: CharacterSet(charactersIn: ".!?"))
            .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        
        let paragraphs = text.components(separatedBy: "\n\n")
            .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        
        let words = text.components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
        
        let averageWordLength = words.isEmpty ? 0.0 : 
            Double(words.reduce(0) { $0 + $1.count }) / Double(words.count)
        
        let readabilityScore = calculateReadabilityScore(
            sentences: sentences.count,
            words: words.count,
            averageWordLength: averageWordLength
        )
        
        return TextAnalysis(
            sentenceCount: sentences.count,
            paragraphCount: paragraphs.count,
            averageWordLength: averageWordLength,
            readabilityScore: readabilityScore
        )
    }
    
    // MARK: - Приватные методы
    
    private func normalizeText(_ text: String) -> String {
        return text
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
    }
    
    private func detectLanguage(_ text: String) async -> SupportedLanguage {
        // Простая эвристика определения языка
        let patterns: [SupportedLanguage: String] = [
            .russian: "[а-яё]",
            .english: "[a-z]",
            .german: "[äöüß]",
            .french: "[àâäéèêëïîôöùûüÿ]",
            .spanish: "[ñáéíóúü]"
        ]
        
        for (language, pattern) in patterns {
            if text.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil {
                return language
            }
        }
        
        return .english // По умолчанию
    }
    
    private func processText(_ text: String, language: SupportedLanguage) async -> String {
        // Имитация асинхронной обработки
        try? await Task.sleep(nanoseconds: 100_000_000) // 0.1 секунды
        
        return "[\(language.rawValue.uppercased())] \(text)"
    }
    
    private func countWords(in text: String) -> Int {
        return text.components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .count
    }
    
    private func calculateConfidence(for text: String, language: SupportedLanguage) -> Double {
        let baseConfidence = 0.8
        let lengthFactor = min(Double(text.count) / 1000.0, 1.0) * 0.2
        return min(baseConfidence + lengthFactor, 1.0)
    }
    
    private func calculateReadabilityScore(sentences: Int, words: Int, averageWordLength: Double) -> Double {
        guard sentences > 0 && words > 0 else { return 0.0 }
        
        let avgSentenceLength = Double(words) / Double(sentences)
        let score = 206.835 - 1.015 * avgSentenceLength - 84.6 * (averageWordLength / 4.7)
        
        return max(0.0, min(100.0, score))
    }
}

// MARK: - Расширения

extension String {
    var wordCount: Int {
        return self.components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .count
    }
    
    var characterCountWithoutSpaces: Int {
        return self.replacingOccurrences(of: " ", with: "").count
    }
}

// MARK: - Пример использования

func demonstrateTextProcessing() {
    let processor = AdvancedTextProcessor()
    
    let sampleText = """
    Это тестовый текст для демонстрации обработки в Swift.
    Система извлечения текста поддерживает множество форматов файлов.
    Swift - мощный язык программирования от Apple.
    """
    
    print("Начинаем обработку текста...")
    
    // Асинхронная обработка
    Task {
        do {
            let result = try await processor.process(sampleText)
            print(result.statistics)
            
            let analysis = processor.analyze(sampleText)
            print(analysis.description)
            
        } catch {
            print("Ошибка: \(error.localizedDescription)")
        }
    }
} 