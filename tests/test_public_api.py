import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from config.users import get_or_create_user
from src.api.public import app, _recent_queries
from src.pipeline.library import create_library


@pytest.fixture
def public_client(monkeypatch):
    user = get_or_create_user("public-reader")
    digest = hashlib.sha256(b"test-reader-token").hexdigest()
    monkeypatch.setenv("CRAG_PUBLIC_TOKEN_USERS", json.dumps({digest: user.id}))
    _recent_queries.clear()
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer test-reader-token"
        yield client, user


def test_public_surface_excludes_local_administration(public_client):
    client, _ = public_client
    routes = client.get("/openapi.json").json()["paths"]
    assert set(routes) == {"/health", "/libraries", "/query", "/libraries/{library_id}/sources"}
    for path in ("/jobs", "/config/cookies", "/posts", "/users", "/media/test.mp4"):
        assert client.get(path).status_code == 404
    assert client.post("/libraries", json={"name": "unauthorized"}).status_code == 405


def test_public_identity_comes_from_token(public_client):
    client, user = public_client
    other = get_or_create_user("public-other")
    own = create_library(user.id, "Reader library")
    foreign = create_library(other.id, "Other library")
    result = client.get("/libraries", headers={"X-User-Id": other.id}).json()
    assert own["id"] in {item["id"] for item in result}
    assert foreign["id"] not in {item["id"] for item in result}
    assert client.get(f"/libraries/{foreign['slug']}/sources").status_code == 404
    response = client.post("/query", json={"library": foreign["slug"], "question": "Secret?"})
    assert response.status_code == 404


def test_missing_and_invalid_credentials(public_client):
    client, _ = public_client
    client.headers.pop("Authorization")
    assert client.get("/libraries", headers={"X-User-Id": "public-reader"}).status_code == 401
    assert client.get("/libraries", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.get("/health").status_code == 200
    assert client.post("/query", content=b"x" * (128 * 1024 + 1)).status_code == 413


def test_public_queries_never_hydrate_or_accept_user_override(public_client, monkeypatch):
    client, user = public_client
    library = create_library(user.id, "Query library")
    captured = {}

    def fake_query(question, **kwargs):
        captured.update(kwargs)
        return {"answer": question, "sources": []}

    monkeypatch.setattr("src.pipeline.query.query_knowledge", fake_query)
    response = client.post("/query", json={"question": "What is indexed?", "library": library["slug"], "user_id": "other"})
    assert response.status_code == 200
    assert captured["allow_hydration"] is False
    assert captured["user_id"] == user.id
    assert response.headers["cache-control"] == "no-store"
    assert client.post("/query", json={"question": " ", "library": library["slug"]}).status_code == 422


def test_public_rate_limit_and_provider_failure(public_client, monkeypatch):
    client, user = public_client
    library = create_library(user.id, "Rate limited")

    def fail(*args, **kwargs):
        raise RuntimeError("secret upstream details")

    monkeypatch.setattr("src.pipeline.query.query_knowledge", fail)
    body = {"question": "Question", "library": library["slug"]}
    response = client.post("/query", json=body)
    assert response.status_code == 502
    assert "secret" not in response.text
    for _ in range(19):
        assert client.post("/query", json=body).status_code == 502
    assert client.post("/query", json=body).status_code == 429


def test_public_startup_requires_credentials(monkeypatch):
    monkeypatch.setenv("CRAG_PUBLIC_TOKEN_USERS", "{}")
    with pytest.raises(RuntimeError, match="SHA-256"):
        with TestClient(app):
            pass
