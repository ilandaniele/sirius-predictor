from __future__ import annotations

from engine.backtest import HistoricalMatch, parse_openfootball


def parse_historical_results(
    payload: bytes, edition: int, source_url: str
) -> list[HistoricalMatch]:
    return parse_openfootball(payload.decode("utf-8-sig"), edition, source_url)
