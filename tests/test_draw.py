import random
from collections import Counter

from engine.draw import draw_groups, validate_draw


def test_draw_invariants_across_seeds(scenario, teams):
    appearances = Counter()
    for seed in range(30):
        groups = draw_groups(teams, scenario, random.Random(seed))
        validate_draw(groups, scenario)
        assert len(groups) == 16
        for group in groups.values():
            assert {team.pot for team in group} == {1, 2, 3, 4}
            confeds = Counter(team.confed for team in group)
            assert confeds["UEFA"] <= 2
            assert all(count <= (2 if confed == "UEFA" else 1) for confed, count in confeds.items())
            appearances.update(team.team_id for team in group)
    assert set(appearances) == {team.team_id for team in teams}
    assert set(appearances.values()) == {30}
