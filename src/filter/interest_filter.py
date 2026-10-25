import json
import logging
import os
import re
from typing import Dict, List, Set
from config.env import load_runtime_env
from src.llm.factory import LLMClientFactory

load_runtime_env()
logger = logging.getLogger(__name__)


class InterestFilter:
    def __init__(self):
        self.llm = LLMClientFactory.get_client(stage="filter")
        self.model = os.getenv("FILTER_MODEL")

    def filter_batch(self, posts: List[Dict], interests: str, chunk_size: int = 40) -> Set[str]:
        if not interests or not interests.strip():
            return {p["id"] for p in posts}

        matching_ids: Set[str] = set()
        chunks = [posts[i:i + chunk_size] for i in range(0, len(posts), chunk_size)]

        def process_chunk(chunk):
            items_for_prompt = [
                {
                    "id": p["id"],
                    "caption": (p.get("description") or p.get("caption") or "")[:300],
                    "hashtags": p.get("hashtags", [])[:5],
                }
                for p in chunk
            ]

            prompt = f"""You are a batch content triage AI for an Instagram knowledge base.
The user is ONLY interested in posts related to: "{interests}".

Review the following list of posts (by caption and hashtags):
{json.dumps(items_for_prompt, ensure_ascii=False)}

Task:
Determine which post IDs should be KEPT for deep video analysis.
CRITICAL RULE: If a caption is ambiguous, generic, or has no text, YOU MUST KEEP IT. 
ONLY discard a post if the text explicitly proves it is entirely irrelevant (e.g., a clear personal photo, an ad for something unrelated, a meme, etc.).
When in doubt, KEEP the post.

Respond with ONLY a valid JSON array of the IDs you decided to KEEP, like:
["id1", "id2"]
If none match, respond with: []"""

            try:
                raw_response = self.llm.generate(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.model,
                    temperature=0.0,
                )
                clean_text = raw_response.strip()
                if clean_text.startswith("```"):
                    clean_text = re.sub(r"^```[a-zA-Z]*\n?", "", clean_text)
                    clean_text = re.sub(r"\n?```$", "", clean_text)
                clean_text = clean_text.strip()

                accepted_ids = json.loads(clean_text)
                if isinstance(accepted_ids, list):
                    return [str(aid) for aid in accepted_ids]
            except Exception as e:
                logger.warning("Batch filter failed on chunk (%s). Defaulting to include all chunk items.", e)
                return [p["id"] for p in chunk]
            return []

        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=min(5, len(chunks))) as executor:
            futures = [executor.submit(process_chunk, chunk) for chunk in chunks]
            for future in as_completed(futures):
                for aid in future.result():
                    matching_ids.add(aid)

        return matching_ids
