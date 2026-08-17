from __future__ import annotations

import ipaddress
import socket
from collections.abc import Collection
from urllib.parse import urlsplit


class UnsafeUrlError(ValueError):
    """Raised when a collector URL violates the outbound allow-list."""


def validate_public_url(url: str, allowed_hosts: Collection[str]) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise UnsafeUrlError("collectors require HTTPS")
    if parsed.username or parsed.password or parsed.fragment:
        raise UnsafeUrlError("credentials and fragments are not allowed")
    hostname = (parsed.hostname or "").lower().rstrip(".")
    allowed = {host.lower().rstrip(".") for host in allowed_hosts}
    if hostname not in allowed:
        raise UnsafeUrlError(f"host is not allow-listed: {hostname}")
    if parsed.port not in {None, 443}:
        raise UnsafeUrlError("non-standard ports are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise UnsafeUrlError("private, loopback and link-local addresses are not allowed")
    return url


def validate_public_dns(hostname: str) -> None:
    """Reject a configured hostname when any current DNS answer is non-public."""

    answers = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    if not answers:
        raise UnsafeUrlError(f"host has no DNS answers: {hostname}")
    for answer in answers:
        address = ipaddress.ip_address(answer[4][0])
        if not address.is_global:
            raise UnsafeUrlError(f"host resolves to a non-public address: {hostname}")
