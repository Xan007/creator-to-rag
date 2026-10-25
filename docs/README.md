# CreatorRAG Backend Documentation

CreatorRAG is a Retrieval-Augmented Generation (RAG) platform engineered to ingest, analyze, index, and query multimodal content from Instagram Reels, TikTok videos, and other supported URLs.

---

## Documentation Index

| Document | Description |
|---|---|
| [**Architecture Overview**](architecture.md) | CQRS-inspired design separating private heavy ingestion from low-latency public query serving. |
| [**HTTP API**](api.md) | FastAPI service overview, authentication, and interactive OpenAPI documentation link. |
| [**Content Management**](content-management.md) | Content Browser architecture, global pool vs. scoped libraries, title derivation, bulk linking, and bulk deletion. |
| [**RAG Pipeline & Hybrid Search**](rag-pipeline.md) | Hybrid retrieval architecture combining Pinecone dense vector search and SQLite FTS5 lexical search, multi-turn query condensation, citation attribution, and response grounding modes. |
| [**Database Schema & Storage**](database-schema.md) | Relational database models (SQLAlchemy), SQLite FTS5 virtual tables, and Pinecone vector metadata specifications. |
| [**Internal Modules**](modules) | Technical specifications for analyzers, indexers, connectors, scrapers, and downloaders. |

---

## Quickstart

### Prerequisites and Configuration

Configure the required environment variables in `.env`:

```env
# Gemini API credentials
GEMINI_API_KEY="AIzaSy..."

# Pinecone Vector Database configuration
PINECONE_API_KEY="pcsk_..."
INDEX_NAME="creatorrag"

# Database storage path
CRAG_DB_PATH="~/.crag/crag.db"

# Optional Apify profile scraper token
APIFY_API_TOKEN="apify_api_..."
```

### Running the API Server

Start the FastAPI application with Uvicorn:

```powershell
.venv\Scripts\python.exe -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

Interactive OpenAPI documentation is accessible at `http://127.0.0.1:8000/docs`.

### Test Suites Execution

Execute automated verification suites using the project virtual environment:

```powershell
# Unit and integration test suite
.venv\Scripts\pytest.exe tests/

```
