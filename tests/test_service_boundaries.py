import os
import sqlite3
import subprocess
import sys

import pytest

from scripts.snapshot_database import snapshot
from src.connectors.url import detect_platform, extract_url_source


def test_public_import_does_not_load_ingestion():
    code = (
        "import sys; import src.api.public; "
        "assert not any(name in sys.modules for name in "
        "['src.api.app', 'src.api.jobs', 'yt_dlp', 'faster_whisper', 'apify_client'])"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=os.environ.copy())
    assert result.returncode == 0, result.stderr


def test_snapshot_is_consistent_and_never_overwrites(tmp_path):
    source = tmp_path / "source.db"
    target = tmp_path / "snapshot.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE items (value TEXT)")
        db.execute("INSERT INTO items VALUES ('indexed content')")
    snapshot(source, target)
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT value FROM items").fetchone()[0] == "indexed content"
    with pytest.raises(ValueError):
        snapshot(source, target)
    with pytest.raises(ValueError):
        snapshot(source, source)


def test_social_hosts_require_a_real_domain():
    assert detect_platform("https://www.instagram.com/p/123") == "instagram"
    assert detect_platform("https://vm.tiktok.com/123") == "tiktok"
    assert detect_platform("https://instagram.com.attacker.example/post") == "url"
    assert detect_platform("https://tiktok.com@attacker.example/post") == "url"
    with pytest.raises(ValueError, match="YouTube"):
        extract_url_source("https://www.youtube.com/watch?v=123")


def test_packaged_cli_can_show_help():
    from typer.testing import CliRunner
    from src.cli import app
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "instagram" in result.stdout


def test_local_service_rejects_untrusted_browser_origin(monkeypatch):
    from fastapi.testclient import TestClient
    import src.api.app as local_api
    monkeypatch.setattr(local_api, "_cors_origins", ["http://localhost:5173"])
    with TestClient(local_api.app) as client:
        assert client.get("/health", headers={"Origin": "https://untrusted.example"}).status_code == 403
        assert client.get("/health", headers={"Origin": "http://localhost:5173"}).status_code == 200


def test_bulk_delete_does_not_resolve_bulk_as_a_post_id():
    from fastapi.testclient import TestClient
    from src.api.app import app
    with TestClient(app) as client:
        response = client.request("DELETE", "/libraries/missing/posts/bulk", json={"post_ids": []})
    assert response.status_code == 422
    assert response.json()["detail"] == "Provide at least one post_id."
