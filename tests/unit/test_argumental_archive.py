import json
from datetime import UTC, datetime

import pytest

from collectors.argumental_archive import build_archive_index, parse_archive_index


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
        "id": {"$t": f"tag:blogger.com,1999:blog-2.post-{post_id}"},
        "published": {"$t": "2026-07-10T15:01:00-03:00"},
        "updated": {"$t": "2026-07-10T15:02:00-03:00"},
        "title": {"$t": title},
        "content": {"$t": content},
        "link": [
            {
                "rel": "alternate",
                "href": f"https://astrologiaargumental.blogspot.com/post-{post_id}.html",
            }
        ],
    }


def test_archive_is_complete_deduplicated_and_review_only() -> None:
    captured = datetime(2026, 8, 23, tzinfo=UTC)
    first = _entry(
        1, "Mundial", "Analisis del partido mediante el metodo Frawley. Ganara la final."
    )
    second = _entry(2, "Otro tema", "Sin contenido deportivo.")
    payload = build_archive_index([_page([first], 2), _page([first, second], 2)], captured)
    raw = json.loads(payload)
    assert raw["schema_version"] == "argumental-archive-v1"
    assert raw["complete"] is True
    assert raw["captured_total"] == 2
    posts = parse_archive_index(payload)
    assert posts[0].review_status == "pending"
    assert posts[0].sports_relevant is True
    assert "frawley_method" in posts[0].technique_mentions


def test_incomplete_archive_is_rejected() -> None:
    payload = build_archive_index([_page([_entry(1, "Mundial", "Partido")], 2)])
    with pytest.raises(ValueError, match="incomplete"):
        parse_archive_index(payload)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("El método Frawley favorece a Argentina en este partido.", "frawley_method"),
        ("El regente de la casa del partido define al ganador.", "house_rulers"),
        (
            "El aspecto aplicativo entre los significadores es clave.",
            "aspects_applying_separating",
        ),
        ("El ascendente de la carta del partido marca al favorito.", "midheaven_ascendant"),
        (
            "Una buena electiva y domificación ayudan a elegir el mejor momento.",
            "electional_domification",
        ),
        (
            "La dignidad y el domicilio de Marte favorecen a la selección.",
            "essential_dignities_argumental",
        ),
        ("Los tránsitos del partido son favorables para el local.", "transits_argumental"),
        (
            "Neptuno direccionado en la carta de Argentina marca el pronostico.",
            "directed_progressions_argumental",
        ),
        ("El nodo lunar de la selección favorece al equipo en la final.", "lunar_nodes"),
        ("Las estrellas fijas del partido son un buen augurio.", "fixed_stars_argumental"),
        ("Mercurio retrógrado complica al equipo en este partido.", "retrograde_planets"),
        ("La sinastría entre las cartas de ambos equipos define el partido.", "synastry"),
        ("La astrología mundana de Argentina favorece esta final.", "mundane_astrology"),
    ],
)
def test_argumental_technique_vocabulary_is_recognized(content: str, expected: str) -> None:
    captured = datetime(2026, 8, 23, tzinfo=UTC)
    entry = _entry(1, "Mundial", content)
    payload = build_archive_index([_page([entry], 1)], captured)
    posts = parse_archive_index(payload)
    assert expected in posts[0].technique_mentions
