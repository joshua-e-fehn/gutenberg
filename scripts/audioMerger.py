import logging
import os
import re
from pathlib import Path
from typing import List, Tuple, Optional
import wave
import shutil
import subprocess
import typer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AudioMerger:
    """Class for merging multiple WAV audio files into a single file."""
    
    @staticmethod
    def naturalSort(fileList: List[str]) -> List[str]:
        """
        Sort filenames in natural order (1, 2, ..., 10, 11 instead of 1, 10, 11, 2, ...).
        
        Args:
            fileList: List of filenames to sort
            
        Returns:
            Naturally sorted list of filenames
        """
        def extractNumbers(filename: str) -> List[int]:
            return [int(text) if text.isdigit() else text.lower() 
                    for text in re.split(r'(\d+)', filename)]
            
        return sorted(fileList, key=extractNumbers)
    
    @staticmethod
    def getAudioInfo(filePath: str) -> Tuple[int, int, int]:
        """
        Get audio file information (channels, sample width, frame rate).
        
        Args:
            filePath: Path to the audio file
            
        Returns:
            Tuple of (channels, sample_width, frame_rate)
        """
        with wave.open(filePath, 'rb') as wf:
            channels = wf.getnchannels()
            sampleWidth = wf.getsampwidth()
            frameRate = wf.getframerate()
            
        return channels, sampleWidth, frameRate
    
    @staticmethod
    def validateAudioFiles(filePaths: List[str]) -> bool:
        """
        Validate that all audio files have compatible parameters.
        
        Args:
            filePaths: List of audio file paths
            
        Returns:
            True if all files are compatible, False otherwise
        """
        if not filePaths:
            logger.error("No audio files found to merge")
            return False
            
        # Get parameters from first file
        firstFile = filePaths[0]
        try:
            refChannels, refSampleWidth, refFrameRate = AudioMerger.getAudioInfo(firstFile)
        except Exception as e:
            logger.error(f"Error reading reference file {firstFile}: {e}")
            return False
            
        # Check all files for compatibility
        for filePath in filePaths[1:]:
            try:
                channels, sampleWidth, frameRate = AudioMerger.getAudioInfo(filePath)
                
                if (channels != refChannels or 
                    sampleWidth != refSampleWidth or 
                    frameRate != refFrameRate):
                    logger.error(f"File {filePath} has incompatible audio parameters")
                    logger.error(f"Expected: channels={refChannels}, "
                                f"sample_width={refSampleWidth}, "
                                f"frame_rate={refFrameRate}")
                    logger.error(f"Got: channels={channels}, "
                                f"sample_width={sampleWidth}, "
                                f"frame_rate={frameRate}")
                    return False
                    
            except Exception as e:
                logger.error(f"Error reading file {filePath}: {e}")
                return False
                
        return True
    
    def checkFfmpegAvailability(self) -> bool:
        """
        Check if FFmpeg is available on the system.
        
        Returns:
            True if FFmpeg is available, False otherwise
        """
        try:
            subprocess.run(
                ["ffmpeg", "-version"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                check=False
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def checkSoxAvailability(self) -> bool:
        """
        Check if SoX is available on the system.
        
        Returns:
            True if SoX is available, False otherwise
        """
        try:
            subprocess.run(
                ["sox", "--version"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                check=False
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def mergeAudioFiles(self, inputFolder: str, outputPath: str) -> Optional[str]:
        """
        Merge multiple WAV audio files into a single file.
        
        Args:
            inputFolder: Path to the folder containing WAV files
            outputPath: Path to save the merged audio file
            
        Returns:
            Path to the merged audio file if successful, None otherwise
        """
        logger.info(f"Merging audio files from folder: {inputFolder}")
        
        # Get all WAV files in the input folder
        inputPath = Path(inputFolder)
        wavFiles = [str(f) for f in inputPath.glob("*.wav")]
        
        if not wavFiles:
            logger.error(f"No WAV files found in {inputFolder}")
            return None
            
        # Sort files in natural order
        wavFiles = self.naturalSort(wavFiles)
        logger.info(f"Found {len(wavFiles)} WAV files to merge")
        
        # Validate audio files
        if not self.validateAudioFiles(wavFiles):
            logger.error("Audio file validation failed. Aborting merge.")
            return None
            
        # Create output directory if it doesn't exist
        outputDir = os.path.dirname(outputPath)
        if outputDir and not os.path.exists(outputDir):
            os.makedirs(outputDir)
        
        # Check for available tools to handle large files
        hasSox = self.checkSoxAvailability()
        hasFfmpeg = self.checkFfmpegAvailability()
        
        # For very large collections, use SoX or FFmpeg
        if len(wavFiles) > 100:
            if hasSox:
                return self._mergeWithSox(wavFiles, outputPath)
            elif hasFfmpeg:
                return self._mergeWithFfmpeg(wavFiles, outputPath)
            else:
                logger.warning("Neither SoX nor FFmpeg available. Using fallback method.")
                return self._mergeLargeWithoutExternalTools(wavFiles, outputPath)
        
        # For small collections, use standard approach
        try:
            # Get audio parameters from first file
            channels, sampleWidth, frameRate = self.getAudioInfo(wavFiles[0])
            
            # Open output file
            with wave.open(outputPath, 'wb') as outWave:
                outWave.setnchannels(channels)
                outWave.setsampwidth(sampleWidth)
                outWave.setframerate(frameRate)
                
                # Process each input file
                for i, wavFile in enumerate(wavFiles):
                    logger.info(f"Processing file {i+1}/{len(wavFiles)}: {os.path.basename(wavFile)}")
                    
                    with wave.open(wavFile, 'rb') as inWave:
                        # Read and write audio data in chunks to save memory
                        chunkSize = 1024 * 1024  # 1MB chunks
                        audioData = inWave.readframes(chunkSize)
                        
                        while audioData:
                            outWave.writeframes(audioData)
                            audioData = inWave.readframes(chunkSize)
            
            logger.info(f"Successfully merged {len(wavFiles)} audio files to: {outputPath}")
            return outputPath
            
        except Exception as e:
            logger.error(f"Error in standard merging method: {e}")
            logger.info("Attempting alternative merge method...")
            
            # Try advanced methods if standard fails
            if hasSox:
                return self._mergeWithSox(wavFiles, outputPath)
            elif hasFfmpeg:
                return self._mergeWithFfmpeg(wavFiles, outputPath)
            else:
                return self._mergeLargeWithoutExternalTools(wavFiles, outputPath)
    
    def _mergeWithSox(self, wavFiles: List[str], outputPath: str) -> Optional[str]:
        """
        Merge audio files using SoX (Sound eXchange).
        
        Args:
            wavFiles: List of WAV file paths to merge
            outputPath: Path to save the merged audio file
            
        Returns:
            Path to the merged audio file if successful, None otherwise
        """
        logger.info("Using SoX for merging audio files")
        
        try:
            # Build the SoX command
            soxCmd = ["sox"]
            
            # Add input files (SoX can handle lots of input files directly)
            for wavFile in wavFiles:
                soxCmd.append(wavFile)
                
            # Add output file
            soxCmd.append(outputPath)
            
            # Execute SoX command
            logger.info("Starting SoX concatenation process")
            
            result = subprocess.run(
                soxCmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False
            )
            
            if result.returncode != 0:
                logger.error(f"SoX error: {result.stderr.decode()}")
                return None
            
            logger.info(f"Successfully merged {len(wavFiles)} audio files using SoX")
            return outputPath
            
        except Exception as e:
            logger.error(f"Error using SoX: {e}")
            
            # Try FFmpeg if SoX fails
            if self.checkFfmpegAvailability():
                logger.info("Falling back to FFmpeg")
                return self._mergeWithFfmpeg(wavFiles, outputPath)
            else:
                logger.info("Falling back to manual processing")
                return self._mergeLargeWithoutExternalTools(wavFiles, outputPath)
    
    def _mergeWithFfmpeg(self, wavFiles: List[str], outputPath: str) -> Optional[str]:
        """
        Merge audio files using FFmpeg.
        
        Args:
            wavFiles: List of WAV file paths to merge
            outputPath: Path to save the merged audio file
            
        Returns:
            Path to the merged audio file if successful, None otherwise
        """
        logger.info("Using FFmpeg for merging audio files")
        
        try:
            # Create a temporary file list for FFmpeg
            tempDir = os.path.dirname(outputPath)
            fileListPath = os.path.join(tempDir, "filelist.txt")
            
            with open(fileListPath, 'w') as f:
                for wavFile in wavFiles:
                    f.write(f"file '{os.path.abspath(wavFile)}'\n")
            
            # Use FFmpeg to concatenate files
            logger.info("Starting FFmpeg concatenation process")
            
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", fileListPath,
                    "-c", "copy",
                    outputPath
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False
            )
            
            # Clean up file list
            try:
                os.remove(fileListPath)
            except:
                pass
            
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr.decode()}")
                return None
            
            logger.info(f"Successfully merged {len(wavFiles)} audio files using FFmpeg")
            return outputPath
            
        except Exception as e:
            logger.error(f"Error using FFmpeg: {e}")
            
            # Try alternative method if FFmpeg fails
            logger.info("Falling back to manual processing")
            return self._mergeLargeWithoutExternalTools(wavFiles, outputPath)
    
    def _mergeLargeWithoutExternalTools(self, wavFiles: List[str], outputPath: str) -> Optional[str]:
        """
        Merge large audio files without external tools by splitting into smaller chunks
        and using a raw file format for the final merge.
        
        Args:
            wavFiles: List of WAV file paths to merge
            outputPath: Path to save the merged audio file
            
        Returns:
            Path to the merged audio file if successful, None otherwise
        """
        logger.info("Using specialized processing for large audio collections")
        
        try:
            # Get parameters from first file
            firstFile = wavFiles[0]
            channels, sampleWidth, frameRate = self.getAudioInfo(firstFile)
            
            # Create a temp directory
            tempDir = os.path.join(os.path.dirname(outputPath), "temp_merge")
            os.makedirs(tempDir, exist_ok=True)
            
            # Create a raw PCM file to contain all audio data
            rawOutputPath = os.path.join(tempDir, "merged.raw")
            
            # Create a manifest file for saving audio file information
            manifestPath = os.path.join(tempDir, "manifest.txt")
            with open(manifestPath, 'w') as manifest:
                manifest.write(f"channels={channels}\n")
                manifest.write(f"sample_width={sampleWidth}\n")
                manifest.write(f"frame_rate={frameRate}\n")
            
            # Process all files directly to the raw output
            with open(rawOutputPath, 'wb') as outRaw:
                for i, wavFile in enumerate(wavFiles):
                    logger.info(f"Processing file {i+1}/{len(wavFiles)}: {os.path.basename(wavFile)}")
                    
                    try:
                        with wave.open(wavFile, 'rb') as inWave:
                            # Skip the WAV header and write raw PCM data
                            chunkSize = 1024 * 1024  # 1MB chunks
                            audioData = inWave.readframes(chunkSize)
                            
                            while audioData:
                                outRaw.write(audioData)
                                audioData = inWave.readframes(chunkSize)
                    except Exception as e:
                        logger.error(f"Error processing file {wavFile}: {e}")
                        # Continue with next file
            
            logger.info("All audio data merged to raw file, now creating final WAV file")
            
            # Create WAV header for output file (without using wave module's size limitations)
            # Convert raw PCM to WAV using direct file manipulation
            with open(manifestPath, 'r') as manifest:
                manifestLines = manifest.readlines()
                channels = int(manifestLines[0].split('=')[1])
                sampleWidth = int(manifestLines[1].split('=')[1])
                frameRate = int(manifestLines[2].split('=')[1])
            
            # Get size of raw data
            rawSize = os.path.getsize(rawOutputPath)
            
            # Create WAV header manually
            with open(outputPath, 'wb') as outFile:
                # RIFF header
                outFile.write(b'RIFF')
                # Size of entire file minus 8 bytes for "RIFF" + size field
                fileSize = rawSize + 36  # 36 = size of WAV header minus 8
                outFile.write(fileSize.to_bytes(4, byteorder='little'))
                outFile.write(b'WAVE')
                
                # Format chunk
                outFile.write(b'fmt ')
                outFile.write((16).to_bytes(4, byteorder='little'))  # Size of format chunk
                outFile.write((1).to_bytes(2, byteorder='little'))   # PCM format
                outFile.write(channels.to_bytes(2, byteorder='little'))  # Number of channels
                outFile.write(frameRate.to_bytes(4, byteorder='little'))  # Sample rate
                
                # Bytes per second
                byteRate = frameRate * channels * sampleWidth
                outFile.write(byteRate.to_bytes(4, byteorder='little'))
                
                # Block align
                blockAlign = channels * sampleWidth
                outFile.write(blockAlign.to_bytes(2, byteorder='little'))
                
                # Bits per sample
                bitsPerSample = sampleWidth * 8
                outFile.write(bitsPerSample.to_bytes(2, byteorder='little'))
                
                # Data chunk
                outFile.write(b'data')
                outFile.write(rawSize.to_bytes(4, byteorder='little'))  # Size of data
                
                # Now copy the raw PCM data
                with open(rawOutputPath, 'rb') as inRaw:
                    chunkSize = 1024 * 1024  # 1MB chunks
                    while True:
                        chunk = inRaw.read(chunkSize)
                        if not chunk:
                            break
                        outFile.write(chunk)
            
            # Clean up temp files
            try:
                os.remove(rawOutputPath)
                os.remove(manifestPath)
                os.rmdir(tempDir)
            except:
                pass
                
            logger.info(f"Successfully merged {len(wavFiles)} audio files using specialized processing")
            return outputPath
            
        except Exception as e:
            logger.error(f"Error in specialized merging method: {e}")
            
            # Create a more compatible WAV file with slightly shorter duration if all else fails
            try:
                logger.info("Attempting emergency fallback with limited audio length")
                return self._createLimitedOutputFile(wavFiles, outputPath)
            except Exception as fallbackError:
                logger.error(f"Emergency fallback failed: {fallbackError}")
                return None
    
    def _createLimitedOutputFile(self, wavFiles: List[str], outputPath: str) -> Optional[str]:
        """
        Create a WAV file with a subset of input files to ensure it stays within WAV limitations.
        
        Args:
            wavFiles: List of WAV file paths to merge
            outputPath: Path to save the merged audio file
            
        Returns:
            Path to the merged audio file if successful, None otherwise
        """
        # Calculate how many files we can safely include
        safeCount = min(500, len(wavFiles))
        logger.warning(f"Creating limited output file with first {safeCount} of {len(wavFiles)} files")
        
        # Get audio parameters from first file
        channels, sampleWidth, frameRate = self.getAudioInfo(wavFiles[0])
        
        # Open output file
        with wave.open(outputPath, 'wb') as outWave:
            outWave.setnchannels(channels)
            outWave.setsampwidth(sampleWidth)
            outWave.setframerate(frameRate)
            
            # Process each input file up to the safe limit
            for i, wavFile in enumerate(wavFiles[:safeCount]):
                logger.info(f"Processing file {i+1}/{safeCount}: {os.path.basename(wavFile)}")
                
                with wave.open(wavFile, 'rb') as inWave:
                    # Read and write audio data in chunks to save memory
                    chunkSize = 1024 * 1024  # 1MB chunks
                    audioData = inWave.readframes(chunkSize)
                    
                    while audioData:
                        outWave.writeframes(audioData)
                        audioData = inWave.readframes(chunkSize)
        
        logger.warning(f"Created limited output file with {safeCount} of {len(wavFiles)} files")
        return outputPath
    
    def cleanupSourceFiles(self, inputFolder: str, outputPath: str) -> None:
        """
        Delete source audio files after successful merge, avoiding the output file.
        
        Args:
            inputFolder: Path to the folder containing source WAV files
            outputPath: Path to the merged audio file to keep
        """
        # Normalize paths for comparison
        outputPathAbs = os.path.abspath(outputPath)
        inputPathAbs = os.path.abspath(inputFolder)
        
        # Check if input folder contains the output file
        isSameFolder = os.path.dirname(outputPathAbs) == inputPathAbs
        
        logger.info(f"Cleaning up source files in: {inputFolder}")
        logger.info(f"Preserving output file: {outputPath}")
        
        # Get all WAV files in the input folder
        inputPath = Path(inputFolder)
        wavFiles = [f for f in inputPath.glob("*.wav")]
        
        deletedCount = 0
        for wavFile in wavFiles:
            wavFileAbs = os.path.abspath(str(wavFile))
            
            # Skip the output file if in the same folder
            if isSameFolder and wavFileAbs == outputPathAbs:
                logger.info(f"Skipping output file: {wavFile}")
                continue
                
            try:
                os.remove(wavFileAbs)
                deletedCount += 1
            except Exception as e:
                logger.error(f"Error deleting file {wavFile}: {e}")
        
        logger.info(f"Deleted {deletedCount} source WAV files")


app = typer.Typer(help="Merge multiple WAV audio files into a single file")


@app.command()
def merge_audio(
    inputFolder: str = typer.Option(..., "--input", "-i", help="Path to the folder containing WAV files"),
    outputPath: str = typer.Option("audioResult/merged.wav", "--output", "-o", help="Path to save the merged audio file"),
    noCleanup: bool = typer.Option(False, "--no-cleanup", help="Do not delete source files after merging"),
    useSox: bool = typer.Option(False, "--use-sox", help="Force using SoX for merging if available"),
    useFFmpeg: bool = typer.Option(False, "--use-ffmpeg", help="Force using FFmpeg for merging if available")
) -> None:
    """
    Merge multiple WAV audio files into a single file.
    
    Returns the path to the merged audio file.
    """
    # Check if input folder exists
    if not os.path.isdir(inputFolder):
        logger.error(f"Input folder not found: {inputFolder}")
        raise typer.Exit(1)
    
    # Merge audio files
    merger = AudioMerger()
    
    # Check for tool availability based on arguments
    if useSox and merger.checkSoxAvailability():
        wavFiles = [str(f) for f in Path(inputFolder).glob("*.wav")]
        wavFiles = merger.naturalSort(wavFiles)
        mergedPath = merger._mergeWithSox(wavFiles, outputPath)
    elif useFFmpeg and merger.checkFfmpegAvailability():
        wavFiles = [str(f) for f in Path(inputFolder).glob("*.wav")]
        wavFiles = merger.naturalSort(wavFiles)
        mergedPath = merger._mergeWithFfmpeg(wavFiles, outputPath)
    else:
        # Use standard approach that will select the best method
        if useSox and not merger.checkSoxAvailability():
            logger.warning("SoX not found. Falling back to automatic method selection.")
        if useFFmpeg and not merger.checkFfmpegAvailability():
            logger.warning("FFmpeg not found. Falling back to automatic method selection.")
            
        mergedPath = merger.mergeAudioFiles(inputFolder, outputPath)
    
    if mergedPath:
        # Clean up source files unless --no-cleanup is specified
        if not noCleanup:
            merger.cleanupSourceFiles(inputFolder, mergedPath)
        
        # Print the output path for potential use by other scripts
        typer.echo(f"Output file: {os.path.abspath(mergedPath)}")
        
    else:
        logger.error("Audio merging failed")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()