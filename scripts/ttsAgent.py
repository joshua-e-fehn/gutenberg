import logging
import os
import re
from pathlib import Path
from typing import Optional, Union, List

import typer
from TTS.utils.manage import ModelManager
from TTS.utils.synthesizer import Synthesizer

# Create Typer app
app = typer.Typer(help="Convert text to speech using Coqui TTS")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TextToSpeech:
    """Class for handling text-to-speech conversion using Coqui TTS."""
    
    def __init__(self, modelName: Optional[str] = None, modelPath: Optional[str] = None):
        """
        Initialize the TTS engine.
        
        Args:
            modelName: Name of the pre-trained TTS model to use
            modelPath: Path to a custom TTS model
        """
        logger.info("Initializing Text-to-Speech engine")
        
        # Get model manager and list of available models
        self.modelManager = ModelManager()
        
        if modelPath and os.path.exists(modelPath):
            # Use custom model if path is provided
            logger.info(f"Using custom model from path: {modelPath}")
            self.modelPath = modelPath
            self.configPath = os.path.join(os.path.dirname(modelPath), "config.json")
        else:
            # Use pre-trained model
            if not modelName:
                # Default to English TTS model if none specified
                modelName = "tts_models/en/ljspeech/vits"
                
            logger.info(f"Using pre-trained model: {modelName}")
            self.modelPath, self.configPath, _ = self.modelManager.download_model(modelName)
        
        # Initialize synthesizer
        self.synthesizer = Synthesizer(
            self.modelPath,
            self.configPath,
            use_cuda=False  # Set to True if GPU is available
        )
        logger.info("Text-to-Speech engine initialized successfully")
    
    def convertTextToSpeech(self, text: str, outputPath: str, speakerId: Optional[int] = None) -> str:
        """
        Convert text to speech and save to file.
        
        Args:
            text: Input text to convert to speech
            outputPath: Path to save the audio file
            speakerId: Optional speaker ID for multi-speaker models
            
        Returns:
            Path to the generated audio file
        """
        logger.info(f"Converting text to speech (length: {len(text)} chars)")
        
        # Create output directory if it doesn't exist
        outputDir = os.path.dirname(outputPath)
        if outputDir and not os.path.exists(outputDir):
            os.makedirs(outputDir)
            
        # Synthesize speech
        wav = self.synthesizer.tts(
            text=text,
            speaker_id=speakerId
        )
        
        # Save the audio to file
        self.synthesizer.save_wav(wav, outputPath)
        
        logger.info(f"Audio saved to: {outputPath}")
        return outputPath
    
    def convertLongText(self, text: str, outputPath: str, maxChars: int = 2000) -> List[str]:
        """
        Convert long text by splitting it into smaller chunks.
        Preserves SSML tags like <speak> and <break> across chunks.
        
        Args:
            text: Long input text to convert (with SSML tags)
            outputPath: Base path for the output audio files
            maxChars: Maximum characters per chunk
            
        Returns:
            List of paths to generated audio files
        """
        outputPaths = []
        
        # Get file extension
        basePath, extension = os.path.splitext(outputPath)
        if not extension:
            extension = ".wav"
        
        # Ensure text has <speak> tags if missing
        if not text.strip().startswith("<speak>"):
            logger.info("Adding <speak> tags to input text")
            text = f"<speak>{text}</speak>"
        
        # Split text into chunks while preserving SSML structure
        chunks = self._splitTextIntoChunks(text, maxChars)
        
        logger.info(f"Split SSML text into {len(chunks)} chunks for processing")
        
        # Process each chunk
        for i, chunk in enumerate(chunks):
            chunkPath = f"{basePath}_{i+1}{extension}"
            
            # Validate chunk has proper SSML structure
            if not chunk.strip().startswith("<speak>") or not chunk.strip().endswith("</speak>"):
                logger.warning(f"Chunk {i+1} is missing SSML tags, adding them")
                chunk = f"<speak>{chunk}</speak>"
            
            self.convertTextToSpeech(chunk, chunkPath)
            outputPaths.append(chunkPath)
            
        return outputPaths
    
    def processFolder(self, folderPath: str, outputDir: str, speakerId: Optional[int] = None) -> List[str]:
        """
        Process all text files in a folder and convert them to speech.
        
        Args:
            folderPath: Path to the folder containing text files
            outputDir: Directory to save the audio files
            speakerId: Optional speaker ID for multi-speaker models
            
        Returns:
            List of paths to the generated audio files
        """
        logger.info(f"Processing text files in folder: {folderPath}")
        
        # Create output directory if it doesn't exist
        if not os.path.exists(outputDir):
            os.makedirs(outputDir)
            
        # Get all text files in the folder
        textFiles = [f for f in os.listdir(folderPath) if f.endswith('.txt')]
        
        if not textFiles:
            logger.warning(f"No text files found in {folderPath}")
            return []
            
        logger.info(f"Found {len(textFiles)} text files to process")
        
        outputPaths = []
        for textFile in sorted(textFiles):  # Sorting ensures consistent processing order
            inputPath = os.path.join(folderPath, textFile)
            # Create output filename with .wav extension
            outputFilename = os.path.splitext(textFile)[0] + ".wav"
            outputPath = os.path.join(outputDir, outputFilename)
            
            try:
                # Read the text file
                with open(inputPath, 'r', encoding='utf-8') as f:
                    text = f.read()
                    
                logger.info(f"Processing file: {textFile}")
                
                # Check if text is long and needs splitting
                if len(text) > 2000:
                    logger.info(f"Long text detected in {textFile}, splitting into chunks")
                    chunkPaths = self.convertLongText(text, outputPath)
                    outputPaths.extend(chunkPaths)
                else:
                    path = self.convertTextToSpeech(text, outputPath, speakerId)
                    outputPaths.append(path)
                    
            except Exception as e:
                logger.error(f"Error processing file {inputPath}: {e}")
                # Continue with next file even if one fails
                
        logger.info(f"Completed processing {len(outputPaths)} audio files")
        return outputPaths
    
    def _splitTextIntoChunks(self, text: str, maxChars: int) -> List[str]:
        """
        Split text into chunks of maximum size while preserving SSML tags.
        
        Args:
            text: Text to split (with SSML tags)
            maxChars: Maximum characters per chunk
            
        Returns:
            List of text chunks with properly preserved SSML tags
        """
        logger.info(f"Splitting text with SSML tags (length: {len(text)} chars)")
        
        try:
            # Extract content between <speak> tags
            speakMatch = re.match(r'<speak>(.*)</speak>', text, re.DOTALL)
            if not speakMatch:
                logger.warning("No <speak> tags found in input text, adding them")
                innerContent = text
                hasTagsAlready = False
            else:
                innerContent = speakMatch.group(1)
                hasTagsAlready = True
            
            # Extract chapter title and main content
            titleBreakMatch = re.match(r'(.*?)<break time=\'4000ms\'/>(.*)', innerContent, re.DOTALL)
            if titleBreakMatch:
                chapterTitle = titleBreakMatch.group(1).strip()
                mainContent = titleBreakMatch.group(2).strip()
            else:
                logger.warning("No chapter title break found, treating all as main content")
                chapterTitle = ""
                mainContent = innerContent.strip()
            
            # Replace <break> tags with placeholders for easier sentence splitting
            breakPlaceholder = "||BREAK_2000MS||"
            mainContent = re.sub(r"<break time='2000ms'/>", breakPlaceholder, mainContent)
            
            # Split content by sentences while preserving breakpoints
            segments = []
            for section in mainContent.split(breakPlaceholder):
                sentences = section.replace('\n', ' ').split('. ')
                for i, sentence in enumerate(sentences):
                    if i < len(sentences) - 1 or section.strip().endswith('.'):
                        segments.append(sentence + '. ')
                    else:
                        segments.append(sentence)
                # Add break marker after each section (except the last one)
                if section != mainContent.split(breakPlaceholder)[-1]:
                    segments.append(breakPlaceholder)
            
            # Reassemble into chunks
            chunks = []
            currentChunk = []
            currentLength = 0
            
            # Always include title in each chunk
            titleWithBreak = f"{chapterTitle} <break time='4000ms'/> " if chapterTitle else ""
            titleLength = len(titleWithBreak)
            
            for segment in segments:
                segmentLength = len(segment)
                
                if segment == breakPlaceholder:
                    # Handle break placeholder separately
                    if currentLength + len("<break time='2000ms'/>") > maxChars - titleLength - len("</speak>"):
                        # Current chunk is full, finalize it
                        chunkText = titleWithBreak + "".join(currentChunk)
                        chunks.append(f"<speak>{chunkText}</speak>")
                        currentChunk = ["<break time='2000ms'/> "]
                        currentLength = len("<break time='2000ms'/> ")
                    else:
                        # Add break to current chunk
                        currentChunk.append("<break time='2000ms'/> ")
                        currentLength += len("<break time='2000ms'/> ")
                else:
                    if currentLength + segmentLength > maxChars - titleLength - len("</speak>"):
                        # Finalize current chunk before adding new segment
                        if currentChunk:
                            chunkText = titleWithBreak + "".join(currentChunk)
                            chunks.append(f"<speak>{chunkText}</speak>")
                        
                        # Start new chunk with this segment
                        currentChunk = [segment]
                        currentLength = segmentLength
                    else:
                        # Add to current chunk
                        currentChunk.append(segment)
                        currentLength += segmentLength
            
            # Add the final chunk if not empty
            if currentChunk:
                chunkText = titleWithBreak + "".join(currentChunk)
                chunks.append(f"<speak>{chunkText}</speak>")
            
            logger.info(f"Split text into {len(chunks)} chunks with SSML tags preserved")
            return chunks
            
        except Exception as e:
            logger.error(f"Error splitting text into chunks: {e}")
            # Fallback: return the entire text as a single chunk
            if not text.strip().startswith("<speak>"):
                text = f"<speak>{text}</speak>"
            return [text]


