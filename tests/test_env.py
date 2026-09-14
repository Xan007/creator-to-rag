import os

from config.env import _strip_env_quotes, getenv


def test_strip_env_quotes():
    assert _strip_env_quotes('"sqlite:///C:/tmp/x.db"') == "sqlite:///C:/tmp/x.db"
    assert _strip_env_quotes("'sqlite:///C:/tmp/x.db'") == "sqlite:///C:/tmp/x.db"
    assert _strip_env_quotes("sqlite:///C:/tmp/x.db") == "sqlite:///C:/tmp/x.db"


def test_getenv_strips_quotes(monkeypatch):
    monkeypatch.setenv("CRAG_DATABASE_URL", '"sqlite:///C:/Users/sierr/.instarag/instarag.db"')
    assert getenv("DATABASE_URL") == "sqlite:///C:/Users/sierr/.instarag/instarag.db"
