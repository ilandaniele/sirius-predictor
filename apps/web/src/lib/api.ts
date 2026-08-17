import type {
  ApiEnvelope,
  BacktestResult,
  Draw,
  HistoryPoint,
  Prediction,
  Scenario,
  SourceRecord,
  Team,
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
  scenario: () => request<ApiEnvelope<Scenario>>("/scenario"),
  teams: () => request<ApiEnvelope<Team[]>>("/teams"),
  latest: () => request<ApiEnvelope<Prediction | null>>("/predictions/latest"),
  history: () => request<ApiEnvelope<HistoryPoint[]>>("/predictions/history"),
  draw: (seed = 2030) => request<ApiEnvelope<Draw>>(`/draw?seed=${seed}`),
  sources: () => request<ApiEnvelope<SourceRecord[]>>("/sources"),
  backtest: () => request<ApiEnvelope<BacktestResult | null>>("/backtesting/latest"),
  latestUpdate: () => request<ApiEnvelope<UpdateEvent | null>>("/updates/latest"),
  update: async () => {
    const response = await fetch("/api/update", {
      method: "POST",
      body: JSON.stringify({ iterations: 100_000, seed: 2030 })
    });
    if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
    return response.json() as Promise<{ job_id: string; status: string; detail: string }>;
  }
};
