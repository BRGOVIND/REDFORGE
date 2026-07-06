/**
 * Centralized API surface. Components never call axios directly — they import
 * these typed functions (usually via the hooks in ../hooks). No business logic
 * lives here; it only shapes requests/responses.
 */
import { http } from './client';
import type {
  EnginePreview,
  EvaluateResponse,
  EvaluationEvent,
  EvaluationProfile,
  FindingsResponse,
  HistoryResponse,
  LeaderboardEntry,
  ModelsResponse,
  PlanResponse,
  ReportResponse,
  SessionResponse,
} from './types';

// Models
export const getModels = () =>
  http.get<ModelsResponse>('/models').then((r) => r.data);

// Evaluation profiles & engine previews (Sprint 2)
export const getProfiles = () =>
  http.get<EvaluationProfile[]>('/evaluation-profiles').then((r) => r.data);

export const getProfile = (name: string) =>
  http.get<EvaluationProfile>(`/evaluation-profiles/${encodeURIComponent(name)}`).then((r) => r.data);

export const previewPlan = (profile: string, models: string[]) =>
  http.post<EnginePreview>('/evaluation-plan', { profile, models }).then((r) => r.data);

// Pipeline (Sprint 3)
export const startEvaluation = (profile: string, models: string[]) =>
  http.post<EvaluateResponse>('/evaluate', { profile, models }).then((r) => r.data);

export const getPlan = (sessionId: string) =>
  http.get<PlanResponse>(`/plans/${sessionId}`).then((r) => r.data);

export const getFindings = (sessionId: string) =>
  http.get<FindingsResponse>(`/findings/${sessionId}`).then((r) => r.data);

export const getReport = (sessionId: string) =>
  http.get<ReportResponse>(`/report/${sessionId}`).then((r) => r.data);

// Sessions (Sprint 1)
export const listSessions = (params?: { status?: string; limit?: number }) =>
  http.get<SessionResponse[]>('/sessions', { params }).then((r) => r.data);

export const getSession = (id: string) =>
  http.get<SessionResponse>(`/sessions/${id}`).then((r) => r.data);

export const getSessionEvents = (id: string, afterId = 0) =>
  http
    .get<EvaluationEvent[]>(`/sessions/${id}/events`, { params: { after_id: afterId } })
    .then((r) => r.data);

export const pauseSession = (id: string) =>
  http.post<SessionResponse>(`/sessions/${id}/pause`).then((r) => r.data);

export const resumeSession = (id: string) =>
  http.post<SessionResponse>(`/sessions/${id}/resume`).then((r) => r.data);

export const cancelSession = (id: string) =>
  http.post<SessionResponse>(`/sessions/${id}/cancel`).then((r) => r.data);

// Leaderboard & history (existing)
export const getLeaderboard = () =>
  http.get<LeaderboardEntry[]>('/leaderboard').then((r) => r.data);

export const getHistory = (model: string) =>
  http.get<HistoryResponse>(`/history/${encodeURIComponent(model)}`).then((r) => r.data);
