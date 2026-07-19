# AGENTS.md

> Repo-specific contract for any coding agent working here. `CLAUDE.md` is a
> symlink to this file. The shared vibe protocol lives in `.vibe/PROTOCOL.md`
> and is imported below — keep this file for what is true of *this repo only*.

@.vibe/PROTOCOL.md

## Techstack

- **Pixi** is the runtime, not an option. It resolves the conda env carrying the
  two heaviest deps (Coqui TTS, google-genai); `pip install -e .` produces a CLI
  whose chapter and format commands die at import. The lockfile is pinned to
  `osx-arm64` only — nothing else resolves.
- **Typer** composes the pipeline: each stage is its own Typer app, mounted as a
  subcommand by `cli.py`. Adding a stage means exporting an `app` and mounting it.
- **BeautifulSoup + Gemini** turn a Gutenberg HTML dump into chapter files —
  BeautifulSoup strips markup, Gemini reads the table of contents and decides
  where chapters actually begin (heuristics were not reliable enough).
- **Gemini** again rewrites each chapter for narration: numbers and abbreviations
  spelled out, dialogue attributed, headers de-duplicated — losslessly, no
  summarizing.
- **Coqui TTS** synthesizes chapter WAVs locally; **wave/ffmpeg** concatenate
  them, normalizing sample rate and channel count first.
- **RSS scraper** polls Gutenberg's "today" feed on a cron and pulls new English
  books.
- **CDK / TypeScript / Bun**, with Aurora Postgres and Step Functions, describe
  the intended cloud port of the same pipeline. See below — it does not run yet.

## Non-obvious structure

- **The `aws/` CDK app does not synth.** `bin/gutenberg-cdk.ts` imports
  `../lib/gutenberg-cdk-stack` and that file does not exist; `cdk.json` still
  points its `app` at `bin/hello-cdk.ts`, also absent. Every handler under
  `aws/lambda/` is a stub returning canned values. Treat `aws/` as a design
  target described by `database-schema.sql` and `step_by_step_instructions.md`,
  not as deployed infrastructure.
- **`lambda-functions/` is a dead earlier port**, superseded by `aws/lambda/`.
  Do not extend it. Its handlers are more fleshed out than the ones that replaced
  them, which makes it look current — it isn't.
- **TTS is deliberately unmounted in `cli.py`.** `scripts/ttsAgent.py` exports a
  Typer app but is never registered, so the shipped flow is
  chapters → format → *(TTS run by hand)* → merge. Importing it at CLI startup
  would drag Coqui's model manager into every invocation.
- **`cli.py` swallows `ImportError` per stage on purpose** — a half-installed env
  loses one subcommand instead of the whole CLI. A stage that silently vanishes
  is a missing dependency, not a routing bug.
- **The docs lie about the LLM.** README and the `format-chapters` help text say
  Ollama; the code calls Gemini. `GEMINI_API_KEY` is the only key that matters.
  The `ollama` dependency is vestigial.
- **Python here is camelCase**, per `.github/instructions/`. Deliberate PEP 8
  deviation — match it.
- **`scripts/scraper/scraper_state.json` is committed and is the dedup ledger.**
  Processed ebook IDs live in git; if a run's state update isn't committed, the
  next run re-downloads those books.
- `scripts/bookScraper.py`, `scripts/setup_scraper.py`, and the root
  `BOOK_SCRAPER_README.md` are **zero-byte leftovers**. The live copies are under
  `scripts/scraper/`.

## Operational commands

- `pixi install` — set up the environment (required first step).
- `pixi run gutenberg --help` — CLI entry; `dev-install` runs as a dependency.
- `pixi run gutenberg create-chapters convert-html --input <html> --output <dir>`
- `pixi run gutenberg format-chapters format-audiobook --input <dir> --output <dir>`
- `pixi run gutenberg merge-audio-chapters merge-audio --input <wavs> --output <wav>`
- `pixi run test-cli` / `test-create-chapters` / `test-format-chapters` /
  `test-merge-audio-chapters` — smoke checks that each subcommand loads. There is
  no Python test suite; these are the whole story.
- `bash scripts/scraper/run_daily_scraper.sh` — the cron entry point.
- In `aws/`: `bun install`, then `bun run cdk list` / `synth` / `diff` / `deploy`,
  `bun run lint`, `bun run format`, `bun run test`. All CDK commands fail until
  the missing stack file exists.

- Third-party source is vendored under `.vibe/sources/`. To read a dependency's real implementation instead of guessing, run `vibe vendor <pkg>`. Prefer this over recalling the API from memory.
