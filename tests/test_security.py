"""Phase 0 security tests: path traversal, asset allow-list, CORS, and rate limiting."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import app, rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    rate_limiter.reset()
    yield
    rate_limiter.reset()


def test_spa_path_traversal_blocked():
    client = TestClient(app)
    for path in (
        "/..%2f..%2frequirements.txt",
        "/..%2f..%2f..%2fetc%2fos-release",
        "/%2e%2e/%2e%2e/requirements.txt",
        "/..%5c..%5crequirements.txt",
    ):
        resp = client.get(path)
        assert resp.status_code in (200, 404), f"Unexpected status for {path}: {resp.status_code}"
        body = resp.text
        assert "fastapi" not in body.lower(), f"Leaked requirements.txt for {path}"
        assert "pretty_name=" not in body.lower(), f"Leaked /etc/os-release for {path}"
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            assert "text/html" in content_type or "application/json" in content_type


def test_asset_endpoint_allowlist_and_traversal():
    client = TestClient(app)
    for path in (
        "/api/assets/..%2f..%2frequirements.txt",
        "/api/assets/not_a_known_asset.png",
        "/api/assets/%2e%2e%2f.env",
    ):
        resp = client.get(path)
        assert resp.status_code == 404, f"Expected 404 for {path}, got {resp.status_code}"


def test_cors_no_wildcard_credentials():
    client = TestClient(app)
    resp = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") != "*"
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"
    assert resp.headers.get("access-control-allow-credentials") != "true"


def test_rate_limiter_returns_429_after_limit():
    # Test the token bucket directly and through an endpoint to keep the test fast and offline.
    cap = int(rate_limiter.capacity)
    assert cap >= 30
    for _ in range(cap):
        allowed, _ = rate_limiter.consume("203.0.113.10", cost=1)
        assert allowed is True
    allowed, retry_after = rate_limiter.consume("203.0.113.10", cost=1)
    assert allowed is False
    assert retry_after >= 1

    # Verify HTTP 429 response on /api/inspect once the bucket for this IP is exhausted.
    client = TestClient(app)
    resp = client.post(
        "/api/inspect",
        json={"scenario_key": "LINE_A_PCB"},
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.json()["detail"]
    assert "Retry-After" in resp.headers
