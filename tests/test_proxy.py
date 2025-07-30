"""
Unit-tests for the AI-API proxy.

We rely on FastAPI’s TestClient to make synchronous calls to the ASGI app,
and we monkey-patch httpx.AsyncClient.request so no real upstream traffic
is generated.
"""
import json
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Import the FastAPI app object
from src.main import app, UPSTREAMS


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------
class DummyResponse:  # Mimics httpx.Response
    def __init__(self, status_code=200, content=b"OK", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"content-type": "application/json"}


@pytest.fixture(autouse=True)
def patch_httpx(monkeypatch):
    """
    Patch httpx.AsyncClient so requests never leave the test process.
    We record the last request for assertions.
    """
    captured = {}

    async def fake_request(self, method, url, headers=None, params=None, content=None, **kw):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["params"] = params or {}
        captured["content"] = content
        return DummyResponse()

    monkeypatch.setattr("httpx.AsyncClient.request", fake_request, raising=True)
    yield captured  # allows tests to inspect what was “sent”


@pytest.fixture
def client():
    """Return a TestClient for the FastAPI application."""
    return TestClient(app)


# -------------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------------
def test_root_endpoint(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json() == {"message": "AI proxy is running"}


@pytest.mark.parametrize("prefix", ["openai", "gemini", "grok"])
def test_swagger_is_available(client, prefix):
    r = client.get("/docs")
    assert r.status_code == 200
    assert b"Swagger UI" in r.content


def test_environment_key_is_used(client, patch_httpx, monkeypatch):
    """
    If an env key exists and no per-request key is sent, proxy must add it.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "env-key-123")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/openai")
    r = client.post(
        "/openai/v1/chat/completions",
        json={"foo": "bar"},
    )
    assert r.status_code == 200
    # Upstream call captured by patch_httpx
    auth_header = patch_httpx["headers"].get("Authorization")
    assert auth_header == "Bearer env-key-123"
    assert patch_httpx["url"].startswith("https://example.com/openai/v1/chat/completions")


def test_header_key_overrides_env(client, patch_httpx, monkeypatch):
    """
    Sending OpenAI-Api-Key header should override any default/env key.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "env-key-should-NOT-be-used")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/openai")
    r = client.post(
        "/openai/v1/chat/completions",
        headers={"OpenAI-Api-Key": "per-request-key-999"},
        json={"foo": "bar"},
    )
    assert r.status_code == 200
    auth_header = patch_httpx["headers"]["Authorization"]
    assert auth_header == "Bearer per-request-key-999"


def test_unconfigured_prefix_returns_502(client):
    r = client.get("/unknown/hello")
    assert r.status_code == 502
    assert r.json()["detail"].startswith("Upstream for prefix")
