"""Platform connectors that normalize external content into source records."""

from src.connectors.models import NormalizedSource
from src.connectors.url import extract_url_source

__all__ = ["NormalizedSource", "extract_url_source"]
