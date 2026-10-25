"""Process-local throttling for Gemini API calls.

The Gemini quota is project-wide, so independent ingestion workers must not
all send requests at once. The limit is intentionally conservative by default.
"""

import os
import threading


def _max_concurrent_requests() -> int:
    try:
        max_per_key = max(1, int(os.getenv("GEMINI_MAX_CONCURRENT_REQUESTS", "2")))
    except ValueError:
        max_per_key = 2
    
    keys_str = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
    num_keys = max(1, len([k for k in keys_str.split(",") if k.strip()]))
    return num_keys * max_per_key


GEMINI_REQUEST_LIMIT = threading.Semaphore(_max_concurrent_requests())
