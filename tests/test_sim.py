import numpy as np

from engine.reporting import bracket_html, build_markdown_report
from engine.sim import run_engine


def test_simulation_is_reproducible_and_complete(scenario, teams):
    first = run_engine(teams, scenario, n=25, seed=99, mode="combined", final_hour=18)
    second = run_engine(teams, scenario, n=25, seed=99, mode="combined", final_hour=18)
    assert first.manifest.run_id == second.manifest.run_id
    assert first.ranking["Campeón %"].tolist() == second.ranking["Campeón %"].tolist()
    assert np.isclose(first.ranking["Campeón %"].sum(), 100.0)
    assert len(first.top_brackets) == 5
    assert all(item["scope"] == "SF_AND_FINAL" for item in first.top_brackets)
    assert all(item["signature_version"] == "decisive-v1" for item in first.top_brackets)
    assert all(len(item["decisive_matches"]) == 3 for item in first.top_brackets)
    representative = first.top_brackets[0]["representative"]
    assert representative.density_signature.startswith("SF:")
    assert "|F:" in representative.density_signature
    assert len(first.sensitivity) == 12
    assert first.argentina_stages.iloc[0]["Probabilidad %"] == 100.0
    report = build_markdown_report(first, scenario.name)
    assert first.manifest.run_id in report
    visual = bracket_html(first.top_brackets[0]["representative"], teams)
    assert "champion-card" in visual
    assert "eliminated" in visual
