"""Process-local throttling for Gemini API calls.

The Gemini quota is project-wide, so independent ingestion workers must not
all send requests at once. The limit is intentionally conservative by default.
"""

import os
import threading


def _max_concurrent_requests() -> int:
    try:
        return max(1, int(os.getenv("GEMINI_MAX_CONCURRENT_REQUESTS", "1")))
    except ValueError:
        return 1


GEMINI_REQUEST_LIMIT = threading.Semaphore(_max_concurrent_requests())
