"""
Lambda function for scraping books from Project Gutenberg
Migrated from existing bookScraper.py functionality
"""
import json
import os
import boto3
import logging
from typing import Dict, Any
import requests
from urllib.parse import urlparse

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
s3_client = boto3.client('s3')
secretsmanager_client = boto3.client('secretsmanager')

def get_database_connection():
    """Get database connection using RDS Proxy"""
    # TODO: Implement database connection using psycopg2 and RDS Proxy
    # This will be similar to your existing database connection code
    pass

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler for book scraping
    
    Expected input:
    {
        "bookId": "uuid",
        "sourceUrl": "https://gutenberg.org/...",
        "scrapeOptions": {"force": false}
    }
    
    Output:
    {
        "bookId": "uuid",
        "rawS3Key": "raw/2025-08-21/book_uuid/book.txt"
    }
    """
    try:
        book_id = event['bookId']
        source_url = event['sourceUrl']
        scrape_options = event.get('scrapeOptions', {})
        
        logger.info(f"Starting scrape for book {book_id} from {source_url}")
        
        # Get S3 bucket from environment
        bucket_name = os.environ['BUCKET_NAME']
        
        # Generate S3 key for raw content
        from datetime import datetime
        date_str = datetime.now().strftime('%Y-%m-%d')
        raw_s3_key = f"raw/{date_str}/{book_id}/book.txt"
        
        # Check if already exists (unless force=True)
        if not scrape_options.get('force', False):
            try:
                s3_client.head_object(Bucket=bucket_name, Key=raw_s3_key)
                logger.info(f"Book {book_id} already scraped, skipping")
                return {
                    'bookId': book_id,
                    'rawS3Key': raw_s3_key
                }
            except s3_client.exceptions.NoSuchKey:
                pass  # File doesn't exist, continue with scraping
        
        # Download content from source URL
        response = requests.get(source_url, timeout=60)
        response.raise_for_status()
        
        # Upload to S3
        s3_client.put_object(
            Bucket=bucket_name,
            Key=raw_s3_key,
            Body=response.text.encode('utf-8'),
            ContentType='text/plain; charset=utf-8'
        )
        
        logger.info(f"Successfully scraped book {book_id} to {raw_s3_key}")
        
        # Update database status
        # TODO: Update book_processing table with scrape_status='complete'
        
        return {
            'bookId': book_id,
            'rawS3Key': raw_s3_key
        }
        
    except Exception as e:
        logger.error(f"Error scraping book {book_id}: {str(e)}")
        # TODO: Update database with error status
        raise
