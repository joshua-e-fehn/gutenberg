#!/usr/bin/env python3
"""
Setup script for the daily book scraper.
Helps configure cron job and test the scraper.
"""

import os
import sys
import subprocess
from pathlib import Path

def get_project_dir():
    """Get the project root directory."""
    script_dir = Path(__file__).parent
    return script_dir.parent.parent

def test_scraper():
    """Test the scraper with a dry run."""
    project_dir = get_project_dir()
    scraper_script = project_dir / "scripts" / "scraper" / "bookScraper.py"
    
    print("Testing the book scraper...")
    try:
        # Run with limited books for testing
        result = subprocess.run([
            sys.executable, str(scraper_script), 
            "--max-books", "2", 
            "--verbose"
        ], cwd=project_dir, capture_output=True, text=True)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        if result.returncode == 0:
            print("✓ Scraper test completed successfully!")
        else:
            print(f"✗ Scraper test failed with exit code {result.returncode}")
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"Error running scraper test: {e}")
        return False

def setup_cron_job():
    """Help user set up a cron job for daily scraping."""
    project_dir = get_project_dir()
    runner_script = project_dir / "scripts" / "scraper" / "run_daily_scraper.sh"
    
    # Suggest cron job entry
    cron_entry = f"0 6 * * * {runner_script} >> {project_dir}/scraper_daily.log 2>&1"
    
    print("\n" + "="*60)
    print("CRON JOB SETUP")
    print("="*60)
    print("To set up daily scraping, add the following line to your crontab:")
    print("(This will run the scraper every day at 6:00 AM)")
    print()
    print(f"  {cron_entry}")
    print()
    print("To edit your crontab, run:")
    print("  crontab -e")
    print()
    print("Alternative times:")
    print("  0 2 * * *   - Run at 2:00 AM daily")
    print("  30 8 * * *  - Run at 8:30 AM daily")
    print("  0 18 * * *  - Run at 6:00 PM daily")
    print()
    print("To view current crontab entries:")
    print("  crontab -l")
    print()
    print("Log files will be created at:")
    print(f"  {project_dir}/scraper_daily.log (daily run logs)")
    print(f"  {project_dir}/scripts/scraper/book_scraper.log (detailed scraper logs)")
    print("="*60)

def check_dependencies():
    """Check if required dependencies are available."""
    print("Checking dependencies...")
    
    required_modules = ['requests', 'beautifulsoup4']
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module.replace('beautifulsoup4', 'bs4'))
            print(f"✓ {module}")
        except ImportError:
            print(f"✗ {module} - MISSING")
            missing_modules.append(module)
    
    if missing_modules:
        print(f"\nMissing dependencies: {', '.join(missing_modules)}")
        print("Install them with:")
        print(f"  pip install {' '.join(missing_modules)}")
        return False
    
    print("All dependencies are available!")
    return True

def main():
    """Main setup function."""
    print("Project Gutenberg Book Scraper Setup")
    print("="*40)
    
    # Check dependencies
    if not check_dependencies():
        print("Please install missing dependencies before proceeding.")
        sys.exit(1)
    
    # Test scraper
    print("\nTesting scraper...")
    if not test_scraper():
        print("Scraper test failed. Please check the output above.")
        sys.exit(1)
    
    # Show cron setup instructions
    setup_cron_job()
    
    # Show manual run instructions
    print("\nMANUAL USAGE")
    print("="*60)
    project_dir = get_project_dir()
    print("To run the scraper manually:")
    print(f"  cd {project_dir}")
    print("  python scripts/scraper/bookScraper.py --help")
    print()
    print("Example commands:")
    print("  python scripts/scraper/bookScraper.py --max-books 5")
    print("  python scripts/scraper/bookScraper.py --verbose")
    print("  ./scripts/scraper/run_daily_scraper.sh")
    print("="*60)

if __name__ == "__main__":
    main()
