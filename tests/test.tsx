/**
 * Тестовый TypeScript React файл для проверки извлечения текста
 * Демонстрирует React компоненты с TypeScript
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

// Интерфейсы и типы
interface TextExtractionResult {
    text: string;
    wordCount: number;
    characterCount: number;
    language: string;
    confidence: number;
}

interface FileUploadProps {
    onFileUpload: (file: File) => void;
    acceptedTypes: string[];
    maxSize: number;
    disabled?: boolean;
}

interface ProcessingStatusProps {
    isProcessing: boolean;
    progress: number;
    error?: string;
}

// Компонент для загрузки файлов
const FileUpload: React.FC<FileUploadProps> = ({ 
    onFileUpload, 
    acceptedTypes, 
    maxSize, 
    disabled = false 
}) => {
    const { t } = useTranslation();
    const [dragActive, setDragActive] = useState(false);

    const handleDrag = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === 'dragenter' || e.type === 'dragover') {
            setDragActive(true);
        } else if (e.type === 'dragleave') {
            setDragActive(false);
        }
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        
        if (disabled) return;

        const files = e.dataTransfer.files;
        if (files && files[0]) {
            onFileUpload(files[0]);
        }
    }, [disabled, onFileUpload]);

    const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (files && files[0]) {
            onFileUpload(files[0]);
        }
    }, [onFileUpload]);

    return (
        <div
            className={`upload-area ${dragActive ? 'drag-active' : ''} ${disabled ? 'disabled' : ''}`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
        >
            <div className="upload-content">
                <svg className="upload-icon" viewBox="0 0 24 24">
                    <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
                </svg>
                <h3>{t('upload.title')}</h3>
                <p>{t('upload.description')}</p>
                <input
                    type="file"
                    accept={acceptedTypes.join(',')}
                    onChange={handleFileSelect}
                    disabled={disabled}
                    className="file-input"
                />
                <button type="button" disabled={disabled} className="upload-button">
                    {t('upload.button')}
                </button>
            </div>
        </div>
    );
};

// Компонент статуса обработки
const ProcessingStatus: React.FC<ProcessingStatusProps> = ({ 
    isProcessing, 
    progress, 
    error 
}) => {
    const { t } = useTranslation();

    if (error) {
        return (
            <div className="status-error">
                <svg className="error-icon" viewBox="0 0 24 24">
                    <path d="M13,13H11V7H13M13,17H11V15H13M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2Z" />
                </svg>
                <span>{t('processing.error')}: {error}</span>
            </div>
        );
    }

    if (isProcessing) {
        return (
            <div className="status-processing">
                <div className="progress-bar">
                    <div 
                        className="progress-fill" 
                        style={{ width: `${progress}%` }}
                    />
                </div>
                <span>{t('processing.inProgress')} ({progress}%)</span>
            </div>
        );
    }

    return null;
};

// Главный компонент приложения
const TextExtractionApp: React.FC = () => {
    const { t } = useTranslation();
    const [file, setFile] = useState<File | null>(null);
    const [result, setResult] = useState<TextExtractionResult | null>(null);
    const [isProcessing, setIsProcessing] = useState(false);
    const [progress, setProgress] = useState(0);
    const [error, setError] = useState<string | null>(null);

    const supportedTypes = [
        '.pdf', '.docx', '.doc', '.txt', '.html', '.md',
        '.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.gif',
        '.py', '.js', '.ts', '.java', '.cpp', '.bsl', '.os'
    ];

    const maxFileSize = 20 * 1024 * 1024; // 20MB

    const handleFileUpload = useCallback(async (uploadedFile: File) => {
        if (uploadedFile.size > maxFileSize) {
            setError(t('errors.fileSize'));
            return;
        }

        setFile(uploadedFile);
        setError(null);
        setIsProcessing(true);
        setProgress(0);

        try {
            const formData = new FormData();
            formData.append('file', uploadedFile);

            // Имитация прогресса
            const progressInterval = setInterval(() => {
                setProgress(prev => Math.min(prev + 10, 90));
            }, 200);

            const response = await fetch('/v1/extract-text/', {
                method: 'POST',
                body: formData,
            });

            clearInterval(progressInterval);
            setProgress(100);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            setResult(data);
            
        } catch (err) {
            setError(err instanceof Error ? err.message : t('errors.unknown'));
        } finally {
            setIsProcessing(false);
        }
    }, [maxFileSize, t]);

    return (
        <div className="app">
            <header className="app-header">
                <h1>{t('app.title')}</h1>
                <p>{t('app.description')}</p>
            </header>

            <main className="app-main">
                <FileUpload
                    onFileUpload={handleFileUpload}
                    acceptedTypes={supportedTypes}
                    maxSize={maxFileSize}
                    disabled={isProcessing}
                />

                <ProcessingStatus
                    isProcessing={isProcessing}
                    progress={progress}
                    error={error}
                />

                {result && (
                    <div className="result-section">
                        <h2>{t('result.title')}</h2>
                        <div className="result-stats">
                            <div className="stat">
                                <span className="stat-label">{t('result.wordCount')}</span>
                                <span className="stat-value">{result.wordCount}</span>
                            </div>
                            <div className="stat">
                                <span className="stat-label">{t('result.characterCount')}</span>
                                <span className="stat-value">{result.characterCount}</span>
                            </div>
                            <div className="stat">
                                <span className="stat-label">{t('result.language')}</span>
                                <span className="stat-value">{result.language}</span>
                            </div>
                            <div className="stat">
                                <span className="stat-label">{t('result.confidence')}</span>
                                <span className="stat-value">{Math.round(result.confidence * 100)}%</span>
                            </div>
                        </div>
                        <div className="result-text">
                            <h3>{t('result.extractedText')}</h3>
                            <pre>{result.text}</pre>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
};

export default TextExtractionApp; 