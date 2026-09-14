from typing import Any, Dict, List, Optional
from config.groups import (
    GroupInfo,
    add_post_to_group,
    create_group,
    get_post_ids_in_group,
    load_group_by_name,
    remove_post_from_group,
    share_group,
    unshare_group,
)
from config.users import load_user
from src.pipeline._common import Progress, echo
from storage.db import get_session
import storage.repositories as repo


def populate_group_from_profile(
    user_id: str,
    group_name: str,
    creator_username: str,
    *,
    interests: Optional[str] = None,
    progress: Progress = echo,
) -> Dict[str, Any]:
    group = load_group_by_name(user_id, group_name)
    if not group:
        raise ValueError(f"Group '{group_name}' not found for user.")

    db = get_session()
    try:
        posts = repo.list_posts(db, creator_username=creator_username)
    finally:
        db.close()

    if not posts:
        raise ValueError(f"No posts found for creator @{creator_username}. Run 'profile scrape {creator_username}' first.")

    existing_group_post_ids = set(get_post_ids_in_group(group.id))
    candidates = [p for p in posts if p.id not in existing_group_post_ids]

    if not candidates:
        progress("All posts from this creator are already in the group.")
        return {"added": 0, "matched": 0, "total_candidates": 0}

    progress(f"Adding all {len(candidates)} posts from @{creator_username}.")
    matching_ids = {p.id for p in candidates}

    added_count = 0
    for pid in matching_ids:
        if add_post_to_group(group.id, pid):
            added_count += 1

    return {
        "added": added_count,
        "matched": len(matching_ids),
        "total_candidates": len(candidates),
    }

