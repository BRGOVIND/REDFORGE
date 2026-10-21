import { http } from './client';

export interface AnomalyRule {
  id: string; name: string; metric: string; threshold: number; min_samples: number;
  observed_minutes: number; baseline_minutes: number; interval_seconds: number;
  cooldown_seconds: number; severity: 'info' | 'warning' | 'critical'; enabled: boolean;
}
export interface AnomalyAlert {
  id: string; rule_id: string; state: 'open' | 'acknowledged' | 'resolved' | 'suppressed';
  classification: 'observed' | 'incident'; metric: string; observed: number;
  baseline: number | null; sample_count: number; severity: string; created_at: string;
  occurrences: number; evidence: { scope?: Record<string, string | null> };
}
export interface FeedbackCase {
  id: string; trace_event_id: number; source_event_id: string | null; trace_id: string | null; category: string;
  state: 'draft' | 'in_review' | 'approved' | 'rejected' | 'archived';
  title: string; labels: string[]; notes: string | null; prompt_text: string | null;
  expected_output: string | null; evaluation_prompt_id: string | null;
  dataset_version: number | null; created_at: string;
}
export interface Page<T> { items: T[]; total: number; offset: number; limit: number }

const path = (project: string) => `/projects/${encodeURIComponent(project)}`;
export const listRules = (project: string) => http.get<Page<AnomalyRule>>(`${path(project)}/anomaly-rules`).then(r => r.data);
export const createRule = (project: string, data: Record<string, unknown>) => http.post<AnomalyRule>(`${path(project)}/anomaly-rules`, data).then(r => r.data);
export const dryRunRule = (project: string, id: string) => http.post<{status: string; reason?: string; observed?: number; samples?: number}>(`${path(project)}/anomaly-rules/${id}/dry-run`).then(r => r.data);
export const listAlerts = (project: string) => http.get<Page<AnomalyAlert>>(`${path(project)}/alerts`).then(r => r.data);
export const setAlertState = (project: string, id: string, state: string, confirmIncident = false) => http.post<AnomalyAlert>(`${path(project)}/alerts/${id}/state`, { state, confirm_incident: confirmIncident }).then(r => r.data);
export const listFeedback = (project: string) => http.get<Page<FeedbackCase>>(`${path(project)}/feedback/cases`).then(r => r.data);
export const createFeedback = (project: string, data: Record<string, unknown>) => http.post<FeedbackCase>(`${path(project)}/feedback/cases`, data).then(r => r.data);
export const getFeedback = (project: string, id: string) => http.get<FeedbackCase>(`${path(project)}/feedback/cases/${id}`, { params: { include_bodies: true }, headers: { 'X-RedForge-Sensitive-Access': 'allow' } }).then(r => r.data);
export const editFeedback = (project: string, id: string, data: Record<string, unknown>) => http.put<FeedbackCase>(`${path(project)}/feedback/cases/${id}`, data).then(r => r.data);
export const setFeedbackState = (project: string, id: string, state: string) => http.post<FeedbackCase>(`${path(project)}/feedback/cases/${id}/state`, { state }).then(r => r.data);
export const approveFeedback = (project: string, id: string, promptSetId: string) => http.post<FeedbackCase>(`${path(project)}/feedback/cases/${id}/approve`, { prompt_set_id: promptSetId }).then(r => r.data);
export const replayFeedback = (project: string, id: string, candidateModel: string) => http.post<{id: string}>(`${path(project)}/feedback/cases/${id}/replay`, { environment: 'local_evaluation', candidate_model: candidateModel }).then(r => r.data);
