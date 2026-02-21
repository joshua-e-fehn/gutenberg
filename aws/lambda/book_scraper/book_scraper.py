import json
import boto3
import logging
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda handler for scraping individual books from Project Gutenberg
    """
    try:
        logger.info("Starting book scraper lambda")
        
        book_id = event.get('bookId')
        book_url = event.get('bookUrl')
        
        logger.info(f"Scraping book ID: {book_id}, URL: {book_url}")
        
        # TODO: Implement book scraping logic
        # - Download book from Project Gutenberg
        # - Save to S3 raw bucket
        # - Update database with book metadata
        # - Return S3 keys for downloaded files
        
        return {
            'statusCode': 200,
            'bookId': book_id,
            'bookFolderS3Key': f"books/{book_id}/",
            'bookFileS3Key': f"books/{book_id}/book.txt"
        }
        
    except Exception as e:
        logger.error(f"Error in book scraper: {str(e)}")
        raise e
