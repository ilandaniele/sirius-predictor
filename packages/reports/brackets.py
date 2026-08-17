from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from engine.domain import Team, TournamentResult

ROUNDS = ("R32", "R16", "QF", "SF", "F")
ROUND_LABELS = {
    "R32": "DIECISEISAVOS",
    "R16": "OCTAVOS",
    "QF": "CUARTOS",
    "SF": "SEMIFINAL",
    "F": "FINAL · MADRID · 21/07/2030",
}
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


def _winner_probability(match: Any) -> float:
    if match.winner_id == match.home_id:
        return float(match.probabilities.home)
    return float(match.probabilities.away)


def _round_layout(
    result: TournamentResult, spec: BracketExportSpec
) -> Iterator[tuple[str, Any, tuple[float, float, float, float]]]:
    top = spec.margin + int(spec.height * 0.16)
    bottom = spec.height - spec.margin - int(spec.height * 0.16)
    usable_height = bottom - top
    column_width = (spec.width - 2 * spec.margin) / 6
    for round_index, round_name in enumerate(ROUNDS):
        matches = [match for match in result.matches if match.round_name == round_name]
        row_height = usable_height / max(1, len(matches))
        for row_index, match in enumerate(matches):
            x = spec.margin + round_index * column_width
            y = top + row_index * row_height + max(2, row_height * 0.08)
            height = min(max(42, row_height * 0.82), spec.height * 0.12)
            yield round_name, match, (x, y, column_width * 0.86, height)


def _svg(
    result: TournamentResult,
    teams: dict[str, Team],
    density: float,
    reasons: list[str],
    spec: BracketExportSpec,
) -> str:
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{spec.width}" height="{spec.height}" '
        f'viewBox="0 0 {spec.width} {spec.height}">',
        f'<rect width="100%" height="100%" fill="{COLORS["background"]}"/>',
        f'<text x="{spec.margin}" y="{spec.margin}" fill="{COLORS["gold"]}" '
        'font-family="Arial" font-size="30" letter-spacing="7">MUNDIAL 2030 · SIRIUS ENGINE</text>',
        f'<text x="{spec.margin}" y="{spec.margin + 70}" fill="{COLORS["text"]}" '
        'font-family="Georgia" font-size="64" font-weight="bold">Llave simulada completa</text>',
        f'<text x="{spec.width - spec.margin}" y="{spec.margin + 20}" '
        f'fill="{COLORS["muted"]}" text-anchor="end" font-family="Arial" font-size="26">'
        f"Familia de llave · {density:.4f}%</text>",
    ]
    column_width = (spec.width - 2 * spec.margin) / 6
    for index, round_name in enumerate(ROUNDS):
        x = spec.margin + index * column_width
        elements.append(
            f'<text x="{x}" y="{spec.margin + 180}" fill="{COLORS["muted"]}" '
            f'font-family="Arial" font-size="19" letter-spacing="2">'
            f"{ROUND_LABELS[round_name]}</text>"
        )
    for _round_name, match, (x, y, width, height) in _round_layout(result, spec):
        name_size = max(12, int(spec.width / 170))
        elements.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
            f'rx="10" fill="{COLORS["panel"]}" stroke="{COLORS["line"]}"/>'
        )
        half = height / 2
        for row, team_id, goals in (
            (0, match.home_id, match.home_goals),
            (1, match.away_id, match.away_goals),
        ):
            winner = match.winner_id == team_id
            color = COLORS["winner"] if winner else COLORS["muted"]
            weight = "bold" if winner else "normal"
            name = html.escape(teams[team_id].team)
            baseline_y = y + half * row + half * 0.68
            elements.append(
                f'<text x="{x + 16:.1f}" y="{baseline_y:.1f}" fill="{color}" '
                f'font-family="Arial" font-size="{name_size}" font-weight="{weight}">{name}</text>'
            )
            elements.append(
                f'<text x="{x + width - 16:.1f}" y="{baseline_y:.1f}" fill="{color}" '
                f'text-anchor="end" font-family="Arial" font-size="{name_size}" '
                f'font-weight="bold">{goals}</text>'
            )
        probability = _winner_probability(match) * 100
        elements.append(
            f'<text x="{x + width - 16:.1f}" y="{y + height + 18:.1f}" '
            f'fill="{COLORS["muted"]}" text-anchor="end" font-family="Arial" '
            f'font-size="{max(9, name_size - 7)}">P ganador 90′ {probability:.1f}%</text>'
        )
    champion = html.escape(teams[result.champion_id].team)
    card_x = spec.width - spec.margin - column_width * 0.9
    card_y = spec.height * 0.38
    elements.extend(
        [
            f'<rect x="{card_x:.1f}" y="{card_y:.1f}" width="{column_width * 0.9:.1f}" '
            f'height="{spec.height * 0.18:.1f}" rx="22" fill="{COLORS["gold"]}"/>',
            f'<text x="{card_x + column_width * 0.45:.1f}" y="{card_y + 75:.1f}" '
            f'fill="{COLORS["background"]}" text-anchor="middle" font-family="Arial" '
            'font-size="24" font-weight="bold">CAMPEÓN</text>',
            f'<text x="{card_x + column_width * 0.45:.1f}" y="{card_y + 155:.1f}" '
            f'fill="{COLORS["background"]}" text-anchor="middle" font-family="Georgia" '
            f'font-size="48" font-weight="bold">{champion}</text>',
        ]
    )
    reasons_y = spec.height - spec.margin - 130
    elements.append(
        f'<text x="{card_x:.1f}" y="{reasons_y:.1f}" fill="{COLORS["gold"]}" '
        'font-family="Arial" font-size="19">RAZONES SIRIUS · EXPERIMENTAL</text>'
    )
    for index, reason in enumerate(reasons[:4]):
        elements.append(
            f'<text x="{card_x:.1f}" y="{reasons_y + 35 + index * 28:.1f}" '
            f'fill="{COLORS["muted"]}" font-family="Arial" font-size="16">• '
            f"{html.escape(reason)}</text>"
        )
    elements.append("</svg>")
    return "".join(elements)


