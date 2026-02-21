#!/bin/bash

# Gutenberg Simplified Deployment Script
# Deploys only scraping, parsing, and formatting (no TTS)

set -e

echo "🚀 Gutenberg Simplified Deployment (Scrape + Parse + Format)"
echo "============================================================"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check prerequisites
echo -e "${BLUE}🔍 Checking prerequisites...${NC}"

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI not found. Please install AWS CLI v2.${NC}"
    echo "Install guide: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    exit 1
fi

# Check AWS credentials (support both traditional and SSO profiles)
if ! aws sts get-caller-identity --profile Gutenberg &> /dev/null; then
    echo -e "${RED}❌ AWS credentials not configured or SSO session expired.${NC}"
    echo "For AWS SSO, run: aws sso login --profile Gutenberg"
    echo "For traditional credentials, run: aws configure"
    exit 1
fi

# Set the AWS profile for all subsequent commands
export AWS_PROFILE=Gutenberg
echo -e "${GREEN}✅ Using AWS profile: $AWS_PROFILE${NC}"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js not found. Please install Node.js 18+.${NC}"
    exit 1
fi

NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo -e "${RED}❌ Node.js version must be 18 or higher. Current: $(node --version)${NC}"
    exit 1
fi

# Check CDK
if ! command -v cdk &> /dev/null; then
    echo -e "${YELLOW}⚠️ AWS CDK not found. Installing...${NC}"
    npm install -g aws-cdk
fi

echo -e "${GREEN}✅ All prerequisites met!${NC}"

# Get AWS account info
ACCOUNT_ID=$(aws sts get-caller-identity --profile Gutenberg --query Account --output text)
REGION=$(aws configure get region --profile Gutenberg || echo "us-east-1")

echo -e "${BLUE}📋 Deployment details:${NC}"
echo "Account ID: $ACCOUNT_ID"
echo "Region: $REGION"
echo "Stack: GutenbergSimplifiedStack"

# Navigate to infrastructure directory
cd "$(dirname "$0")"

# Install dependencies
echo -e "${BLUE}📦 Installing CDK dependencies...${NC}"
npm install

# Bootstrap CDK (one-time setup)
echo -e "${BLUE}🏗️ Bootstrapping CDK...${NC}"
cdk bootstrap

# Create simplified Lambda function directories if they don't exist
echo -e "${BLUE}📁 Setting up Lambda function directories...${NC}"

mkdir -p ../lambda-functions/scraper
mkdir -p ../lambda-functions/parser
mkdir -p ../lambda-functions/formatter
mkdir -p ../lambda-functions/database

# Create placeholder Lambda function files if they don't exist
if [ ! -f "../lambda-functions/scraper/index.py" ]; then
    cat > ../lambda-functions/scraper/index.py << 'EOF'
import json
import boto3
import requests
import logging
import os
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Scrape a book from Project Gutenberg
    """
    try:
        # Extract parameters
        book_id = event.get('bookId', 'unknown')
        source_url = event.get('sourceUrl')
        
        if not source_url:
            return {
                'statusCode': 400,
                'error': 'sourceUrl is required'
            }
        
        logger.info(f"Scraping book {book_id} from {source_url}")
        
        # Download the book content
        response = requests.get(source_url, timeout=30)
        response.raise_for_status()
        
        # Get S3 client
        s3 = boto3.client('s3')
        bucket_name = os.environ['BUCKET_NAME']
        
        # Store raw content in S3
        today = datetime.now().strftime('%Y-%m-%d')
        s3_key = f"raw/{today}/{book_id}/book.txt"
        
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=response.content,
            ContentType='text/plain',
            Metadata={
                'source_url': source_url,
                'scraped_at': datetime.now().isoformat()
            }
        )
        
        return {
            'statusCode': 200,
            'bookId': book_id,
            'sourceUrl': source_url,
            's3Key': s3_key,
            'contentLength': len(response.content),
            'scrapedAt': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error scraping book: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e)
        }
EOF
fi

if [ ! -f "../lambda-functions/parser/index.py" ]; then
    cat > ../lambda-functions/parser/index.py << 'EOF'
import json
import boto3
import re
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Parse a book into chapters
    """
    try:
        # Extract parameters
        book_id = event.get('bookId')
        s3_key = event.get('s3Key')
        
        if not book_id or not s3_key:
            return {
                'statusCode': 400,
                'error': 'bookId and s3Key are required'
            }
        
        logger.info(f"Parsing book {book_id} from {s3_key}")
        
        # Get S3 client
        s3 = boto3.client('s3')
        bucket_name = os.environ['BUCKET_NAME']
        
        # Download the book content
        response = s3.get_object(Bucket=bucket_name, Key=s3_key)
        content = response['Body'].read().decode('utf-8')
        
        # Simple chapter detection (can be enhanced)
        chapters = split_into_chapters(content)
        
        # Store each chapter in S3
        chapter_keys = []
        for i, chapter in enumerate(chapters, 1):
            chapter_key = f"parsed/{book_id}/chapter_{i:03d}.txt"
            
            s3.put_object(
                Bucket=bucket_name,
                Key=chapter_key,
                Body=chapter.encode('utf-8'),
                ContentType='text/plain',
                Metadata={
                    'book_id': book_id,
                    'chapter_number': str(i),
                    'parsed_at': datetime.now().isoformat()
                }
            )
            
            chapter_keys.append({
                'chapterNumber': i,
                's3Key': chapter_key,
                'wordCount': len(chapter.split())
            })
        
        return {
            'statusCode': 200,
            'bookId': book_id,
            'chapters': chapter_keys,
            'totalChapters': len(chapters),
            'parsedAt': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error parsing book: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e)
        }

