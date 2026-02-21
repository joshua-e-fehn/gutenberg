# Gutenberg

Turn open source Gutenberg text automatically into audiobooks.

This tool provides a complete pipeline for converting Project Gutenberg HTML books into high-quality audiobooks with modern TTS technology.

## Installation

This project uses [Pixi](https://pixi.sh/) for dependency management. To get started:

1. Make sure you have Pixi installed
2. Clone this repository
3. Run `pixi install` to set up the environment
4. The `gutenberg` command will be automatically available via `pixi run`

## Usage

### Basic Command Structure

```bash
pixi run gutenberg <command> <subcommand> [options]
```

### Available Commands

#### `create-chapters` - Convert HTML books to plain text chapters

```bash
pixi run gutenberg create-chapters convert-html --input <html_file> --output <output_dir>
```

#### `format-chapters` - Format text files for audiobook use with Ollama LLM

```bash
pixi run gutenberg format-chapters format-audiobook --input <input_dir> --output <output_dir> --model <model_name>
```

#### `merge-audio-chapters` - Merge multiple WAV audio files into a single file

```bash
pixi run gutenberg merge-audio-chapters merge-audio --input <wav_folder> --output <output_file>
```

### Getting Help

- `pixi run gutenberg --help` - Show main help
- `pixi run gutenberg <command> --help` - Show help for a specific command group
- `pixi run gutenberg <command> <subcommand> --help` - Show help for a specific subcommand

### Examples

**Convert HTML book to text chapters:**

```bash
pixi run gutenberg create-chapters convert-html --input books/alice_in_wonderland.html --output chapters/
```

**Format chapters for audiobook:**

```bash
pixi run gutenberg format-chapters format-audiobook --input chapters/ --output formatted/ --model llama3.2
```

**Merge audio files:**

```bash
pixi run gutenberg merge-audio-chapters merge-audio --input audioResults/ --output final_audiobook.wav
```

## Development

The project is structured as a proper Python package:

- `cli.py` - Main CLI entry point
- `scripts/` - Individual script modules containing the business logic
- `pyproject.toml` - Project configuration and dependencies

The CLI uses Typer for command-line interface management and integrates directly with the Typer applications from the individual scripts to provide a unified interface.

## AWS CDK Infrastructure

All AWS infrastructure code lives in:

- `aws/`

Use this as the single source of truth for infrastructure changes and deployments.
