-- Тестовый SQL файл для проверки извлечения текста из исходного кода
-- Этот файл содержит различные SQL команды для тестирования

-- Создание базы данных
CREATE DATABASE text_extraction_db
    WITH 
    OWNER = textuser
    ENCODING = 'UTF8'
    LC_COLLATE = 'ru_RU.UTF-8'
    LC_CTYPE = 'ru_RU.UTF-8'
    TABLESPACE = pg_default
    CONNECTION LIMIT = -1;

-- Использование базы данных
USE text_extraction_db;

-- Создание таблицы для хранения файлов
CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_size INTEGER NOT NULL,
    content_hash VARCHAR(64) UNIQUE NOT NULL,
    extracted_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- Индексы для быстрого поиска
    INDEX idx_filename (filename),
    INDEX idx_file_type (file_type),
    INDEX idx_created_at (created_at),
    INDEX idx_content_hash (content_hash)
);

-- Создание таблицы для статистики обработки
CREATE TABLE processing_stats (
    id SERIAL PRIMARY KEY,
    file_id INTEGER NOT NULL,
    processing_time_ms INTEGER NOT NULL,
    word_count INTEGER DEFAULT 0,
    character_count INTEGER DEFAULT 0,
    language_detected VARCHAR(10),
    ocr_used BOOLEAN DEFAULT FALSE,
    error_message TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Внешний ключ
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    
    -- Индексы
    INDEX idx_file_id (file_id),
    INDEX idx_processed_at (processed_at)
);

-- Создание таблицы для поддерживаемых форматов
CREATE TABLE supported_formats (
    id SERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    extension VARCHAR(10) NOT NULL,
    mime_type VARCHAR(100),
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Уникальное ограничение
    UNIQUE KEY unique_extension (extension),
    
    -- Индексы
    INDEX idx_category (category),
    INDEX idx_extension (extension)
);

-- Вставка данных о поддерживаемых форматах
INSERT INTO supported_formats (category, extension, mime_type, description) VALUES
-- Документы
('documents', 'pdf', 'application/pdf', 'Portable Document Format'),
('documents', 'docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'Microsoft Word Document'),
('documents', 'doc', 'application/msword', 'Microsoft Word Document (Legacy)'),
('documents', 'rtf', 'application/rtf', 'Rich Text Format'),
('documents', 'odt', 'application/vnd.oasis.opendocument.text', 'OpenDocument Text'),

-- Изображения
('images_ocr', 'jpg', 'image/jpeg', 'JPEG Image'),
('images_ocr', 'jpeg', 'image/jpeg', 'JPEG Image'),
('images_ocr', 'png', 'image/png', 'PNG Image'),
('images_ocr', 'tiff', 'image/tiff', 'TIFF Image'),
('images_ocr', 'bmp', 'image/bmp', 'Bitmap Image'),
('images_ocr', 'gif', 'image/gif', 'GIF Image'),

-- Исходный код
('source_code', 'py', 'text/x-python', 'Python Source Code'),
('source_code', 'js', 'application/javascript', 'JavaScript Source Code'),
('source_code', 'java', 'text/x-java-source', 'Java Source Code'),
('source_code', 'cpp', 'text/x-c++src', 'C++ Source Code'),
('source_code', 'sql', 'application/sql', 'SQL Script'),
('source_code', 'toml', 'application/toml', 'TOML Configuration'),

-- Прочие форматы
('other', 'txt', 'text/plain', 'Plain Text'),
('other', 'html', 'text/html', 'HTML Document'),
('other', 'md', 'text/markdown', 'Markdown Document'),
('structured_data', 'json', 'application/json', 'JSON Data'),
('structured_data', 'xml', 'application/xml', 'XML Data'),
('structured_data', 'yaml', 'application/x-yaml', 'YAML Data');

-- Создание представления для статистики
CREATE VIEW file_processing_summary AS
SELECT 
    f.filename,
    f.file_type,
    f.file_size,
    ps.processing_time_ms,
    ps.word_count,
    ps.character_count,
    ps.language_detected,
    ps.ocr_used,
    ps.processed_at
FROM files f
LEFT JOIN processing_stats ps ON f.id = ps.file_id
ORDER BY ps.processed_at DESC;

-- Создание хранимой процедуры для обновления статистики
DELIMITER //
CREATE PROCEDURE UpdateFileStats(
    IN p_file_id INTEGER,
    IN p_processing_time INTEGER,
    IN p_word_count INTEGER,
    IN p_character_count INTEGER,
    IN p_language VARCHAR(10),
    IN p_ocr_used BOOLEAN
)
BEGIN
    INSERT INTO processing_stats (
        file_id, processing_time_ms, word_count, 
        character_count, language_detected, ocr_used
    ) VALUES (
        p_file_id, p_processing_time, p_word_count,
        p_character_count, p_language, p_ocr_used
    );
    
    -- Обновление времени изменения файла
    UPDATE files 
    SET updated_at = CURRENT_TIMESTAMP 
    WHERE id = p_file_id;
END //
DELIMITER ;

-- Запросы для аналитики
-- Топ-10 наиболее обрабатываемых типов файлов
SELECT 
    file_type,
    COUNT(*) as file_count,
    AVG(processing_time_ms) as avg_processing_time,
    AVG(word_count) as avg_word_count
FROM file_processing_summary
GROUP BY file_type
ORDER BY file_count DESC
LIMIT 10;

-- Статистика по языкам
SELECT 
    language_detected,
    COUNT(*) as count,
    AVG(processing_time_ms) as avg_time
FROM processing_stats
WHERE language_detected IS NOT NULL
GROUP BY language_detected
ORDER BY count DESC;

-- Файлы, обработанные с использованием OCR
SELECT 
    filename,
    file_type,
    processing_time_ms,
    word_count
FROM file_processing_summary
WHERE ocr_used = TRUE
ORDER BY processing_time_ms DESC;

-- Очистка старых записей (старше 30 дней)
DELETE FROM processing_stats 
WHERE processed_at < DATE_SUB(NOW(), INTERVAL 30 DAY);

-- Создание триггера для автоматического обновления updated_at
CREATE TRIGGER update_files_timestamp
    BEFORE UPDATE ON files
    FOR EACH ROW
    SET NEW.updated_at = CURRENT_TIMESTAMP; 