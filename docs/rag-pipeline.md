# RAG Pipeline and Hybrid Retrieval Architecture

CreatorRAG implements a production-grade, hybrid Retrieval-Augmented Generation (RAG) pipeline tailored specifically for structured knowledge extracted from creator video and audio content across Instagram Reels, TikTok, and YouTube Shorts.

---

## 1. End-to-End Pipeline Workflow

```mermaid
flowchart TD
    User([Client Application]) -->|POST /query| API[FastAPI /query Endpoint]
    API --> QE[QueryEngine Execution]
    
    subgraph MultiTurn ["1. Multi-Turn Context Processing"]
        QE --> QC[Standalone Question Condensation\n_condense_question]
    end
    
    subgraph Retrieval ["2. Scoped Hybrid Retrieval"]
        QC -->|Embedding| Dense[Pinecone Dense Search\nMetadata Filter: library_id]
        QC -->|Tokens| Sparse[SQLite FTS5 Lexical Search\nScoped to library_id]
        Dense & Sparse --> HR[HybridRetriever\nReciprocal Rank Fusion & Deduplication]
    end
    
    subgraph Hydration ["3. On-Demand Hydration (Optional)"]
        HR --> HydrateCheck{Caption-Only Matches?}
        HydrateCheck -->|Yes| Hydrate[yt-dlp Media Download + Gemini Multimodal Analysis]
        HydrateCheck -->|No| PromptBuild[Grounded Prompt Construction]
        Hydrate --> PromptBuild
    end
    
    subgraph Generation ["4. Grounded Synthesis & Citations"]
        PromptBuild --> LLM[Gemini LLM / Groq Fallback Client]
        LLM --> Annotate[Citation Extraction\n[Source N] -> cited: true/false]
        Annotate --> Response([Structured JSON Response])
    end
```

---

## 2. Hybrid Retrieval Strategy

To maximize both semantic concept recall and exact lexical keyword precision (e.g., anatomical terms, recipe ingredients, specific training equipment), the engine executes a dual-branch search:

### A. Dense Semantic Branch
- **Vector Database:** Managed Pinecone index specified via `PINECONE_API_KEY` and `INDEX_NAME`.
- **Embedding Provider:** Google Gemini `text-embedding-004` (768 dimensions), with optional fallback to local FastEmbed.
- **Strict Boundary Isolation:** Vector search queries always enforce a library filter:
  ```json
  { "filter": { "library_id": { "$eq": "<library_uuid>" } } }
  ```
  This guarantees that vectors associated with unlinked creators or other libraries never leak into the retrieval set.

### B. Lexical Sparse Branch
- **Engine:** SQLite FTS5 virtual table (`chunks_fts`) with unicode61 tokenization.
- **Scoped Ranking:** Evaluates BM25 relevancy scores constrained by the requested `library_id`.
- **Purpose:** Surfaces domain-specific terminology, proper nouns, numerical measurements, and rare phrases that embedding models may inadvertently smooth over.

### C. Fusion and Ranking (`HybridRetriever`)
The `HybridRetriever` module merges candidate documents from both branches:
- Deduplicates matches by canonical post URL and shortcode.
- Re-ranks candidate segments using Reciprocal Rank Fusion (RRF).
- Applies score thresholding (`min_score`, default: 0.35).
- Returns the top-ranked segments constrained by `top_k` (default: 6).

---

## 3. Multi-Turn Context Condensation

When users submit follow-up prompts (e.g., *"How should I adjust this if I'm a beginner?"* or *"How many sets per week?"*), direct retrieval on the raw question yields poor search vectors due to missing subject context.

The system handles this through automated condensation:
1. Validates and normalizes past conversation turns via `normalize_history()`.
2. Prompts Gemini with the condensed history block:
   ```text
   Given the following conversation and a follow-up question, rephrase the follow-up
   question to be a standalone search query that contains all necessary context from
   previous turns. Do NOT answer the question. Only return the standalone question.
   ```
3. The resulting standalone question (e.g., *"adjusting hypertrophy workout volume for beginners"*) drives the hybrid search queries.
4. The conversational history is preserved and injected into the final synthesis prompt to maintain continuity and conversational tone.

---

## 4. Response Modes

The query endpoint validates the `mode` parameter against two supported synthesis policies:

| Mode | Policy | Recommended Use Case |
|---|---|---|
| `grounded_plus` *(Default)* | Synthesizes an answer grounded strictly in retrieved creator excerpts with numbered citations. If the prompt requests general knowledge or out-of-scope advice, appends a clearly demarcated general knowledge section. | Interactive user-facing conversational chat interfaces. |
| `strict` | 100% creator grounding. If the library lacks relevant content, explicitly refuses to answer without hallucinating external knowledge. | Creator hubs, verified instruction spaces, medical or professional fitness guides. |

---

## 5. Citation Annotation Engine

Retrieved sources supplied in the prompt are indexed as `[Source 1]`, `[Source 2]`, through `[Source N]`.

The `annotate_citations()` post-processor:
1. Analyzes the model output using regular expressions (`\[Source\s*(\d+)\]`) and creator mention detection.
2. Annotates each item in the returned `sources` array with `cited: true` or `cited: false`.
3. Sanitizes references in the answer text to ensure no non-existent source indices remain.
4. Enriches every cited source with canonical metadata:
   - `id` and `post_id`
   - `title` (concise topic title derived from `## Topic`)
   - `creator_username`
   - `url` (direct link to original Instagram/TikTok post)
   - `summary` (1-2 sentence preview)
   - `cited` (boolean flag)

---

## 6. On-Demand Media Hydration (`HYDRATE_ON_QUERY`)

CreatorRAG supports a two-tier ingest pipeline to manage API quotas and bandwidth:

1. **Caption-First Ingestion:** Posts with extensive captions are initially ingested with text-only data (`ingest_status: caption_indexed`).
2. **Runtime Hydration:** When a user query matches a caption-only post as a top candidate, and `HYDRATE_ON_QUERY=true` is set:
   - The system downloads the video via `yt-dlp`.
   - Sends the file to Gemini multimodal vision/audio analysis.
   - Updates relational chunks in SQLite and vectors in Pinecone with `ingest_status: full_indexed`.
   - Overlays the newly extracted deep facts directly into the active prompt context.
