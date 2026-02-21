#!/usr/bin/env python3
"""
Daily Book Scraper for Project Gutenberg
Checks RSS feed for new English books, downloads HTML zip files,
and organizes them in the books directory structure.
"""

import os
import re
import sys
import json
import time
import zipfile
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Optional, Set
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging (will be updated in __init__ to use proper path)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class Book:
    """Represents a Project Gutenberg book."""
    title: str
    link: str
    description: str
    ebook_id: str = ""
    language: str = ""
    safe_title: str = ""
    
    def __post_init__(self):
        """Clean and validate book data after initialization."""
        self.ebook_id = self.extract_ebook_id()
        self.language = self.extract_language()
        self.safe_title = self.make_safe_title()
    
    def extract_ebook_id(self) -> str:
        """Extract ebook ID from the link."""
        match = re.search(r'/ebooks/(\d+)', self.link)
        return match.group(1) if match else ""
    
    def extract_language(self) -> str:
        """Extract language from description."""
        match = re.search(r'Language:\s*(\w+)', self.description)
        return match.group(1) if match else ""
    
    def make_safe_title(self) -> str:
        """Create a filesystem-safe version of the title."""
        # Remove author info if present (text after "by")
        title_clean = re.split(r'\s+by\s+', self.title)[0].strip()
        
        # Remove special characters and replace with underscores
        safe = re.sub(r'[^\w\s-]', '', title_clean)
        safe = re.sub(r'[-\s]+', '_', safe)
        safe = safe.strip('_').lower()
        
        # Limit length
        return safe[:50] if len(safe) > 50 else safe