def split_into_chapters(content):
    """
    Split content into chapters
    """
    # Remove Project Gutenberg header/footer
    lines = content.split('\n')
    start_idx = 0
    end_idx = len(lines)
    
    for i, line in enumerate(lines):
        if '*** START OF' in line.upper():
            start_idx = i + 1
            break
    
    for i in range(len(lines) - 1, -1, -1):
        if '*** END OF' in lines[i].upper():
            end_idx = i
            break
    
    clean_content = '\n'.join(lines[start_idx:end_idx])
    
    # Simple chapter splitting
    chapter_patterns = [
        r'\n\s*CHAPTER\s+[IVXLCDM\d]+',  # CHAPTER I, CHAPTER 1, etc.
        r'\n\s*Chapter\s+[IVXLCDM\d]+',  # Chapter I, Chapter 1, etc.
        r'\n\s*[IVXLCDM]+\.',           # I., II., III., etc.
        r'\n\s*\d+\.',                  # 1., 2., 3., etc.
    ]
    
    for pattern in chapter_patterns:
        matches = list(re.finditer(pattern, clean_content, re.IGNORECASE))
        if len(matches) > 1:  # Found multiple chapters
            chapters = []
            for i, match in enumerate(matches):
                start = match.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(clean_content)
                chapter = clean_content[start:end].strip()
                if len(chapter) > 100:  # Filter out very short chapters
                    chapters.append(chapter)
            return chapters
    
    # If no chapters found, split by length
    words = clean_content.split()
    chunk_size = 2000  # ~2000 words per chunk
    chapters = []
    
    for i in range(0, len(words), chunk_size):
        chunk = ' '.join(words[i:i + chunk_size])
        chapters.append(chunk)
    
    return chapters if chapters else [clean_content]
EOF
fi

if [ ! -f "../lambda-functions/formatter/index.py" ]; then
    cat > ../lambda-functions/formatter/index.py << 'EOF'
import json
import boto3
import logging
import os
from datetime import datetime
import google.generativeai as genai

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Enhanced system prompt from your local audioBookFormatter.py
SYSTEM_PROMPT = """You are an expert audiobook editor. Your task is to optimize text for audio narration by improving readability and flow without changing the core content or meaning.

CRITICAL RULES:
1. NEVER change character names, places, or proper nouns
2. NEVER alter dialogue or quoted speech
3. NEVER remove or change chapter titles/headers in the actual text
4. If you see redundant chapter titles (like "Introduction" appearing twice), remove only the redundant instances, keeping one clear chapter marker
5. Preserve the author's writing style and voice
6. Keep all paragraph breaks and structure

FORMATTING IMPROVEMENTS:
- Fix obvious OCR/scanning errors (missing spaces, weird characters)
- Expand abbreviations that might be unclear when spoken (Mr. → Mister, Dr. → Doctor, etc.)
- Convert numbers to written form when appropriate for narration
- Ensure proper punctuation for natural speech pauses
- Remove or clarify text that would be confusing when heard (not seen)
- Ensure smooth transitions between paragraphs
- Remove redundant elements like duplicate chapter titles, but preserve one clear chapter marker

OUTPUT FORMAT:
Return ONLY the cleaned text ready for audio narration. Do not add explanations, comments, or metadata."""

