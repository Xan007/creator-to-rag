# HTTP API

FastAPI service for libraries, background ingest, and grounded queries.

## Run

```bash
uv sync --extra api
uv run crag-api
# or: uv run python -m src.api.main
```

Binds `http://127.0.0.1:8000` by default. OpenAPI: `/docs`.

Docker: `docker compose up -d --build`.

## Auth and user

- `CRAG_API_KEY`: when set, every route except `/health` needs `X-API-Key`.
- Identity: `X-User-Id` or `X-Username`. `CRAG_AUTO_CREATE_USERS=true` (default) provisions users on the fly.
- If headers are omitted, falls back to `CRAG_USER` or the single registered user.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| GET / PATCH | `/config` | `audio_only`, `engine`, `embed_provider` |
| GET / POST | `/libraries` | List or create libraries for the current user |
| POST | `/libraries/{id}/sources` | Ingest `url` or `urls` asynchronously (`202`). Caption-first by default; `full_media` forces download. |
| GET / POST | `/users` | List or create users |
| GET / DELETE | `/users/{username}` | Get or delete a user |
| GET / POST | `/groups` | Legacy groups |
| GET / DELETE | `/groups/{group_id}` | Group detail or delete |
| POST / DELETE | `/groups/{group_id}/posts` | Group membership |
| POST / DELETE | `/groups/{group_id}/share` | Share access |
| GET / POST | `/profiles` | Legacy Instagram profile registry |
| GET / PATCH / DELETE | `/profiles/{username}` | Profile CRUD |
| POST | `/profiles/{username}/reset` | Reset scrape history |
| POST | `/jobs/run` | Background profile ingest |
| POST | `/jobs/add-reel` | Background reel ingest |
| POST | `/jobs/saved-process` | Background saved-post ingest |
| GET | `/jobs` | Recent jobs |
| GET | `/jobs/{job_id}` | Status and log tail |
| POST | `/saved/import` | Upload Instagram export |
| GET | `/saved/status` | Import counters |
| POST | `/saved/reset` | Clear saved-post state |
| POST | `/query` | Grounded RAG |

Heavy ingest routes return `202` with `{ "job_id", "status_url" }`. Poll `GET /jobs/{job_id}`.

## Query body

```json
{
  "question": "What protein sources does this library recommend?",
  "library": "mis-creadores",
  "mode": "grounded_plus",
  "top_k": 6,
  "min_score": 0.35,
  "history": [
    {"role": "user", "content": "Tell me about diet recommendations."},
    {"role": "assistant", "content": "The creator recommends eggs and Greek yogurt."}
  ]
}
```

Optional scopes: `library` or `library_id`, `creator`, `group_name`. Retrieved caption-only sources are hydrated (download + full index) before the answer is generated.

Optional export (never inferred from `question`):

```json
"artifact_type": "workout_plan"
```

Allowed: `workout_plan`, `recipe_book`, `grocery_list`.

### Response

- `answer`: text with `[Source N]` tags.
- `sources`: `creator`, `url`, `score`, `cited`.
- `mode`: `grounded_plus` or `strict`.
- `timings_ms`: embedding / retrieve / generate (when present).
- `artifact`: `{ path, filename, type, format, title }` only if `artifact_type` was set.
- `standalone_question`: condensed follow-up query when `history` is used.
