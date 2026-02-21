#!/bin/bash
# Daily Book Scraper Runner
# This script can be added to crontab for daily execution

# Set the project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Change to project directory
cd "$PROJECT_DIR"

# Set environment variables if needed
export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"

# Run the scraper with logging
echo "Starting daily book scraper at $(date)"

# Run with pixi if available, otherwise use system Python
if command -v pixi &> /dev/null; then
    pixi run python scripts/scraper/bookScraper.py --max-books 5 --verbose
else
    python3 scripts/scraper/bookScraper.py --max-books 5 --verbose
fi

SCRAPER_EXIT_CODE=$?

echo "Book scraper finished at $(date) with exit code $SCRAPER_EXIT_CODE"

# Optional: Send notification or log to system log
if [ $SCRAPER_EXIT_CODE -eq 0 ]; then
    echo "✓ Daily book scraping completed successfully"
else
    echo "✗ Daily book scraping failed with exit code $SCRAPER_EXIT_CODE"
fi

exit $SCRAPER_EXIT_CODE
