from __future__ import annotations

import time

import httpx

from packages.common.security import validate_public_dns, validate_public_url


class SafeHttpClient:
    def __init__(
        self,
        allowed_hosts: tuple[str, ...],
        timeout: float = 15.0,
        max_bytes: int = 5 * 1024 * 1024,
        min_interval: float = 1.0,
    ):
        self.allowed_hosts = allowed_hosts
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.min_interval = min_interval
        self._last_request = 0.0

    def get(self, url: str) -> bytes:
        validated = validate_public_url(url, self.allowed_hosts)
        hostname = httpx.URL(validated).host
        if hostname is None:
            raise ValueError("collector URL has no hostname")
        validate_public_dns(hostname)
        remaining = self.min_interval - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)
        headers = {"User-Agent": "Mundial2030SiriusEngine/0.1 (+research; contact local-owner)"}
        with httpx.Client(
            timeout=self.timeout,
            follow_redirects=False,
            headers=headers,
            trust_env=False,
        ) as client:
            with client.stream("GET", validated) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise ValueError(f"response exceeds {self.max_bytes} bytes")
                    chunks.append(chunk)
        self._last_request = time.monotonic()
        return b"".join(chunks)
