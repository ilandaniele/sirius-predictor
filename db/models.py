from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, IdMixin, TimestampMixin


class DataQuality(Base):
    __tablename__ = "data_qualities"

    code: Mapped[str] = mapped_column(String(1), primary_key=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    precedence: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    requires_manual_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (CheckConstraint("code IN ('A','B','C','D','X')", name="valid_code"),)


class Source(Base, IdMixin, TimestampMixin):
    __tablename__ = "sources"

    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    quality_code: Mapped[str] = mapped_column(ForeignKey("data_qualities.code"), nullable=False)
    official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    terms_url: Mapped[str | None] = mapped_column(Text)


class SourceClaim(Base, IdMixin, TimestampMixin):
    __tablename__ = "source_claims"

    entity_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    entity_key: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False)
    consulted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    inferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manually_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_reference: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )


class Confederation(Base, IdMixin):
    __tablename__ = "confederations"

    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    group_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Team(Base, IdMixin, TimestampMixin):
    __tablename__ = "teams"

    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    confederation_id: Mapped[str] = mapped_column(ForeignKey("confederations.id"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TournamentFormat(Base, IdMixin):
    __tablename__ = "tournament_formats"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    team_count: Mapped[int] = mapped_column(Integer, nullable=False)
    group_count: Mapped[int] = mapped_column(Integer, nullable=False)
    group_size: Mapped[int] = mapped_column(Integer, nullable=False)
    qualifiers_per_group: Mapped[int] = mapped_column(Integer, nullable=False)
    rules: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class Tournament(Base, IdMixin, TimestampMixin):
    __tablename__ = "tournaments"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    edition: Mapped[int] = mapped_column(Integer, nullable=False)
    format_id: Mapped[str] = mapped_column(ForeignKey("tournament_formats.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    assumptions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    __table_args__ = (UniqueConstraint("name", "edition"),)


class RankingSnapshot(Base, IdMixin, TimestampMixin):
    __tablename__ = "ranking_snapshots"

    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    ranking_date: Mapped[date] = mapped_column(Date, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[float | None] = mapped_column(Float)
    source_claim_id: Mapped[str] = mapped_column(ForeignKey("source_claims.id"), nullable=False)
    __table_args__ = (UniqueConstraint("team_id", "ranking_date"),)


class DrawPot(Base, IdMixin):
    __tablename__ = "draw_pots"

    tournament_id: Mapped[str] = mapped_column(ForeignKey("tournaments.id"), nullable=False)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    pot_number: Mapped[int] = mapped_column(Integer, nullable=False)
    host: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_claim_id: Mapped[str | None] = mapped_column(ForeignKey("source_claims.id"))
    __table_args__ = (UniqueConstraint("tournament_id", "team_id"),)


class Group(Base, IdMixin):
    __tablename__ = "tournament_groups"

    tournament_id: Mapped[str] = mapped_column(ForeignKey("tournaments.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(4), nullable=False)
    draw_seed: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("tournament_id", "code"),)


class Venue(Base, IdMixin, TimestampMixin):
    __tablename__ = "venues"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    country_code: Mapped[str] = mapped_column(String(8), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)


class Fixture(Base, IdMixin, TimestampMixin):
    __tablename__ = "fixtures"

    tournament_id: Mapped[str] = mapped_column(ForeignKey("tournaments.id"), nullable=False)
    group_id: Mapped[str | None] = mapped_column(ForeignKey("tournament_groups.id"))
    venue_id: Mapped[str | None] = mapped_column(ForeignKey("venues.id"))
    home_team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    kickoff_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    home_goals: Mapped[int | None] = mapped_column(Integer)
    away_goals: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="scheduled")
    source_claim_id: Mapped[str | None] = mapped_column(ForeignKey("source_claims.id"))


class Person(Base, IdMixin, TimestampMixin):
    __tablename__ = "persons"

    canonical_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    country_code: Mapped[str | None] = mapped_column(String(8))


class CoachTenure(Base, IdMixin, TimestampMixin):
    __tablename__ = "coach_tenures"

    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id"), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    source_claim_id: Mapped[str] = mapped_column(ForeignKey("source_claims.id"), nullable=False)


class CaptainTenure(Base, IdMixin, TimestampMixin):
    __tablename__ = "captain_tenures"

    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id"), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    source_claim_id: Mapped[str] = mapped_column(ForeignKey("source_claims.id"), nullable=False)


class BirthData(Base, IdMixin, TimestampMixin):
    __tablename__ = "birth_data"

    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id"), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    birth_time: Mapped[str | None] = mapped_column(String(8))
    timezone: Mapped[str | None] = mapped_column(String(80))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    time_known: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rodden_rating: Mapped[str | None] = mapped_column(String(8))
    __table_args__ = (
        CheckConstraint(
            "time_known IS FALSE OR (birth_time IS NOT NULL AND timezone IS NOT NULL)",
            name="known_time_requires_value",
        ),
    )


class BirthDataSource(Base, IdMixin):
    __tablename__ = "birth_data_sources"

    birth_data_id: Mapped[str] = mapped_column(ForeignKey("birth_data.id"), nullable=False)
    source_claim_id: Mapped[str] = mapped_column(ForeignKey("source_claims.id"), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FederationEvent(Base, IdMixin, TimestampMixin):
    __tablename__ = "federation_events"

    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source_claim_id: Mapped[str] = mapped_column(ForeignKey("source_claims.id"), nullable=False)


class WorldCupDebutEvent(Base, IdMixin):
    __tablename__ = "world_cup_debut_events"

    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), unique=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fixture_id: Mapped[str | None] = mapped_column(ForeignKey("fixtures.id"))
    source_claim_id: Mapped[str] = mapped_column(ForeignKey("source_claims.id"), nullable=False)


class CoachDebutEvent(Base, IdMixin):
    __tablename__ = "coach_debut_events"

    coach_tenure_id: Mapped[str] = mapped_column(ForeignKey("coach_tenures.id"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fixture_id: Mapped[str | None] = mapped_column(ForeignKey("fixtures.id"))
    source_claim_id: Mapped[str] = mapped_column(ForeignKey("source_claims.id"), nullable=False)


class AstrologyChart(Base, IdMixin, TimestampMixin):
    __tablename__ = "astrology_charts"

    subject_type: Mapped[str] = mapped_column(String(60), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    input_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    chart_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    house_system: Mapped[str | None] = mapped_column(String(4))
    ephemeris_version: Mapped[str] = mapped_column(String(80), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class AstrologyTechniqueResult(Base, IdMixin, TimestampMixin):
    __tablename__ = "astrology_technique_results"

    chart_id: Mapped[str] = mapped_column(ForeignKey("astrology_charts.id"), nullable=False)
    technique: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    data_confidence: Mapped[float] = mapped_column(Float, nullable=False)


class SiriusReviewCandidate(Base, IdMixin, TimestampMixin):
    """Immutable sentence extracted from the public Sirius archive for human review."""

    __tablename__ = "sirius_review_candidates"

    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    post_id: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    claim_index: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    consulted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quality_code: Mapped[str] = mapped_column(ForeignKey("data_qualities.code"), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    technique_mentions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    inferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (
        UniqueConstraint("post_id", "content_sha256", "claim_index"),
        CheckConstraint("claim_index >= 0", name="non_negative_claim_index"),
    )


class SiriusReviewDecision(Base, IdMixin, TimestampMixin):
    """Append-only human decision; the latest decision determines effective status."""

    __tablename__ = "sirius_review_decisions"

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("sirius_review_candidates.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("sirius_review_decisions.id")
    )
    observation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    __table_args__ = (
        CheckConstraint("action IN ('approved','rejected')", name="valid_review_action"),
    )


class ModelVersion(Base, IdMixin, TimestampMixin):
    __tablename__ = "model_versions"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    mode: Mapped[str] = mapped_column(String(40), nullable=False)
    feature_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    weights: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    git_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("name", "version", "mode"),)


class PredictionSnapshot(Base, IdMixin, TimestampMixin):
    __tablename__ = "prediction_snapshots"

    tournament_id: Mapped[str] = mapped_column(ForeignKey("tournaments.id"), nullable=False)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), nullable=False)
    git_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    assumptions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    simulations: Mapped[int] = mapped_column(Integer, nullable=False)
    weights: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    results: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class SimulationRun(Base, IdMixin, TimestampMixin):
    __tablename__ = "simulation_runs"

    prediction_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("prediction_snapshots.id"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(40), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    iterations: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class SimulationPath(Base, IdMixin):
    __tablename__ = "simulation_paths"

    simulation_run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"), nullable=False)
    family_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    density: Mapped[float] = mapped_column(Float, nullable=False)
    champion_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    bracket: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    asset_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("simulation_run_id", "family_rank"),)


class BacktestRun(Base, IdMixin, TimestampMixin):
    __tablename__ = "backtest_runs"

    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), nullable=False)
    editions: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    cutoff_policy: Mapped[str] = mapped_column(String(120), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    ablations: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False)


IMMUTABLE_MODELS = (
    AstrologyChart,
    AstrologyTechniqueResult,
    SiriusReviewCandidate,
    SiriusReviewDecision,
    ModelVersion,
    PredictionSnapshot,
    SimulationPath,
    BacktestRun,
)


def _prevent_mutation(_mapper: object, _connection: object, target: object) -> None:
    raise ValueError(f"{type(target).__name__} is append-only")


for _model in IMMUTABLE_MODELS:
    event.listen(_model, "before_update", _prevent_mutation)
    event.listen(_model, "before_delete", _prevent_mutation)
