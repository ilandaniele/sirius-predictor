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
  format: { teams: number; groups: number; group_size: number };
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
  top_brackets: Array<Record<string, string | number>>;
  model_comparison?: Record<string, number | null>;
  changes?: string[];
  update_summary?: string;
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

export type HistoryPoint = {
  snapshot_id: string;
  created_at: string;
  model_version: string;
  mode: string;
  team_id: string;
  team: string;
  champion_probability: number;
};