def lambda_handler(event, context):
    """
    Format chapter text using Gemini API
    """
    try:
        # Extract parameters
        book_id = event.get('bookId')
        chapter_info = event.get('chapterInfo', {})
        chapter_key = chapter_info.get('s3Key')
        
        if not book_id or not chapter_key:
            return {
                'statusCode': 400,
                'error': 'bookId and chapterInfo.s3Key are required'
            }
        
        logger.info(f"Formatting chapter {chapter_key} for book {book_id}")
        
        # Get Gemini API key from Secrets Manager
        secrets_client = boto3.client('secretsmanager')
        secret_response = secrets_client.get_secret_value(
            SecretId=os.environ['GEMINI_SECRET_ARN']
        )
        api_key = json.loads(secret_response['SecretString'])['apiKey']
        
        # Configure Gemini
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # Get S3 client
        s3 = boto3.client('s3')
        bucket_name = os.environ['BUCKET_NAME']
        
        # Download the chapter content
        response = s3.get_object(Bucket=bucket_name, Key=chapter_key)
        content = response['Body'].read().decode('utf-8')
        
        # Format using Gemini
        prompt = f"{SYSTEM_PROMPT}\n\nText to optimize:\n\n{content}"
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=7000,
                temperature=0.1,
                top_p=0.9,
            )
        )
        
        formatted_text = response.text
        
        # Store formatted content in S3
        formatted_key = chapter_key.replace('parsed/', 'formatted/')
        
        s3.put_object(
            Bucket=bucket_name,
            Key=formatted_key,
            Body=formatted_text.encode('utf-8'),
            ContentType='text/plain',
            Metadata={
                'book_id': book_id,
                'original_key': chapter_key,
                'formatted_at': datetime.now().isoformat(),
                'model': 'gemini-2.0-flash-exp'
            }
        )
        
        return {
            'statusCode': 200,
            'bookId': book_id,
            'chapterNumber': chapter_info.get('chapterNumber'),
            'originalKey': chapter_key,
            'formattedKey': formatted_key,
            'wordCount': len(formatted_text.split()),
            'formattedAt': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error formatting chapter: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e)
        }
EOF
fi

if [ ! -f "../lambda-functions/database/index.py" ]; then
    cat > ../lambda-functions/database/index.py << 'EOF'
import json
import boto3
import psycopg2
import logging
import os
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Update database with processing status
    """
    try:
        # Extract parameters
        book_id = event.get('bookId')
        status = event.get('status', 'completed')
        
        logger.info(f"Updating database status for book {book_id}: {status}")
        
        # Get database credentials from Secrets Manager
        secrets_client = boto3.client('secretsmanager')
        secret_response = secrets_client.get_secret_value(
            SecretId=os.environ['DB_SECRET_ARN']
        )
        db_credentials = json.loads(secret_response['SecretString'])
        
        # Connect to database
        conn = psycopg2.connect(
            host=os.environ['DB_CLUSTER_ENDPOINT'],
            port=5432,
            database='gutenberg_pipeline',
            user=db_credentials['username'],
            password=db_credentials['password']
        )
        
        with conn.cursor() as cursor:
            # Update book status
            cursor.execute("""
                INSERT INTO books (book_id, title, status, last_updated)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (book_id) 
                DO UPDATE SET 
                    status = EXCLUDED.status,
                    last_updated = EXCLUDED.last_updated
            """, (book_id, f"Book {book_id}", status, datetime.now()))
            
            # Log processing step
            cursor.execute("""
                INSERT INTO processing_logs (book_id, step, status, message, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (book_id, 'pipeline_complete', 'success', 'Scraping, parsing, and formatting completed', datetime.now()))
            
            conn.commit()
        
        conn.close()
        
        return {
            'statusCode': 200,
            'bookId': book_id,
            'status': status,
            'updatedAt': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error updating database: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e)
        }
EOF
fi

# Add requirements.txt for each Lambda function
for func_dir in ../lambda-functions/*/; do
    if [ ! -f "$func_dir/requirements.txt" ]; then
        cat > "$func_dir/requirements.txt" << 'EOF'
boto3==1.34.0
requests==2.31.0
psycopg2-binary==2.9.9
google-generativeai==0.5.0
EOF
    fi
done

echo -e "${GREEN}✅ Lambda function templates created!${NC}"

# Deploy the stack
echo -e "${BLUE}🚀 Deploying simplified infrastructure...${NC}"
cdk deploy GutenbergSimplifiedStack --require-approval never

echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"
echo ""
echo -e "${BLUE}📋 Next steps:${NC}"
echo "1. Set your Gemini API key:"
echo "   aws secretsmanager update-secret --secret-id 'gutenberg/gemini-api-key' --secret-string '{\"apiKey\":\"YOUR_API_KEY\"}'"
echo ""
echo "2. Apply database schema:"
echo "   Get the database endpoint from CDK output above, then:"
echo "   psql -h <DB_ENDPOINT> -U gutenberg_admin -d gutenberg_pipeline -f database-schema.sql"
echo ""
echo "3. Test the pipeline:"
echo "   aws stepfunctions start-execution --state-machine-arn <STATE_MACHINE_ARN> --input '{\"bookId\":\"test-book\",\"sourceUrl\":\"https://www.gutenberg.org/files/11/11-0.txt\"}'"
echo ""
echo -e "${YELLOW}💡 Stack outputs are shown above with all the ARNs and endpoints you need!${NC}"
