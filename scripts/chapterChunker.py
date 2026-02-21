import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup, NavigableString
import re
import typer
import json
import time
from google import genai

try:
    from dotenv import load_dotenv
    load_dotenv()  # Load environment variables from .env file
except ImportError:
    logger = logging.getLogger(__name__)
    logger.debug("python-dotenv not available, .env files will not be loaded automatically")

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class HtmlBookProcessor:
    """Class for processing HTML books into plain text format for audiobook creation."""
    
    def __init__(self, inputFile: str, outputDir: str, useLlm: bool = True, splitLongChapters: bool = True):
        """
        Initialize the HTML book processor.
        
        Args:
            inputFile: Path to the HTML book file
            outputDir: Directory to save the formatted chapter files
            useLlm: Whether to use LLM for chapter detection (now required)
            splitLongChapters: Whether to split very long chapters into parts
        """
        self.inputFile = inputFile
        self.outputDir = outputDir
        self.useLlm = useLlm
        self.splitLongChapters = splitLongChapters
        
        # Initialize Google GenAI client - it automatically gets the API key from GEMINI_API_KEY environment variable
        try:
            self.genaiModel = genai.Client()
            logger.info("Google GenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Google GenAI client: {e}")
            logger.error("Make sure GEMINI_API_KEY environment variable is set")
            raise ValueError("Failed to initialize Google GenAI client. Ensure GEMINI_API_KEY environment variable is set.")
        
    def processBook(self) -> List[str]:
        """
        Process HTML book file into plain text chapter files using LLM-based table of contents detection.
        
        Returns:
            List of paths to the generated chapter files
        """
        logger.info(f"Processing HTML book: {self.inputFile}")
        
        # Create output directory if it doesn't exist
        if not os.path.exists(self.outputDir):
            os.makedirs(self.outputDir)
        
        # Read the HTML file
        try:
            with open(self.inputFile, 'r', encoding='utf-8') as f:
                htmlContent = f.read()
        except Exception as e:
            logger.error(f"Error reading HTML file: {e}")
            raise
            
        # Parse the HTML
        soup = BeautifulSoup(htmlContent, 'html.parser')
        
        # Use LLM to detect table of contents and extract chapter links
        chapters = self._detectChaptersWithLlm(soup)
        
        if not chapters:
            logger.error("No chapters found with LLM-based table of contents detection")
            return []
            
        logger.info(f"Found {len(chapters)} chapters using LLM table of contents detection")
        
        # Validate and clean chapters
        chapters = self._validateAndCleanChapters(chapters)
        logger.info(f"After validation: {len(chapters)} valid chapters")
        
        if not chapters:
            logger.error("No valid chapters found after validation")
            return []
        
        # Split long chapters if enabled
        if self.splitLongChapters:
            chapters = self._splitLongChapters(chapters)
            logger.info(f"After splitting long chapters: {len(chapters)} total chapters")
        
        # Process each chapter
        chapterPaths = []
        
        for i, chapter in enumerate(chapters, 1):
            chapterPath = self._saveChapterToFile(chapter, i)
            if chapterPath:
                chapterPaths.append(chapterPath)
                
        return chapterPaths
    
    def _detectChaptersWithLlm(self, soup: BeautifulSoup, maxRetries: int = 2) -> List[Dict]:
        """
        Use Google Gemini to detect table of contents and extract chapter links directly.
        Includes retry logic if the detected pattern fails.
        
        Args:
            soup: BeautifulSoup object of the HTML content
            maxRetries: Maximum number of retries if pattern detection fails
            
        Returns:
            List of chapter dictionaries with title, content, and pattern info
        """
        try:
            logger.info("Starting LLM-based table of contents detection...")
            
            # Step 1: Get all chapter names and links from TOC using LLM
            chapterLinks = self._extractAllChapterLinksWithLlm(soup)
            if not chapterLinks:
                logger.error("No chapter links found in table of contents")
                return []
            
            logger.info(f"Found {len(chapterLinks)} chapter links in table of contents")
            
            # Step 2: Use LLM to find parent containers for all chapters with retry logic
            failedPatterns = []  # Track patterns that didn't work
            
            for attempt in range(maxRetries + 1):
                logger.info(f"Container detection attempt {attempt + 1}/{maxRetries + 1}")
                
                # Get chapter containers using LLM
                chapterContainers = self._findAllChapterContainersWithLlm(soup, chapterLinks, failedPatterns)
                if not chapterContainers:
                    logger.error(f"No chapter containers found on attempt {attempt + 1}")
                    if attempt == maxRetries:
                        return []
                    continue
                
                # Step 3: Extract content from each container and validate success
                chapters = []
                successfulExtractions = 0
                extractionFailures = []
                
                for containerInfo in chapterContainers:
                    chapter = self._extractContentFromChapterContainer(soup, containerInfo)
                    if chapter:
                        chapters.append(chapter)
                        successfulExtractions += 1
                    else:
                        extractionFailures.append({
                            'title': containerInfo.get('title', 'unknown'),
                            'href': containerInfo.get('href', 'unknown'),
                            'extraction_method': containerInfo.get('extraction_method', 'unknown'),
                            'container_selector': containerInfo.get('container_selector', 'unknown'),
                            'reason': 'extraction_failed'  # Could be expanded to include more specific reasons
                        })
                
                # Calculate success rate
                successRate = successfulExtractions / len(chapterContainers) if chapterContainers else 0
                logger.info(f"Attempt {attempt + 1}: {successfulExtractions}/{len(chapterContainers)} chapters extracted successfully ({successRate:.1%} success rate)")
                
                # If we have good success rate (>= 70%), use this result
                if successRate >= 0.7:
                    logger.info(f"✅ Pattern detection successful! Using results from attempt {attempt + 1}")
                    return chapters
                
                # If this is the last attempt, return what we have
                if attempt == maxRetries:
                    if chapters:
                        logger.warning(f"⚠️ Final attempt had low success rate ({successRate:.1%}), but returning {len(chapters)} chapters")
                        return chapters
                    else:
                        logger.error("❌ All attempts failed - no chapters extracted")
                        return []
                
                # Prepare feedback for next attempt
                logger.warning(f"❌ Attempt {attempt + 1} failed ({successRate:.1%} success rate). Preparing feedback for retry...")
                
                # Analyze the most common extraction method from this attempt
                currentPattern = {
                    'extraction_method': chapterContainers[0].get('extraction_method', 'unknown') if chapterContainers else 'unknown',
                    'container_selector': chapterContainers[0].get('container_selector', 'unknown') if chapterContainers else 'unknown',
                    'success_rate': successRate,
                    'failure_examples': extractionFailures[:3],  # Limit to first 3 failures
                    'attempt': attempt + 1
                }
                failedPatterns.append(currentPattern)
                
                logger.info(f"🔄 Will retry with feedback about failed pattern: {currentPattern['extraction_method']} + {currentPattern['container_selector']}")
            
            return []
            
        except Exception as e:
            logger.error(f"LLM-based chapter detection failed: {e}")
            return []
    
    def _extractAllChapterLinksWithLlm(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Use LLM to directly extract all chapter names and their links from the HTML.
        
        Args:
            soup: BeautifulSoup object of the HTML content
            
        Returns:
            List of dictionaries with chapter link information
        """
        # Get a sample of the HTML that likely contains the table of contents
        htmlSample = self._getTocHtmlSample(soup)
        
        prompt = f"""
        Analyze this HTML sample from a book and find ALL chapter links in the table of contents.
        
        HTML Sample:
        {htmlSample}

        Look for HTML structures that contain chapter links with href attributes pointing to chapter anchors.
        Examples of patterns to look for:
        1. <a href="#BOOK_I" class="pginternal">Women, Cars, and Men</a>
        2. <a href="#chap01" class="pginternal">CHAPTER I. Out to Sea</a>
        3. <a href="#linkC2HCH0001" class="pginternal">Chapter 1. Marseilles—The Arrival</a>
        4. <a href="#chapter-1" class="pginternal">I</a>

        Please respond with a JSON object containing:
        1. "found_chapters": true/false if chapters were found
        2. "chapters": array of chapter objects, each with:
           - "title": the full chapter title text
           - "href": the href value (without the # symbol)
           - "full_link": the complete <a> tag as a string
        3. "confidence": Your confidence level (0-1) in this detection

        For example:
        {{
            "found_chapters": true,
            "chapters": [
                {{
                    "title": "CHAPTER I. Out to Sea",
                    "href": "chap01",
                    "full_link": "<a href=\\"#chap01\\" class=\\"pginternal\\">CHAPTER I. Out to Sea</a>"
                }},
                {{
                    "title": "CHAPTER II. The Savage Home", 
                    "href": "chap02",
                    "full_link": "<a href=\\"#chap02\\" class=\\"pginternal\\">CHAPTER II. The Savage Home</a>"
                }}
            ],
            "confidence": 0.9
        }}

        If no chapters are found, return {{"found_chapters": false, "confidence": 0}}.
        
        Extract ALL chapters you can find in the table of contents.
        Only return the JSON object, no other text.
        """
        
        result = self._queryGeminiWithPrompt(prompt)
        
        if not result or not result.get('found_chapters'):
            logger.error("LLM could not find any chapters in the table of contents")
            return []
        
        chapters = result.get('chapters', [])
        if not chapters:
            logger.error("LLM found chapters but returned empty chapter list")
            return []
        
        # Convert to our expected format
        chapterLinks = []
        seenHrefs = set()  # Track hrefs to avoid duplicates
        
        for chapter in chapters:
            if 'title' in chapter and 'href' in chapter:
                href = chapter['href']
                # Skip if we've already seen this href (avoid duplicates)
                if href in seenHrefs:
                    logger.debug(f"Skipping duplicate chapter with href: {href}")
                    continue
                    
                seenHrefs.add(href)
                chapterLinks.append({
                    'title': chapter['title'],
                    'href': href,
                    'full_link': chapter.get('full_link', ''),
                })
        
        logger.info(f"LLM extracted {len(chapterLinks)} chapter links (after deduplication)")
        return chapterLinks
    
    def _getTocHtmlSample(self, soup: BeautifulSoup, maxLength: int = 20000) -> str:
        """
        Extract HTML sample that likely contains the table of contents.
        
        Args:
            soup: BeautifulSoup object
            maxLength: Maximum length of the sample
            
        Returns:
            HTML sample string focused on potential TOC areas
        """
        # Look for common TOC indicators in order of preference
        tocCandidates = []
        
        # Look for headings that might indicate TOC
        tocHeadings = soup.find_all(['h1', 'h2', 'h3'], 
                                   string=re.compile(r'contents?|table\s+of\s+contents?|toc', re.IGNORECASE))
        
        for heading in tocHeadings:
            # Get content after the heading
            parent = heading.find_parent(['div', 'section', 'body'])
            if parent:
                tocCandidates.append(parent)
        
        # Look for tables or lists with multiple links
        tables = soup.find_all('table')
        for table in tables:
            links = table.find_all('a', href=True)
            if len(links) > 3:  # Likely a TOC if it has many links
                tocCandidates.append(table)
        
        lists = soup.find_all(['ul', 'ol'])
        for lst in lists:
            links = lst.find_all('a', href=True)
            if len(links) > 3:
                tocCandidates.append(lst)
        
        # If no specific candidates found, use the beginning of the document
        if not tocCandidates:
            body = soup.find('body') or soup
            tocCandidates = [body]
        
        # Combine all candidates into a sample
        combinedHtml = ""
        for candidate in tocCandidates[:3]:  # Limit to first 3 candidates
            candidateHtml = str(candidate)
            if len(combinedHtml + candidateHtml) < maxLength:
                combinedHtml += candidateHtml + "\n\n"
            else:
                # Add partial content if it fits
                remainingSpace = maxLength - len(combinedHtml)
                if remainingSpace > 1000:  # Only add if there's substantial space
                    combinedHtml += candidateHtml[:remainingSpace]
                break
        
        return combinedHtml or str(soup)[:maxLength]
    
    def _extractContentUntilNextChapter(self, soup: BeautifulSoup, startElement) -> str:
        """
        Extract all content from the start element until the next chapter heading.
        
        Args:
            soup: BeautifulSoup object
            startElement: The element to start extracting from
            
        Returns:
            Extracted text content
        """
        content = []
        
        # Start from the element after our target (or the target itself if it's a heading)
        if startElement.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            # Include the chapter title
            chapterTitle = startElement.get_text(strip=True)
            content.append(chapterTitle)
            current = startElement.next_sibling
        else:
            current = startElement
        
        # Collect all content until we hit the next chapter heading or end of document
        while current:
            if hasattr(current, 'name') and current.name:
                # If it's a heading that looks like a chapter, stop
                if current.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    text = current.get_text(strip=True)
                    # Check if this looks like a chapter heading
                    if any(keyword in text.lower() for keyword in ['chapter', 'book', 'part', 'section']) or \
                       re.search(r'\b(chapter|ch\.?)\s*[ivxlcdm0-9]+', text, re.IGNORECASE):
                        # This is likely the next chapter, stop here
                        break
                
                # Extract text from paragraphs and other content elements
                if current.name in ['p', 'div', 'blockquote', 'pre']:
                    text = current.get_text(strip=True)
                    if text and len(text) > 10:  # Ignore very short text
                        content.append(text)
                elif current.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    # Include section headings within the chapter
                    text = current.get_text(strip=True)
                    if text and not any(keyword in text.lower() for keyword in ['chapter', 'book', 'part']):
                        content.append(text)
            elif isinstance(current, NavigableString):
                # Include direct text content
                text = str(current).strip()
                if text and len(text) > 10:
                    content.append(text)
            
            current = current.next_sibling
        
        return '\n\n'.join(content)
    
    def _findChapterContainer(self, targetElement) -> Optional[object]:
        """
        Find the appropriate container element for the chapter content.
        
        Args:
            targetElement: The element referenced by the chapter link
            
        Returns:
            The container element that holds the chapter content
        """
        # Try to find a semantic container
        for containerType in ['div', 'section', 'article', 'chapter']:
            container = targetElement.find_parent(containerType)
            if container:
                # Check if this container has class attributes that suggest it's a chapter
                classNames = container.get('class', [])
                if any('chapter' in str(cls).lower() or 'section' in str(cls).lower() 
                       for cls in classNames):
                    return container
        
        # If no semantic container found, look for a div that contains substantial content
        parent = targetElement
        while parent:
            parent = parent.find_parent()
            if parent and parent.name in ['div', 'section', 'article']:
                # Check if this parent contains enough text to be a chapter
                text = parent.get_text(strip=True)
                if len(text) > 500:  # Minimum chapter length
                    return parent
        
        # Fallback: return the immediate parent or the target element itself
        return targetElement.find_parent() or targetElement
    
    def _extractContentFromContainer(self, container, targetElement) -> str:
        """
        Extract text content from a chapter container.
        
        Args:
            container: The container element holding the chapter
            targetElement: The original target element (for reference)
            
        Returns:
            Extracted text content
        """
        content = []
        
        # Start collecting content from the target element or after it
        startCollecting = False
        
        for element in container.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'], recursive=True):
            # Skip if we haven't reached the target element area yet
            if not startCollecting:
                if element == targetElement or targetElement in element.parents:
                    startCollecting = True
                elif element.find(id=targetElement.get('id')) if targetElement.get('id') else False:
                    startCollecting = True
                else:
                    continue
            
            # Extract text from the element
            text = element.get_text(strip=True)
            if text and len(text) > 10:  # Ignore very short text
                content.append(text)
            
            # Stop if we hit the next chapter (heuristic)
            if startCollecting and len(content) > 5:  # After collecting some content
                if element.name in ['h1', 'h2', 'h3'] and any(
                    keyword in text.lower() for keyword in ['chapter', 'book', 'part', 'section']
                ):
                    # This might be the next chapter, stop here
                    break
        
        return '\n\n'.join(content)
    
    def _queryGeminiWithPrompt(self, prompt: str, maxOutputTokens: int = 8000) -> Optional[Dict]:
        """
        Generic method to query Gemini with a custom prompt using the Google GenAI client.
        Includes retry logic for empty or truncated responses.
        
        Args:
            prompt: The prompt to send to Gemini
            maxOutputTokens: Maximum output tokens for the response
            
        Returns:
            Parsed JSON response or None if failed
        """
        maxRetries = 3
        currentTokens = maxOutputTokens
        
        for attempt in range(maxRetries):
            try:
                logger.debug(f"Sending prompt to Gemini (attempt {attempt + 1}/{maxRetries}, length: {len(prompt)} characters, max_tokens: {currentTokens})")
                
                # Use the Google Generative AI client
                response = self.genaiModel.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=currentTokens
                    )
                )
                
                # Extract text from response
                if response and response.text:
                    content = response.text.strip()
                    logger.debug(f"Gemini response (length: {len(content)} characters): {content[:1000]}...")
                    
                    # Check if response appears empty or too short
                    if len(content) < 50:
                        logger.warning(f"Response too short on attempt {attempt + 1}: {len(content)} characters")
                        if attempt < maxRetries - 1:
                            currentTokens *= 2  # Double tokens for next attempt
                            logger.info(f"Retrying with increased tokens: {currentTokens}")
                            continue
                        else:
                            logger.error("All retry attempts failed - response too short")
                            return None
                    
                    # Try to extract JSON from the response
                    try:
                        # Remove any markdown formatting
                        if content.startswith('```json'):
                            content = content[7:]
                        if content.endswith('```'):
                            content = content[:-3]
                        content = content.strip()
                        
                        # Try to parse JSON
                        result = json.loads(content)
                        logger.debug(f"Successfully parsed JSON response on attempt {attempt + 1}")
                        return result
                        
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse JSON on attempt {attempt + 1}: {e}")
                        logger.debug(f"Raw response: {content}")
                        
                        # Check if response was truncated (common issue)
                        if len(content) > 500 and not content.rstrip().endswith('}'):
                            logger.warning("Response appears to be truncated - likely due to token limit")
                            if attempt < maxRetries - 1:
                                currentTokens *= 2  # Double tokens for next attempt
                                logger.info(f"Retrying with increased tokens: {currentTokens}")
                                continue
                            else:
                                logger.error("All retry attempts failed - response still truncated")
                                return None
                        
                        # If it's the last attempt, return None
                        if attempt == maxRetries - 1:
                            logger.error("All retry attempts failed - JSON parsing failed")
                            return None
                        
                        # Otherwise, retry with same settings
                        logger.info(f"Retrying JSON parsing (attempt {attempt + 2}/{maxRetries})")
                        continue
                        
                else:
                    logger.warning(f"No text content in Gemini response on attempt {attempt + 1}")
                    if attempt < maxRetries - 1:
                        logger.info(f"Retrying due to empty response (attempt {attempt + 2}/{maxRetries})")
                        continue
                    else:
                        logger.error("All retry attempts failed - no response content")
                        return None
                
            except Exception as e:
                logger.warning(f"Error querying Gemini API on attempt {attempt + 1}: {e}")
                if attempt < maxRetries - 1:
                    logger.info(f"Retrying due to API error (attempt {attempt + 2}/{maxRetries})")
                    continue
                else:
                    logger.error("All retry attempts failed - API error")
                    return None
        
        return None
    
    def _saveChapterToFile(self, chapter: Dict, index: int) -> Optional[str]:
        """
        Save a chapter to a plain text file.
        
        Args:
            chapter: Dictionary containing chapter data
            index: Chapter index for filename
            
        Returns:
            Path to the saved chapter file, or None if saving failed
        """
        try:
            title = chapter['title']
            content = chapter['content']
            
            # If no explicit title, use numbered format
            if not title or title == "Chapter":
                title = self._generateChapterTitle(index)
            
            logger.info(f"Processing chapter {index}: {title}")
            
            # Format the chapter content as plain text
            formattedText = f"{title}\n\n{content}"
            
            # Save to file
            baseFileName = Path(self.inputFile).stem
            outFileName = f"{baseFileName}_chapter_{index:02d}.txt"
            outPath = os.path.join(self.outputDir, outFileName)
            
            with open(outPath, 'w', encoding='utf-8') as f:
                f.write(formattedText)
                
            logger.info(f"Saved chapter {index} to {outPath}")
            return outPath
            
        except Exception as e:
            logger.error(f"Error saving chapter {index}: {e}")
            return None
    
    def _generateChapterTitle(self, index: int) -> str:
        """Generate a chapter title using number words."""
        numberWords = [
            "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
            "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", 
            "Eighteen", "Nineteen", "Twenty", "Twenty-One", "Twenty-Two", "Twenty-Three",
            "Twenty-Four", "Twenty-Five", "Twenty-Six", "Twenty-Seven", "Twenty-Eight",
            "Twenty-Nine", "Thirty"
        ]
        
        if index < len(numberWords):
            return f"Chapter {numberWords[index]}"
        else:
            return f"Chapter {index}"
    
    def _validateAndCleanChapters(self, chapters: List[Dict]) -> List[Dict]:
        """
        Validate and clean chapter content to ensure quality.
        
        Args:
            chapters: List of raw chapter dictionaries
            
        Returns:
            List of validated and cleaned chapter dictionaries
        """
        validChapters = []
        
        for i, chapter in enumerate(chapters):
            title = chapter.get('title', '').strip()
            content = chapter.get('content', '').strip()
            
            # Skip chapters with insufficient content
            if len(content) < 100:  # Minimum 100 characters
                logger.debug(f"Skipping chapter {i+1} - insufficient content ({len(content)} chars)")
                continue
            
            # Clean up title
            if not title or title == "Chapter":
                title = self._generateChapterTitle(i + 1)
            
            # Clean up content - remove excessive whitespace
            content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)  # Collapse multiple newlines
            content = re.sub(r'[ \t]+', ' ', content)  # Collapse multiple spaces
            
            # Remove common artifacts
            content = re.sub(r'\[Illustration[^\]]*\]', '', content, flags=re.IGNORECASE)
            content = re.sub(r'\[Page \d+\]', '', content, flags=re.IGNORECASE)
            content = re.sub(r'Project Gutenberg.*?END OF.*?PROJECT GUTENBERG', '', content, flags=re.DOTALL | re.IGNORECASE)
            
            # Ensure content still has substance after cleaning
            if len(content.strip()) < 100:
                logger.debug(f"Skipping chapter {i+1} - insufficient content after cleaning")
                continue
            
            validChapters.append({
                'title': title,
                'content': content.strip(),
                'pattern': chapter.get('pattern', 'unknown')
            })
        
        return validChapters
    
    def _splitLongChapters(self, chapters: List[Dict], maxLength: int = 5000) -> List[Dict]:
        """
        Split very long chapters into smaller chunks for better TTS processing.
        
        Args:
            chapters: List of chapter dictionaries
            maxLength: Maximum length in characters for a single chunk
            
        Returns:
            List of chapter dictionaries with long chapters split
        """
        processedChapters = []
        
        for chapter in chapters:
            content = chapter['content']
            title = chapter['title']
            
            if len(content) <= maxLength:
                processedChapters.append(chapter)
                continue
            
            # Split long chapter into parts
            sentences = re.split(r'(?<=[.!?])\s+', content)
            currentChunk = ""
            chunkNumber = 1
            
            for sentence in sentences:
                if len(currentChunk + sentence) <= maxLength:
                    currentChunk += sentence + " "
                else:
                    # Save current chunk
                    if currentChunk.strip():
                        processedChapters.append({
                            'title': f"{title} - Part {chunkNumber}",
                            'content': currentChunk.strip(),
                            'pattern': chapter['pattern']
                        })
                        chunkNumber += 1
                    
                    # Start new chunk
                    currentChunk = sentence + " "
            
            # Add remaining content
            if currentChunk.strip():
                processedChapters.append({
                    'title': f"{title} - Part {chunkNumber}",
                    'content': currentChunk.strip(),
                    'pattern': chapter['pattern']
                })
        
        return processedChapters

    def _findAllChapterContainersWithLlm(self, soup: BeautifulSoup, chapterLinks: List[Dict], failedPatterns: List[Dict] = None) -> List[Dict]:
        """
        Use LLM to find parent containers for all chapter links in one query.
        Includes feedback from previous failed attempts to improve detection.
        
        Args:
            soup: BeautifulSoup object
            chapterLinks: List of chapter link information
            failedPatterns: List of patterns that failed in previous attempts
            
        Returns:
            List of dictionaries with chapter container information
        """
        try:
            if failedPatterns:
                logger.info(f"Finding parent containers using LLM with feedback from {len(failedPatterns)} failed pattern(s)...")
            else:
                logger.info("Finding parent containers for all chapters using LLM...")
            
            # Select chapters 2-10 for context analysis (skip first chapter, limit to max 9 chapters for analysis)
            analysisChapters = chapterLinks[1:10] if len(chapterLinks) > 1 else chapterLinks
            logger.info(f"Using chapters 2-{min(10, len(chapterLinks))} for pattern analysis ({len(analysisChapters)} chapters)")
            
            # Gather HTML context around each selected chapter anchor
            contextData = []
            for linkInfo in analysisChapters:
                href = linkInfo['href']
                title = linkInfo['title']
                
                # Find the target element
                targetElement = soup.find(id=href)
                if not targetElement:
                    targetElement = soup.find('a', name=href)
                    if targetElement:
                        targetElement = targetElement.find_parent(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']) or targetElement.find_parent()
                
                if targetElement:
                    # Get HTML context (before and after the target element)
                    contextHtml = self._getChapterContextHtml(targetElement, maxLength=5000)  # Reduced from 8000 to save tokens for output
                    contextData.append({
                        'href': href,
                        'title': title,
                        'context_html': contextHtml,
                        'target_tag': f'<{targetElement.name} id="{href}">' if targetElement.get('id') == href else f'<{targetElement.name}>'
                    })
                else:
                    logger.warning(f"Could not find target element for chapter: {title} (href: {href})")
            
            if not contextData:
                logger.error("No context data found for chapters")
                return []
            
            # Create structured prompt for LLM using only the selected chapters
            prompt = self._createContainerDetectionPrompt(contextData, failedPatterns)
            
            # Debug: log the prompt being sent
            logger.debug(f"Container detection prompt length: {len(prompt)} characters")
            logger.debug(f"Context data count: {len(contextData)}")
            for i, data in enumerate(contextData):
                logger.debug(f"Analysis chapter {i+1}: {data['title']} - context length: {len(data['context_html'])}")
            
            # Query LLM to find containers
            result = self._queryGeminiWithPrompt(prompt)
            
            if not result or not result.get('found_containers'):
                logger.error("LLM could not find chapter containers")
                return []
            
            containers = result.get('containers', [])
            logger.info(f"LLM found {len(containers)} chapter containers from analysis")
            
            # Apply the detected pattern to ALL chapters (including chapter 1 and chapters beyond 10)
            # Create container info for all chapters using the most common values for each attribute
            allContainers = []
            if containers:
                # Analyze each attribute separately to find the most common value
                extractionMethods = [container.get('extraction_method', 'container_only') for container in containers]
                containerSelectors = [container.get('container_selector', 'div.chapter') for container in containers]
                contentStarts = [container.get('content_start', 'within_container') for container in containers]
                contentEndMarkers = [container.get('content_end_marker', 'div.chapter') for container in containers]
                stopAtElementsLists = [container.get('stop_at_elements', ['div.chapter']) for container in containers]
                
                # Function to find most common value
                def getMostCommon(values, default):
                    if not values:
                        return default
                    counts = {}
                    for value in values:
                        # Handle lists by converting to string for comparison
                        key = str(value) if isinstance(value, list) else value
                        counts[key] = counts.get(key, 0) + 1
                    mostCommonKey = max(counts, key=counts.get)
                    # For stop_at_elements, find the original list value
                    if isinstance(values[0], list):
                        for value in values:
                            if str(value) == mostCommonKey:
                                return value
                    return mostCommonKey
                
                # Find most common value for each attribute
                mostCommonMethod = getMostCommon(extractionMethods, 'container_plus_following')
                mostCommonSelector = getMostCommon(containerSelectors, 'div.chapter')
                mostCommonContentStart = getMostCommon(contentStarts, 'within_container')
                mostCommonEndMarker = getMostCommon(contentEndMarkers, 'div.chapter')
                mostCommonStopElements = getMostCommon(stopAtElementsLists, ['div.chapter'])
                
                # Calculate average confidence from analyzed chapters
                confidenceValues = [container.get('confidence', 0.5) for container in containers]
                averageConfidence = sum(confidenceValues) / len(confidenceValues) if confidenceValues else 0.8
                
                # Log analysis results
                logger.info(f"📊 ATTRIBUTE ANALYSIS from {len(containers)} chapters:")
                logger.info(f"   extraction_method: {mostCommonMethod} (from {extractionMethods})")
                logger.info(f"   container_selector: {mostCommonSelector} (from {set(containerSelectors)})")
                logger.info(f"   content_start: {mostCommonContentStart} (from {set(contentStarts)})")
                logger.info(f"   content_end_marker: {mostCommonEndMarker} (from {set(contentEndMarkers)})")
                logger.info(f"   stop_at_elements: {mostCommonStopElements} (from {set(str(x) for x in stopAtElementsLists)})")
                logger.info(f"   average_confidence: {averageConfidence:.3f} (from {confidenceValues})")
                
                logger.info(f"Applying most common pattern to all {len(chapterLinks)} chapters")
                
                # Create container info for ALL chapters using the detected pattern
                for linkInfo in chapterLinks:
                    allContainers.append({
                        'href': linkInfo['href'],
                        'title': linkInfo['title'],
                        'extraction_method': mostCommonMethod,
                        'container_selector': mostCommonSelector,
                        'content_start': mostCommonContentStart,
                        'content_end_marker': mostCommonEndMarker,
                        'stop_at_elements': mostCommonStopElements,
                        'confidence': averageConfidence  # Use actual average confidence from analyzed chapters
                    })
                    logger.debug(f"Applied most common pattern to chapter: {linkInfo['title']}")
            
            return allContainers
            
        except Exception as e:
            logger.error(f"Error finding chapter containers with LLM: {e}")
            return []
    
    def _getChapterContextHtml(self, targetElement, maxLength: int = 5000) -> str:
        """
        Get HTML context around a target element (before and after).
        
        Args:
            targetElement: The element to get context for
            maxLength: Maximum length of context
            
        Returns:
            HTML context string
        """
        contextParts = []
        
        # Get the target element itself first
        targetHtml = str(targetElement)
        contextParts.append(f"<!-- TARGET ELEMENT -->\n{targetHtml}")
        
        # Get parent context - look for chapter containers
        parent = targetElement.parent
        ancestorDepth = 0
        while parent and ancestorDepth < 3:  # Reduced from 5 to 3 to save tokens
            parentHtml = str(parent)
            if len(parentHtml) < maxLength * 3:  # Include parent if not too large
                contextParts.insert(0, f"<!-- PARENT LEVEL {ancestorDepth + 1} -->\n{parentHtml[:1000]}...")  # Reduced from 1500 to 1000
            parent = parent.parent
            ancestorDepth += 1
        
        # Get following siblings (limited amount) - this is where chapter content usually is
        nextSiblings = []
        current = targetElement.next_sibling
        nextLength = 0
        siblingCount = 0
        
        while current and nextLength < maxLength and siblingCount < 10:  # Reduced from 15 to 10 siblings
            if hasattr(current, 'name') and current.name:
                siblingHtml = str(current)
                # Stop if we hit another chapter heading
                if current.name in ['h1', 'h2', 'h3'] and any(word in current.get_text().lower() 
                                                            for word in ['book', 'chapter', 'part']):
                    nextSiblings.append(f"<!-- NEXT CHAPTER DETECTED: {current.get_text()[:50]} -->")
                    break
                
                if nextLength + len(siblingHtml) < maxLength:
                    nextSiblings.append(siblingHtml)
                    nextLength += len(siblingHtml)
                    siblingCount += 1
                else:
                    break
            current = current.next_sibling
        
        # Combine all parts
        if nextSiblings:
            contextParts.extend(["\n<!-- FOLLOWING CONTENT -->"] + nextSiblings)
        
        combinedHtml = '\n'.join(contextParts)
        
        # Increase the truncation limit
        if len(combinedHtml) > maxLength * 2:  # Increased truncation threshold
            combinedHtml = combinedHtml[:maxLength * 2] + "\n<!-- TRUNCATED -->"
        
        return combinedHtml
    
    def _createContainerDetectionPrompt(self, contextData: List[Dict], failedPatterns: List[Dict] = None) -> str:
        """
        Create a prompt for LLM to detect chapter containers.
        Includes feedback from failed attempts to improve detection.
        
        Args:
            contextData: List of context data for each chapter
            failedPatterns: List of patterns that failed in previous attempts
            
        Returns:
            Formatted prompt string
        """
        contextSections = []
        for i, data in enumerate(contextData, 1):
            contextSections.append(f"""
CHAPTER {i}: {data['title']} (href: {data['href']})
Target element: {data['target_tag']}
HTML Context:
{data['context_html']}
""")
        
        combinedContext = '\n'.join(contextSections)
        
        # Create feedback section about failed patterns
        failedPatternsSection = ""
        if failedPatterns:
            failedPatternsSection = "\n\n⚠️ IMPORTANT - AVOID THESE FAILED PATTERNS:\n"
            for i, pattern in enumerate(failedPatterns, 1):
                failedPatternsSection += f"""
FAILED PATTERN {i} (Attempt {pattern.get('attempt', 'unknown')}):
- extraction_method: {pattern.get('extraction_method', 'unknown')}
- container_selector: {pattern.get('container_selector', 'unknown')}
- Success Rate: {pattern.get('success_rate', 0):.1%}
- Failed Examples: {pattern.get('failure_examples', [])}

This pattern DID NOT WORK - please try a different approach!
"""
            failedPatternsSection += "\nPlease analyze why these patterns failed and choose a DIFFERENT approach.\n"
        
        prompt = f"""
Analyze the HTML structure for each chapter and determine the BEST METHOD to extract the complete chapter content.
{failedPatternsSection}
{combinedContext}

I need you to understand different chapter organization patterns:

These are some examples:
PATTERN 1 - Container wraps everything:
<div class="chapter">
  <h2>Chapter Title</h2>
  <p>Chapter content here...</p>
  <p>More content...</p>
</div>

PATTERN 2 - Header div + following content:
<div class="chapter">
  <h2>Chapter Title</h2>
</div>
<p>Chapter content starts here...</p>
<p>More content...</p>

PATTERN 3 - Header div + separator + content:
<hr class="chap">
<div class="chapter">
  <h2>Chapter Title</h2>
</div>
<p>Content follows...</p>

PATTERN 4 - ID-based sections:
<div id="chapter-4">
  <h2>IV</h2>
  <p>Content here...</p>
</div>

Your task is to identify which pattern each chapter follows and provide extraction instructions.

For each chapter, analyse:
1. Does the chapter container include ALL content, or just the heading?
2. If just the heading, where does the actual content start?
3. What marks the END of this chapter's content?
4. Look at the HTML context to see where the bulk of the chapter text is located


Please respond with a JSON object:
{{
    "found_containers": true/false,
    "pattern_analysis": "Brief description of the pattern found",
    "containers": [
        {{
            "href": "BOOK_I",
            "title": "Women, Cars, and Men",
            "extraction_method": "container_only|container_plus_following|following_only",
            "container_selector": "div.chapter",
            "content_start": "after_container|within_container|next_sibling",
            "content_end_marker": "next_chapter|hr.chap|div.chapter|end_of_document",
            "stop_at_elements": ["hr.chap", "div.chapter"],
            "confidence": 0.9
        }}
    ]
}}

EXTRACTION_METHOD options:
- "container_only": All content is within the container
- "container_plus_following": Container has title, content follows after
- "following_only": Container is just structure, real content starts after

CONTENT_START options:
- "within_container": Content is inside the identified container
- "after_container": Content starts after the container element
- "next_sibling": Content is in the next sibling element

{"DO NOT use the failed patterns mentioned above!" if failedPatterns else ""}
Choose the method that will capture the complete chapter content from title to the start of the next chapter.
Analyze the HTML structure carefully and pick a DIFFERENT approach if previous attempts failed.
Only return the JSON object, no other text.
"""
        
        return prompt
    
    def _extractContentFromChapterContainer(self, soup: BeautifulSoup, containerInfo: Dict) -> Optional[Dict]:
        """
        Extract chapter content using flexible methods determined by LLM.
        
        Args:
            soup: BeautifulSoup object
            containerInfo: Container information from LLM with extraction method
            
        Returns:
            Dictionary with chapter title and content, or None if extraction fails
        """
        try:
            href = containerInfo['href']
            title = containerInfo['title']
            extractionMethod = containerInfo.get('extraction_method', 'container_only')
            containerSelector = containerInfo.get('container_selector', '')
            contentStart = containerInfo.get('content_start', 'within_container')
            stopAtElements = containerInfo.get('stop_at_elements', ['hr.chap', 'div.chapter'])
            
            logger.debug(f"Extracting content for chapter: {title} (href: {href})")
            logger.debug(f"Method: {extractionMethod}, Start: {contentStart}, Stop at: {stopAtElements}")
            
            # Find the container or starting element
            container = self._findChapterElement(soup, containerSelector, href)
            if not container:
                logger.warning(f"Could not find container for chapter: {title} (href: {href})")
                return None
            
            logger.debug(f"Found container for {title}: {container.name} with {len(str(container))} characters")
            logger.debug(f"Container ID: {container.get('id', 'no-id')}, Classes: {container.get('class', 'no-class')}")
            
            # Verify we have the right container by checking if it contains the target element or is the target element
            targetCheck = None
            try:
                targetCheck = container.find(id=href) or container.find('a', attrs={'name': href})
            except Exception as e:
                logger.debug(f"Error in target verification: {e}")
            
            # Also check if the container itself is the target element
            is_target_element = container.get('id') == href
            
            if not targetCheck and not is_target_element:
                logger.warning(f"Container for {title} doesn't contain expected target element {href}")
            
            # Log the actual container used for this specific chapter
            logger.info(f"Chapter {title} -> Using container: {container.name}#{container.get('id', 'no-id')} with classes {container.get('class', 'no-class')}")
            
            # Extract content based on the method determined by LLM
            content = ""
            
            if extractionMethod == "container_only":
                # All content is within the container
                logger.debug(f"Container HTML preview: {str(container)[:500]}...")
                content = self._extractTextFromContainer(container)
                
            elif extractionMethod == "container_plus_following":
                # Container has title, content follows after
                titleText = self._extractTextFromContainer(container)
                followingContent = self._extractFollowingContent(container, stopAtElements)
                content = f"{titleText}\n\n{followingContent}" if followingContent else titleText
                
            elif extractionMethod == "following_only":
                # Container is just structure, real content starts after
                content = self._extractFollowingContent(container, stopAtElements)
                if not content:
                    # Fallback to container content if no following content found
                    content = self._extractTextFromContainer(container)
            
            # Debug: show what was actually found
            logger.debug(f"Raw extracted content: '{content[:200]}...' (total length: {len(content)})")
            
            if content and len(content.strip()) > 50:  # Minimum content threshold
                logger.debug(f"Extracted {len(content)} characters for chapter: {title}")
                return {
                    'title': title,
                    'content': content.strip(),
                    'pattern': f'llm_flexible_{extractionMethod}',
                    'href': href,
                    'container_info': containerInfo
                }
            else:
                logger.warning(f"Insufficient content for chapter: {title} (length: {len(content) if content else 0})")
                return None
                
        except Exception as e:
            logger.error(f"Error extracting content for chapter {containerInfo.get('title', 'unknown')}: {e}")
            return None
    
    def _findChapterElement(self, soup: BeautifulSoup, containerSelector: str, href: str):
        """
        Find the chapter element using href-specific lookup first, then container logic.
        
        Args:
            soup: BeautifulSoup object
            containerSelector: CSS selector for the container (used as guidance)
            href: Chapter href for specific lookup
            
        Returns:
            Found element or None
        """
        # PRIORITY 1: Find the specific chapter element first by its href
        targetElement = soup.find(id=href) or soup.find('a', name=href)
        
        if not targetElement:
            logger.warning(f"Could not find target element for href: {href}")
            return None
            
        logger.debug(f"Found target element for {href}: {targetElement.name} with ID: {targetElement.get('id', 'no-id')}")
        
        # SPECIAL CASE: If the target element itself is a div with the chapter ID, use it directly
        # This handles cases like <div id="chapter-1"> where the div IS the chapter container
        if (targetElement.name == 'div' and 
            targetElement.get('id') == href and 
            len(targetElement.get_text(strip=True)) > 500):
            logger.debug(f"Target element {href} is itself a chapter container div")
            return targetElement
        
        # PRIORITY 2: Look through parents of the target element to find chapter containers FIRST
        # This ensures we always try to find a proper container before falling back
        for parent in targetElement.parents:
            # Look for semantic containers with meaningful classes (highest priority)
            if parent.name in ['div', 'section', 'article']:
                classes = parent.get('class', [])
                if any(cls for cls in classes if 'chapter' in cls.lower() or 'book' in cls.lower()):
                    logger.debug(f"Found container via parent with chapter/book class for {href}: {parent.get('class')}")
                    return parent
                
                # Also check if parent has an ID that suggests it's a chapter container
                parent_id = parent.get('id', '')
                if ('chapter' in parent_id.lower() and 
                    len(parent.get_text(strip=True)) > 500):
                    logger.debug(f"Found container via parent with chapter ID for {href}: {parent_id}")
                    return parent
        
        # PRIORITY 3: Look for containers with significant content
        for parent in targetElement.parents:
            if parent.name in ['div', 'section', 'article']:
                # Check if this parent has substantial content (likely a chapter container)
                text_content = parent.get_text(strip=True)
                if len(text_content) > 500:  # Has substantial content
                    logger.debug(f"Found substantial container for {href}: {parent.name} with {len(text_content)} chars")
                    return parent
        
        # PRIORITY 4: Try CSS selector as backup (moved lower in priority)
        if containerSelector:
            try:
                # Look for containers of the expected type that contain our target
                containers = soup.select(containerSelector)
                for container in containers:
                    # Check if this container contains our specific target element
                    if container.find(id=href) or container.find('a', name=href):
                        logger.debug(f"Found specific container for {href} using selector: {containerSelector}")
                        return container
            except Exception as e:
                logger.debug(f"CSS selector failed: {e}")
        
        # PRIORITY 5: Look for any reasonable parent container as last resort
        for parent in targetElement.parents:
            if parent.name in ['div', 'section', 'article']:
                # Even if it doesn't have chapter class, if it has some content, use it
                text_content = parent.get_text(strip=True)
                if len(text_content) > 100:  # Lower threshold for last resort
                    logger.debug(f"Found fallback container for {href}: {parent.name} with {len(text_content)} chars")
                    return parent
        
        # PRIORITY 6: Return the target element itself only if absolutely no container found
        logger.warning(f"No suitable container found for {href}, using target element itself")
        return targetElement
    
    def _extractFollowingContent(self, startElement, stopAtElements: List[str]) -> str:
        """
        Extract content that follows after a container element until stop markers.
        
        Args:
            startElement: The element to start after
            stopAtElements: List of CSS selectors that mark the end of content
            
        Returns:
            Extracted text content
        """
        content = []
        current = startElement.next_sibling
        
        logger.debug(f"Extracting following content, stopping at: {stopAtElements}")
        
        while current:
            if hasattr(current, 'name') and current.name:
                # Check if this element matches any stop condition
                shouldStop = False
                
                for stopSelector in stopAtElements:
                    try:
                        # Parse simple selectors like "hr.chap", "div.chapter"
                        if '.' in stopSelector:
                            tag, className = stopSelector.split('.', 1)
                            if (current.name == tag and 
                                current.get('class') and 
                                className in current.get('class')):
                                shouldStop = True
                                logger.debug(f"Stopped at element: {stopSelector}")
                                break
                        elif current.name == stopSelector:
                            shouldStop = True
                            logger.debug(f"Stopped at element: {stopSelector}")
                            break
                    except:
                        continue
                
                if shouldStop:
                    break
                
                # Extract text from content elements
                if current.name in ['p', 'div', 'blockquote', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    text = current.get_text(strip=True)
                    if text and len(text) > 10:
                        # Skip common artifacts
                        if not any(skip_word in text.lower() for skip_word in 
                                 ['table of contents', 'next chapter', 'previous chapter', 'back to top']):
                            if not re.match(r'^\[?(page|illustration|figure)\s*\d*\]?$', text, re.IGNORECASE):
                                content.append(text)
            
            current = current.next_sibling
        
        # Join content with appropriate spacing
        result = '\n\n'.join(content)
        
        # Clean up excessive whitespace
        result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)  # Collapse multiple newlines
        result = re.sub(r'[ \t]+', ' ', result)  # Collapse multiple spaces
        
        logger.debug(f"Following content extracted: {len(result)} characters")
        return result.strip()
    
    def _extractTextFromContainer(self, container) -> str:
        """
        Extract clean text content from a container element.
        
        Args:
            container: BeautifulSoup element containing chapter content
            
        Returns:
            Extracted and cleaned text content
        """
        if not container:
            logger.warning("No container provided to _extractTextFromContainer")
            return ""
        
        # Debug: log what we're working with
        container_info = f"{container.name}"
        if container.get('class'):
            container_info += f".{'.'.join(container.get('class'))}"
        if container.get('id'):
            container_info += f"#{container.get('id')}"
        
        logger.debug(f"Extracting text from container: {container_info}")
        logger.debug(f"Container HTML preview: {str(container)[:500]}...")
        
        content = []
        
        # First try to get all text from the container, including nested content
        allText = container.get_text(separator=' ', strip=True)  # Use space separator to keep inline elements together
        logger.debug(f"Direct text extraction got {len(allText)} characters: '{allText[:200]}...'")
        
        # If we get substantial content this way, use it
        if len(allText) > 200:  # If we get good content directly
            # Split into paragraphs by looking for sentence endings followed by multiple spaces or new content
            paragraphs = []
            sentences = re.split(r'([.!?])\s+', allText)
            
            current_paragraph = ""
            for i in range(0, len(sentences), 2):
                sentence = sentences[i]
                if i + 1 < len(sentences):
                    punct = sentences[i + 1]
                    sentence += punct
                
                current_paragraph += sentence + " "
                
                # Check if this looks like the end of a paragraph (heuristic)
                if len(current_paragraph.strip()) > 100 and (
                    sentence.strip().endswith('.') or 
                    sentence.strip().endswith('!') or 
                    sentence.strip().endswith('?')
                ):
                    cleaned_para = current_paragraph.strip()
                    if len(cleaned_para) > 20:  # Skip very short paragraphs
                        # Skip navigation elements and common artifacts
                        if not any(skip_word in cleaned_para.lower() for skip_word in 
                                 ['table of contents', 'next chapter', 'previous chapter', 'back to top']):
                            # Skip page numbers and illustrations
                            if not re.match(r'^\[?(page|illustration|figure)\s*\d*\]?$', cleaned_para, re.IGNORECASE):
                                paragraphs.append(cleaned_para)
                    current_paragraph = ""
            
            # Add remaining content
            if current_paragraph.strip():
                cleaned_para = current_paragraph.strip()
                if len(cleaned_para) > 20:
                    if not any(skip_word in cleaned_para.lower() for skip_word in 
                             ['table of contents', 'next chapter', 'previous chapter', 'back to top']):
                        if not re.match(r'^\[?(page|illustration|figure)\s*\d*\]?$', cleaned_para, re.IGNORECASE):
                            paragraphs.append(cleaned_para)
            
            result = '\n\n'.join(paragraphs)
            
            # Clean up excessive whitespace
            result = re.sub(r'\s+', ' ', result)  # Normalize all whitespace
            result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)  # Collapse multiple newlines
            
            logger.debug(f"Extracted content using direct text extraction: {len(result)} characters")
            return result.strip()
        
        # Fallback: extract text from specific elements within the container
        logger.debug("Using element-by-element extraction fallback")
        elements_found = container.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div', 'blockquote', 'pre', 'span'])
        logger.debug(f"Found {len(elements_found)} elements to check")
        
        for element in elements_found:
            text = element.get_text(strip=True)
            
            # Debug: log what we're checking
            logger.debug(f"Checking element {element.name}: '{text[:100]}...' (length: {len(text)})")
            
            # Skip very short text and common artifacts (changed from 10 to 2 to preserve dropcaps)
            if len(text) < 2:
                logger.debug(f"  Skipping: too short ({len(text)} chars)")
                continue
            
            # Skip navigation elements and common artifacts
            if any(skip_word in text.lower() for skip_word in ['table of contents', 'next chapter', 'previous chapter', 'back to top']):
                logger.debug(f"  Skipping: navigation artifact")
                continue
                
            # Skip page numbers and illustrations
            if re.match(r'^\[?(page|illustration|figure)\s*\d*\]?$', text, re.IGNORECASE):
                logger.debug(f"  Skipping: page/illustration reference")
                continue
            
            logger.debug(f"  Adding: '{text[:50]}...'")
            content.append(text)
        
        # Join content with appropriate spacing
        result = '\n\n'.join(content)
        
        # Clean up excessive whitespace
        result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)  # Collapse multiple newlines
        result = re.sub(r'[ \t]+', ' ', result)  # Collapse multiple spaces
        
        logger.debug(f"Final extracted content using element-by-element extraction: {len(result)} characters")
        logger.debug(f"Final content preview: '{result[:200]}...'")
        return result.strip()
        

app = typer.Typer(help="Convert HTML books to plain text files for audiobooks")


@app.command()
def convert_html(
    inputFile: str = typer.Option(..., "--input", "-i", help="Path to the HTML book file to process"),
    outputDir: str = typer.Option("", "--output", "-o", help="Output directory for text files (defaults to bookname_chapters)"),
    useLlm: bool = typer.Option(True, "--use-llm/--no-llm", help="Use LLM for chapter detection (required - this option is kept for compatibility)"),
    splitLongChapters: bool = typer.Option(True, "--split-long/--no-split", help="Split very long chapters into smaller parts"),
    geminiApiKey: str = typer.Option("", "--gemini-key", help="Google Gemini API key (or set GEMINI_API_KEY in environment/.env file)")
) -> None:
    """
    Convert HTML books to plain text files for audiobooks using LLM-based table of contents detection.
    
    This version uses Google Gemini LLM to:
    - Find and analyze the table of contents in the HTML
    - Extract ALL chapter names and their corresponding links
    - Follow each link to extract the complete chapter content
    - Automatically validate and clean chapter content
    - Split very long chapters into smaller parts for better TTS processing
    
    REQUIRED: Set GEMINI_API_KEY in:
    - Environment variable: export GEMINI_API_KEY="your-key"
    - .env file in current/parent directory: GEMINI_API_KEY=your-key
    - Command line: --gemini-key your-key
    
    The LLM will extract chapter information in the format:
    {CHAPTER XXIV. Lost Treasure; <a href="#chap24" class="pginternal">CHAPTER XXIV. Lost Treasure</a>}
    
    Returns the path to the output directory containing the processed files.
    """
    # Set API key if provided
    if geminiApiKey:
        os.environ["GEMINI_API_KEY"] = geminiApiKey
    
    # Check if input file exists
    if not os.path.isfile(inputFile):
        logger.error(f"Input file not found: {inputFile}")
        raise typer.Exit(1)
    
    # Determine output directory
    if not outputDir:
        inputBaseName = Path(inputFile).stem
        outputDir = f"{inputBaseName}_chapters"
    
    try:
        # Process the book
        processor = HtmlBookProcessor(inputFile, outputDir, useLlm, splitLongChapters)
        chapterPaths = processor.processBook()
        
        if not chapterPaths:
            logger.error("No chapters were successfully processed")
            raise typer.Exit(1)
            
        logger.info(f"Successfully created {len(chapterPaths)} text files in {outputDir}")
        
        # Print the output directory path for other scripts to use
        typer.echo(f"Output directory: {os.path.abspath(outputDir)}")
        
    except Exception as e:
        logger.error(f"Error processing HTML book: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()