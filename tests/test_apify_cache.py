import json
import time

from src.scraper.apify_cache import load_cache, save_cache


def test_apify_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("APIFY_CACHE", "true")
    monkeypatch.setenv("APIFY_CACHE_TTL_HOURS", "24")
    monkeypatch.setenv("CRAG_CONFIG_DIR", str(tmp_path))

    def fake_dir():
        root = tmp_path / "apify_cache"
        root.mkdir(parents=True, exist_ok=True)
        return root

    monkeypatch.setattr("src.scraper.apify_cache.cache_dir", fake_dir)

    payload = {"username": "dominicantips"}
    assert load_cache("ig_profile", payload) is None
    save_cache("ig_profile", payload, [{"code": "AAA"}, {"code": "BBB"}])
    hit = load_cache("ig_profile", payload, min_count=2)
    assert [item["code"] for item in hit] == ["AAA", "BBB"]
    assert load_cache("ig_profile", payload, min_count=10) is None


def test_apify_cache_respects_ttl(tmp_path, monkeypatch):
    monkeypatch.setenv("APIFY_CACHE", "true")
    monkeypatch.setenv("APIFY_CACHE_TTL_HOURS", "1")
    monkeypatch.setattr("src.scraper.apify_cache.cache_dir", lambda: tmp_path)

    payload = {"username": "x"}
    save_cache("ig_profile", payload, [{"code": "AAA"}])
    files = list(tmp_path.glob("*.json"))
    assert files
    record = json.loads(files[0].read_text(encoding="utf-8"))
    record["fetched_at"] = time.time() - 7200
    files[0].write_text(json.dumps(record), encoding="utf-8")
    assert load_cache("ig_profile", payload) is None


def test_apify_cache_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("APIFY_CACHE", "false")
    monkeypatch.setattr("src.scraper.apify_cache.cache_dir", lambda: tmp_path)
    save_cache("ig_profile", {"username": "x"}, [{"code": "AAA"}])
    assert list(tmp_path.glob("*.json")) == []


def test_cached_profile_items_still_honor_skip_ids(monkeypatch):
    monkeypatch.setenv("APIFY_API_KEY", "test-key")

    class Boom:
        def __init__(self, *args, **kwargs):
            pass

        def actor(self, *args, **kwargs):
            raise AssertionError("Apify should not run on a cache hit")

    monkeypatch.setattr("src.scraper.apify_scraper.ApifyClient", Boom)
    monkeypatch.setattr(
        "src.scraper.apify_cache.load_cache",
        lambda *args, **kwargs: [
            {"code": "OLD", "caption": {"text": "old"}, "media_type": 1, "image_url": "https://cdn/old.jpg"},
            {"code": "NEW", "caption": {"text": "new"}, "media_type": 1, "image_url": "https://cdn/new.jpg"},
        ],
    )
    from src.scraper.apify_scraper import ApifyScraper

    posts = list(ApifyScraper(verbose=False).get_posts_metadata("user", 10, ["OLD"]))
    assert [post["id"] for post in posts] == ["NEW"]
    assert posts[0]["description"] == "new"
