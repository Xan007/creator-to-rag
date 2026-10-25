from importlib import import_module

_MODULES = {
    "Progress": "_common", "echo": "_common", "query_knowledge": "query",
    "hydrate_sources": "hydrate", "add_reel": "reel", "run_profile": "run",
    "scrape_profile": "run", "import_user_saved_posts": "saved", "process_saved": "saved",
    "create_library": "library", "ingest_urls": "library", "link_posts_to_library": "library",
    "list_libraries": "library", "resolve_library": "library",
}


def __getattr__(name):
    if name not in _MODULES:
        raise AttributeError(name)
    value = getattr(import_module(f"src.pipeline.{_MODULES[name]}"), name)
    globals()[name] = value
    return value

__all__ = [
    "Progress",
    "echo",
    "scrape_profile",
    "run_profile",
    "import_user_saved_posts",
    "process_saved",
    "add_reel",
    "query_knowledge",
    "hydrate_sources",
    "create_library",
    "list_libraries",
    "ingest_urls",
    "link_posts_to_library",
    "resolve_library",
]
