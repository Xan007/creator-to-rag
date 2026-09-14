# Filter (`src/filter/`)

`interest_filter.py` still exists as leftover code from an older ingest path that skipped posts which did not match configured interests.

**Library ingest does not use it.** Instagram and TikTok sources the user adds are fully extracted and indexed.

Do not wire interest filtering back into `instagram add` / `tiktok add` unless product requirements change.
