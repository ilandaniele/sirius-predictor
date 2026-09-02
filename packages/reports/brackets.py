from __future__ import annotations

# SVG attributes stay on single source lines so the vector output remains auditable.
# ruff: noqa: E501
import hashlib
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from engine.domain import Team, TournamentResult

from .flags import flag_rects

BRACKET_RENDERER_VERSION = "4.0.0"
BRACKET_SCOPE = "SF_AND_FINAL"
SIGNATURE_VERSION = "decisive-v1"
ROUNDS = ("R32", "R16", "QF", "SF", "F")
DISPLAY_ROUNDS = ("SF", "F")
EARLY_ROUNDS = ("R32", "R16", "QF")
ROUND_LABELS = {
    "R32": "16VOS",
    "R16": "8VOS",
    "QF": "4TOS",
    "SF": "SEMIFINALES",
    "F": "FINAL · MADRID · 21/07/2030",
}
EARLY_PATH_CAPTION = (
    "16vos a cuartos: un camino representativo del conjunto, no una clasificación por ronda"
)
EXPECTED_MATCHES = {"R32": 16, "R16": 8, "QF": 4, "SF": 2, "F": 1}
DECISION_LABELS = {"regulation": "", "extra_time": "t.s.", "penalties": "pen."}
COLORS = {
    "background": "#071019",
    "panel": "#0e1c28",
    "line": "#294050",
    "text": "#f3f0e8",
    "muted": "#71818c",
    "gold": "#d7ad53",
    "winner": "#65c5e8",
}


@dataclass(frozen=True, slots=True)
class BracketExportSpec:
    width: int = 3840
    height: int = 2160
    margin: int = 90

    def __post_init__(self) -> None:
        if self.width < 960 or self.height < 540:
            raise ValueError("bracket canvas must be at least 960×540")
        if self.margin < 0 or self.margin * 2 >= min(self.width, self.height):
            raise ValueError("bracket margin leaves no drawable canvas")


@dataclass(frozen=True, slots=True)
class _MatchBox:
    round_name: str
    match: Any
    x: float
    y: float
    width: float
    height: float

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.width, self.height


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _scale(spec: BracketExportSpec) -> float:
    return min(spec.width / 3840, spec.height / 2160)


def _decisive_name_size(scale: float) -> int:
    return max(12, int(31 * scale))


def _box_name_size(box: _MatchBox, scale: float) -> int:
    if box.round_name in DISPLAY_ROUNDS:
        return _decisive_name_size(scale)
    return max(6, int(box.height * 0.30))


def _row_flag_geometry(box: _MatchBox, row: int) -> tuple[float, float, float, float]:
    """(x, y, width, height) for the small flag block in one row of a match box."""
    flag_height = box.height * 0.30
    flag_width = flag_height * 1.5
    flag_x = box.x + max(3.0, box.height * 0.08)
    flag_y = box.y + box.height * (0.10 if row == 0 else 0.58)
    return flag_x, flag_y, flag_width, flag_height


def _trophy_rects(x: float, y: float, width: float, height: float) -> list[tuple[float, float, float, float]]:
    """Rect-only, original abstract trophy silhouette: bowl, handles, stem, base."""
    bowl_height = height * 0.32
    stem_height = height * 0.38
    base_height = height * 0.14
    handle_width = width * 0.14
    handle_height = height * 0.16
    stem_width = width * 0.22
    stem_x = x + (width - stem_width) / 2
    stem_y = y + bowl_height
    base_width = width * 0.55
    base_x = x + (width - base_width) / 2
    base_y = stem_y + stem_height
    return [
        (x, y, width, bowl_height),
        (x - handle_width * 0.55, y + bowl_height * 0.15, handle_width, handle_height),
        (x + width - handle_width * 0.45, y + bowl_height * 0.15, handle_width, handle_height),
        (stem_x, stem_y, stem_width, stem_height),
        (base_x, base_y, base_width, base_height),
    ]


def _winner_probability(match: Any) -> float:
    if match.winner_id == match.home_id:
        return float(match.probabilities.home)
    return float(match.probabilities.away)


def _match_note(match: Any) -> str:
    decision = DECISION_LABELS.get(str(match.decided_by), str(match.decided_by))
    suffix = f" · {decision}" if decision else ""
    return f"P(90′) ganador {100 * _winner_probability(match):.1f}%{suffix}"


def _fit_text(value: str, available_width: float, font_size: float) -> str:
    max_chars = max(4, int(available_width / max(1.0, font_size * 0.58)))
    if len(value) <= max_chars:
        return value
    return value[: max(1, max_chars - 1)].rstrip() + "…"


