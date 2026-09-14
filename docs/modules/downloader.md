# Downloader (`src/downloader/`)

Downloads media into `data/raw/` for extraction, then deletes it unless `--keep-media`.

## `MediaDownloader`

- HTTP download of actor-provided CDN URLs (images and videos).
- CDN fetches retry 3 times with backoff on dropped connections / 5xx. If the video is still missing, yt-dlp uses the Instagram permalink.
- Carousel items download in parallel (up to 4 workers).
- `cleanup_items()` removes local files after analysis.

Pipelines also call `download_with_ytdlp` in `src/pipeline/_common.py` when Apify does not return a direct file URL (TikTok/URL ingest, reel fallback). yt-dlp requests at most 720p for Gemini extraction. There is no interest-filter gate: if the user added the source, it is downloaded.
