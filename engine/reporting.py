from __future__ import annotations

import html
from dataclasses import asdict

from .domain import SimulationBundle, Team, TournamentResult

ROUND_LABELS = {
    "R32": "16avos",
    "R16": "Octavos",
    "QF": "Cuartos",
    "SF": "Semifinal",
    "F": "Final",
}


def bracket_html(result: TournamentResult, teams: list[Team]) -> str:
    names = {team.team_id: team.team for team in teams}
    columns: list[str] = []
    for round_name in ("R32", "R16", "QF", "SF", "F"):
        cards: list[str] = []
        round_matches = [match for match in result.matches if match.round_name == round_name]
        for match in round_matches:
            home_class = "winner" if match.winner_id == match.home_id else "eliminated"
            away_class = "winner" if match.winner_id == match.away_id else "eliminated"
            suffix = " (pen.)" if match.decided_by == "penalties" else ""
            cards.append(
                "<div class='match-card'>"
                f"<div class='{home_class}'>{html.escape(names[match.home_id])} "
                f"<span>{match.home_goals}</span></div>"
                f"<div class='{away_class}'>{html.escape(names[match.away_id])} "
                f"<span>{match.away_goals}</span>{suffix}</div>"
                "</div>"
            )
        columns.append(
            "<div class='round-column'>"
            f"<h4>{ROUND_LABELS[round_name]}</h4>" + "".join(cards) + "</div>"
        )
    columns.append(
        "<div class='round-column champion-column'><h4>Campeón</h4>"
        f"<div class='champion-card'>🏆 {html.escape(names[result.champion_id])}</div></div>"
    )
    return (
        """
        <style>
        .bracket {display:grid;grid-template-columns:repeat(6,minmax(150px,1fr));gap:12px;
                  overflow-x:auto;padding:8px 2px 18px 2px;align-items:center}
        .round-column {display:flex;flex-direction:column;justify-content:space-around;
                       gap:8px;height:100%}
        .round-column h4 {text-align:center;color:#d7deea;margin:0 0 8px 0}
        .match-card {background:#151d2b;border:1px solid #2e3d55;border-radius:8px;padding:6px 8px;
                     font-size:12px;box-shadow:0 2px 5px rgba(0,0,0,.2)}
        .match-card div {display:flex;justify-content:space-between;gap:6px;padding:2px 0}
        .winner {color:#f8fafc;font-weight:650}
        .winner span {color:#4ade80}
        .eliminated {color:#718096}
        .champion-card {background:linear-gradient(135deg,#7c5c00,#d6a900);color:white;
                        font-weight:750;padding:18px 12px;border-radius:10px;text-align:center;
                        box-shadow:0 0 18px #d6a90055}
        @media(max-width:900px){.bracket{grid-template-columns:repeat(6,170px)}}
        </style>
        <div class="bracket">"""
        + "".join(columns)
        + "</div>"
    )


def _markdown_table(frame, columns: list[str], limit: int = 10) -> str:
    selected = frame.loc[:, columns].head(limit)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    rows = []
    for _, row in selected.iterrows():
        values = []
        for column in columns:
            value = row[column]
            values.append(f"{value:.3f}" if isinstance(value, float) else str(value))
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join([header, separator, *rows])


def build_markdown_report(bundle: SimulationBundle, scenario_name: str) -> str:
    manifest = asdict(bundle.manifest)
    ranking = _markdown_table(
        bundle.ranking,
        ["Selección", "Campeón %", "IC95 ± pp", "Final %", "Semi %"],
        limit=20,
    )
    stages = _markdown_table(
        bundle.argentina_stages, list(bundle.argentina_stages.columns), limit=10
    )
    brackets = "\n".join(
        f"{index}. **{item['champion']}** sobre {item['runner_up']} — "
        f"densidad {item['density_percent']:.3f}%"
        for index, item in enumerate(bundle.top_brackets, 1)
    )
    return f"""# {scenario_name} — informe de simulación

> Modelo experimental. La astrología no tiene validez científica demostrada para predecir
> resultados deportivos. Los resultados deben interpretarse junto al baseline futbolístico.

## Manifiesto

- Run ID: `{manifest["run_id"]}`
- Creado: {manifest["created_at"]}
- Iteraciones: {manifest["iterations"]}
- Semilla: {manifest["seed"]}
- Modo: {manifest["mode"]}
- Hora base final: {manifest["final_hour"]}:00 Madrid
- Snapshot de entrada: `{manifest["input_sha256"]}`
- Baseline: `{manifest["baseline_version"]}`
- Sirius: `{manifest["sirius_version"]}`

## Ranking

{ranking}

## Camino de Argentina

{stages}

## Cinco llaves de mayor densidad

{brackets}

## Limitaciones

- Participantes, bombos, ratings y fecha/hora de la final son hipótesis versionadas del escenario.
- La llave es una extrapolación hasta que FIFA publique el formato oficial.
- La capa Sirius es un proxy acotado y no una afirmación causal.
- Las frecuencias Monte Carlo incluyen incertidumbre muestral; consultar los intervalos mostrados.
"""
