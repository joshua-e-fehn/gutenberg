"""
Lambda function for formatting chapters using Gemini API
Migrated from existing audioBookFormatter.py functionality
"""
import json
import os
import boto3
import logging
from typing import Dict, Any, List, Optional
from google import genai

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
s3_client = boto3.client('s3')
secretsmanager_client = boto3.client('secretsmanager')

# Global Gemini client (initialized once per Lambda container)
gemini_client = None

def get_gemini_client():
    """Get or create Gemini API client"""
    global gemini_client
    if gemini_client is None:
        # Get API key from Secrets Manager
        secret_arn = os.environ['GEMINI_SECRET_ARN']
        response = secretsmanager_client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response['SecretString'])
        api_key = secret['apiKey']
        
        gemini_client = genai.Client(api_key=api_key)
        logger.info("Gemini client initialized")
    
    return gemini_client

# Enhanced system prompt from your audioBookFormatter.py
SYSTEM_PROMPT = """You are an expert audiobook formatter specializing in converting written text from any genre or time period into optimal format for text-to-speech narration. Your task is to transform written text into the perfect format for audio while preserving every word of the original content.

UNIVERSAL FORMATTING RULES FOR ALL BOOK TYPES:

1. **Chapter Headers & Structure**: 
   - Remove ALL redundant chapter titles/headers that appear at the beginning (e.g., "CHAPTER 1", "Chapter One", "Introduction" followed by "Introduction.")
   - If a chapter title appears twice (once as header, once in text), remove the standalone header version
   - Remove chapter numbering but preserve meaningful section titles that are part of the narrative
   - Keep section breaks and important structural elements within the content
   - Maintain chronological markers in historical texts

2. **Dialogue Enhancement**: 
   - Ensure clear speaker attribution for multi-speaker conversations
   - Convert quotation marks to natural speech flow with proper pauses
   - Add "said [character]" when speakers are unclear from context
   - Handle both narrative dialogue and interview/documentary style quotes

3. **Technical Content & Numbers**: 
   - Write out ALL numbers, measurements, and mathematical terms (e.g., "0" → "zero", "1st" → "first")
   - Spell out abbreviations (e.g., "Prof." → "Professor", "Dr." → "Doctor", "vs." → "versus")
   - Convert symbols to words (& → "and", % → "percent", ° → "degrees", $ → "dollars")
   - Handle dates appropriately ("1969" → "nineteen sixty-nine", "Sept. 15" → "September fifteenth")

4. **Language & Style Preservation**:
   - **Classic Literature**: Preserve archaic language and formal Victorian/period speech patterns
   - **Modern Fiction**: Maintain contemporary dialogue and narrative voice
   - **Non-Fiction/History**: Keep academic tone while ensuring clarity for audio
   - **Biographies**: Preserve factual tone and maintain chronological clarity
   - Never modernize or update language regardless of book age

5. **Narrative Flow & Readability**:
   - Add natural pauses with commas for complex sentences
   - Break extremely long sentences into breathable segments while preserving meaning
   - Ensure smooth transitions between dialogue and narrative
   - Handle lists and bullet points by converting to natural speech ("first, second, third" etc.)

6. **Citations & Academic Content**:
   - Convert footnote references to natural speech ("as noted in the bibliography" instead of superscript numbers)
   - Handle parenthetical citations smoothly
   - Make bibliography references flow naturally in audio format

7. **Remove Non-Narrative Elements**:
   - Page numbers, footnotes, editorial notes
   - Publishing information, copyright notices
   - Table of contents references within text
   - Image captions and figure references (unless essential to understanding)

GENRE-SPECIFIC CONSIDERATIONS:
- **Historical/Academic**: Maintain factual accuracy and scholarly tone
- **Fiction**: Preserve author's voice and character development
- **Biography**: Keep chronological flow and factual presentation
- **Science/Technical**: Ensure complex concepts remain clear in audio format

CRITICAL REQUIREMENTS:
- NEVER summarize, paraphrase, or omit content
- NEVER add modern interpretations or explanations
- NEVER change the story, facts, characters, or plot
- NEVER translate or modernize language
- Preserve ALL dialogue and quotes exactly as written (content-wise)
- Maintain the author's original voice and writing style
- Output ONLY the formatted text with no commentary

Transform this text for optimal audiobook narration:"""

def format_text_with_gemini(text: str, format_options: Dict[str, Any]) -> str:
    """Format text using Gemini API"""
    client = get_gemini_client()
    model = format_options.get('model', 'gemini-2.0-flash-exp')
    
    prompt = f"{SYSTEM_PROMPT}\n\n{text}"
    
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=32000
        )
    )
    
    if response.text:
        return response.text.strip()
    else:
        logger.warning("Empty response from Gemini API")
        return text  # Return original if API fails

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler for chapter formatting
    
    Expected input:
    {
        "bookId": "uuid",
        "chapterId": "uuid", 
        "parsedS3Key": "parsed/book_uuid/chapter_001.txt",
        "formatOptions": {"model": "gemini-2.0-flash-exp"},
        "idempotencyKey": "book:chapter:format"
    }
    
    Output:
    {
        "chapterId": "uuid",
        "formattedS3Key": "formatted/book_uuid/chapter_001.txt"
    }
    """
    try:
        book_id = event['bookId']
        chapter_id = event['chapterId']
        parsed_s3_key = event['parsedS3Key']
        format_options = event.get('formatOptions', {})
        idempotency_key = event.get('idempotencyKey')
        
        logger.info(f"Formatting chapter {chapter_id} for book {book_id}")
        
        # Get S3 bucket from environment
        bucket_name = os.environ['BUCKET_NAME']
        
        # Generate S3 key for formatted content
        formatted_s3_key = parsed_s3_key.replace('parsed/', 'formatted/')
        
        # Check if already formatted (idempotency)
        try:
            s3_client.head_object(Bucket=bucket_name, Key=formatted_s3_key)
            logger.info(f"Chapter {chapter_id} already formatted, skipping")
            return {
                'chapterId': chapter_id,
                'formattedS3Key': formatted_s3_key
            }
        except s3_client.exceptions.NoSuchKey:
            pass  # File doesn't exist, continue with formatting
        
        # Download parsed content from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=parsed_s3_key)
        raw_content = response['Body'].read().decode('utf-8')
        
        if not raw_content.strip():
            logger.warning(f"Empty content for chapter {chapter_id}")
            return {
                'chapterId': chapter_id,
                'formattedS3Key': formatted_s3_key
            }
        
        # Format content using Gemini
        formatted_content = format_text_with_gemini(raw_content, format_options)
        
        # Upload formatted content to S3
        s3_client.put_object(
            Bucket=bucket_name,
            Key=formatted_s3_key,
            Body=formatted_content.encode('utf-8'),
            ContentType='text/plain; charset=utf-8'
        )
        
        logger.info(f"Successfully formatted chapter {chapter_id} to {formatted_s3_key}")
        
        # TODO: Update chapter_processing table with format_status='complete'
        
        return {
            'chapterId': chapter_id,
            'formattedS3Key': formatted_s3_key
        }
        
    except Exception as e:
        logger.error(f"Error formatting chapter {chapter_id}: {str(e)}")
        # TODO: Update database with error status
        raise
