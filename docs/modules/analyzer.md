# Analyzer Module (`src/analyzer/`)

The Analyzer module transforms raw downloaded media assets (video, audio, images) and accompanying social captions into structured factual knowledge and topic titles suitable for RAG indexing.

---

## 1. Gemini Multimodal Analyzer (`gemini_analyzer.py`)

- **Primary Model:** Configured via `GEMINI_EXTRACTION_MODEL` (default: `gemini-3.5-flash`). On receiving HTTP 404, 429, or 503 status codes, the client rotates to fallback models (`gemini-3.5-flash-lite`, `gemini-3.8-flash`, etc.).
- **Media Ingestion Flow:** Uploads local video or image assets to the Gemini Files API (`client.files.upload`), monitors processing state, and executes structured prompt extraction:
  - `## Topic`: One-line summary of the core concept taught.
  - `## Summary`: Concise summary of post narrative.
  - `## Key Takeaways / Instructions`: Bulleted actionable instructions, techniques, or ingredients.
  - `## Numbers & Measurements`: Exact numerical quantities, sets, reps, or temperatures.
  - `## On-Screen Text`: Transcribed overlays, text cards, and lower-third graphics.
- **Transcoding Optimization:** Videos with height exceeding `GEMINI_VIDEO_MAX_HEIGHT` (default: 720) are downscaled using FFmpeg prior to upload to optimize bandwidth and minimize processing delay.
- **Resource Cleanup:** Uploaded cloud files and local temporary transcodes are removed in a guaranteed `finally` block upon completion.

---

## 2. Post Title Generator (`title_generator.py`)

Produces concise titles (<= 8 words) for Content Browser interfaces:

- **Primary Mechanism:** Deterministically parses the `## Topic` block from existing extracted knowledge (`r"##\s*Topic\s*\n([^\n#]+)"`). This introduces zero additional network requests and zero token overhead.
- **Caption Fallback:** For posts ingested under caption-only mode that lack a `## Topic` header, invokes a compact LLM prompt (`generate_title_from_caption`).
- **Terminal Fallback:** Truncates the first non-empty line of the caption.

---

## 3. Caption Triage (`caption_triage.py`)

Evaluates whether social media post captions contain sufficient detail to bypass video downloading:
- Comprehensive captions (e.g., full recipes with measurements or numbered workout routines) are marked for `caption-only` indexing.
- Short or promotional captions (e.g., "Check this out below") trigger full video downloads.

---

## 4. Whisper Audio Analyzer (`whisper_analyzer.py`)

Alternative transcription pipeline utilizing local Whisper or OpenAI Whisper endpoints when running in environments without Gemini multimodal access.
