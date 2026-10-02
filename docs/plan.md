# Product status

CreatorRAG is a **creator knowledge library**: ingest Instagram and TikTok, extract knowledge, retrieve with hybrid RAG, answer with citations.

This file used to be an early implementation plan (`profile add`, interest filters, local-only scrape). That plan is obsolete.

## In scope

- User-owned **libraries** (slug) as the chat knowledge base.
- Instagram (profile or URL) and TikTok (video or profile via Apify).
- Gemini multimodal extraction; Whisper as audio-only engine.
- Pinecone + FTS hybrid retrieval, pinned embeddings, library ownership.
- CLI + FastAPI. Optional saved-post import.

## Out of scope (on purpose)

- YouTube (long videos; URLs are rejected).
- Inferring PDF/Markdown export from chat wording. Export is **explicit** (`--artifact` / API `artifact_type`).
- Interest-based ingest filters. If the user added the source, index it.

## Manual check

1. `uv run crag library create "Test"`
2. `uv run crag instagram add <username> --library test --max-posts 5`
3. `uv run crag query "…" --library test --mode strict`
4. Optional: `… --artifact workout_plan -o brief.pdf`
5. `uv run pytest`
