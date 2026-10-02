# Indexer and RAG

## Indexer (`src/indexer/pinecone_indexer.py`)

- Index name: `CRAG_PINECONE_INDEX` (default `creatorrag`). Must exist and match `EMBED_PROVIDER` dimension.
- Providers: Gemini `gemini-embedding-001` (3072), Jina v3 (1024), FastEmbed MiniLM (384). Pin one per index.
- **Posts (legacy Instagram path):** one vector id `{creator}_{post_id}` with caption + extracted knowledge in metadata.
- **Sources (library path):** one vector per chunk `source:{library_id}:{source_id}:{ordinal}`, content hash, chunk version, stale ids deleted on re-index. Status `indexed` only after Pinecone upsert succeeds.

## Lexical (`src/rag/lexical.py`)

Persistent FTS over chunks: SQLite FTS5 or PostgreSQL FTS, scoped by `library_id`. Short in-process cache with invalidation on chunk replace.

## Hybrid (`src/rag/hybrid.py`)

Reciprocal Rank Fusion of Pinecone matches and FTS documents. Dense-optional: if Pinecone is missing, lexical still runs.

## Query engine (`src/rag/query_engine.py`)

Filters: `library_id` or `creator_username`. Condenses follow-up questions from chat history. Modes `grounded_plus` and `strict`. Sanitizes `[Source N]` against retrieved sources. Returns `timings_ms`.

Artifact **system prompts** apply only when `artifact_type` is passed in. Chat wording never selects a brief.

## Briefs (`src/rag/artifacts.py`)

Explicit CLI `--artifact` / `--export` or API `artifact_type`. Types: `workout_plan`, `recipe_book`, `grocery_list`. PDF is a knowledge brief (header, tables, numbered sources), not an auto-download from “hazme un PDF”.
