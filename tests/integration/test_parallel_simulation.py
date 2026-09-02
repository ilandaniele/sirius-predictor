from pathlib import Path

import pytest

from packages.common.types import ModelMode
from packages.montecarlo import run_parallel

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def test_parallel_aggregation_preserves_probability_mass_and_paths() -> None:
    result = run_parallel(
        ROOT / "data" / "scenario.yaml",
        ROOT / "data" / "teams.csv",
        iterations=30,
        seed=90,
        mode=ModelMode.HYBRID,
        workers=2,
    )
    assert result.iterations == 30
    assert result.workers == 2
    assert abs(result.ranking["Campeón %"].sum() - 100) < 1e-9
    assert len(result.top_brackets) == 5
    assert all(bracket["scope"] == "SF_AND_FINAL" for bracket in result.top_brackets)
    assert all(len(bracket["decisive_matches"]) == 3 for bracket in result.top_brackets)
    assert len(result.sensitivity) == 12
    group_probability = result.argentina_stages.loc[
        result.argentina_stages["Etapa alcanzada"] == "Group", "Probabilidad %"
    ].iloc[0]
    assert group_probability == 100
