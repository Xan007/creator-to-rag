# Scraper (`src/scraper/`)

Instagram metadata only. TikTok uses `src/connectors/`.

## `ApifyScraper`

Used by `crag instagram add <username>`. Actor `sones/instagram-posts-scraper-lowcost`. Yields captions, media URLs, types (reel/image/sidecar). Skips already-known post ids. `newerThan` is re-checked locally.

## `ApifyPostScraper`

Used by Instagram URL ingest (`instagram add <url>` / reel pipeline). Actor `apify/instagram-scraper` with `directUrls`. Fallback: yt-dlp.

No Instagram login or cookies. Media comes from actor CDNs or yt-dlp.