class BookScraper:
    """Main scraper class for Project Gutenberg books."""
    
    RSS_URL = "https://gutenberg.org/cache/epub/feeds/today.rss"
    BASE_URL = "https://www.gutenberg.org"
    
    def __init__(self, books_dir: str = None):
        """Initialize the scraper."""
        # Get the project root directory (go up from scripts/scraper/ to project root)
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent
        
        self.books_dir = Path(books_dir) if books_dir else project_root / "books"
        self.books_dir.mkdir(exist_ok=True)
        
        # State file to track processed books (in scraper directory)
        self.state_file = script_dir / "scraper_state.json"
        self.processed_books = self.load_state()
        
        # Log file in scraper directory
        self.log_file = script_dir / "book_scraper.log"
        
        # Configure logging with proper file path
        self._configure_logging()
        
        # Session for HTTP requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'GutenbergBookScraper/1.0 (Educational Project)'
        })
    
    def _configure_logging(self):
        """Configure logging with the proper file path."""
        # Remove existing file handler if present
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)
        
        # Add file handler with correct path
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
    
    def load_state(self) -> Set[str]:
        """Load the set of already processed book IDs."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('processed_books', []))
            except (json.JSONDecodeError, KeyError):
                logger.warning("Could not load state file, starting fresh")
        return set()
    
    def save_state(self):
        """Save the current state of processed books."""
        state_data = {
            'processed_books': list(self.processed_books),
            'last_run': datetime.now().isoformat()
        }
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
            logger.info(f"State saved with {len(self.processed_books)} processed books")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def fetch_rss_feed(self) -> List[Book]:
        """Fetch and parse the RSS feed for new books."""
        try:
            logger.info(f"Fetching RSS feed from {self.RSS_URL}")
            response = self.session.get(self.RSS_URL, timeout=30)
            response.raise_for_status()
            
            # Parse XML
            root = ET.fromstring(response.content)
            books = []
            
            for item in root.findall('.//item'):
                title_elem = item.find('title')
                link_elem = item.find('link')
                desc_elem = item.find('description')
                
                if title_elem is not None and link_elem is not None and desc_elem is not None:
                    book = Book(
                        title=title_elem.text or "",
                        link=link_elem.text or "",
                        description=desc_elem.text or ""
                    )
                    books.append(book)
            
            logger.info(f"Found {len(books)} books in RSS feed")
            return books
            
        except Exception as e:
            logger.error(f"Failed to fetch RSS feed: {e}")
            return []
    
    def filter_english_books(self, books: List[Book]) -> List[Book]:
        """Filter books to only include English language ones."""
        english_books = [book for book in books if book.language.lower() == 'english']
        logger.info(f"Filtered to {len(english_books)} English books")
        return english_books
    
    def filter_new_books(self, books: List[Book]) -> List[Book]:
        """Filter out books that have already been processed."""
        new_books = [book for book in books if book.ebook_id not in self.processed_books]
        logger.info(f"Found {len(new_books)} new books to process")
        return new_books
    
    def get_download_url(self, book: Book) -> Optional[str]:
        """Get the download URL for the HTML zip file."""
        try:
            # First, try the common patterns
            patterns = [
                f"{self.BASE_URL}/files/{book.ebook_id}/{book.ebook_id}-h.zip",
                f"{self.BASE_URL}/cache/epub/{book.ebook_id}/pg{book.ebook_id}-images.zip",
                f"{self.BASE_URL}/files/{book.ebook_id}/pg{book.ebook_id}-images.zip"
            ]
            
            for zip_url in patterns:
                try:
                    response = self.session.head(zip_url, timeout=10)
                    if response.status_code == 200:
                        logger.debug(f"Found HTML zip at: {zip_url}")
                        return zip_url
                except Exception:
                    continue
            
            # If direct patterns fail, parse the book page to find download links
            logger.debug(f"Direct patterns failed, parsing book page for {book.ebook_id}")
            book_page_url = book.link
            
            response = self.session.get(book_page_url, timeout=15)
            response.raise_for_status()
            
            # Look for HTML zip download links in the page
            import re
            html_content = response.text
            
            # Pattern to match HTML zip download links
            zip_patterns = [
                r'href="([^"]*\.zip)"[^>]*>.*?HTML.*?zip',
                r'href="([^"]*\.zip)"[^>]*>.*?Download HTML',
                r'href="(/files/\d+/[^"]*\.zip)"',
                r'href="(/cache/epub/\d+/[^"]*\.zip)"',
                r'href="([^"]*pg\d+-h\.zip)"',
                r'href="([^"]*-h\.zip)"'
            ]
            
            for pattern in zip_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    if match.startswith('/'):
                        full_url = self.BASE_URL + match
                    else:
                        full_url = match
                    
                    # Verify the URL works
                    try:
                        head_response = self.session.head(full_url, timeout=10)
                        if head_response.status_code == 200:
                            logger.debug(f"Found HTML zip via page parsing: {full_url}")
                            return full_url
                    except Exception:
                        continue
            
            logger.warning(f"No HTML zip file found for book {book.ebook_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error finding download URL for book {book.ebook_id}: {e}")
            return None
    
    def create_book_directory(self, book: Book) -> Optional[Path]:
        """Create directory structure for a book."""
        try:
            # Create unique directory name
            base_name = book.safe_title
            book_dir = self.books_dir / base_name
            
            # Handle name conflicts with thread-safe approach
            counter = 1
            while True:
                try:
                    book_dir.mkdir()
                    break
                except FileExistsError:
                    book_dir = self.books_dir / f"{base_name}_{counter}"
                    counter += 1
                    if counter > 100:  # Safety limit
                        raise Exception(f"Could not create unique directory after 100 attempts")
            
            # Create subdirectories
            (book_dir / "source").mkdir()
            (book_dir / "chapters").mkdir()
            
            # Create a metadata file
            metadata = {
                'title': book.title,
                'ebook_id': book.ebook_id,
                'language': book.language,
                'gutenberg_url': book.link,
                'scraped_date': datetime.now().isoformat()
            }
            
            with open(book_dir / "metadata.json", 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Created directory structure: {book_dir}")
            return book_dir
            
        except Exception as e:
            logger.error(f"Failed to create directory for book {book.ebook_id}: {e}")
            return None
    
    def download_and_extract(self, book: Book, download_url: str, book_dir: Path) -> bool:
        """Download the zip file and extract it to the source directory."""
        try:
            logger.info(f"Downloading {book.title} from {download_url}")
            
            # Download the zip file
            response = self.session.get(download_url, timeout=60)
            response.raise_for_status()
            
            # Save to temporary file
            temp_zip = book_dir / "temp_download.zip"
            with open(temp_zip, 'wb') as f:
                f.write(response.content)
            
            # Extract to source directory
            source_dir = book_dir / "source"
            with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                zip_ref.extractall(source_dir)
            
            # Clean up temp file
            temp_zip.unlink()
            
            logger.info(f"Successfully extracted book {book.ebook_id} to {source_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download/extract book {book.ebook_id}: {e}")
            return False
    
    def process_book(self, book: Book) -> bool:
        """Process a single book: create directories, download, and extract."""
        try:
            logger.info(f"Processing book: {book.title} (ID: {book.ebook_id})")
            
            # Get download URL
            download_url = self.get_download_url(book)
            if not download_url:
                return False
            
            # Create directory structure
            book_dir = self.create_book_directory(book)
            if not book_dir:
                return False
            
            # Download and extract
            if self.download_and_extract(book, download_url, book_dir):
                self.processed_books.add(book.ebook_id)
                return True
            else:
                # Clean up failed directory
                import shutil
                shutil.rmtree(book_dir, ignore_errors=True)
                return False
                
        except Exception as e:
            logger.error(f"Failed to process book {book.ebook_id}: {e}")
            return False
    
    def run_daily_scrape(self, max_workers: int = 3, max_books: int = 10) -> Dict[str, int]:
        """Run the daily scraping process."""
        logger.info("Starting daily book scraping process")
        start_time = time.time()
        
        # Fetch RSS feed
        all_books = self.fetch_rss_feed()
        if not all_books:
            return {'total': 0, 'english': 0, 'new': 0, 'processed': 0, 'failed': 0}
        
        # Filter for English books
        english_books = self.filter_english_books(all_books)
        
        # Filter for new books
        new_books = self.filter_new_books(english_books)
        
        if not new_books:
            logger.info("No new English books found")
            return {
                'total': len(all_books),
                'english': len(english_books),
                'new': 0,
                'processed': 0,
                'failed': 0
            }
        
        # Limit the number of books to process
        books_to_process = new_books[:max_books]
        if len(new_books) > max_books:
            logger.info(f"Limiting processing to {max_books} books (found {len(new_books)} new books)")
        
        # Process books with thread pool
        processed_count = 0
        failed_count = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all jobs
            future_to_book = {
                executor.submit(self.process_book, book): book 
                for book in books_to_process
            }
            
            # Process completed jobs
            for future in as_completed(future_to_book):
                book = future_to_book[future]
                try:
                    if future.result():
                        processed_count += 1
                        logger.info(f"✓ Successfully processed: {book.title}")
                    else:
                        failed_count += 1
                        logger.warning(f"✗ Failed to process: {book.title}")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"✗ Exception processing {book.title}: {e}")
                
                # Add small delay to be respectful
                time.sleep(0.5)
        
        # Save state
        self.save_state()
        
        # Log summary
        elapsed_time = time.time() - start_time
        logger.info(f"Scraping completed in {elapsed_time:.2f} seconds")
        logger.info(f"Summary: {processed_count} processed, {failed_count} failed")
        
        return {
            'total': len(all_books),
            'english': len(english_books),
            'new': len(new_books),
            'processed': processed_count,
            'failed': failed_count
        }

def main():
    """Main entry point for the scraper."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Project Gutenberg Daily Book Scraper')
    parser.add_argument('--books-dir', type=str, help='Directory to store books')
    parser.add_argument('--max-workers', type=int, default=3, help='Maximum concurrent downloads')
    parser.add_argument('--max-books', type=int, default=10, help='Maximum books to process per run')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize and run scraper
    scraper = BookScraper(books_dir=args.books_dir)
    
    try:
        results = scraper.run_daily_scrape(
            max_workers=args.max_workers,
            max_books=args.max_books
        )
        
        print("\n=== Scraping Results ===")
        print(f"Total books in feed: {results['total']}")
        print(f"English books: {results['english']}")
        print(f"New books found: {results['new']}")
        print(f"Successfully processed: {results['processed']}")
        print(f"Failed: {results['failed']}")
        
        # Exit with non-zero code if there were failures
        sys.exit(1 if results['failed'] > 0 else 0)
        
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()