def _ordered_rounds(result: TournamentResult) -> dict[str, list[Any]]:
    ordered: dict[str, list[Any]] = {}
    for round_name in ROUNDS:
        matches = sorted(
            (match for match in result.matches if match.round_name == round_name),
            key=lambda match: match.match_index,
        )
        expected = EXPECTED_MATCHES[round_name]
        if len(matches) != expected:
            raise ValueError(f"{round_name} must contain {expected} matches, found {len(matches)}")
        if [match.match_index for match in matches] != list(range(expected)):
            raise ValueError(f"{round_name} match indexes must be contiguous from zero")
        if any(match.winner_id is None for match in matches):
            raise ValueError(f"{round_name} contains a knockout match without a winner")
        ordered[round_name] = matches

    for round_index in range(1, len(ROUNDS)):
        previous = ordered[ROUNDS[round_index - 1]]
        current = ordered[ROUNDS[round_index]]
        for index, match in enumerate(current):
            expected_teams = {
                previous[index * 2].winner_id,
                previous[index * 2 + 1].winner_id,
            }
            if {match.home_id, match.away_id} != expected_teams:
                raise ValueError(
                    f"{match.round_name} match {match.match_index} does not follow its feeder matches"
                )
    final = ordered["F"][0]
    if result.champion_id != final.winner_id:
        raise ValueError("champion does not match the final winner")
    if result.runner_up_id not in {final.home_id, final.away_id} - {final.winner_id}:
        raise ValueError("runner-up does not match the final loser")
    return ordered


_HALF_COLUMN_ORDER = ("R32", "R16", "QF", "SF")
_HALF_COLUMN_WIDTH = {"R32": 0.100, "R16": 0.085, "QF": 0.085, "SF": 0.125}
_HALF_COLUMN_GAP = 0.012
_CENTER_GAP = 0.022