@app.command()
def main(
    input: Optional[str] = typer.Option(None, "--input", "-i", help="Input text or file path"),
    folder: Optional[str] = typer.Option(None, "--folder", "-f", help="Path to folder containing text files"),
    output: str = typer.Option("audioResults/output.wav", "--output", "-o", help="Output audio file path or directory (when using --folder)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="TTS model name or path"),
    speakerId: Optional[int] = typer.Option(None, "--speaker-id", help="Speaker ID for multi-speaker models")
):
    """Convert text to speech using Coqui TTS."""
    
    # Ensure either input or folder is provided (but not both)
    if not input and not folder:
        typer.echo("Error: Must provide either --input or --folder", err=True)
        raise typer.Exit(1)
    
    if input and folder:
        typer.echo("Error: Cannot provide both --input and --folder", err=True)
        raise typer.Exit(1)
    
    # Initialize TTS engine
    tts = TextToSpeech(modelName=model)
    
    if folder:
        # Handle folder input: process all text files in the folder
        logger.info(f"Processing text files from folder: {folder}")
        
        # Determine output directory
        outputDir = output
        if os.path.splitext(outputDir)[1]:  # If output has extension, use its parent directory
            outputDir = os.path.dirname(outputDir)
        if not outputDir:
            outputDir = "audioResults"
            
        audioFiles = tts.processFolder(folder, outputDir, speakerId)
        logger.info(f"Generated {len(audioFiles)} audio files in {outputDir}")
        typer.echo(f"Output directory: {os.path.abspath(outputDir)}")
        
    else:
        # Handle single input: either file or direct text
        inputText = input
        if os.path.exists(inputText):
            logger.info(f"Reading text from file: {inputText}")
            with open(inputText, 'r', encoding='utf-8') as f:
                inputText = f.read()
        elif not inputText:
            # Read from stdin if no input is provided
            logger.info("Reading text from standard input")
            import sys
            inputText = sys.stdin.read()
        
        # Check if text is long and needs splitting
        if len(inputText) > 2000:
            logger.info("Long text detected, splitting into chunks")
            tts.convertLongText(inputText, output)
        else:
            tts.convertTextToSpeech(inputText, output, speakerId)
        
        logger.info(f"Output path: {os.path.abspath(output)}")
    
    logger.info("Text-to-Speech conversion completed")
    return os.path.abspath(outputDir if folder else os.path.dirname(output))


if __name__ == "__main__":
    app()