import { http } from './client';

const root = (project: string) => `/projects/${encodeURIComponent(project)}`;
export interface Candidate { provider: string; model: string }
export interface ComparisonPlan {
  id: string; status: string; session_id: string | null;
  progress: { completed: number; total: number } | null;
  snapshot: { name: string; candidates: Candidate[]; remote_estimate_usd: number | null;
    dataset: { prompt_set_id: string; prompts: Record<string, { version: number }> } };
}
export interface ComparisonResult {
  provider: string; target_model: string; prompt_title: string; verdict: string;
  similarity_score: number | null; error: string | null;
  metrics: { latency_ms?: number | null; prompt_tokens?: number | null;
    completion_tokens?: number | null; cost_usd?: number | null };
}
export interface RoutingPolicy { id: string; name: string; version: number; definition: {
  mode: string; candidates: Candidate[]; remote_enabled: boolean } }
export interface UsageRow { dimension: string; calls: number; cost_usd: number | null;
  input_tokens: number | null; output_tokens: number | null;
  avg_latency_ms: number | null; unpriced_calls: number }
export interface Budget { configured: boolean; period?: string; soft_limit_usd?: number;
  hard_limit_usd?: number | null; observed_usd?: number; soft_exceeded?: boolean;
  hard_limit_behavior?: string }

export const listComparisons = (p: string) => http.get<ComparisonPlan[]>(`${root(p)}/comparisons`).then(r => r.data);
export const createComparison = (p: string, body: Record<string, unknown>) =>
  http.post<ComparisonPlan>(`${root(p)}/comparisons`, body).then(r => r.data);
export const startComparison = (p: string, id: string, confirmRemote: boolean) =>
  http.post(`${root(p)}/comparisons/${id}/start`, { confirm_remote: confirmRemote });
export const cancelComparison = (p: string, id: string) =>
  http.post(`${root(p)}/comparisons/${id}/cancel`);
export const comparisonResults = (p: string, id: string) =>
  http.get<{ results: ComparisonResult[]; status: string; methodology: string }>(
    `${root(p)}/comparisons/${id}/results`).then(r => r.data);

export const listRouting = (p: string) => http.get<{ active_policy_id: string | null; items: RoutingPolicy[] }>(
  `${root(p)}/routing/policies`).then(r => r.data);
export const createRouting = (p: string, body: Record<string, unknown>) =>
  http.post<RoutingPolicy>(`${root(p)}/routing/policies`, body).then(r => r.data);
export const activateRouting = (p: string, id: string) => http.put(`${root(p)}/routing/active/${id}`);
export const disableRouting = (p: string) => http.delete(`${root(p)}/routing/active`);

export const listPrices = (p: string) => http.get<{ id: string; provider: string; model: string;
  version: number; source: string; effective_at: string; rates: Record<string, number> }[]>(
    `${root(p)}/costs/prices`).then(r => r.data);
export const createPrice = (p: string, body: Record<string, unknown>) =>
  http.post(`${root(p)}/costs/prices`, body);
export const getBudget = (p: string) => http.get<Budget>(`${root(p)}/costs/budget`).then(r => r.data);
export const setBudget = (p: string, body: Record<string, unknown>) =>
  http.put(`${root(p)}/costs/budget`, body);
export const getUsage = (p: string, groupBy: string) =>
  http.get<{ rows: UsageRow[]; pricing_note: string }>(`${root(p)}/costs/usage`, {
    params: { group_by: groupBy },
  }).then(r => r.data);