def _build_layout(result: TournamentResult, spec: BracketExportSpec) -> dict[str, list[_MatchBox]]:
    """Two-sided bracket: each half converges from its outer edge toward the centered final."""
    matches = _ordered_rounds(result)
    scale = _scale(spec)
    available_width = spec.width - 2 * spec.margin
    decisive_height = max(60.0, 230 * scale)
    body_top = spec.margin + 265 * scale
    body_bottom = spec.height - spec.margin - 170 * scale
    if body_bottom - body_top < decisive_height * 2.0:
        raise ValueError("bracket header and footer leave no room for decisive matches")

    half_size = len(matches["R32"]) // 2
    row_span = (body_bottom - body_top) / half_size
    early_height = max(18.0, min(row_span * 0.74, decisive_height * 0.42))
    heights = {round_name: early_height for round_name in EARLY_ROUNDS}
    heights["SF"] = decisive_height
    heights["F"] = decisive_height

    left_x: dict[str, float] = {}
    cursor = 0.0
    for round_name in _HALF_COLUMN_ORDER:
        left_x[round_name] = cursor
        cursor += _HALF_COLUMN_WIDTH[round_name] + _HALF_COLUMN_GAP
    center_x = cursor - _HALF_COLUMN_GAP + _CENTER_GAP
    center_width = 1.0 - 2 * center_x
    if center_width <= 0.04:
        raise ValueError("bracket canvas is too narrow for a two-sided layout")
    right_x = {
        round_name: 1.0 - left_x[round_name] - _HALF_COLUMN_WIDTH[round_name]
        for round_name in _HALF_COLUMN_ORDER
    }

    def half_centers(start_index: int) -> dict[str, list[float]]:
        centers: dict[str, list[float]] = {
            "R32": [
                body_top + row_span * (offset + 0.5)
                for offset in range(half_size)
            ]
        }
        for round_name, previous_name in (("R16", "R32"), ("QF", "R16"), ("SF", "QF")):
            previous_centers = centers[previous_name]
            centers[round_name] = [
                (previous_centers[2 * index] + previous_centers[2 * index + 1]) / 2
                for index in range(len(previous_centers) // 2)
            ]
        return centers

    left_centers = half_centers(0)
    right_centers = half_centers(half_size)

    layout: dict[str, list[_MatchBox]] = {round_name: [] for round_name in ROUNDS}
    for round_name in _HALF_COLUMN_ORDER:
        side_size = len(matches[round_name]) // 2
        for side_x, side_centers, side_matches in (
            (left_x[round_name], left_centers[round_name], matches[round_name][:side_size]),
            (right_x[round_name], right_centers[round_name], matches[round_name][side_size:]),
        ):
            for local_index, match in enumerate(side_matches):
                layout[round_name].append(
                    _MatchBox(
                        round_name=round_name,
                        match=match,
                        x=spec.margin + available_width * side_x,
                        y=side_centers[local_index] - heights[round_name] / 2,
                        width=available_width * _HALF_COLUMN_WIDTH[round_name],
                        height=heights[round_name],
                    )
                )
    final_center_y = (left_centers["SF"][0] + right_centers["SF"][0]) / 2
    layout["F"].append(
        _MatchBox(
            round_name="F",
            match=matches["F"][0],
            x=spec.margin + available_width * center_x,
            y=final_center_y - decisive_height / 2,
            width=available_width * center_width,
            height=decisive_height,
        )
    )
    return layout


def _champion_box(layout: dict[str, list[_MatchBox]], spec: BracketExportSpec) -> _MatchBox:
    scale = _scale(spec)
    final = layout["F"][0]
    return _MatchBox(
        round_name="_champion",
        match=None,
        x=final.x,
        y=final.y + final.height + 42 * scale,
        width=final.width,
        height=final.height * 0.92,
    )


def _connector_segments(
    layout: dict[str, list[_MatchBox]], champion: _MatchBox
) -> list[tuple[float, float, float, float]]:
    left_sf, right_sf = layout["SF"]
    final = layout["F"][0]
    return [
        (left_sf.right, left_sf.center_y, final.x, final.center_y),
        (final.right, final.center_y, right_sf.x, right_sf.center_y),
        (
            final.x + final.width / 2,
            final.y + final.height,
            champion.x + champion.width / 2,
            champion.y,
        ),
    ]


def _header_labels(
    layout: dict[str, list[_MatchBox]], scale: float
) -> list[tuple[float, str, int, bool]]:
    """(x, text, font_size, centered) for each column label, both sides plus the shared center."""
    labels: list[tuple[float, str, int, bool]] = []
    for round_name in (*EARLY_ROUNDS, "SF"):
        boxes = layout[round_name]
        half = len(boxes) // 2
        size = (
            max(6, int(14 * scale))
            if round_name in EARLY_ROUNDS
            else max(8, int(18 * scale))
        )
        labels.append((boxes[0].x, ROUND_LABELS[round_name], size, False))
        labels.append((boxes[half].x, ROUND_LABELS[round_name], size, False))
    final = layout["F"][0]
    size = max(8, int(18 * scale))
    labels.append((final.x + final.width / 2, ROUND_LABELS["F"], size, True))
    return labels


def _status_copy(application: dict[str, Any]) -> tuple[str, str, str]:
    effective = bool(application.get("effective", False))
    label = str(application.get("label") or "Sirius neutral: estado no informado")
    reviewed = int(application.get("reviewed_observations", 0) or 0)
    teams = int(application.get("teams_with_evidence", 0) or 0)
    detail = f"{reviewed} observaciones revisadas · {teams} selecciones con evidencia"
    return label.upper(), detail, COLORS["winner"] if effective else COLORS["gold"]


def _svg_segment(x1: float, y1: float, x2: float, y2: float, thickness: float) -> str:
    if abs(y1 - y2) < 0.01:
        return (
            f'<rect data-role="connector" x="{min(x1, x2):.1f}" '
            f'y="{y1 - thickness / 2:.1f}" width="{abs(x2 - x1):.1f}" '
            f'height="{thickness:.1f}" fill="{COLORS["line"]}"/>'
        )
    return (
        f'<rect data-role="connector" x="{x1 - thickness / 2:.1f}" '
        f'y="{min(y1, y2):.1f}" width="{thickness:.1f}" '
        f'height="{abs(y2 - y1):.1f}" fill="{COLORS["line"]}"/>'
    )


def _svg(
    result: TournamentResult,
    teams: dict[str, Team],
    density: float,
    rank: int,
    reasons: list[str],
    application: dict[str, Any],
    spec: BracketExportSpec,
    layout: dict[str, list[_MatchBox]],
) -> str:
    champion = _champion_box(layout, spec)
    scale = _scale(spec)
    status, status_detail, status_color = _status_copy(application)
    name_size = max(12, int(31 * scale))
    note_size = max(8, int(16 * scale))
    padding = max(8.0, 24 * scale)
    label_y = spec.margin + 225 * scale
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{spec.width}" height="{spec.height}" viewBox="0 0 {spec.width} {spec.height}">',
        f'<rect width="100%" height="100%" fill="{COLORS["background"]}"/>',
        f'<text x="{spec.margin}" y="{spec.margin}" fill="{COLORS["gold"]}" font-family="Arial" font-size="{max(9, int(28 * scale))}" letter-spacing="{max(1, 6 * scale):.1f}">MUNDIAL 2030 · SIRIUS ENGINE</text>',
        f'<text x="{spec.width / 2:.1f}" y="{spec.margin + 72 * scale:.1f}" fill="{COLORS["text"]}" text-anchor="middle" font-family="Georgia" font-size="{max(20, int(62 * scale))}" font-weight="bold">Cruces decisivos más probables</text>',
        f'<text x="{spec.width - spec.margin}" y="{spec.margin + 12 * scale:.1f}" fill="{COLORS["muted"]}" text-anchor="end" font-family="Arial" font-size="{max(9, int(22 * scale))}">Escenario conjunto #{rank} · {density:.4f}% Monte Carlo</text>',
        f'<text x="{spec.width / 2:.1f}" y="{spec.margin + 128 * scale:.1f}" fill="{status_color}" text-anchor="middle" font-family="Arial" font-size="{max(8, int(20 * scale))}" font-weight="bold">{html.escape(status)}</text>',
        f'<text x="{spec.width / 2:.1f}" y="{spec.margin + 164 * scale:.1f}" fill="{COLORS["muted"]}" text-anchor="middle" font-family="Arial" font-size="{max(7, int(15 * scale))}">{html.escape(status_detail)}</text>',
        f'<text x="{spec.width / 2:.1f}" y="{label_y - 22 * scale:.1f}" fill="{COLORS["muted"]}" text-anchor="middle" font-family="Arial" font-size="{max(6, int(13 * scale))}" font-style="italic">{html.escape(EARLY_PATH_CAPTION)}</text>',
        *(
            f'<text x="{x:.1f}" y="{label_y:.1f}" fill="{COLORS["gold"] if text == "CAMPEÓN" else COLORS["muted"]}" text-anchor="{"middle" if centered else "start"}" font-family="Arial" font-size="{size}" font-weight="bold">{html.escape(text)}</text>'
            for x, text, size, centered in _header_labels(layout, scale)
        ),
    ]
    thickness = max(1.0, 4 * scale)
    elements.extend(
        _svg_segment(x1, y1, x2, y2, thickness)
        for x1, y1, x2, y2 in _connector_segments(layout, champion)
    )
    for round_name in ROUNDS:
        decisive = round_name in DISPLAY_ROUNDS
        for box in layout[round_name]:
            match = box.match
            box_name_size = _box_name_size(box, scale)
            box_padding = padding if decisive else max(3.0, box.height * 0.12)
            corner_radius = max(4, 14 * scale) if decisive else max(2, 5 * scale)
            elements.append(
                f'<rect data-role="match" x="{box.x:.1f}" y="{box.y:.1f}" width="{box.width:.1f}" height="{box.height:.1f}" rx="{corner_radius:.1f}" fill="{COLORS["panel"]}" stroke="{COLORS["line"]}"/>'
            )
            for row, team_id, goals in (
                (0, match.home_id, match.home_goals),
                (1, match.away_id, match.away_goals),
            ):
                color = COLORS["winner"] if match.winner_id == team_id else COLORS["muted"]
                flag_x, flag_y, flag_width, flag_height = _row_flag_geometry(box, row)
                elements.extend(
                    f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{rh:.1f}" fill="{fill}"/>'
                    for rx, ry, rw, rh, fill in flag_rects(flag_x, flag_y, flag_width, flag_height, team_id)
                )
                text_x = flag_x + flag_width + max(3.0, box.height * 0.06)
                name = _fit_text(
                    teams[team_id].team, box.right - box_padding - text_x, box_name_size
                )
                baseline_y = box.y + box.height * (0.34 if row == 0 else 0.82)
                elements.append(
                    f'<text x="{text_x:.1f}" y="{baseline_y:.1f}" fill="{color}" font-family="Arial" font-size="{box_name_size}" font-weight="bold">{html.escape(name)}</text>'
                )
                elements.append(
                    f'<text x="{box.right - box_padding:.1f}" y="{baseline_y:.1f}" fill="{color}" text-anchor="end" font-family="Arial" font-size="{box_name_size}" font-weight="bold">{goals}</text>'
                )
            if not decisive:
                continue
            elements.append(
                f'<text x="{box.right:.1f}" y="{box.y + box.height + 25 * scale:.1f}" fill="{COLORS["muted"]}" text-anchor="end" font-family="Arial" font-size="{note_size}">{html.escape(_match_note(match))}</text>'
            )
    champion_name = _fit_text(
        teams[result.champion_id].team, champion.width - 30 * scale, name_size
    )
    trophy_width = champion.width * 0.30
    trophy_height = champion.height * 0.40
    trophy_x = champion.x + (champion.width - trophy_width) / 2
    trophy_y = champion.y + champion.height * 0.05
    champion_flag_height = champion.height * 0.15
    champion_flag_width = champion_flag_height * 1.5
    champion_flag_x = champion.x + (champion.width - champion_flag_width) / 2
    champion_flag_y = champion.y + champion.height * 0.50
    elements.append(
        f'<rect data-role="champion" x="{champion.x:.1f}" y="{champion.y:.1f}" width="{champion.width:.1f}" height="{champion.height:.1f}" rx="{max(4, 18 * scale):.1f}" fill="{COLORS["gold"]}"/>'
    )
    elements.extend(
        f'<rect x="{tx:.1f}" y="{ty:.1f}" width="{tw:.1f}" height="{th:.1f}" fill="{COLORS["background"]}"/>'
        for tx, ty, tw, th in _trophy_rects(trophy_x, trophy_y, trophy_width, trophy_height)
    )
    elements.extend(
        f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{rh:.1f}" fill="{fill}"/>'
        for rx, ry, rw, rh, fill in flag_rects(
            champion_flag_x, champion_flag_y, champion_flag_width, champion_flag_height,
            result.champion_id,
        )
    )
    elements.extend(
        [
            f'<text x="{champion.x + champion.width / 2:.1f}" y="{champion.y + champion.height * 0.66:.1f}" fill="{COLORS["background"]}" text-anchor="middle" font-family="Arial" font-size="{max(9, int(18 * scale))}" font-weight="bold">CAMPEÓN</text>',
            f'<text x="{champion.x + champion.width / 2:.1f}" y="{champion.y + champion.height * 0.90:.1f}" fill="{COLORS["background"]}" text-anchor="middle" font-family="Georgia" font-size="{name_size}" font-weight="bold">{html.escape(champion_name)}</text>',
        ]
    )
    footer_y = spec.height - spec.margin - 105 * scale
    footer_title = (
        "SEÑALES SIRIUS REVISADAS"
        if application.get("effective")
        else "CONTROL DE EVIDENCIA SIRIUS"
    )
    elements.append(
        f'<text x="{spec.margin}" y="{footer_y:.1f}" fill="{status_color}" font-family="Arial" font-size="{max(8, int(16 * scale))}" font-weight="bold">{footer_title} · EXPERIMENTAL</text>'
    )
    for index, reason in enumerate(reasons[:3]):
        fitted = _fit_text(str(reason), spec.width - 2 * spec.margin, max(7, int(14 * scale)))
        elements.append(
            f'<text x="{spec.margin}" y="{footer_y + (30 + index * 27) * scale:.1f}" fill="{COLORS["muted"]}" font-family="Arial" font-size="{max(7, int(14 * scale))}">• {html.escape(fitted)}</text>'
        )
    elements.append("</svg>")
    return "".join(elements)


