from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FlagSpec:
    """A simplified, color-accurate flag: stripes or a field-with-circle.

    Central emblems (eagles, stars, coats of arms) are intentionally dropped —
    this renders each team's real, official base colors and orientation, not a
    pixel-perfect reproduction. That keeps 64 flags tractable to draw as plain
    vector shapes while staying recognizable.
    """

    kind: str  # "h" (horizontal stripes), "v" (vertical stripes), "circle"
    colors: tuple[str, ...]


# Real, official base colors per team, sourced from public national flag
# specifications. Complex emblems (Brazil's globe, Mexico's eagle, Turkey's
# star/crescent, etc.) are dropped in favor of the flag's field colors.
FLAGS: dict[str, FlagSpec] = {
    "ARG": FlagSpec("h", ("#6CACE4", "#FFFFFF", "#6CACE4")),
    "ESP": FlagSpec("h", ("#AA151B", "#F1BF00", "#AA151B")),
    "FRA": FlagSpec("v", ("#0055A4", "#FFFFFF", "#EF4135")),
    "ENG": FlagSpec("circle", ("#FFFFFF", "#CF142B")),
    "BRA": FlagSpec("h", ("#009739", "#FEDD00", "#009739")),
    "GER": FlagSpec("h", ("#000000", "#DD0000", "#FFCE00")),
    "NED": FlagSpec("h", ("#AE1C28", "#FFFFFF", "#21468B")),
    "BEL": FlagSpec("v", ("#000000", "#FDDA24", "#EF3340")),
    "POR": FlagSpec("v", ("#046A38", "#DA020E")),
    "MAR": FlagSpec("h", ("#C1272D", "#C1272D", "#006233")),
    "PAR": FlagSpec("h", ("#D52B1E", "#FFFFFF", "#0038A8")),
    "UR": FlagSpec("h", ("#FFFFFF", "#0038A8", "#FFFFFF", "#0038A8")),
    "MEX": FlagSpec("v", ("#006847", "#FFFFFF", "#CE1126")),
    "USA": FlagSpec("h", ("#B22234", "#FFFFFF", "#B22234", "#FFFFFF", "#3C3B6E")),
    "JPN": FlagSpec("circle", ("#FFFFFF", "#BC002D")),
    "SEN": FlagSpec("v", ("#00853F", "#FDEF42", "#E31B23")),
    "ITA": FlagSpec("v", ("#009246", "#FFFFFF", "#CE2B37")),
    "CRO": FlagSpec("h", ("#FF0000", "#FFFFFF", "#171796")),
    "COL": FlagSpec("h", ("#FCD116", "#FCD116", "#003893", "#CE1126")),
    "ECU": FlagSpec("h", ("#FFDD00", "#FFDD00", "#034EA2", "#ED1C24")),
    "DEN": FlagSpec("circle", ("#C60C30", "#FFFFFF")),
    "SUI": FlagSpec("circle", ("#D52B1E", "#FFFFFF")),
    "KOR": FlagSpec("circle", ("#FFFFFF", "#CD2E3A")),
    "IRN": FlagSpec("h", ("#239F40", "#FFFFFF", "#DA0000")),
    "CAN": FlagSpec("v", ("#FF0000", "#FFFFFF", "#FF0000")),
    "NGA": FlagSpec("v", ("#008751", "#FFFFFF", "#008751")),
    "EGY": FlagSpec("h", ("#CE1126", "#FFFFFF", "#000000")),
    "ALG": FlagSpec("v", ("#006233", "#FFFFFF")),
    "AUS": FlagSpec("circle", ("#00247D", "#FFFFFF")),
    "KSA": FlagSpec("h", ("#006C35", "#006C35")),
    "PAN": FlagSpec("h", ("#FFFFFF", "#DA121A", "#FFFFFF", "#08529C")),
    "CIV": FlagSpec("v", ("#FF8200", "#FFFFFF", "#009E60")),
    "AUT": FlagSpec("h", ("#ED2939", "#FFFFFF", "#ED2939")),
    "TUR": FlagSpec("circle", ("#E30A17", "#FFFFFF")),
    "SRB": FlagSpec("h", ("#C6363C", "#0C4076", "#FFFFFF")),
    "NOR": FlagSpec("circle", ("#BA0C2F", "#00205B")),
    "UKR": FlagSpec("h", ("#005BBB", "#FFD500")),
    "CHI": FlagSpec("h", ("#FFFFFF", "#D52B1E")),
    "PER": FlagSpec("v", ("#D91023", "#FFFFFF", "#D91023")),
    "CRC": FlagSpec("h", ("#002B7F", "#FFFFFF", "#CE1126", "#FFFFFF", "#002B7F")),
    "JAM": FlagSpec("h", ("#009B3A", "#FED100", "#000000")),
    "TUN": FlagSpec("circle", ("#E70013", "#FFFFFF")),
    "CMR": FlagSpec("v", ("#007A5E", "#CE1126", "#FCD116")),
    "GHA": FlagSpec("h", ("#CE1126", "#FCD116", "#006B3F")),
    "MLI": FlagSpec("v", ("#14B53A", "#FCD116", "#CE1126")),
    "QAT": FlagSpec("v", ("#FFFFFF", "#8D1B3D")),
    "UZB": FlagSpec("h", ("#0099B5", "#FFFFFF", "#1EB53A")),
    "IRQ": FlagSpec("h", ("#CE1126", "#FFFFFF", "#000000")),
    "NZL": FlagSpec("circle", ("#00247D", "#FFFFFF")),
    "SWE": FlagSpec("circle", ("#006AA7", "#FECC02")),
    "POL": FlagSpec("h", ("#FFFFFF", "#DC143C")),
    "CZE": FlagSpec("h", ("#FFFFFF", "#D7141A")),
    "GRE": FlagSpec("h", ("#0D5EAF", "#FFFFFF", "#0D5EAF", "#FFFFFF")),
    "HON": FlagSpec("h", ("#0073CF", "#FFFFFF", "#0073CF")),
    "GUA": FlagSpec("v", ("#4997D0", "#FFFFFF", "#4997D0")),
    "RSA": FlagSpec("h", ("#DE3831", "#FFFFFF", "#007A4D", "#001489")),
    "COD": FlagSpec("h", ("#007FFF", "#F7D618", "#CE1021")),
    "UAE": FlagSpec("h", ("#00732F", "#FFFFFF", "#000000")),
    "CHN": FlagSpec("circle", ("#DE2910", "#FFDE00")),
    "JOR": FlagSpec("h", ("#000000", "#FFFFFF", "#007A3D")),
    "IDN": FlagSpec("h", ("#FF0000", "#FFFFFF")),
    "NCL": FlagSpec("h", ("#00853D", "#ED1C24", "#0072CE")),
    "SOL": FlagSpec("h", ("#215B33", "#FCD116", "#0051A5")),
    "TAH": FlagSpec("h", ("#CE1126", "#FFFFFF", "#CE1126")),
}

