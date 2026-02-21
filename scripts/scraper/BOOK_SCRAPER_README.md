# Project Gutenberg Book Scraper

This daily book scraper automatically checks the Project Gutenberg RSS feed for new English language books, downloads their HTML zip files, and organizes them in the books directory.

## Features

- **Daily RSS Monitoring**: Checks https://gutenberg.org/cache/epub/feeds/today.rss for new books
- **English Language Filtering**: Only processes books marked as English language
- **Duplicate Prevention**: Tracks processed books to avoid re-downloading
- **Organized Structure**: Creates standardized directory structure for each book
- **Robust Download**: Handles multiple URL patterns and parses book pages when needed
- **Concurrent Processing**: Downloads multiple books in parallel (respectfully)
- **Comprehensive Logging**: Detailed logs for monitoring and debugging

## Directory Structure

For each downloaded book, the scraper creates:

```
books/
└── book_title_safe_name/
    ├── metadata.json          # Book information and scraping metadata
    ├── source/               # Extracted HTML content and images
    │   ├── pg[ID]-images.html # Main HTML file
    │   └── images/           # Associated images (if any)
    └── chapters/             # Empty directory for future chapter processing
```

## Installation & Setup

1. **Install Dependencies**: The scraper uses the existing project dependencies (requests, beautifulsoup4)

2. **Test the Scraper**:

   ```bash
   cd /path/to/gutenberg/project
   python scripts/setup_scraper.py
   ```

3. **Manual Usage**:

   ```bash
   # Basic usage (process up to 10 new books)
   python scripts/bookScraper.py

   # Process only 2 books with verbose output
   python scripts/bookScraper.py --max-books 2 --verbose

   # Custom books directory
   python scripts/bookScraper.py --books-dir /custom/path

   # Help
   python scripts/bookScraper.py --help
   ```

## Daily Automation

### Using Cron (Recommended)

Add to your crontab (`crontab -e`):

```bash
# Run daily at 6:00 AM
0 6 * * * /path/to/gutenberg/scripts/run_daily_scraper.sh >> /path/to/gutenberg/scraper_daily.log 2>&1
```

Alternative schedules:

- `0 2 * * *` - 2:00 AM daily
- `30 8 * * *` - 8:30 AM daily
- `0 18 * * *` - 6:00 PM daily

### Using the Shell Script

```bash
# Run the daily scraper manually
./scripts/run_daily_scraper.sh
```

## Configuration Options

| Parameter       | Default   | Description                         |
| --------------- | --------- | ----------------------------------- |
| `--max-books`   | 10        | Maximum books to process per run    |
| `--max-workers` | 3         | Maximum concurrent downloads        |
| `--books-dir`   | `./books` | Directory to store downloaded books |
| `--verbose`     | False     | Enable verbose logging              |

## State Management

The scraper maintains state in `scraper_state.json` to track:

- Previously processed book IDs
- Last run timestamp

This prevents re-downloading books and enables incremental processing.

## Logging

The scraper generates logs in multiple locations:

1. **Console Output**: Real-time status during execution
2. **book_scraper.log**: Detailed scraper logs with debug information
3. **scraper_daily.log**: Daily cron job logs (when using shell script)

Log levels:

- `INFO`: General operation status
- `WARNING`: Non-fatal issues (missing files, etc.)
- `ERROR`: Serious problems requiring attention
- `DEBUG`: Detailed technical information (with `--verbose`)

## Troubleshooting

### Common Issues

1. **No Books Found**:

   - Check internet connectivity
   - Verify RSS feed is accessible: https://gutenberg.org/cache/epub/feeds/today.rss
   - Project Gutenberg may not have new English books on some days

2. **Download Failures**:

   - Some books may not have HTML versions available
   - Network timeouts are automatically handled with retries
   - Check logs for specific error messages

3. **Permission Errors**:

   - Ensure write permissions on the books directory
   - Check that the script has execution permissions: `chmod +x scripts/run_daily_scraper.sh`

4. **Cron Job Not Running**:
   - Verify cron service is running: `sudo systemctl status cron` (Linux) or `sudo launchctl list | grep cron` (macOS)
   - Check cron logs: `/var/log/cron` (Linux) or `/var/log/system.log` (macOS)
   - Ensure full paths are used in crontab entries

### Debug Mode

Run with verbose logging to diagnose issues:

```bash
python scripts/bookScraper.py --verbose --max-books 1
```

## Performance Considerations

- **Rate Limiting**: The scraper includes delays between requests to be respectful to Project Gutenberg
- **Concurrent Downloads**: Limited to 3 simultaneous downloads by default
- **File Size**: HTML zip files are typically 1-20 MB each
- **Processing Time**: Expect 5-30 seconds per book depending on file size and network speed

## Integration

The scraper is designed to work with the existing Gutenberg project workflow:

1. **Books Discovery**: Scraper populates the `books/` directory
2. **Chapter Processing**: Use existing tools to split HTML into chapters
3. **Audio Generation**: Process chapters into audio files
4. **Publishing**: Upload to various platforms

## Contributing

When modifying the scraper:

1. Test changes with `--max-books 1 --verbose`
2. Ensure proper error handling for network issues
3. Maintain the existing directory structure
4. Update logs appropriately
5. Consider rate limiting and Project Gutenberg's terms of service

## License & Terms

This scraper is for educational and personal use. Please respect Project Gutenberg's terms of service and bandwidth. All downloaded content is in the public domain as provided by Project Gutenberg.
