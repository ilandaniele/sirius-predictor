from pathlib import Path

import pytest

from engine.config import load_scenario, load_teams

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def scenario():
    return load_scenario(ROOT / "data" / "scenario.yaml")


@pytest.fixture(scope="session")
def teams():
    return load_teams(ROOT / "data" / "teams.csv")