DEFAULT_FLAG = FlagSpec("h", ("#2c3e50", "#71818c"))


def flag_for(team_id: str) -> FlagSpec:
    return FLAGS.get(team_id, DEFAULT_FLAG)


def flag_rects(
    x: float, y: float, width: float, height: float, team_id: str
) -> list[tuple[float, float, float, float, str]]:
    """(rect_x, rect_y, rect_w, rect_h, color) tuples approximating the flag.

    Rect-only by design: the bracket SVG security validator allows only
    <rect>/<text> elements, so "circle" flags (Japan, Denmark, Tunisia...)
    are approximated as a field with a centered square block rather than a
    true circle, keeping every export format visually consistent.
    """
    spec = flag_for(team_id)
    if spec.kind == "h":
        band_height = height / len(spec.colors)
        return [
            (x, y + index * band_height, width, band_height, color)
            for index, color in enumerate(spec.colors)
        ]
    if spec.kind == "v":
        band_width = width / len(spec.colors)
        return [
            (x + index * band_width, y, band_width, height, color)
            for index, color in enumerate(spec.colors)
        ]
    if spec.kind == "circle":
        background, foreground = spec.colors
        block_width = width * 0.42
        block_height = height * 0.42
        block_x = x + (width - block_width) / 2
        block_y = y + (height - block_height) / 2
        return [
            (x, y, width, height, background),
            (block_x, block_y, block_width, block_height, foreground),
        ]
    return [(x, y, width, height, DEFAULT_FLAG.colors[0])]
