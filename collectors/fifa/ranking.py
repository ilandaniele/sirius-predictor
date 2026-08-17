from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup

from collectors.common.base import Collector, CollectorSpec, claim_from_record
from collectors.common.http import SafeHttpClient
from collectors.common.normalization import normalize_name
from collectors.common.records import RankingRecord
from packages.common.provenance import DataGrade, SourceClaimInput


def _record_from_mapping(item: dict[str, Any], ranking_date: date) -> RankingRecord | None:
    name = item.get("teamName") or item.get("name") or item.get("team")
    rank = item.get("rank") or item.get("position")
    code = item.get("teamCode") or item.get("code") or item.get("id")
    if not name or not rank or not code:
        return None
    points = item.get("totalPoints") or item.get("points")
    return RankingRecord(
        team_code=str(code).upper(),
        team_name=normalize_name(str(name)),
        rank=int(rank),
        points=float(points) if points is not None else None,
        ranking_date=ranking_date,
    )


def parse_fifa_ranking(payload: bytes, ranking_date: date) -> list[RankingRecord]:
    soup = BeautifulSoup(payload, "html.parser")
    records: list[RankingRecord] = []
    for script in soup.find_all("script", type="application/json"):
        try:
            node = json.loads(script.get_text())
        except json.JSONDecodeError:
            continue
        stack: list[Any] = [node]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                record = _record_from_mapping(value, ranking_date)
                if record is not None:
                    records.append(record)
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
    if not records:
        for row in soup.select("table tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.select("th,td")]
            if len(cells) < 3 or not cells[0].isdigit():
                continue
            records.append(
                RankingRecord(
                    rank=int(cells[0]),
                    team_name=normalize_name(cells[1]),
                    team_code=cells[2].upper(),
                    points=float(cells[3]) if len(cells) > 3 else None,
                    ranking_date=ranking_date,
                )
            )
    unique = {record.team_code: record for record in records}
    return sorted(unique.values(), key=lambda record: record.rank)


class FifaRankingCollector(Collector):
    spec = CollectorSpec(
        source_id="fifa_ranking",
        url="https://inside.fifa.com/fifa-world-ranking/men",
        grade=DataGrade.A,
        official=True,
        allowed_hosts=("inside.fifa.com",),
        terms_url="https://www.fifa.com/terms-of-service",
        robots_policy="review-before-enable; no browser bypass",
        priority=10,
    )

    def __init__(self, ranking_date: date, client: SafeHttpClient | None = None):
        self.ranking_date = ranking_date
        self.client = client or SafeHttpClient(self.spec.allowed_hosts)

    def fetch(self) -> bytes:
        return self.client.get(self.spec.url)

    def parse(self, payload: bytes, consulted_at: datetime) -> list[SourceClaimInput]:
        claims: list[SourceClaimInput] = []
        for record in parse_fifa_ranking(payload, self.ranking_date):
            for field_name, value in (
                ("name", record.team_name),
                ("rank", record.rank),
                ("points", record.points),
                ("ranking_date", record.ranking_date.isoformat()),
            ):
                claims.append(
                    claim_from_record(
                        self.spec,
                        consulted_at,
                        "RankingSnapshot",
                        record.team_code,
                        field_name,
                        value,
                        confidence=1.0,
                    )
                )
        return claims
