import type {
  ApiEnvelope,
  AstroSource,
  BacktestResult,
  CombinedAssessment,
  CycleFortune,
  Draw,
  HistoryPoint,
  Prediction,
  Scenario,
  SiriusArchive,
  SiriusReviewDecisionInput,
  SiriusReviewQueue,
  SiriusReviewStatus,
  SourceRecord,
  Team,
  TrackRecordAudit,
  UpdateEvent
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store"
  });
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
  return response.json() as Promise<T>;
}

export const api = {
  scenario: (formatSize: 48 | 64 = 64) =>
    request<ApiEnvelope<Scenario>>(`/scenario?format_size=${formatSize}`),
  teams: (formatSize: 48 | 64 = 64) =>
    request<ApiEnvelope<Team[]>>(`/teams?format_size=${formatSize}`),
  latest: (formatSize: 48 | 64 = 64) =>
    request<ApiEnvelope<Prediction | null>>(`/predictions/latest?format_size=${formatSize}`),
  history: (formatSize: 48 | 64 = 64) =>
    request<ApiEnvelope<HistoryPoint[]>>(`/predictions/history?format_size=${formatSize}`),
  draw: (seed = 2030, formatSize: 48 | 64 = 64) =>
    request<ApiEnvelope<Draw>>(`/draw?seed=${seed}&format_size=${formatSize}`),
  sources: () => request<ApiEnvelope<SourceRecord[]>>("/sources"),
  trackRecordAudit: () => request<ApiEnvelope<TrackRecordAudit>>("/audit/track-record"),
  backtest: () => request<ApiEnvelope<BacktestResult | null>>("/backtesting/latest"),
  latestUpdate: () => request<ApiEnvelope<UpdateEvent | null>>("/updates/latest"),
  siriusArchive: () => request<ApiEnvelope<SiriusArchive | null>>("/sirius/archive"),
  argumentalArchive: () => request<ApiEnvelope<SiriusArchive | null>>("/argumental/archive"),
  argumentalCycleFortune: (formatSize: 48 | 64 = 64) =>
    request<ApiEnvelope<Record<string, CycleFortune>>>(
      `/argumental/cycle-fortune?format_size=${formatSize}`
    ),
  combinedAssessment: (formatSize: 48 | 64 = 64) =>
    request<ApiEnvelope<CombinedAssessment>>(
      `/astrology/combined-assessment?format_size=${formatSize}`
    ),
  astroReviewCandidates: (source: AstroSource, status: SiriusReviewStatus = "pending", offset = 0) =>
    request<ApiEnvelope<SiriusReviewQueue>>(
      `/${source}/review-candidates?status=${status}&limit=200&offset=${offset}`
    ),
  syncAstroReviewCandidates: (source: AstroSource, apiKey: string) =>
    request<ApiEnvelope<Record<string, unknown>>>(`/${source}/review-candidates/sync`, {
      method: "POST",
      headers: apiKey ? { "X-API-Key": apiKey } : undefined
    }),
  decideAstroReviewCandidate: (
    source: AstroSource,
    candidateId: string,
    payload: SiriusReviewDecisionInput,
    apiKey: string
  ) =>
    request<ApiEnvelope<Record<string, unknown>>>(
      `/${source}/review-candidates/${candidateId}/decisions`,
      {
        method: "POST",
        headers: apiKey ? { "X-API-Key": apiKey } : undefined,
        body: JSON.stringify(payload)
      }
    ),
  asset: (path: string) => `${API_URL}${path}`
};