def _draw_match_png(
    draw: ImageDraw.ImageDraw,
    box: _MatchBox,
    teams: dict[str, Team],
    scale: float,
) -> None:
    match = box.match
    decisive = box.round_name in DISPLAY_ROUNDS
    name_size = _box_name_size(box, scale)
    padding = max(8.0, 24 * scale) if decisive else max(3.0, box.height * 0.12)
    draw.rounded_rectangle(
        (box.x, box.y, box.right, box.y + box.height),
        radius=max(4, int(14 * scale)) if decisive else max(2, int(5 * scale)),
        fill=COLORS["panel"],
        outline=COLORS["line"],
        width=max(1, int(2 * scale)),
    )
    for row, team_id, goals in (
        (0, match.home_id, match.home_goals),
        (1, match.away_id, match.away_goals),
    ):
        color = COLORS["winner"] if match.winner_id == team_id else COLORS["muted"]
        flag_x, flag_y, flag_width, flag_height = _row_flag_geometry(box, row)
        for rx, ry, rw, rh, fill in flag_rects(flag_x, flag_y, flag_width, flag_height, team_id):
            draw.rectangle((rx, ry, rx + rw, ry + rh), fill=fill)
        text_x = flag_x + flag_width + max(3.0, box.height * 0.06)
        name = _fit_text(teams[team_id].team, box.right - padding - text_x, name_size)
        y = box.y + box.height * (0.29 if row == 0 else 0.76)
        draw.text((text_x, y), name, fill=color, font=_font(name_size, True), anchor="lm")
        draw.text(
            (box.right - padding, y),
            str(goals),
            fill=color,
            font=_font(name_size, True),
            anchor="rm",
        )
    if not decisive:
        return
    draw.text(
        (box.right, box.y + box.height + 8 * scale),
        _match_note(match),
        fill=COLORS["muted"],
        font=_font(max(8, int(16 * scale))),
        anchor="ra",
    )


