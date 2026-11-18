from __future__ import annotations

import pytest
from pydantic import ValidationError

from packages.common.config import ROOT, Settings
from services.api.schemas import UpdateRequest
from services.api.tasks import celery_app
from services.api.update_pipeline import _git_state


def test_simulation_worker_limit_is_explicit_and_validated() -> None:
    assert (ROOT / "data" / "scenario.yaml").is_file()
    assert Settings(simulation_workers=2).simulation_workers == 2
    assert UpdateRequest(workers=2).workers == 2
    with pytest.raises(ValidationError):
        UpdateRequest(workers=0)


def test_long_tasks_are_requeued_if_a_scale_to_zero_stop_loses_the_worker() -> None:
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_cancel_long_running_tasks_on_connection_loss is True


def test_deployed_code_provenance_does_not_require_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIRIUS_GIT_COMMIT", "a" * 40)
    monkeypatch.setenv("SIRIUS_GIT_DIRTY", "true")
    monkeypatch.setenv("SIRIUS_WORKING_TREE_SHA256", "b" * 64)

    assert _git_state() == {
        "git_commit": "a" * 40,
        "git_dirty": True,
        "working_tree_sha256": "b" * 64,
    }
