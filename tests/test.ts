/**
 * Тестовый TypeScript файл для проверки извлечения текста
 * Демонстрирует основные возможности TypeScript
 */

// Интерфейсы и типы
interface TextProcessor {
    id: string;
    name: string;
    version: string;
    process(text: string): Promise<ProcessResult>;
}

interface ProcessResult {
    processedText: string;
    wordCount: number;
    characterCount: number;
    language: string;
    confidence: number;
}

type SupportedLanguage = 'ru' | 'en' | 'de' | 'fr' | 'es';
type ProcessingMode = 'fast' | 'accurate' | 'comprehensive';

// Класс для обработки текста
class AdvancedTextProcessor implements TextProcessor {
    public readonly id: string;
    public readonly name: string;
    public readonly version: string;
    private readonly supportedLanguages: SupportedLanguage[];
    private processingMode: ProcessingMode;

    constructor(
        id: string,
        name: string = 'Advanced Text Processor',
        version: string = '1.0.0'
    ) {
        this.id = id;
        this.name = name;
        this.version = version;
        this.supportedLanguages = ['ru', 'en', 'de', 'fr', 'es'];
        this.processingMode = 'accurate';
    }

    // Основной метод обработки текста
    public async process(text: string): Promise<ProcessResult> {
        if (!text || text.trim().length === 0) {
            throw new Error('Текст не может быть пустым');
        }

        const startTime = Date.now();
        
        try {
            // Предварительная обработка
            const normalizedText = this.normalizeText(text);
            
            // Определение языка
            const language = await this.detectLanguage(normalizedText);
            
            // Обработка текста
            const processedText = await this.processText(normalizedText, language);
            
            // Подсчет статистики
            const wordCount = this.countWords(processedText);
            const characterCount = processedText.length;
            
            // Вычисление уверенности
            const confidence = this.calculateConfidence(processedText, language);
            
            const processingTime = Date.now() - startTime;
            
            console.log(`Обработка завершена за ${processingTime}мс`);
            
            return {
                processedText,
                wordCount,
                characterCount,
                language,
                confidence
            };
            
        } catch (error) {
            console.error('Ошибка при обработке текста:', error);
            throw error;
        }
    }

    // Приватные методы
    private normalizeText(text: string): string {
        return text
            .replace(/\s+/g, ' ')
            .trim()
            .toLowerCase();
    }

    private async detectLanguage(text: string): Promise<SupportedLanguage> {
        // Простая эвристика определения языка
        const patterns = {
            'ru': /[а-я]/i,
            'en': /[a-z]/i,
            'de': /[äöüß]/i,
            'fr': /[àâäéèêëïîôöùûüÿ]/i,
            'es': /[ñáéíóúü]/i
        };

        for (const [lang, pattern] of Object.entries(patterns)) {
            if (pattern.test(text)) {
                return lang as SupportedLanguage;
            }
        }

        return 'en'; // По умолчанию
    }

    private async processText(text: string, language: SupportedLanguage): Promise<string> {
        // Имитация асинхронной обработки
        return new Promise((resolve) => {
            setTimeout(() => {
                resolve(`[${language.toUpperCase()}] ${text}`);
            }, 100);
        });
    }

    private countWords(text: string): number {
        return text.split(/\s+/).filter(word => word.length > 0).length;
    }

    private calculateConfidence(text: string, language: SupportedLanguage): number {
        // Простое вычисление уверенности
        const baseConfidence = 0.8;
        const lengthFactor = Math.min(text.length / 1000, 1) * 0.2;
        return Math.min(baseConfidence + lengthFactor, 1.0);
    }

    // Геттеры и сеттеры
    public get mode(): ProcessingMode {
        return this.processingMode;
    }

    public set mode(mode: ProcessingMode) {
        this.processingMode = mode;
    }
}

// Экспорт
export { AdvancedTextProcessor, TextProcessor, ProcessResult, SupportedLanguage };
export default AdvancedTextProcessor; 