def _png(
    result: TournamentResult,
    teams: dict[str, Team],
    density: float,
    rank: int,
    reasons: list[str],
    application: dict[str, Any],
    spec: BracketExportSpec,
    path: Path,
    layout: dict[str, list[_MatchBox]],
) -> None:
    champion = _champion_box(layout, spec)
    scale = _scale(spec)
    status, status_detail, status_color = _status_copy(application)
    image = Image.new("RGB", (spec.width, spec.height), COLORS["background"])
    draw = ImageDraw.Draw(image)
    draw.text(
        (spec.margin, spec.margin),
        "MUNDIAL 2030 · SIRIUS ENGINE",
        fill=COLORS["gold"],
        font=_font(max(9, int(28 * scale)), True),
    )
    draw.text(
        (spec.width / 2, spec.margin + 50 * scale),
        "Cruces decisivos más probables",
        fill=COLORS["text"],
        font=_font(max(20, int(62 * scale)), True),
        anchor="ma",
    )
    draw.text(
        (spec.width - spec.margin, spec.margin),
        f"Escenario conjunto #{rank} · {density:.4f}% Monte Carlo",
        fill=COLORS["muted"],
        font=_font(max(9, int(22 * scale))),
        anchor="ra",
    )
    draw.text(
        (spec.width / 2, spec.margin + 118 * scale),
        status,
        fill=status_color,
        font=_font(max(8, int(20 * scale)), True),
        anchor="ma",
    )
    draw.text(
        (spec.width / 2, spec.margin + 154 * scale),
        status_detail,
        fill=COLORS["muted"],
        font=_font(max(7, int(15 * scale))),
        anchor="ma",
    )
    label_y = spec.margin + 225 * scale
    draw.text(
        (spec.width / 2, label_y - 22 * scale),
        EARLY_PATH_CAPTION,
        fill=COLORS["muted"],
        font=_font(max(6, int(13 * scale))),
        anchor="ma",
    )
    for x, text, size, centered in _header_labels(layout, scale):
        draw.text(
            (x, label_y),
            text,
            fill=COLORS["gold"] if text == "CAMPEÓN" else COLORS["muted"],
            font=_font(size, True),
            anchor="ma" if centered else "la",
        )
    for segment in _connector_segments(layout, champion):
        draw.line(segment, fill=COLORS["line"], width=max(1, int(4 * scale)))
    for round_name in ROUNDS:
        for box in layout[round_name]:
            _draw_match_png(draw, box, teams, scale)
    draw.rounded_rectangle(
        (champion.x, champion.y, champion.right, champion.y + champion.height),
        radius=max(4, int(18 * scale)),
        fill=COLORS["gold"],
    )
    trophy_width = champion.width * 0.30
    trophy_height = champion.height * 0.40
    trophy_x = champion.x + (champion.width - trophy_width) / 2
    trophy_y = champion.y + champion.height * 0.05
    for tx, ty, tw, th in _trophy_rects(trophy_x, trophy_y, trophy_width, trophy_height):
        draw.rectangle((tx, ty, tx + tw, ty + th), fill=COLORS["background"])
    champion_flag_height = champion.height * 0.15
    champion_flag_width = champion_flag_height * 1.5
    champion_flag_x = champion.x + (champion.width - champion_flag_width) / 2
    champion_flag_y = champion.y + champion.height * 0.50
    for rx, ry, rw, rh, fill in flag_rects(
        champion_flag_x, champion_flag_y, champion_flag_width, champion_flag_height,
        result.champion_id,
    ):
        draw.rectangle((rx, ry, rx + rw, ry + rh), fill=fill)
    name_size = max(12, int(31 * scale))
    champion_name = _fit_text(
        teams[result.champion_id].team, champion.width - 30 * scale, name_size
    )
    draw.text(
        (champion.x + champion.width / 2, champion.y + champion.height * 0.66),
        "CAMPEÓN",
        fill=COLORS["background"],
        font=_font(max(9, int(18 * scale)), True),
        anchor="mm",
    )
    draw.text(
        (champion.x + champion.width / 2, champion.y + champion.height * 0.90),
        champion_name,
        fill=COLORS["background"],
        font=_font(name_size, True),
        anchor="mm",
    )
    footer_y = spec.height - spec.margin - 105 * scale
    footer_title = (
        "SEÑALES SIRIUS REVISADAS"
        if application.get("effective")
        else "CONTROL DE EVIDENCIA SIRIUS"
    )
    draw.text(
        (spec.margin, footer_y),
        f"{footer_title} · EXPERIMENTAL",
        fill=status_color,
        font=_font(max(8, int(16 * scale)), True),
    )
    for index, reason in enumerate(reasons[:3]):
        fitted = _fit_text(str(reason), spec.width - 2 * spec.margin, max(7, int(14 * scale)))
        draw.text(
            (spec.margin, footer_y + (30 + index * 27) * scale),
            f"• {fitted}",
            fill=COLORS["muted"],
            font=_font(max(7, int(14 * scale))),
        )
    image.save(path, "PNG", optimize=True)


