import { http } from './client';

const path = (project: string) => `/projects/${encodeURIComponent(project)}`;
export interface SecurityCandidate {
  id: string; title: string; category: string; source_event_id: string | null;
  state: 'draft' | 'in_review' | 'approved' | 'archived'; approved_version: number | null;
  prompt_text: string | null; model: string | null; provider: string | null;
}
export interface GatePolicy {
  id: string; name: string; environment: string; version: number;
  rules: Record<string, unknown>;
}
export interface GateDecision {
  id: string; outcome: 'pass' | 'fail' | 'warning' | 'inconclusive';
  dry_run: boolean; candidate: Record<string, unknown>;
  checks: { name: string; status: string; reason: string; observed: unknown; threshold: unknown }[];
  created_at: string;
}
interface Page<T> { items: T[]; total: number }

export const listSecurityCandidates = (project: string) =>
  http.get<Page<SecurityCandidate>>(`${path(project)}/security-candidates`).then(r => r.data);
export const createSecurityCandidate = (project: string, body: Record<string, unknown>) =>
  http.post<SecurityCandidate>(`${path(project)}/security-candidates`, body).then(r => r.data);
export const readSecurityCandidate = (project: string, id: string) =>
  http.get<SecurityCandidate>(`${path(project)}/security-candidates/${id}`, {
    params: { include_body: true }, headers: { 'X-RedForge-Sensitive-Access': 'allow' },
  }).then(r => r.data);
export const editSecurityCandidate = (project: string, id: string, title: string, promptText: string) =>
  http.put(`${path(project)}/security-candidates/${id}`, { title, prompt_text: promptText });
export const reviewSecurityCandidate = (project: string, id: string) =>
  http.post(`${path(project)}/security-candidates/${id}/review`);
export const approveSecurityCandidate = (project: string, id: string) =>
  http.post(`${path(project)}/security-candidates/${id}/approve`, {}, {
    headers: { 'X-RedForge-Confirm-Action': 'approve-security-candidate' },
  });
export const runSecurityCandidate = (project: string, id: string, model: string) =>
  http.post<{ run_id: string; job: { id: string } }>(`${path(project)}/security-candidates/${id}/runs`, {
    environment: 'local_evaluation', model, max_external_cost_usd: 0,
  }).then(r => r.data);
export const listSecurityRuns = (project: string, id: string) =>
  http.get<{ id: string; model: string; status: string; outcome: string | null;
    classification: string; severity: string | null }[]>(
    `${path(project)}/security-candidates/${id}/runs`).then(r => r.data);
export const classifySecurityRun = (project: string, candidateId: string, runId: string,
  severity: string, justification: string) =>
  http.post(`${path(project)}/security-candidates/${candidateId}/runs/${runId}/classify`, {
    classification: 'confirmed', severity, justification,
  }, { headers: { 'X-RedForge-Confirm-Action': 'classify-security-run' } });
export const createSecurityRegression = (project: string, candidateId: string, runId: string) =>
  http.post<{ case_id: string }>(`${path(project)}/security-candidates/${candidateId}/runs/${runId}/regression`, {}, {
    headers: { 'X-RedForge-Confirm-Action': 'create-security-regression' },
  }).then(r => r.data);

export const listGatePolicies = (project: string) =>
  http.get<GatePolicy[]>(`${path(project)}/release-gates/policies`).then(r => r.data);
export const createGatePolicy = (project: string, body: Record<string, unknown>) =>
  http.post<GatePolicy>(`${path(project)}/release-gates/policies`, body).then(r => r.data);
export const listGateDecisions = (project: string) =>
  http.get<GateDecision[]>(`${path(project)}/release-gates/decisions`).then(r => r.data);
export const evaluateGate = (project: string, policyId: string, body: Record<string, unknown>) =>
  http.post<GateDecision>(`${path(project)}/release-gates/policies/${policyId}/evaluate`, body).then(r => r.data);
