from __future__ import annotations

from enum import StrEnum


class ModelMode(StrEnum):
    FOOTBALL_ONLY = "FOOTBALL_ONLY"
    SIRIUS_ONLY = "SIRIUS_ONLY"
    HYBRID = "HYBRID"


class SiriusMode(StrEnum):
    PURIST = "SIRIUS_PURIST"
    CALIBRATED = "SIRIUS_CALIBRATED"