def _pdf_match(
    pdf: canvas.Canvas,
    box: _MatchBox,
    teams: dict[str, Team],
    spec: BracketExportSpec,
    scale: float,
) -> None:
    match = box.match
    decisive = box.round_name in DISPLAY_ROUNDS
    pdf_y = spec.height - box.y - box.height
    pdf.setFillColor(COLORS["panel"])
    pdf.setStrokeColor(COLORS["line"])
    corner_radius = max(4, 14 * scale) if decisive else max(2, 5 * scale)
    pdf.roundRect(box.x, pdf_y, box.width, box.height, corner_radius, fill=1, stroke=1)
    name_size = _box_name_size(box, scale)
    padding = max(8.0, 24 * scale) if decisive else max(3.0, box.height * 0.12)
    pdf.setFont("Helvetica-Bold", name_size)
    for row, team_id, goals in (
        (0, match.home_id, match.home_goals),
        (1, match.away_id, match.away_goals),
    ):
        color = COLORS["winner"] if match.winner_id == team_id else COLORS["muted"]
        flag_x, flag_y, flag_width, flag_height = _row_flag_geometry(box, row)
        for rx, ry, rw, rh, fill in flag_rects(flag_x, flag_y, flag_width, flag_height, team_id):
            pdf.setFillColor(fill)
            pdf.rect(rx, spec.height - ry - rh, rw, rh, fill=1, stroke=0)
        pdf.setFillColor(color)
        text_x = flag_x + flag_width + max(3.0, box.height * 0.06)
        name = _fit_text(teams[team_id].team, box.right - padding - text_x, name_size)
        y = pdf_y + box.height * (0.67 if row == 0 else 0.18)
        pdf.drawString(text_x, y, name)
        pdf.drawRightString(box.right - padding, y, str(goals))
    if not decisive:
        return
    pdf.setFillColor(COLORS["muted"])
    pdf.setFont("Helvetica", max(8, 16 * scale))
    pdf.drawRightString(box.right, pdf_y - 25 * scale, _match_note(match))


