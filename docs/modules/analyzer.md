# Analyzer (`src/analyzer/`)

Turns downloaded media plus the caption into structured knowledge for indexing.

## Gemini (`gemini_analyzer.py`)

- Default model: `GEMINI_EXTRACTION_MODEL` (`gemini-3.5-flash`). On 404/429/503 it tries `3.5-flash-lite`, then `3.8`, `3.7`, `3.6`, `3.1-lite`, `2.5`, `2.5-lite`. Optional `GEMINI_EXTRACTION_FALLBACK_MODELS` is prepended. Gemma and Pro 3.1 are not in this list (no hosted video+audio, and paid-only).
- Uploads video/images via the Gemini Files API, waits until processing finishes, then extracts facts (numbers, steps, on-screen text, spoken points).
- Videos are capped at `GEMINI_VIDEO_MAX_HEIGHT` (default 720) with ffmpeg before upload. `GEMINI_VIDEO_OPTIMIZE=false` sends the original. yt-dlp also prefers `height<=720`. Sidecar photos stay separate — stitching them into one collage is slower locally and can make on-screen text unreadable.
- Shares `GEMINI_MAX_CONCURRENT_REQUESTS` with embeddings and Gemini answers. 404/429/503 retry with backoff, then the next model.
- Uploaded files are deleted in a `finally` block.

## Whisper (`whisper_analyzer.py`)

Used when `engine` / analysis mode is `local_whisper` or `openai_whisper`. Transcribes audio only — no overlays or on-screen text. Library ingest uses this path when settings.engine is Whisper.

Primary product path: Gemini multimodal.
