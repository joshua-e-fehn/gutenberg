import logging
import os
import re
from pathlib import Path
from typing import List, Optional
from google import genai
import typer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AudioBookFormatter:
    """Format book chapters for audiobook narration using Gemini API."""
    
    # Universal system prompt for audiobook formatting
    SYSTEM_PROMPT = """You are an expert audiobook formatter specializing in converting written text from any genre or time period into optimal format for text-to-speech narration. Your task is to transform written text into the perfect format for audio while preserving every word of the original content.

UNIVERSAL FORMATTING RULES FOR ALL BOOK TYPES:

1. **Chapter Headers & Structure**: 
   - If a chapter title appears twice (once as header, once in text), remove the in text version
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

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the formatter with Gemini API."""
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("Gemini API key is required. Set GEMINI_API_KEY environment variable or pass it directly.")
        
        # Initialize Google GenAI client - matching chapterChunker pattern
        try:
            self.genaiModel = genai.Client(api_key=self.api_key)
            logger.info("AudioBookFormatter initialized with Gemini API")
        except Exception as e:
            logger.error(f"Failed to initialize Google GenAI client: {e}")
            logger.error("Make sure GEMINI_API_KEY environment variable is set")
            raise ValueError("Failed to initialize Google GenAI client. Ensure GEMINI_API_KEY environment variable is set.")

    def split_text_intelligently(self, text: str, max_tokens: int = 30000) -> List[str]:
        """Split text into chunks at natural break points.
        
        With Gemini's 1M input token limit, we can handle much larger chunks.
        Using 200K tokens (~800K characters) allows for better context preservation.
        """
        # Rough estimate: 1 token ≈ 4 characters for English text
        max_chars = max_tokens * 4
        
        if len(text) <= max_chars:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # For classic literature, try to split by chapters or major sections first
        chapter_breaks = re.split(r'\n\s*(?:CHAPTER|Chapter|BOOK|Book)\s+[IVX\d]+', text)
        
        if len(chapter_breaks) > 1:
            logger.info(f"Found {len(chapter_breaks)} natural chapter/section breaks")
            # If we have natural chapter breaks, use them
            for i, section in enumerate(chapter_breaks):
                if len(section.strip()) > max_chars:
                    # If individual section is still too long, split by paragraphs
                    section_chunks = self._split_by_paragraphs(section, max_chars)
                    chunks.extend(section_chunks)
                elif section.strip():
                    chunks.append(section.strip())
        else:
            # No natural chapter breaks, split by paragraphs
            chunks = self._split_by_paragraphs(text, max_chars)
        
        logger.info(f"Split text into {len(chunks)} chunks")
        return chunks
    
    def _split_by_paragraphs(self, text: str, max_chars: int) -> List[str]:
        """Split text by paragraphs when no natural chapter breaks exist."""
        chunks = []
        current_chunk = ""
        
        # Split by paragraphs first (double newlines)
        paragraphs = text.split('\n\n')
        
        for paragraph in paragraphs:
            # If adding this paragraph would exceed the limit
            if len(current_chunk) + len(paragraph) > max_chars:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = paragraph
                else:
                    # If single paragraph is too long, split by sentences
                    sentences = re.split(r'(?<=[.!?])\s+', paragraph)
                    for sentence in sentences:
                        if len(current_chunk) + len(sentence) > max_chars:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                                current_chunk = sentence
                            else:
                                # If single sentence is still too long, force split
                                chunks.append(sentence[:max_chars])
                                current_chunk = sentence[max_chars:]
                        else:
                            current_chunk += " " + sentence if current_chunk else sentence
            else:
                current_chunk += "\n\n" + paragraph if current_chunk else paragraph
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks

    def format_text_chunk(self, text: str) -> str:
        """Format a single chunk of text using Gemini API."""
        try:
            prompt = f"{self.SYSTEM_PROMPT}\n\n{text}"
            
            response = self.genaiModel.models.generate_content(
                model="gemini-2.0-flash-exp",
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
                
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return text  # Return original text if API fails

    def format_chapter(self, chapter_path: Path) -> str:
        """Format a complete chapter file."""
        logger.info(f"Processing chapter: {chapter_path.name}")
        
        try:
            with open(chapter_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error reading file {chapter_path}: {e}")
            return ""
        
        if not content.strip():
            logger.warning(f"Empty chapter file: {chapter_path}")
            return ""
        
        # Split into manageable chunks
        chunks = self.split_text_intelligently(content)
        formatted_chunks = []
        
        for i, chunk in enumerate(chunks, 1):
            logger.info(f"Formatting chunk {i}/{len(chunks)} for {chapter_path.name}")
            formatted_chunk = self.format_text_chunk(chunk)
            formatted_chunks.append(formatted_chunk)
        
        # Join chunks with proper spacing
        formatted_content = "\n\n".join(formatted_chunks)
        logger.info(f"Successfully formatted {chapter_path.name}")
        return formatted_content

    def process_book(self, book_path: Path) -> Optional[Path]:
        """Process all chapters in a book directory."""
        logger.info(f"Processing book: {book_path.name}")
        
        chapters_dir = book_path / "chapters"
        if not chapters_dir.exists():
            logger.error(f"Chapters directory not found: {chapters_dir}")
            return None
        
        # Create formatted chapters directory
        formatted_dir = book_path / "formattedChapters"
        formatted_dir.mkdir(exist_ok=True)
        
        # Get all chapter files sorted by name
        chapter_files = sorted(chapters_dir.glob("*.txt"))
        
        if not chapter_files:
            logger.warning(f"No chapter files found in {chapters_dir}")
            return None
        
        logger.info(f"Found {len(chapter_files)} chapters to process")
        
        processed_count = 0
        for chapter_file in chapter_files:
            output_file = formatted_dir / chapter_file.name
            
            # Skip if already processed
            if output_file.exists():
                logger.info(f"Skipping existing file: {output_file.name}")
                continue
            
            formatted_content = self.format_chapter(chapter_file)
            
            if formatted_content:
                try:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(formatted_content)
                    processed_count += 1
                    logger.info(f"Saved formatted chapter: {output_file}")
                except Exception as e:
                    logger.error(f"Error saving formatted chapter {output_file}: {e}")
            else:
                logger.error(f"Failed to format chapter: {chapter_file}")
        
        logger.info(f"Successfully processed {processed_count}/{len(chapter_files)} chapters")
        return formatted_dir if processed_count > 0 else None


app = typer.Typer(help="Format book chapters for audiobook narration using Gemini AI - supports all genres: fiction, non-fiction, history, biography, classic literature, and more")


@app.command()
def format_book(
    book_path: str = typer.Argument(..., help="Path to the book directory containing 'chapters' folder"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="Gemini API key (or set GEMINI_API_KEY env var)")
) -> None:
    """
    Format all chapters in a book directory for audiobook narration.
    
    Works with ANY book genre: classic literature, modern fiction, non-fiction, 
    history, biography, science, technical books, and more.
    
    The book directory should contain a 'chapters' folder with text files.
    All chapters will be processed and saved in a new 'formattedChapters' folder
    within the book directory.
    
    Example usage:
        pixi run python scripts/audioBookFormatter.py format-book books/myBook/
    """
    book_dir = Path(book_path)
    
    if not book_dir.exists():
        logger.error(f"Book directory not found: {book_path}")
        raise typer.Exit(1)
    
    if not book_dir.is_dir():
        logger.error(f"Path is not a directory: {book_path}")
        raise typer.Exit(1)
    
    try:
        formatter = AudioBookFormatter(api_key=api_key)
        result_dir = formatter.process_book(book_dir)
        
        if result_dir:
            typer.echo(f"✅ Successfully formatted chapters!")
            typer.echo(f"📁 Formatted chapters saved in: {result_dir}")
        else:
            typer.echo("❌ No chapters were successfully formatted")
            raise typer.Exit(1)
            
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        typer.echo(f"❌ {e}")
        raise typer.Exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        typer.echo(f"❌ Error: {e}")
        raise typer.Exit(1)


@app.command()
def format_single_chapter(
    chapter_path: str = typer.Argument(..., help="Path to a single chapter text file"),
    output_path: str = typer.Argument(..., help="Path for the formatted output file"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="Gemini API key (or set GEMINI_API_KEY env var)")
) -> None:
    """Format a single chapter file for audiobook narration."""
    chapter_file = Path(chapter_path)
    output_file = Path(output_path)
    
    if not chapter_file.exists():
        logger.error(f"Chapter file not found: {chapter_path}")
        raise typer.Exit(1)
    
    try:
        formatter = AudioBookFormatter(api_key=api_key)
        formatted_content = formatter.format_chapter(chapter_file)
        
        if formatted_content:
            # Create output directory if needed
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(formatted_content)
            
            typer.echo(f"✅ Successfully formatted chapter!")
            typer.echo(f"📁 Saved to: {output_file}")
        else:
            typer.echo("❌ Failed to format chapter")
            raise typer.Exit(1)
            
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        typer.echo(f"❌ {e}")
        raise typer.Exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        typer.echo(f"❌ Error: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()