def _pdf(
    result: TournamentResult,
    teams: dict[str, Team],
    density: float,
    rank: int,
    reasons: list[str],
    application: dict[str, Any],
    spec: BracketExportSpec,
    path: Path,
    layout: dict[str, list[_MatchBox]],
) -> None:
    champion = _champion_box(layout, spec)
    scale = _scale(spec)
    status, status_detail, status_color = _status_copy(application)
    pdf = canvas.Canvas(str(path), pagesize=(spec.width, spec.height), pageCompression=1)
    pdf.setFillColor(COLORS["background"])
    pdf.rect(0, 0, spec.width, spec.height, fill=1, stroke=0)
    pdf.setFillColor(COLORS["gold"])
    pdf.setFont("Helvetica-Bold", max(9, 28 * scale))
    pdf.drawString(spec.margin, spec.height - spec.margin, "MUNDIAL 2030 · SIRIUS ENGINE")
    pdf.setFillColor(COLORS["text"])
    pdf.setFont("Helvetica-Bold", max(20, 62 * scale))
    pdf.drawCentredString(
        spec.width / 2, spec.height - spec.margin - 72 * scale, "Cruces decisivos más probables"
    )
    pdf.setFillColor(COLORS["muted"])
    pdf.setFont("Helvetica", max(9, 22 * scale))
    pdf.drawRightString(
        spec.width - spec.margin,
        spec.height - spec.margin,
        f"Escenario conjunto #{rank} · {density:.4f}% Monte Carlo",
    )
    pdf.setFillColor(status_color)
    pdf.setFont("Helvetica-Bold", max(8, 20 * scale))
    pdf.drawCentredString(spec.width / 2, spec.height - spec.margin - 128 * scale, status)
    pdf.setFillColor(COLORS["muted"])
    pdf.setFont("Helvetica", max(7, 15 * scale))
    pdf.drawCentredString(
        spec.width / 2, spec.height - spec.margin - 164 * scale, status_detail
    )
    label_y = spec.margin + 225 * scale
    pdf.setFillColor(COLORS["muted"])
    pdf.setFont("Helvetica", max(6, 13 * scale))
    pdf.drawCentredString(
        spec.width / 2, spec.height - (label_y - 22 * scale), EARLY_PATH_CAPTION
    )
    for x, text, size, centered in _header_labels(layout, scale):
        pdf.setFillColor(COLORS["gold"] if text == "CAMPEÓN" else COLORS["muted"])
        pdf.setFont("Helvetica-Bold", size)
        if centered:
            pdf.drawCentredString(x, spec.height - label_y, text)
        else:
            pdf.drawString(x, spec.height - label_y, text)
    pdf.setStrokeColor(COLORS["line"])
    pdf.setLineWidth(max(1, 4 * scale))
    for x1, y1, x2, y2 in _connector_segments(layout, champion):
        pdf.line(x1, spec.height - y1, x2, spec.height - y2)
    for round_name in ROUNDS:
        for box in layout[round_name]:
            _pdf_match(pdf, box, teams, spec, scale)
    champion_pdf_y = spec.height - champion.y - champion.height
    pdf.setFillColor(COLORS["gold"])
    pdf.roundRect(
        champion.x,
        champion_pdf_y,
        champion.width,
        champion.height,
        max(4, 18 * scale),
        fill=1,
        stroke=0,
    )
    trophy_width = champion.width * 0.30
    trophy_height = champion.height * 0.40
    trophy_x = champion.x + (champion.width - trophy_width) / 2
    trophy_y = champion.y + champion.height * 0.05
    pdf.setFillColor(COLORS["background"])
    for tx, ty, tw, th in _trophy_rects(trophy_x, trophy_y, trophy_width, trophy_height):
        pdf.rect(tx, spec.height - ty - th, tw, th, fill=1, stroke=0)
    champion_flag_height = champion.height * 0.15
    champion_flag_width = champion_flag_height * 1.5
    champion_flag_x = champion.x + (champion.width - champion_flag_width) / 2
    champion_flag_y = champion.y + champion.height * 0.50
    for rx, ry, rw, rh, fill in flag_rects(
        champion_flag_x, champion_flag_y, champion_flag_width, champion_flag_height,
        result.champion_id,
    ):
        pdf.setFillColor(fill)
        pdf.rect(rx, spec.height - ry - rh, rw, rh, fill=1, stroke=0)
    name_size = max(12, 31 * scale)
    champion_name = _fit_text(
        teams[result.champion_id].team, champion.width - 30 * scale, name_size
    )
    pdf.setFillColor(COLORS["background"])
    pdf.setFont("Helvetica-Bold", max(9, 18 * scale))
    pdf.drawCentredString(
        champion.x + champion.width / 2, champion_pdf_y + champion.height * 0.34, "CAMPEÓN"
    )
    pdf.setFont("Helvetica-Bold", name_size)
    pdf.drawCentredString(
        champion.x + champion.width / 2, champion_pdf_y + champion.height * 0.10, champion_name
    )
    footer_y = spec.height - spec.margin - 105 * scale
    footer_title = (
        "SEÑALES SIRIUS REVISADAS"
        if application.get("effective")
        else "CONTROL DE EVIDENCIA SIRIUS"
    )
    pdf.setFillColor(status_color)
    pdf.setFont("Helvetica-Bold", max(8, 16 * scale))
    pdf.drawString(spec.margin, spec.height - footer_y, f"{footer_title} · EXPERIMENTAL")
    pdf.setFillColor(COLORS["muted"])
    pdf.setFont("Helvetica", max(7, 14 * scale))
    for index, reason in enumerate(reasons[:3]):
        fitted = _fit_text(str(reason), spec.width - 2 * spec.margin, max(7, 14 * scale))
        pdf.drawString(
            spec.margin, spec.height - footer_y - (30 + index * 27) * scale, f"- {fitted}"
        )
    pdf.save()