def _png(
    result: TournamentResult,
    teams: dict[str, Team],
    density: float,
    reasons: list[str],
    spec: BracketExportSpec,
    path: Path,
) -> None:
    image = Image.new("RGB", (spec.width, spec.height), COLORS["background"])
    draw = ImageDraw.Draw(image)
    scale = spec.width / 3840
    draw.text(
        (spec.margin, spec.margin),
        "MUNDIAL 2030 · SIRIUS ENGINE",
        fill=COLORS["gold"],
        font=_font(max(12, int(30 * scale)), True),
    )
    draw.text(
        (spec.margin, spec.margin + 60 * scale),
        "Llave simulada completa",
        fill=COLORS["text"],
        font=_font(max(24, int(64 * scale)), True),
    )
    draw.text(
        (spec.width - spec.margin - 340 * scale, spec.margin),
        f"Familia {density:.4f}%",
        fill=COLORS["muted"],
        font=_font(max(11, int(24 * scale))),
    )
    column_width = (spec.width - 2 * spec.margin) / 6
    for index, round_name in enumerate(ROUNDS):
        draw.text(
            (spec.margin + index * column_width, spec.margin + 180 * scale),
            ROUND_LABELS[round_name],
            fill=COLORS["muted"],
            font=_font(max(8, int(17 * scale)), True),
        )
    body_font = _font(max(8, int(20 * scale)), True)
    for _round_name, match, (x, y, width, height) in _round_layout(result, spec):
        draw.rounded_rectangle(
            (x, y, x + width, y + height), radius=10, fill=COLORS["panel"], outline=COLORS["line"]
        )
        for row, team_id, goals in (
            (0, match.home_id, match.home_goals),
            (1, match.away_id, match.away_goals),
        ):
            winner = match.winner_id == team_id
            color = COLORS["winner"] if winner else COLORS["muted"]
            baseline_y = y + row * height / 2 + 8 * scale
            draw.text((x + 12 * scale, baseline_y), teams[team_id].team, fill=color, font=body_font)
            draw.text((x + width - 32 * scale, baseline_y), str(goals), fill=color, font=body_font)
    champion = teams[result.champion_id].team
    card_x = spec.width - spec.margin - column_width * 0.9
    card_y = spec.height * 0.38
    draw.rounded_rectangle(
        (card_x, card_y, card_x + column_width * 0.9, card_y + spec.height * 0.18),
        radius=max(8, int(22 * scale)),
        fill=COLORS["gold"],
    )
    draw.text(
        (card_x + 28 * scale, card_y + 45 * scale),
        "CAMPEÓN",
        fill=COLORS["background"],
        font=_font(max(13, int(26 * scale)), True),
    )
    draw.text(
        (card_x + 28 * scale, card_y + 110 * scale),
        champion,
        fill=COLORS["background"],
        font=_font(max(17, int(42 * scale)), True),
    )
    reasons_y = spec.height - spec.margin - 130 * scale
    draw.text(
        (card_x, reasons_y),
        "RAZONES SIRIUS · EXPERIMENTAL",
        fill=COLORS["gold"],
        font=_font(max(9, int(17 * scale)), True),
    )
    for index, reason in enumerate(reasons[:4]):
        draw.text(
            (card_x, reasons_y + (32 + index * 28) * scale),
            f"• {reason}",
            fill=COLORS["muted"],
            font=_font(max(8, int(14 * scale))),
        )
    image.save(path, "PNG", optimize=True)


