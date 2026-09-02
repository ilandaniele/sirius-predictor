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
    r"river|boca|racing|independiente|san lorenzo|tenis|deport)\b",
    re.IGNORECASE,
)
PREDICTION_TERMS = re.compile(
    r"\b(pron[oó]stic|predi(?:je|cci[oó]n)|campe[oó]n|ganar[aá]?|no ganar[aá]?|"
    r"final(?:ista)?|semifinal|clasificar[aá]?|avanzar[aá]?|eliminad|pelear[aá]? por)\b",
    re.IGNORECASE,
)
TECHNIQUE_TERMS: dict[str, re.Pattern[str]] = {
    "coach_cycle": re.compile(r"\b(ciclo|debut)\s+(?:del\s+)?(?:dt|t[eé]cnico|entrenador)\b", re.I),
    "world_cup_debut": re.compile(r"\bdebut mundialista\b", re.I),
    "federation_chart": re.compile(
        r"\b(carta\s+(?:de la\s+)?(?:afa|federaci[oó]n)|federaci[oó]n)\b", re.I
    ),
    "captain_chart": re.compile(r"\b(capit[aá]n|messi natal|carta natal)\b", re.I),
    "coach_natal": re.compile(
        r"\b(?:dt|t[eé]cnico|entrenador)\s+natal\b|\bnatal\s+del\s+(?:dt|t[eé]cnico|entrenador)\b",
        re.I,
    ),
    "solar_return": re.compile(r"\brevoluci[oó]n solar\b|\bRS\b", re.I),
    "lunar_return": re.compile(r"\brevoluci[oó]n lunar\b|\bRL\b", re.I),
    "primary_directions": re.compile(r"\bdirecciones primarias\b", re.I),
    "progressions": re.compile(r"\bprogresiones\b", re.I),
    "proluna": re.compile(r"\bproluna\b", re.I),
    "transits": re.compile(r"\btr[aá]nsitos?\b", re.I),
    "dignities_receptions": re.compile(r"\bdignidades?\b|\brecepci[oó]n(?:es)?\b", re.I),
    "solar_lunar_factors": re.compile(
        r"\bposici[oó]n del sol\b|\bposici[oó]n de la luna\b|\bsol[-/ ]luna\b", re.I
    ),
    "antiscia": re.compile(r"\bcontra-?antiscias?|antiscias?\b", re.I),
    "demi_lunar": re.compile(r"\bdemi-?lunar\b", re.I),
    "quarti_lunar": re.compile(r"\bcuarti-?lunar\b", re.I),
    "eclipse": re.compile(
        r"\beclipses?\b|\blunaci[oó]n(?:es)?\b|\bingreso\s+planetario\b|\bingreso\s+de\s+\w+\s+en\b",
        re.I,
    ),
    "harmonics": re.compile(r"\barm[oó]nicas?\b", re.I),
    "fixed_stars": re.compile(r"\bestrellas? fijas?\b", re.I),
    "arabic_parts": re.compile(
        r"\b(parte de (?:fortuna|victoria|esp[ií]ritu)|partes? ar[aá]bigas?)\b", re.I
    ),
    "kickoff_chart": re.compile(r"\bcarta del (?:kick-?off|partido|inicio del partido)\b", re.I),
    "houses_i_vii": re.compile(r"\b[Cc]asas?\s+(?:I|VII|1|7)\b"),
    "rulers_mc_moon": re.compile(r"\bregentes?\b|\bmedio\s*cielo\b|\bMC\b"),
    "modality": re.compile(r"\bmodalidad\s+(?:cardinal|fija|mutable)\b", re.I),
    "critical_minutes": re.compile(
        r"\bminutos?\s+(?:cr[ií]ticos?|de los? goles?)\b"
        r"|\bventanas?\s+de\s+(?:minutos?|activaci[oó]n)\b",
        re.I,
    ),
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
        "schema_version": "sirius-archive-v2",
        "source_name": "Juan Cruz Sirius — Astrología con rigurosidad",
        "source_url": "https://astrologiadeportivaa.blogspot.com/",
        "feed_url": "https://astrologiadeportivaa.blogspot.com/feeds/posts/default",
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
    if raw.get("schema_version") != "sirius-archive-v2":
        raise ValueError("unsupported Sirius archive schema")
    if not raw.get("complete"):
        raise ValueError("incomplete Sirius archive cannot be treated as a complete corpus")
    return [ArchivedPrediction.model_validate(item) for item in raw.get("posts", [])]