def export_five_brackets(
    brackets: list[dict[str, Any]],
    teams: list[Team],
    output_dir: str | Path,
    sirius_reasons: dict[str, list[str]] | None = None,
    sirius_application: dict[str, Any] | None = None,
    spec: BracketExportSpec | None = None,
) -> list[dict[str, Any]]:
    if len(brackets) != 5:
        raise ValueError("exactly five decisive scenarios are required")
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    team_map = {team.team_id: team for team in teams}
    if len(team_map) != len(teams):
        raise ValueError("team ids must be unique")
    configured = spec or BracketExportSpec()
    application = dict(
        sirius_application
        or {
            "status": "neutral_status_not_supplied",
            "label": "Sirius neutral: estado no informado",
            "effective": False,
            "reviewed_observations": 0,
            "pending_observations": 0,
            "teams_with_evidence": 0,
            "teams_with_nonzero_adjustment": 0,
        }
    )
    manifests = []
    for rank, bracket in enumerate(brackets, 1):
        result = bracket.get("representative")
        if not isinstance(result, TournamentResult):
            raise TypeError("each decisive scenario must include a TournamentResult representative")
        if (
            bracket.get("scope") != BRACKET_SCOPE
            or bracket.get("signature_version") != SIGNATURE_VERSION
        ):
            raise ValueError(
                "bracket clustering must use the decisive-v1 semifinal/final signature"
            )
        required_team_ids = {
            team_id
            for match in result.matches
            if match.round_name in ROUNDS
            for team_id in (match.home_id, match.away_id)
        } | {result.champion_id, result.runner_up_id}
        missing = sorted(required_team_ids - set(team_map))
        if missing:
            raise ValueError(f"bracket contains unknown team ids: {', '.join(missing)}")
        layout = _build_layout(result, configured)
        reasons = (sirius_reasons or {}).get(
            result.champion_id,
            ["Sin testimonios Sirius revisados; el ajuste aplicado es neutral"],
        )
        base = target / f"bracket-{rank}"
        svg_path = base.with_suffix(".svg")
        png_path = base.with_suffix(".png")
        pdf_path = base.with_suffix(".pdf")
        svg_path.write_text(
            _svg(
                result,
                team_map,
                float(bracket["density_percent"]),
                rank,
                reasons,
                application,
                configured,
                layout,
            ),
            encoding="utf-8",
        )
        _png(
            result,
            team_map,
            float(bracket["density_percent"]),
            rank,
            reasons,
            application,
            configured,
            png_path,
            layout,
        )
        _pdf(
            result,
            team_map,
            float(bracket["density_percent"]),
            rank,
            reasons,
            application,
            configured,
            pdf_path,
            layout,
        )
        files = {}
        for extension, path in (("svg", svg_path), ("png", png_path), ("pdf", pdf_path)):
            files[extension] = {
                "path": path.as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
        manifests.append(
            {
                "rank": rank,
                "scope": BRACKET_SCOPE,
                "signature_version": SIGNATURE_VERSION,
                "signature": str(bracket["signature"]),
                "champion_id": result.champion_id,
                "runner_up_id": result.runner_up_id,
                "density_percent": float(bracket["density_percent"]),
                "decisive_matches": bracket.get("decisive_matches", []),
                "sirius_application": application,
                "reasons": reasons,
                "renderer_version": BRACKET_RENDERER_VERSION,
                "canvas": {"width": configured.width, "height": configured.height},
                "files": files,
            }
        )
    (target / "manifest.json").write_text(
        json.dumps(manifests, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifests
