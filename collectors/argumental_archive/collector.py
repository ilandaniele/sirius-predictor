from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlencode, urlsplit

from collectors.common.base import Collector, CollectorSpec
from collectors.common.http import SafeHttpClient
from packages.common.provenance import DataGrade, SourceClaimInput

from .parser import build_archive_index, parse_archive_index


class ArgumentalBloggerArchiveCollector(Collector):
    """Capture all Astrología Argumental Blogger posts as a reviewable corpus."""

    def __init__(
        self,
        spec: CollectorSpec,
        client: SafeHttpClient | None = None,
        page_size: int = 100,
    ):
        self.spec = spec
        self.client = client or SafeHttpClient(spec.allowed_hosts, min_interval=1.0)
        self.page_size = page_size

    def _page_url(self, start_index: int) -> str:
        base = f"{self.spec.url.rstrip('/')}/feeds/posts/default"
        query = urlencode(
            {"alt": "json", "max-results": self.page_size, "start-index": start_index}
        )
        return f"{base}?{query}"

    def fetch(self) -> bytes:
        pages = [self.client.get(self._page_url(1))]
        first = json.loads(pages[0])
        total = int(first["feed"]["openSearch$totalResults"]["$t"])
        for start in range(1 + self.page_size, total + 1, self.page_size):
            pages.append(self.client.get(self._page_url(start)))
        payload = build_archive_index(pages)
        if len(payload) > self.client.max_bytes:
            raise ValueError("normalized Argumental archive exceeds configured snapshot limit")
        return payload

    def parse(self, payload: bytes, consulted_at: datetime) -> list[SourceClaimInput]:
        posts = parse_archive_index(payload)
        return [
            SourceClaimInput(
                entity_type="ArgumentalArchivePost",
                entity_key=post.post_id,
                field_name="review_candidate",
                value={
                    "published_at": post.published_at.isoformat(),
                    "title": post.title,
                    "url": str(post.url),
                    "sports_relevant": post.sports_relevant,
                    "technique_mentions": post.technique_mentions,
                    "explicit_claims": post.explicit_claims,
                    "content_sha256": post.content_sha256,
                },
                source_id=self.spec.source_id,
                source_url=post.url,
                consulted_at=consulted_at,
                grade=self.spec.grade,
                confidence=0.6,
                official=False,
                inferred=True,
                manually_confirmed=False,
                raw_reference=post.content_sha256,
            )
            for post in posts
            if post.sports_relevant
        ]


def argumental_archive_collector_from_config(
    record: dict[str, object],
) -> ArgumentalBloggerArchiveCollector:
    url = str(record["url"])
    host = urlsplit(url).hostname
    if host is None:
        raise ValueError("Argumental archive source URL has no hostname")
    grade = DataGrade(str(record["grade"]))
    spec = CollectorSpec(
        source_id=str(record["id"]),
        url=url,
        grade=grade,
        official=False,
        allowed_hosts=(host,),
        terms_url=str(record["terms_url"]),
        robots_policy=str(record["robots_policy"]),
        priority=20,
    )
    return ArgumentalBloggerArchiveCollector(spec)
