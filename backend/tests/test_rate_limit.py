from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.rate_limit import RateLimitMiddleware, RateLimitRule


def test_rate_limit_blocks_excess_requests_without_calling_route():
    app = FastAPI()
    calls = 0

    @app.post("/login")
    def login():
        nonlocal calls
        calls += 1
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        rules=(RateLimitRule("/login", frozenset({"POST"}), 2, 60),),
    )
    client = TestClient(app)

    assert client.post("/login").status_code == 200
    assert client.post("/login").status_code == 200
    blocked = client.post("/login")

    assert blocked.status_code == 429
    assert blocked.headers["retry-after"]
    assert blocked.headers["cache-control"] == "no-store"
    assert calls == 2


def test_rate_limit_uses_valid_proxy_ip_and_ignores_invalid_spoof_key():
    app = FastAPI()

    @app.post("/login")
    def login():
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        rules=(RateLimitRule("/login", frozenset({"POST"}), 1, 60),),
    )
    client = TestClient(app)

    assert client.post("/login", headers={"X-Real-IP": "203.0.113.10"}).status_code == 200
    assert client.post("/login", headers={"X-Real-IP": "203.0.113.11"}).status_code == 200
    assert client.post("/login", headers={"X-Real-IP": "not-an-ip"}).status_code == 200
    assert client.post("/login", headers={"X-Real-IP": "another-invalid-value"}).status_code == 429


def test_rate_limit_client_state_has_hard_lru_cap():
    downstream = FastAPI()

    @downstream.post("/login")
    def login():
        return {"ok": True}

    middleware = RateLimitMiddleware(
        downstream,
        rules=(RateLimitRule("/login", frozenset({"POST"}), 5, 60),),
        max_tracked_clients=2,
    )
    client = TestClient(middleware)

    for address in ("203.0.113.1", "203.0.113.2", "203.0.113.3"):
        assert client.post("/login", headers={"X-Real-IP": address}).status_code == 200

    assert len(middleware._events) == 2
    assert ("/login", "203.0.113.1") not in middleware._events


def test_dynamic_route_uses_one_canonical_bucket_across_session_ids():
    app = FastAPI()
    calls = 0

    @app.post("/onboarding/interview/{session_id}/answer")
    def answer(session_id: str):
        nonlocal calls
        calls += 1
        return {"session_id": session_id}

    pattern = "/onboarding/interview/{session_id}/answer"
    middleware = RateLimitMiddleware(
        app,
        rules=(RateLimitRule(pattern, frozenset({"POST"}), 2, 60),),
    )
    client = TestClient(middleware)

    assert client.post("/onboarding/interview/session-a/answer").status_code == 200
    assert client.post("/onboarding/interview/session-b/answer").status_code == 200
    assert client.post("/onboarding/interview/session-c/answer").status_code == 429
    assert calls == 2
    assert list(middleware._events) == [(pattern, "testclient")]


def test_route_body_limit_rejects_before_downstream_parsing():
    app = FastAPI()
    calls = 0

    @app.post("/sync")
    async def sync(request: Request):
        nonlocal calls
        await request.body()
        calls += 1
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        rules=(
            RateLimitRule(
                "/sync",
                frozenset({"POST"}),
                5,
                60,
                max_body_bytes=5,
            ),
        ),
    )
    client = TestClient(app)

    rejected = client.post("/sync", content=b"123456")
    assert rejected.status_code == 413
    assert rejected.headers["cache-control"] == "no-store"
    assert calls == 0

    rejected_chunked = client.post("/sync", content=iter((b"123", b"456")))
    assert rejected_chunked.status_code == 413
    assert calls == 0
