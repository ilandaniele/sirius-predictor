from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup
from pydantic import BaseModel, HttpUrl

SPORT_TERMS = re.compile(
    r"\b(mundial|f[úu]tbol|selecci[oó]n|copa|libertadores|champions|partido|"
    r"river|boca|racing|independiente|san lorenzo|palmeiras|tenis|deport)\b",
    re.IGNORECASE,
)
PREDICTION_TERMS = re.compile(
    r"\b(pron[oó]stic|predi(?:je|cci[oó]n)|campe[oó]n|ganar[aá]?|no ganar[aá]?|"
    r"final(?:ista)?|semifinal|clasificar[aá]?|avanzar[aá]?|eliminad|pelear[aá]? por|empat)\b",
    re.IGNORECASE,
)
TECHNIQUE_TERMS: dict[str, re.Pattern[str]] = {
    "frawley_method": re.compile(r"\bfrawley\b", re.I),
    "house_rulers": re.compile(
        r"\bregente(?:s)?\s+(?:de\s+)?(?:la\s+)?(?:ascendente|casa|mc|medio\s*cielo)\b", re.I
    ),
    "aspects_applying_separating": re.compile(r"\b(?:aplicativ|separativ)[oa]s?\b", re.I),
    "midheaven_ascendant": re.compile(r"\bascendente\b|\bmedio\s*cielo\b|\bMC\b"),
    "electional_domification": re.compile(
        r"\belectiv[ao]s?\b|\bdomificaci[oó]n\b|\bmejor\s+momento\b", re.I
    ),
    "essential_dignities_argumental": re.compile(
        r"\bdignidad(?:es)?\b|\bdomicilio\b|\bexaltaci[oó]n\b", re.I
    ),
    "transits_argumental": re.compile(r"\btr[aá]nsitos?\b", re.I),
    "directed_progressions_argumental": re.compile(
        r"\bprogresi[oó]n(?:es)?\b"
        r"|\b(?:neptuno|sol|luna|marte|venus|mercurio|j[uú]piter|saturno)\s+direccionad[oa]\b"
        r"|\bdirecciones?\s+(?:secundarias?|primarias?|solares?)\b",
        re.I,
    ),
    "lunar_nodes": re.compile(r"\bnodo(?:s)?\s+(?:lunar(?:es)?|norte|sur)\b", re.I),
    "fixed_stars_argumental": re.compile(r"\bestrella(?:s)?\s+fija(?:s)?\b", re.I),
    "retrograde_planets": re.compile(r"\bretr[oó]grad[oa]s?\b", re.I),
    "synastry": re.compile(r"\bsinastr[ií]a\b", re.I),
    "mundane_astrology": re.compile(r"\b(?:astrolog[ií]a|carta)\s+mundana\b", re.I),
}


class ArchivedPrediction(BaseModel):
    post_id: str
    published_at: datetime
    updated_at: datetime
    captured_at: datetime
    url: HttpUrl
    title: str
    content_sha256: str
    sports_relevant: bool
    technique_mentions: list[str]
    explicit_claims: list[str]
    inferred_notes: list[str]
    review_status: str
    quality: str


def _plain_text(content: str) -> str:
    text = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def _canonical_url(entry: dict[str, Any]) -> str:
    for link in entry.get("link", []):
        if link.get("rel") == "alternate" and link.get("href"):
            return str(link["href"])
    raise ValueError("Blogger entry has no canonical alternate URL")


def _claim_candidates(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    candidates = []
    for sentence in sentences:
        if PREDICTION_TERMS.search(sentence):
            candidates.append(sentence[:360])
        if len(candidates) == 3:
            break
    return candidates


def reduce_blogger_entry(entry: dict[str, Any], captured_at: datetime) -> dict[str, Any]:
    content = str(entry.get("content", {}).get("$t", ""))
    title = str(entry.get("title", {}).get("$t", "")).strip()
    text = _plain_text(content)
    combined = f"{title} {text}"
    post_id = str(entry.get("id", {}).get("$t", "")).rsplit("post-", 1)[-1]
    techniques = sorted(
        name for name, pattern in TECHNIQUE_TERMS.items() if pattern.search(combined)
    )
    return {
        "post_id": post_id,
        "published_at": entry["published"]["$t"],
        "updated_at": entry["updated"]["$t"],
        "captured_at": captured_at.isoformat(),
        "url": _canonical_url(entry),
        "title": title,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "sports_relevant": bool(SPORT_TERMS.search(combined)),
        "technique_mentions": techniques,
        "explicit_claims": _claim_candidates(text),
        "inferred_notes": [],
        "review_status": "pending",
        "quality": "B",
    }


def build_archive_index(pages: list[bytes], captured_at: datetime | None = None) -> bytes:
    captured = captured_at or datetime.now(UTC)
    posts: dict[str, dict[str, Any]] = {}
    declared_total = 0
    for payload in pages:
        raw = json.loads(payload)
        feed = raw.get("feed", {})
        declared_total = max(
            declared_total, int(feed.get("openSearch$totalResults", {}).get("$t", 0))
        )
        for entry in feed.get("entry", []):
            post = reduce_blogger_entry(entry, captured)
            posts[post["post_id"]] = post
    ordered = sorted(posts.values(), key=lambda item: item["published_at"])
    result = {
        "schema_version": "argumental-archive-v1",
        "source_name": "Astrología Argumental — Santiago Rodríguez Spuch",
        "source_url": "https://astrologiaargumental.blogspot.com/",
        "feed_url": "https://astrologiaargumental.blogspot.com/feeds/posts/default",
        "consulted_at": captured.isoformat(),
        "quality": "B",
        "declared_total": declared_total,
        "captured_total": len(ordered),
        "complete": bool(ordered) and len(ordered) == declared_total,
        "earliest_published_at": ordered[0]["published_at"] if ordered else None,
        "latest_published_at": ordered[-1]["published_at"] if ordered else None,
        "sports_relevant_total": sum(post["sports_relevant"] for post in ordered),
        "posts": ordered,
    }
    return json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def parse_archive_index(payload: bytes) -> list[ArchivedPrediction]:
    raw = json.loads(payload)
    if raw.get("schema_version") != "argumental-archive-v1":
        raise ValueError("unsupported Astrología Argumental archive schema")
    if not raw.get("complete"):
        raise ValueError(
            "incomplete Astrología Argumental archive cannot be treated as a complete corpus"
        )
    return [ArchivedPrediction.model_validate(item) for item in raw.get("posts", [])]
