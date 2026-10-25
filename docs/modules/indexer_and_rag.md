# Indexer and RAG Modules (`src/indexer/`, `src/rag/`)

These modules handle vectorization, storage, and hybrid retrieval across creator knowledge bases.

---

## 1. Pinecone Vector Indexer (`pinecone_indexer.py`)

- **Index Name:** Defined by `INDEX_NAME` or `CRAG_PINECONE_INDEX` (default: `creatorrag`).
- **Embedding Provider:** Google Gemini `text-embedding-004` (768 dimensions) or FastEmbed (`BAAI/bge-small-en-v1.5`).
- **Post Preparation (`prepare_post_index`):**
  - Resolves `post_title` via `extract_topic_from_knowledge()`.
  - Instantiates the `Post` model with `title=post_title`.
  - Instantiates the `Source` model with `title=post_title`.
  - Attaches `title: post_title` within Pinecone vector metadata.
- **Chunk Indexing:** Partitions long text segments using `chunk_text()` and assigns vector IDs using the format `source:{library_id}:{source_id}:{ordinal}`.
- **Metadata Updates:** Supports bulk library reassignments (`update_posts_library()`) without re-embedding text payloads.

---

## 2. Lexical Retrieval (`src/rag/lexical.py`)

- Executes full-text search against the persistent SQLite FTS5 table (`chunks_fts`) or PostgreSQL `tsvector`.
- Strictly scopes queries to `library_id` to enforce multi-tenant isolation.
- Manages an in-process cache with automatic invalidation (`LexicalRetriever.invalidate(library_id)`) upon link, update, or deletion events.

---

## 3. Hybrid Fusion (`src/rag/hybrid.py`)

- Merges dense matches from Pinecone with sparse documents from SQLite FTS5.
- Applies Reciprocal Rank Fusion (RRF) with configurable weighting.
- Fault-tolerant fallback: if Pinecone is temporarily unavailable, query processing continues using local lexical search.

---

## 4. Query Engine (`src/rag/query_engine.py`)

- **Filtering:** Combines `$eq: library_id` with optional `creator_username` or `post_ids` constraints.
- **Multi-Turn Question Condensation:** Leverages past conversation turns to rewrite contextual follow-up questions into standalone queries (`_condense_question`).
- **Synthesis Modes:**
  - `grounded_plus`: Creator-grounded response with labeled external knowledge addendum if required.
  - `strict`: Zero-hallucination policy; explicitly refuses queries lacking sufficient support in creator content.
- **Attribution:** Detects `[Source N]` references and flags each source record with `cited: true` or `cited: false`.
- **Telemetry:** Returns detailed execution latency benchmarks in `timings_ms` (embedding, dense, lexical, hydration).

---

## 5. Artifact Generators (`src/rag/artifacts.py`)

Generates structured briefs and exports when an `artifact_type` parameter is provided:
- `workout_plan`: Structured exercise regimens with target muscle groups, sets, repetitions, and rest periods.
- `recipe_book`: Culinary guides with ingredient lists, measurements, and numbered cooking instructions.
- `grocery_list`: Categorized shopping checklists organized by store aisles or food categories.
