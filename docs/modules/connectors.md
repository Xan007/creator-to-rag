# Connectors (`src/connectors/`)

Normalize public URLs into `NormalizedSource` (platform, url, author, title, description) before library ingest.

- `url.py`: yt-dlp metadata. **Rejects YouTube.** Detects TikTok vs generic.
- `apify_social.py`: TikTok profile/listing expansion via `APIFY_TIKTOK_ACTOR` (default `clockworks/full-tiktok-api-scraper`), capped by `APIFY_MAX_TOTAL_CHARGE_USD`.
- `models.py`: `NormalizedSource` dataclass.

`crag tiktok add` and `library add-url` go through this layer. Instagram profiles still use `src/scraper/`.
