from dataclasses import dataclass
from typing import Optional


@dataclass
class NormalizedSource:
    url: str
    platform: str
    content_type: str = "video"
    author: str = ""
    title: str = ""
    description: str = ""
    external_id: Optional[str] = None

