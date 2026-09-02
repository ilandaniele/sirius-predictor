from pathlib import Path

import yaml

from packages.sirius import build_sirius_assessments


def _snapshot(record_count: int, feature_id: str) -> dict[str, object]:
    return {
        "schema_version": "sirius-observations-v1",
        "status": "reviewed_observations_only",
        "records": [
            {
                "team_id": "ARG",
                "feature_id": feature_id,
                "layer": "match",
                "polarity": "favorable",
                "strength": 0.8,
                "data_grade": "B",
                "data_confidence": 0.7,
                "hour_robustness": None,
                "explicit_public_rule": True,
                "description": f"testimony {index}",
                "source_claim_ids": [f"claim-{feature_id}-{index}"],
                "source_url": "https://example.com",
                "consulted_at": "2026-08-23T00:00:00+00:00",
                "manually_confirmed": True,
                "requires_known_time": False,
                "time_known": False,
                "parameters": {},
            }
            for index in range(record_count)
        ],
    }


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


def test_build_sirius_assessments_merges_a_single_additional_path(tmp_path: Path) -> None:
    base = _write(tmp_path / "base.yaml", _snapshot(0, "frawley_method"))
    additional = _write(tmp_path / "additional.yaml", _snapshot(1, "frawley_method"))
    assessments, audit = build_sirius_assessments(
        {"ARG"}, base, additional_observations_path=additional
    )
    assert audit["reviewed_observations"] == 1
    assert audit["observation_files"] == 2
    assert len(assessments["ARG"].favorable) == 1


def test_build_sirius_assessments_merges_multiple_additional_paths(tmp_path: Path) -> None:
    base = _write(tmp_path / "base.yaml", _snapshot(0, "frawley_method"))
    sirius_reviewed = _write(tmp_path / "sirius.yaml", _snapshot(1, "solar_return"))
    argumental_reviewed = _write(tmp_path / "argumental.yaml", _snapshot(1, "frawley_method"))
    assessments, audit = build_sirius_assessments(
        {"ARG"},
        base,
        additional_observations_path=[sirius_reviewed, argumental_reviewed],
    )
    assert audit["reviewed_observations"] == 2
    assert audit["observation_files"] == 3
    assert len(audit["observation_snapshots"]) == 3
    feature_ids = {item.feature_id for item in assessments["ARG"].favorable}
    assert feature_ids == {"solar_return", "frawley_method"}


def test_build_sirius_assessments_without_additional_path_behaves_as_before(
    tmp_path: Path,
) -> None:
    base = _write(tmp_path / "base.yaml", _snapshot(1, "solar_return"))
    assessments, audit = build_sirius_assessments({"ARG"}, base)
    assert audit["reviewed_observations"] == 1
    assert "observation_files" not in audit
    assert len(assessments["ARG"].favorable) == 1
