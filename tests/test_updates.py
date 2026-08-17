from engine.updates import StateStore, _csv_change_summary


def test_content_addressed_snapshots_and_change_detection(tmp_path):
    store = StateStore(tmp_path / "state")
    first = store.capture(
        "source", "https://example.test", b"one", quality="X", content_type="text/plain"
    )
    second = store.capture(
        "source", "https://example.test", b"one", quality="X", content_type="text/plain"
    )
    third = store.capture(
        "source", "https://example.test", b"two", quality="X", content_type="text/plain"
    )
    assert first["status"] == "new"
    assert second["status"] == "unchanged"
    assert third["status"] == "changed"
    assert store.latest_payload("source") == b"two"
    assert len(store.snapshots()) == 3
    assert set(store.snapshots()["quality"]) == {"X"}


def test_csv_diff_is_field_level():
    old = b"team_id,team,pot\nARG,Argentina,1\nESP,Spain,1\n"
    new = b"team_id,team,pot\nARG,Argentina,1\nESP,Espana,2\nBRA,Brazil,1\n"
    summary = _csv_change_summary(old, new)
    assert "altas: BRA" in summary
    assert "ESP(pot,team)" in summary
