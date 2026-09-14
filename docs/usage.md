# CLI usage

Primary workflow: **user → library → Instagram/TikTok sources → `query` / `chat`**.

Use `uv run crag` (avoids a stale global `crag` install). There is no `profile` command group.

---

## Environment

Copy `.env.example` to `.env`. Minimum:

```env
GEMINI_API_KEY=...
PINECONE_API_KEY=...
APIFY_API_KEY=...
EMBED_PROVIDER=gemini
CRAG_PINECONE_INDEX=creatorrag
GEMINI_EXTRACTION_MODEL=gemini-3.5-flash
GEMINI_MAX_CONCURRENT_REQUESTS=1
GEMINI_VIDEO_OPTIMIZE=true
GEMINI_VIDEO_MAX_HEIGHT=720
```

Optional Groq answers (Llama 3.3 is shut down on free/developer):

```env
GROQ_API_KEY=...
RAG_PROVIDER=groq
RAG_MODEL=openai/gpt-oss-120b
```

Default CLI user: `CRAG_USER=me`.

---

## 1. User

```bash
uv run crag user create me
uv run crag user list
```

---

## 2. Library

```bash
uv run crag library create "Mis creadores"
uv run crag library list
uv run crag library add-url mis-creadores https://www.tiktok.com/@creator/video/123
```

`--caption-only` never downloads media. `--full` always downloads (skips caption-first triage). Default is caption-first: rich captions are indexed as text; thin captions download the video. Query hydrates any retrieved caption-only source before answering.

`--keep-media` keeps files under `data/raw/`.

---

## 3. Instagram

```bash
uv run crag instagram add fitness_coach --library mis-creadores --max-posts 20
uv run crag instagram add https://www.instagram.com/reel/SHORTCODE/ --library mis-creadores
```

`--newer-than` limits profile scrapes. Default ingest is caption-first. `--full` forces media download. Query always hydrates retrieved caption-only hits (including the top hit) before answering.

---

## 4. TikTok

```bash
uv run crag tiktok add https://www.tiktok.com/@creator/video/123 --library mis-creadores
uv run crag tiktok add https://www.tiktok.com/@creator --library mis-creadores
```

A profile URL is expanded with `APIFY_TIKTOK_ACTOR` (default `clockworks/full-tiktok-api-scraper`). YouTube URLs error.

---

## 5. Query and chat

```bash
uv run crag query "Warm-up from this library?" --library mis-creadores
uv run crag query "Creatine dosage?" --library mis-creadores --mode strict
uv run crag chat --library mis-creadores
```

- `grounded_plus` (default): answer from sources; may add a labeled general-knowledge block.
- `strict`: refuse if the library does not cover it.

Legacy scopes: `--group` / `-g`, `--creator` / `-c`.

---

## 6. Document export (explicit only)

Wording such as “házmelo en PDF” does **not** write a file. You must pass flags:

```bash
uv run crag query "Rutina de 4 días" --library mis-creadores \
  --artifact workout_plan -o rutina.pdf

uv run crag query "Lista de compras de esas recetas" --library mis-creadores \
  --artifact grocery_list -o compras.md
```

| Flag | Meaning |
|---|---|
| `--artifact` / `-a` | `workout_plan`, `recipe_book`, or `grocery_list` (switches the generation prompt) |
| `--export` / `-o` | Output path. `.pdf` or `.md`. Alone, saves the normal answer without a brief prompt |

---

## 7. Groups (optional)

```bash
uv run crag group create HighProteinDiet --desc "Meal prep"
uv run crag group add-post HighProteinDiet https://www.instagram.com/reel/C8xyz123/
uv run crag group share HighProteinDiet alice
uv run crag group list
```

Interest filtering and `group add-from-profile` were removed.

---

## 8. Saved posts (optional)

```bash
uv run crag saved import /path/to/instagram-export.zip
uv run crag saved process --workers 4
```
