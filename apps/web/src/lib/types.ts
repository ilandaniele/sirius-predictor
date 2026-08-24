export type Provenance = {
  source_id: string;
  name: string;
  url: string | null;
  consulted_at: string;
  quality: "A" | "B" | "C" | "D" | "X";
  official: boolean;
  status: string;
};

export type ApiEnvelope<T> = {
  data: T;
  provenance: Provenance[];
  assumptions: string[];
  warnings: string[];
};

export type Scenario = {
  scenario_id: string;
  as_of: string;
  status: string;
  format: {
    teams: 48 | 64;
    pots: number;
    pot_size: number;
    groups: number;
    group_size: number;
    qualifiers_per_group: number;
    best_third_placed: number;
  };
  final: { city: string; local_date: string; base_hour: number };
};

export type Team = {
  team_id: string;
  team: string;
  confed: string;
  pot: number;
  projected_elo: number;
  sirius_index: number;
  sirius_confidence: number;
  source_id: string;
  as_of: string;
};

export type Prediction = {
  run_id: string;
  mode: string;
  iterations: number;
  ranking: Array<Record<string, string | number>>;
  argentina_stages: Array<Record<string, string | number>>;
  argentina_rivals?: Record<string, Array<Record<string, string | number>>>;
  argentina_groups?: Array<Record<string, string | number>>;
  final_pairs: Array<Record<string, string | number>>;
  sensitivity?: Array<Record<string, string | number>>;
  top_brackets: Array<{
    signature: string;
    signature_version?: "decisive-v1";
    scope?: "SF_AND_FINAL";
    champion: string;
    runner_up: string;
    density_percent: number;
    decisive_matches?: Array<{
      round: "SF" | "F";
      match_index: number;
      team_a_id: string;
      team_a: string;
      team_b_id: string;
      team_b: string;
      winner_id: string;
      winner: string;
    }>;
  }>;
  model_comparison?: Record<string, number | null>;
  changes?: string[];
  update_summary?: string;
  format_size?: 48 | 64;
  scenario_id?: string;
  bracket_urls?: Array<{
    rank: number;
    png: string;
    svg: string;
    pdf: string;
  }>;
  sirius_assessments?: Record<string, SiriusAssessment>;
  sirius_evidence_audit?: {
    reviewed_observations: number;
    pending_observations: number;
    teams_with_evidence: number;
  };
  sirius_application?: {
    status: string;
    label: string;
    effective: boolean;
    reviewed_observations: number;
    pending_observations: number;
    teams_with_evidence: number;
    teams_with_nonzero_adjustment: number;
  };
};

export type SiriusAssessment = {
  journey_index: { value: number | null; status: string; evidence_count: number };
  coronation_index: { value: number | null; status: string; evidence_count: number };
  data_confidence: number;
  explanation: string;
};

export type SiriusArchive = {
  source_name: string;
  source_url: string;
  consulted_at: string;
  quality: "B";
  declared_total: number;
  captured_total: number;
  complete: boolean;
  earliest_published_at: string;
  latest_published_at: string;
  sports_relevant_total: number;
  technique_mentions: Record<string, number>;
  review_policy: string;
  recent_sports_posts: Array<{
    post_id: string;
    published_at: string;
    url: string;
    title: string;
    technique_mentions: string[];
    review_status: string;
  }>;
};

export type SiriusReviewStatus = "pending" | "approved" | "rejected" | "all";

export type SiriusReviewDecision = {
  id: string;
  action: "approved" | "rejected";
  reviewer: string;
  reason: string;
  decided_at: string;
  supersedes_decision_id: string | null;
  observation: Record<string, unknown> | null;
};

export type AstroSource = "sirius" | "argumental";

export type SiriusReviewCandidate = {
  id: string;
  fingerprint: string;
  post_id: string;
  claim_index: number;
  claim_text: string;
  title: string;
  published_at: string;
  source_id: "sirius_blog" | "argumental_blog";
  source_url: string;
  consulted_at: string;
  quality: "B";
  content_sha256: string;
  technique_mentions: string[];
  inferred: true;
  status: Exclude<SiriusReviewStatus, "all">;
  latest_decision: SiriusReviewDecision | null;
};

export type SiriusReviewQueue = {
  counts: { pending: number; approved: number; rejected: number; total: number };
  status: SiriusReviewStatus;
  offset: number;
  limit: number;
  items: SiriusReviewCandidate[];
};

export type SiriusReviewDecisionInput = {
  action: "approved" | "rejected";
  reviewer: string;
  reason: string;
  expected_decision_id: string | null;
  approval?: {
    team_id: string;
    feature_id: string;
    polarity: "favorable" | "adverse" | "neutral";
    strength: number;
    data_confidence: number;
    hour_robustness: number | null;
    description: string;
    time_known: boolean;
    time_source_url: string | null;
    time_consulted_at: string | null;
    time_data_grade: Provenance["quality"] | null;
    time_source_note: string | null;
  };
};

export type CombinedAssessment = {
  sirius: Record<string, SiriusAssessment>;
  argumental: Record<string, SiriusAssessment>;
  combined: Record<string, SiriusAssessment>;
  sirius_evidence_audit: { reviewed_observations: number; pending_observations: number };
  argumental_evidence_audit: { reviewed_observations: number; pending_observations: number };
  combined_evidence_audit: { reviewed_observations: number; pending_observations: number };
};

export type Draw = Record<string, Team[]>;

export type SourceRecord = {
  id: string;
  name: string;
  grade: Provenance["quality"];
  url: string | null;
  use: string;
  enabled: boolean;
  terms_url?: string | null;
  robots_policy?: string;
};

export type BacktestResult = {
  requested_editions: number[];
  available_editions: number[];
  missing_editions: number[];
  matches: number;
  metrics: Array<Record<string, string | number>>;
  round_accuracy: Array<Record<string, string | number>>;
  ablations: Array<Record<string, string | number | null>>;
  calibration_manifest: Array<Record<string, string | number | number[] | boolean>>;
};

export type UpdateEvent = {
  event_id: string;
  created_at: string;
  sources: Array<{
    source_id: string;
    fetch_status: string;
    quality: Provenance["quality"];
    model_input: boolean;
  }>;
  accepted_claims: number;
  pending_review: number;
  conflicts: number;
};

export type HistoryPoint = {
  snapshot_id: string;
  created_at: string;
  model_version: string;
  mode: string;
  team_id: string;
  team: string;
  champion_probability: number;
};
