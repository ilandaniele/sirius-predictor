import type {
  ApiEnvelope,
  BacktestResult,
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
  UpdateEvent,
  JobStatus
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
  backtest: () => request<ApiEnvelope<BacktestResult | null>>("/backtesting/latest"),
  latestUpdate: () => request<ApiEnvelope<UpdateEvent | null>>("/updates/latest"),
  siriusArchive: () => request<ApiEnvelope<SiriusArchive | null>>("/sirius/archive"),
  siriusReviewCandidates: (status: SiriusReviewStatus = "pending", offset = 0) =>
    request<ApiEnvelope<SiriusReviewQueue>>(
      `/sirius/review-candidates?status=${status}&limit=200&offset=${offset}`
    ),
  syncSiriusReviewCandidates: (apiKey: string) =>
    request<ApiEnvelope<Record<string, unknown>>>("/sirius/review-candidates/sync", {
      method: "POST",
      headers: apiKey ? { "X-API-Key": apiKey } : undefined
    }),
  decideSiriusReviewCandidate: (
    candidateId: string,
    payload: SiriusReviewDecisionInput,
    apiKey: string
  ) =>
    request<ApiEnvelope<Record<string, unknown>>>(
      `/sirius/review-candidates/${candidateId}/decisions`,
      {
        method: "POST",
        headers: apiKey ? { "X-API-Key": apiKey } : undefined,
        body: JSON.stringify(payload)
      }
    ),
  job: (jobId: string) => request<ApiEnvelope<JobStatus>>(`/jobs/${jobId}`),
  asset: (path: string) => `${API_URL}${path}`,
  update: async (formatSize: 48 | 64 = 64) => {
    const response = await fetch("/api/update", {
      method: "POST",
      body: JSON.stringify({ iterations: 100_000, seed: 2030, format_size: formatSize })
    });
    if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
    return response.json() as Promise<{ job_id: string; status: string; detail: string }>;
  }
};
