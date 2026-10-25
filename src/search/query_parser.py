"""Structured Search Query Parser and SQLAlchemy Filter Generator.

Supports industry-standard filter tokens (GitHub / Gmail / Linear syntax):
- author:username or @username
- title:text or topic:text
- caption:text or desc:text
- knowledge:text or ai:text
- type:reel or type:post
- is:linked or is:unlinked
- has:knowledge or has:ai
- after:YYYY-MM-DD or since:YYYY-MM-DD
- before:YYYY-MM-DD or until:YYYY-MM-DD
- -"negative phrase" or -negative_word
- "exact quoted phrase"
- free multi-word terms (AND logic across words, OR across fields)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, List, Optional
from sqlalchemy import or_, and_

TOKEN_RE = re.compile(
    r'(?:'
    r'(\w+):(?:"([^"]+)"|([^\s]+))|'     # 1: key:"value" or key:value
    r'@([a-zA-Z0-9_\.\-]+)|'             # 4: @username
    r'-(\w+):(?:"([^"]+)"|([^\s]+))|'    # 5: -key:"value" or -key:value
    r'-"([^"]+)"|'                       # 8: -"quoted phrase"
    r'-([^\s]+)|'                        # 9: -word
    r'"([^"]+)"|'                        # 10: "quoted phrase"
    r'([^\s]+)'                          # 11: word
    r')'
)


class ParsedSearchQuery:
    def __init__(self) -> None:
        self.authors: List[str] = []
        self.exclude_authors: List[str] = []
        self.titles: List[str] = []
        self.captions: List[str] = []
        self.knowledge: List[str] = []
        self.positive_terms: List[str] = []
        self.negative_terms: List[str] = []
        self.is_linked: Optional[bool] = None
        self.has_knowledge: Optional[bool] = None
        self.content_type: Optional[str] = None
        self.after_timestamp: Optional[float] = None
        self.before_timestamp: Optional[float] = None

    def is_empty(self) -> bool:
        return (
            not self.authors
            and not self.exclude_authors
            and not self.titles
            and not self.captions
            and not self.knowledge
            and not self.positive_terms
            and not self.negative_terms
            and self.is_linked is None
            and self.has_knowledge is None
            and self.content_type is None
            and self.after_timestamp is None
            and self.before_timestamp is None
        )


def parse_search_query(raw_query: str) -> ParsedSearchQuery:
    pq = ParsedSearchQuery()
    if not raw_query or not raw_query.strip():
        return pq

    for match in TOKEN_RE.finditer(raw_query):
        (
            k, v_quoted, v_raw,
            at_user,
            neg_k, neg_vq, neg_vraw,
            neg_phrase,
            neg_word,
            quoted_phrase,
            word,
        ) = match.groups()

        # 1. key:value or key:"quoted value"
        if k:
            val = (v_quoted or v_raw or "").strip()
            key_lower = k.lower()
            if key_lower in ("author", "creator", "from", "user"):
                pq.authors.append(val.lstrip("@"))
            elif key_lower in ("title", "topic"):
                pq.titles.append(val)
            elif key_lower in ("caption", "desc", "description"):
                pq.captions.append(val)
            elif key_lower in ("knowledge", "content", "ai", "transcript"):
                pq.knowledge.append(val)
            elif key_lower == "type":
                pq.content_type = val.lower()
            elif key_lower == "is":
                if val.lower() == "linked":
                    pq.is_linked = True
                elif val.lower() == "unlinked":
                    pq.is_linked = False
            elif key_lower == "has":
                if val.lower() in ("knowledge", "ai", "transcript"):
                    pq.has_knowledge = True
            elif key_lower in ("after", "since"):
                try:
                    dt = datetime.fromisoformat(val)
                    pq.after_timestamp = dt.timestamp()
                except ValueError:
                    pass
            elif key_lower in ("before", "until"):
                try:
                    dt = datetime.fromisoformat(val)
                    pq.before_timestamp = dt.timestamp()
                except ValueError:
                    pass
            continue

        # 2. @username shorthand
        if at_user:
            pq.authors.append(at_user)
            continue

        # 3. -key:value
        if neg_k:
            neg_val = (neg_vq or neg_vraw or "").strip()
            if neg_k.lower() in ("author", "creator", "from", "user"):
                pq.exclude_authors.append(neg_val.lstrip("@"))
            continue

        # 4. -phrase / -word
        if neg_phrase or neg_word:
            pq.negative_terms.append((neg_phrase or neg_word).strip())
            continue

        # 5. "exact phrase"
        if quoted_phrase:
            pq.positive_terms.append(quoted_phrase.strip())
            continue

        # 6. word
        if word:
            pq.positive_terms.append(word.strip())
            continue

    return pq


def apply_search_filters(base_query: Any, raw_query: str, model_cls: Any) -> Any:
    """Applies parsed filter tokens to an existing SQLAlchemy query on Post."""
    pq = parse_search_query(raw_query)
    if pq.is_empty():
        return base_query

    q = base_query

    # Authors
    for author in pq.authors:
        q = q.filter(model_cls.creator_username.ilike(f"%{author}%"))
    for exc_author in pq.exclude_authors:
        q = q.filter(~model_cls.creator_username.ilike(f"%{exc_author}%"))

    # Explicit field filters
    for title in pq.titles:
        q = q.filter(model_cls.title.ilike(f"%{title}%"))
    for caption in pq.captions:
        q = q.filter(model_cls.description.ilike(f"%{caption}%"))
    for knowledge in pq.knowledge:
        q = q.filter(model_cls.extracted_knowledge.ilike(f"%{knowledge}%"))

    # Type
    if pq.content_type:
        q = q.filter(model_cls.type.ilike(f"%{pq.content_type}%"))

    # Linked / Unlinked
    if pq.is_linked is True:
        q = q.filter(model_cls.library_id != None, model_cls.library_id != "")
    elif pq.is_linked is False:
        q = q.filter(or_(model_cls.library_id == None, model_cls.library_id == ""))

    # Has AI knowledge
    if pq.has_knowledge is True:
        q = q.filter(model_cls.extracted_knowledge != None, model_cls.extracted_knowledge != "")

    # Date ranges
    if pq.after_timestamp:
        q = q.filter(or_(
            model_cls.published_at >= pq.after_timestamp,
            model_cls.indexed_at >= pq.after_timestamp,
        ))
    if pq.before_timestamp:
        q = q.filter(or_(
            model_cls.published_at <= pq.before_timestamp,
            model_cls.indexed_at <= pq.before_timestamp,
        ))

    # Positive terms (AND between terms, OR across all text fields per term)
    for term in pq.positive_terms:
        pat = f"%{term}%"
        q = q.filter(
            or_(
                model_cls.title.ilike(pat),
                model_cls.extracted_knowledge.ilike(pat),
                model_cls.description.ilike(pat),
                model_cls.creator_username.ilike(pat),
            )
        )

    # Negative terms (NOT IN any text fields)
    for term in pq.negative_terms:
        pat = f"%{term}%"
        q = q.filter(
            and_(
                ~model_cls.title.ilike(pat),
                ~model_cls.extracted_knowledge.ilike(pat),
                ~model_cls.description.ilike(pat),
            )
        )

    return q

