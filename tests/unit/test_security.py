import socket

import pytest

from packages.common.security import UnsafeUrlError, validate_public_dns, validate_public_url


def test_url_allow_list_rejects_private_literals_and_unlisted_hosts() -> None:
    assert (
        validate_public_url("https://inside.fifa.com/ranking", {"inside.fifa.com"})
        == "https://inside.fifa.com/ranking"
    )
    with pytest.raises(UnsafeUrlError, match="not allow-listed"):
        validate_public_url("https://example.com", {"inside.fifa.com"})
    with pytest.raises(UnsafeUrlError, match="private"):
        validate_public_url("https://127.0.0.1", {"127.0.0.1"})


def test_dns_guard_rejects_non_public_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))],
    )
    with pytest.raises(UnsafeUrlError, match="non-public"):
        validate_public_dns("inside.fifa.com")


def test_dns_guard_accepts_public_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))],
    )
    validate_public_dns("inside.fifa.com")