def _pdf(
    result: TournamentResult,
    teams: dict[str, Team],
    density: float,
    reasons: list[str],
    spec: BracketExportSpec,
    path: Path,
) -> None:
    pdf = canvas.Canvas(str(path), pagesize=(spec.width, spec.height), pageCompression=1)
    pdf.setFillColor(COLORS["background"])
    pdf.rect(0, 0, spec.width, spec.height, fill=1, stroke=0)
    pdf.setFillColor(COLORS["gold"])
    pdf.setFont("Helvetica-Bold", 30)
    pdf.drawString(spec.margin, spec.height - spec.margin, "MUNDIAL 2030 · SIRIUS ENGINE")
    pdf.setFillColor(COLORS["text"])
    pdf.setFont("Helvetica-Bold", 54)
    pdf.drawString(spec.margin, spec.height - spec.margin - 70, "Llave simulada completa")
    for round_name, match, (x, y, width, height) in _round_layout(result, spec):
        pdf_y = spec.height - y - height
        pdf.setFillColor(COLORS["panel"])
        pdf.roundRect(x, pdf_y, width, height, 10, fill=1, stroke=0)
        pdf.setFont("Helvetica-Bold", 16)
        for row, team_id, goals in (
            (0, match.home_id, match.home_goals),
            (1, match.away_id, match.away_goals),
        ):
            pdf.setFillColor(COLORS["winner"] if match.winner_id == team_id else COLORS["muted"])
            line_y = pdf_y + height - 26 - row * height / 2
            pdf.drawString(x + 12, line_y, teams[team_id].team)
            pdf.drawRightString(x + width - 12, line_y, str(goals))
        if round_name == "F":
            pdf.setFillColor(COLORS["gold"])
            pdf.setFont("Helvetica-Bold", 14)
            pdf.drawString(x, pdf_y - 24, f"Madrid · densidad {density:.4f}%")
    pdf.setFillColor(COLORS["gold"])
    pdf.setFont("Helvetica-Bold", 36)
    pdf.drawRightString(
        spec.width - spec.margin, 180, f"CAMPEÓN · {teams[result.champion_id].team}"
    )
    pdf.setFillColor(COLORS["muted"])
    pdf.setFont("Helvetica", 14)
    for index, reason in enumerate(reasons[:4]):
        pdf.drawRightString(spec.width - spec.margin, 140 - index * 20, reason)
    pdf.save()


def export_five_brackets(
    brackets: list[dict[str, Any]],
    teams: list[Team],
    output_dir: str | Path,
    sirius_reasons: dict[str, list[str]] | None = None,
    spec: BracketExportSpec | None = None,
) -> list[dict[str, Any]]:
    if len(brackets) != 5:
        raise ValueError("exactly five bracket families are required")
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    team_map = {team.team_id: team for team in teams}
    configured = spec or BracketExportSpec()
    manifests = []
    for rank, bracket in enumerate(brackets, 1):
        result = bracket.get("representative")
        if not isinstance(result, TournamentResult):
            raise TypeError("each bracket must include a TournamentResult representative")
        reasons = (sirius_reasons or {}).get(
            result.champion_id,
            ["Sin testimonios Sirius validados para este snapshot"],
        )
        base = target / f"bracket-{rank}"
        svg_path = base.with_suffix(".svg")
        png_path = base.with_suffix(".png")
        pdf_path = base.with_suffix(".pdf")
        svg_path.write_text(
            _svg(result, team_map, float(bracket["density_percent"]), reasons, configured),
            encoding="utf-8",
        )
        _png(result, team_map, float(bracket["density_percent"]), reasons, configured, png_path)
        _pdf(result, team_map, float(bracket["density_percent"]), reasons, configured, pdf_path)
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
                "champion_id": result.champion_id,
                "runner_up_id": result.runner_up_id,
                "density_percent": float(bracket["density_percent"]),
                "reasons": reasons,
                "canvas": {"width": configured.width, "height": configured.height},
                "files": files,
            }
        )
    manifest_path = target / "manifest.json"
    manifest_path.write_text(json.dumps(manifests, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifests
