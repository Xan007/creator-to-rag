# Analyzer (`src/analyzer/`)

Turns downloaded media plus the caption into structured knowledge for indexing.

## Gemini (`gemini_analyzer.py`)

- Default model: `GEMINI_EXTRACTION_MODEL` (`gemini-3.5-flash`). Optional comma-separated `GEMINI_EXTRACTION_FALLBACK_MODELS`.
- Uploads video/images via the Gemini Files API, waits until processing finishes, then extracts facts (numbers, steps, on-screen text, spoken points).
- Shares `GEMINI_MAX_CONCURRENT_REQUESTS` with embeddings and Gemini answers. 404/429/503 retry with backoff, then the next model.
- Uploaded files are deleted in a `finally` block.

## Whisper (`whisper_analyzer.py`)

Used when `engine` / analysis mode is `local_whisper` or `openai_whisper`. Transcribes audio only — no overlays or on-screen text. Library ingest uses this path when settings.engine is Whisper.

Primary product path: Gemini multimodal.
