import json
from datetime import UTC, datetime

import pytest

from collectors.sirius_archive import build_archive_index, parse_archive_index


def _page(entries: list[dict[str, object]], total: int) -> bytes:
    return json.dumps(
        {
            "feed": {
                "openSearch$totalResults": {"$t": str(total)},
                "entry": entries,
            }
        }
    ).encode()


def _entry(post_id: int, title: str, content: str) -> dict[str, object]:
    return {
        "id": {"$t": f"tag:blogger.com,1999:blog-1.post-{post_id}"},
        "published": {"$t": "2014-04-30T15:01:00-03:00"},
        "updated": {"$t": "2014-04-30T15:02:00-03:00"},
        "title": {"$t": title},
        "content": {"$t": content},
        "link": [
            {
                "rel": "alternate",
                "href": f"https://astrologiadeportivaa.blogspot.com/post-{post_id}.html",
            }
        ],
    }


def test_archive_is_complete_deduplicated_and_review_only() -> None:
    captured = datetime(2026, 8, 17, tzinfo=UTC)
    first = _entry(1, "Mundial", "Pronostico que llegará a la final. Revolución solar.")
    second = _entry(2, "Otro tema", "Sin contenido deportivo.")
    payload = build_archive_index([_page([first], 2), _page([first, second], 2)], captured)
    raw = json.loads(payload)
    assert raw["complete"] is True
    assert raw["captured_total"] == 2
    posts = parse_archive_index(payload)
    assert posts[0].review_status == "pending"
    assert posts[0].inferred_notes == []
    assert posts[0].sports_relevant is True
    assert "solar_return" in posts[0].technique_mentions


def test_incomplete_archive_is_rejected() -> None:
    payload = build_archive_index([_page([_entry(1, "Mundial", "Partido")], 2)])
    with pytest.raises(ValueError, match="incomplete"):
        parse_archive_index(payload)
