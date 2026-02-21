#!/usr/bin/env python3
"""
Main CLI entry point for Gutenberg audiobook creation suite.
"""

import typer
from typing import Optional

app = typer.Typer(
    name="gutenberg",
    help="Turn open source gutenberg text automatically into audiobooks",
    no_args_is_help=True
)

# Import the individual Typer apps from scripts
try:
    from scripts.chapterChunker import app as chapter_chunker_app
    app.add_typer(chapter_chunker_app, name="create-chapters", help="Convert HTML books to plain text chapters")
except ImportError as e:
    typer.echo(f"Warning: Could not import chapterChunker: {e}", err=True)

try:
    from scripts.audioBookFormatter import app as formatter_app  
    app.add_typer(formatter_app, name="format-chapters", help="Format text files for audiobook use with Ollama LLM")
except ImportError as e:
    typer.echo(f"Warning: Could not import audioBookFormatter: {e}", err=True)

try:
    from scripts.audioMerger import app as merger_app
    app.add_typer(merger_app, name="merge-audio-chapters", help="Merge multiple WAV audio files into a single file")  
except ImportError as e:
    typer.echo(f"Warning: Could not import audioMerger: {e}", err=True)

if __name__ == "__main__":
    app()
