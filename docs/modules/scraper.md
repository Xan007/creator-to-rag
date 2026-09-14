# Scraper (`src/scraper/`)

Instagram metadata only. TikTok uses `src/connectors/`.

## `ApifyScraper`

Used by `crag instagram add <username>`. Actor `sones/instagram-posts-scraper-lowcost`. Yields captions, media URLs, types (reel/image/sidecar). Skips already-known post ids. `newerThan` is re-checked locally.

Raw Apify datasets are cached under `~/.crag/apify_cache` (TTL `APIFY_CACHE_TTL_HOURS`, default 24h). A second scrape of the same profile reuses that payload and still applies skip/index/caption-first. `APIFY_CACHE=false` disables it. Instagram CDN media URLs can expire; caption-first and hydrate use the permalink.

## `ApifyPostScraper`

Used by Instagram URL ingest (`instagram add <url>` / reel pipeline). Actor `apify/instagram-scraper` with `directUrls`. Fallback: yt-dlp.

No Instagram login or cookies. Media comes from actor CDNs or yt-dlp.
