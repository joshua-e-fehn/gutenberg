-- Gutenberg Audiobook Pipeline Database Schema
-- PostgreSQL 15+ compatible

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Books table - tracks individual books
CREATE TABLE books (
    book_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    gutenberg_id INTEGER UNIQUE, -- Project Gutenberg book ID
    title VARCHAR(500) NOT NULL,
    author VARCHAR(200),
    language VARCHAR(10) DEFAULT 'en',
    source_url TEXT,
    raw_s3_key TEXT, -- S3 path to raw book content
    metadata JSONB, -- Additional book metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Book processing status tracking
CREATE TABLE book_processing (
    book_id UUID PRIMARY KEY REFERENCES books(book_id) ON DELETE CASCADE,
    scrape_status VARCHAR(50) DEFAULT 'pending', -- pending, in_progress, complete, failed
    scrape_started_at TIMESTAMP WITH TIME ZONE,
    scrape_completed_at TIMESTAMP WITH TIME ZONE,
    scrape_error TEXT,
    
    parse_status VARCHAR(50) DEFAULT 'pending',
    parse_started_at TIMESTAMP WITH TIME ZONE,
    parse_completed_at TIMESTAMP WITH TIME ZONE,
    parse_error TEXT,
    
    format_status VARCHAR(50) DEFAULT 'pending',
    format_started_at TIMESTAMP WITH TIME ZONE,
    format_completed_at TIMESTAMP WITH TIME ZONE,
    format_error TEXT,
    
    tts_status VARCHAR(50) DEFAULT 'pending',
    tts_started_at TIMESTAMP WITH TIME ZONE,
    tts_completed_at TIMESTAMP WITH TIME ZONE,
    tts_error TEXT,
    
    chapter_count INTEGER DEFAULT 0,
    chapters_formatted INTEGER DEFAULT 0,
    chapters_audio_complete INTEGER DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Chapters table - individual book chapters
CREATE TABLE chapters (
    chapter_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    book_id UUID NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
    title VARCHAR(500),
    parsed_s3_key TEXT, -- S3 path to parsed chapter content
    word_count INTEGER,
    character_count INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(book_id, chapter_number)
);

-- Chapter processing status tracking
CREATE TABLE chapter_processing (
    chapter_id UUID PRIMARY KEY REFERENCES chapters(chapter_id) ON DELETE CASCADE,
    
    format_status VARCHAR(50) DEFAULT 'pending',
    format_started_at TIMESTAMP WITH TIME ZONE,
    format_completed_at TIMESTAMP WITH TIME ZONE,
    format_error TEXT,
    formatted_s3_key TEXT, -- S3 path to Gemini-formatted content
    formatted_word_count INTEGER,
    
    tts_status VARCHAR(50) DEFAULT 'pending',
    tts_started_at TIMESTAMP WITH TIME ZONE,
    tts_completed_at TIMESTAMP WITH TIME ZONE,
    tts_error TEXT,
    audio_s3_key TEXT, -- S3 path to generated MP3
    audio_duration_seconds INTEGER,
    audio_file_size_bytes BIGINT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Chapter content cache (optional - for frequently accessed chapters)
CREATE TABLE chapter_content (
    chapter_id UUID PRIMARY KEY REFERENCES chapters(chapter_id) ON DELETE CASCADE,
    raw_content TEXT,
    formatted_content TEXT,
    content_hash VARCHAR(64), -- SHA-256 hash for deduplication
    cached_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Processing logs for debugging and monitoring
CREATE TABLE processing_logs (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    book_id UUID REFERENCES books(book_id) ON DELETE SET NULL,
    chapter_id UUID REFERENCES chapters(chapter_id) ON DELETE SET NULL,
    stage VARCHAR(50) NOT NULL, -- scrape, parse, format, tts
    level VARCHAR(10) NOT NULL, -- INFO, WARN, ERROR
    message TEXT NOT NULL,
    details JSONB, -- Additional structured data
    lambda_request_id VARCHAR(100), -- AWS Lambda request ID for correlation
    execution_arn TEXT, -- Step Functions execution ARN
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ==============================================
-- INDEXES for performance
-- ==============================================

-- Books indexes
CREATE INDEX idx_books_gutenberg_id ON books(gutenberg_id);
CREATE INDEX idx_books_created_at ON books(created_at);
CREATE INDEX idx_books_language ON books(language);

-- Book processing indexes
CREATE INDEX idx_book_processing_scrape_status ON book_processing(scrape_status);
CREATE INDEX idx_book_processing_parse_status ON book_processing(parse_status);
CREATE INDEX idx_book_processing_format_status ON book_processing(format_status);
CREATE INDEX idx_book_processing_tts_status ON book_processing(tts_status);
CREATE INDEX idx_book_processing_updated_at ON book_processing(updated_at);

-- Chapters indexes
CREATE INDEX idx_chapters_book_id ON chapters(book_id);
CREATE INDEX idx_chapters_book_chapter ON chapters(book_id, chapter_number);

-- Chapter processing indexes
CREATE INDEX idx_chapter_processing_format_status ON chapter_processing(format_status);
CREATE INDEX idx_chapter_processing_tts_status ON chapter_processing(tts_status);
CREATE INDEX idx_chapter_processing_updated_at ON chapter_processing(updated_at);

-- Processing logs indexes
CREATE INDEX idx_processing_logs_book_id ON processing_logs(book_id);
CREATE INDEX idx_processing_logs_stage ON processing_logs(stage);
CREATE INDEX idx_processing_logs_level ON processing_logs(level);
CREATE INDEX idx_processing_logs_created_at ON processing_logs(created_at);
CREATE INDEX idx_processing_logs_lambda_request_id ON processing_logs(lambda_request_id);

-- ==============================================
-- TRIGGERS for automatic timestamp updates
-- ==============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers
CREATE TRIGGER update_books_updated_at BEFORE UPDATE ON books 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_book_processing_updated_at BEFORE UPDATE ON book_processing 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_chapter_processing_updated_at BEFORE UPDATE ON chapter_processing 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ==============================================
-- VIEWS for common queries
-- ==============================================

-- Book processing overview
CREATE VIEW book_processing_overview AS
SELECT 
    b.book_id,
    b.title,
    b.author,
    b.gutenberg_id,
    bp.scrape_status,
    bp.parse_status,
    bp.format_status,
    bp.tts_status,
    bp.chapter_count,
    bp.chapters_formatted,
    bp.chapters_audio_complete,
    CASE 
        WHEN bp.chapters_audio_complete = bp.chapter_count AND bp.chapter_count > 0 
        THEN 'complete'
        WHEN bp.tts_status = 'failed' OR bp.format_status = 'failed' OR bp.parse_status = 'failed' OR bp.scrape_status = 'failed'
        THEN 'failed'
        ELSE 'in_progress'
    END as overall_status,
    b.created_at,
    bp.updated_at
FROM books b
LEFT JOIN book_processing bp ON b.book_id = bp.book_id;

-- Chapter processing summary
CREATE VIEW chapter_processing_summary AS
SELECT 
    c.book_id,
    COUNT(*) as total_chapters,
    COUNT(CASE WHEN cp.format_status = 'complete' THEN 1 END) as formatted_chapters,
    COUNT(CASE WHEN cp.tts_status = 'complete' THEN 1 END) as audio_complete_chapters,
    COUNT(CASE WHEN cp.format_status = 'failed' THEN 1 END) as format_failed_chapters,
    COUNT(CASE WHEN cp.tts_status = 'failed' THEN 1 END) as tts_failed_chapters,
    SUM(cp.audio_duration_seconds) as total_audio_duration_seconds,
    SUM(cp.audio_file_size_bytes) as total_audio_file_size_bytes
FROM chapters c
LEFT JOIN chapter_processing cp ON c.chapter_id = cp.chapter_id
GROUP BY c.book_id;

-- ==============================================
-- FUNCTIONS for common operations
-- ==============================================

-- Function to get book processing status
CREATE OR REPLACE FUNCTION get_book_status(input_book_id UUID)
RETURNS TABLE(
    book_id UUID,
    title VARCHAR(500),
    overall_status TEXT,
    progress_percentage INTEGER,
    chapters_complete INTEGER,
    chapters_total INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        bpo.book_id,
        bpo.title,
        bpo.overall_status,
        CASE 
            WHEN bpo.chapter_count > 0 
            THEN (bpo.chapters_audio_complete * 100 / bpo.chapter_count)
            ELSE 0 
        END as progress_percentage,
        bpo.chapters_audio_complete as chapters_complete,
        bpo.chapter_count as chapters_total
    FROM book_processing_overview bpo
    WHERE bpo.book_id = input_book_id;
END;
$$ LANGUAGE plpgsql;

-- Function to log processing events
CREATE OR REPLACE FUNCTION log_processing_event(
    p_book_id UUID DEFAULT NULL,
    p_chapter_id UUID DEFAULT NULL,
    p_stage VARCHAR(50),
    p_level VARCHAR(10),
    p_message TEXT,
    p_details JSONB DEFAULT NULL,
    p_lambda_request_id VARCHAR(100) DEFAULT NULL,
    p_execution_arn TEXT DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    log_id UUID;
BEGIN
    INSERT INTO processing_logs (
        book_id, chapter_id, stage, level, message, details, 
        lambda_request_id, execution_arn
    ) VALUES (
        p_book_id, p_chapter_id, p_stage, p_level, p_message, p_details,
        p_lambda_request_id, p_execution_arn
    ) RETURNING processing_logs.log_id INTO log_id;
    
    RETURN log_id;
END;
$$ LANGUAGE plpgsql;

-- ==============================================
-- SAMPLE DATA for testing (optional)
-- ==============================================

-- Insert a test book
INSERT INTO books (gutenberg_id, title, author, language, source_url) VALUES
(11, 'Alice''s Adventures in Wonderland', 'Lewis Carroll', 'en', 'https://www.gutenberg.org/ebooks/11');

-- Insert processing record
INSERT INTO book_processing (book_id) 
SELECT book_id FROM books WHERE gutenberg_id = 11;

-- ==============================================
-- GRANTS for Lambda execution role
-- ==============================================

-- Create application user (will be created by CDK with IAM authentication)
-- These grants should be applied after the IAM role is created

-- GRANT CONNECT ON DATABASE gutenberg_pipeline TO "lambda-execution-role";
-- GRANT USAGE ON SCHEMA public TO "lambda-execution-role";
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "lambda-execution-role";
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "lambda-execution-role";
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO "lambda-execution-role";

-- For future tables
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "lambda-execution-role";
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO "lambda-execution-role";

COMMIT;
