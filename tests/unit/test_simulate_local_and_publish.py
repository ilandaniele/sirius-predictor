from __future__ import annotations

from typing import Any

import pytest
import requests

from scripts.simulate_local_and_publish import _post_with_retries


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300


def test_post_with_retries_succeeds_immediately_when_the_first_attempt_is_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(200)

    monkeypatch.setattr(requests, "post", fake_post)
    response = _post_with_retries("https://example.com", attempts=3, backoff_seconds=0.0)
    assert response.ok
    assert len(calls) == 1


def test_post_with_retries_recovers_after_a_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts_made = []

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        attempts_made.append(url)
        if len(attempts_made) < 3:
            raise requests.exceptions.ConnectionError("socket hang up")
        return _FakeResponse(200)

    monkeypatch.setattr(requests, "post", fake_post)
    response = _post_with_retries("https://example.com", attempts=3, backoff_seconds=0.0)
    assert response.ok
    assert len(attempts_made) == 3


def test_post_with_retries_raises_after_exhausting_every_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts_made = []

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        attempts_made.append(url)
        return _FakeResponse(500)

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(RuntimeError, match="Falló tras 3 intentos"):
        _post_with_retries("https://example.com", attempts=3, backoff_seconds=0.0)
    assert len(attempts_made) == 3


def test_post_with_retries_forwards_kwargs_to_requests_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        received.update(kwargs)
        return _FakeResponse(200)

    monkeypatch.setattr(requests, "post", fake_post)
    _post_with_retries(
        "https://example.com",
        headers={"X-API-Key": "secret"},
        data=b"payload",
        attempts=1,
        backoff_seconds=0.0,
    )
    assert received["headers"] == {"X-API-Key": "secret"}
    assert received["data"] == b"payload"
    assert received["timeout"] == (30, 900)
