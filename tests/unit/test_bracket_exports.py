from dataclasses import replace
from xml.etree import ElementTree

import pytest

from packages.reports import BracketExportSpec, export_five_brackets
from packages.reports.brackets import (
    BRACKET_RENDERER_VERSION,
    EARLY_ROUNDS,
    EXPECTED_MATCHES,
    ROUNDS,
    _build_layout,
    _match_note,
    _ordered_rounds,
)


def test_exactly_five_brackets_export_svg_png_and_pdf(tmp_path, scenario, teams) -> None:
    from engine.sim import run_engine

    bundle = run_engine(teams, scenario, n=15, seed=44, mode="baseline")
    manifests = export_five_brackets(
        bundle.top_brackets,
        teams,
        tmp_path,
        sirius_reasons={"ARG": ["Testimonio documentado"]},
        spec=BracketExportSpec(960, 540, 20),
    )
    assert len(manifests) == 5
    assert all(set(item["files"]) == {"svg", "png", "pdf"} for item in manifests)
    assert all(item["canvas"] == {"width": 960, "height": 540} for item in manifests)
    assert all(item["renderer_version"] == BRACKET_RENDERER_VERSION for item in manifests)
    assert all(item["scope"] == "SF_AND_FINAL" for item in manifests)
    assert all(item["signature_version"] == "decisive-v1" for item in manifests)
    assert (tmp_path / "manifest.json").exists()

    svg = ElementTree.fromstring((tmp_path / "bracket-1.svg").read_bytes())
    elements = list(svg.iter())
    total_matches = sum(EXPECTED_MATCHES[round_name] for round_name in ROUNDS)
    assert sum(element.attrib.get("data-role") == "match" for element in elements) == total_matches
    assert sum(element.attrib.get("data-role") == "connector" for element in elements) == 3
    assert sum(element.attrib.get("data-role") == "champion" for element in elements) == 1


def test_layout_is_uniform_non_overlapping_and_follows_feeders(scenario, teams) -> None:
    from engine.sim import run_engine

    result = run_engine(teams, scenario, n=15, seed=44, mode="baseline").top_brackets[0][
        "representative"
    ]
    layout = _build_layout(result, BracketExportSpec())
    assert set(layout) == set(ROUNDS)

    early_heights = {round(box.height, 5) for name in EARLY_ROUNDS for box in layout[name]}
    decisive_heights = {round(box.height, 5) for name in ("SF", "F") for box in layout[name]}
    assert len(early_heights) == 1
    assert len(decisive_heights) == 1
    assert next(iter(early_heights)) < next(iter(decisive_heights))

    # Each round's boxes are [left-half..., right-half...]; both halves independently
    # span the full canvas height (two-sided bracket), so non-overlap only holds within a side.
    for boxes in layout.values():
        half = len(boxes) // 2
        for side_boxes in (boxes[:half], boxes[half:]) if half else (boxes,):
            for upper, lower in zip(side_boxes, side_boxes[1:], strict=False):
                assert upper.y + upper.height < lower.y

    for round_name, previous_name in (("R16", "R32"), ("QF", "R16"), ("SF", "QF")):
        previous = layout[previous_name]
        for index, box in enumerate(layout[round_name]):
            expected_center = (previous[2 * index].center_y + previous[2 * index + 1].center_y) / 2
            assert box.center_y == pytest.approx(expected_center)

    left_sf, right_sf = layout["SF"]
    expected_center = (left_sf.center_y + right_sf.center_y) / 2
    assert layout["F"][0].center_y == pytest.approx(expected_center)
    assert left_sf.center_y == pytest.approx(right_sf.center_y)


def test_invalid_lineage_is_rejected_and_penalties_are_labeled(scenario, teams) -> None:
    from engine.sim import run_engine

    result = run_engine(teams, scenario, n=15, seed=44, mode="baseline").top_brackets[0][
        "representative"
    ]
    r16 = next(match for match in result.matches if match.round_name == "R16")
    replacement = replace(r16, home_id="ZZZ")
    malformed = replace(
        result,
        matches=[replacement if match is r16 else match for match in result.matches],
    )
    with pytest.raises(ValueError, match="does not follow its feeder matches"):
        _ordered_rounds(malformed)

    assert _match_note(replace(r16, decided_by="penalties")).endswith("· pen.")
