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
  HealthCheck,
  HealthReport,
  HistoryResponse,
  LeaderboardEntry,
  ModelCatalogResponse,
  ModelDetail,
  ModelsResponse,
  OnboardingRecommendations,
  PlanResponse,
  PullStatus,
  ProviderHealth,
  ProviderInfo,
  ProvidersResponse,
  ReportResponse,
  RuntimeLogsResponse,
  RuntimeStatusResponse,
  SessionResponse,
  SystemChecksResponse,
  TerminalResponse,
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

export const getSessionTerminal = (id: string, afterId = 0) =>
  http
    .get<TerminalResponse>(`/sessions/${id}/terminal`, { params: { after_id: afterId } })
    .then((r) => r.data);

// System checks (onboarding)
export const getSystemChecks = () =>
  http.get<SystemChecksResponse>('/system/checks').then((r) => r.data);

// System Health Engine (V1.2)
export const getHealth = (includeNetwork = false) =>
  http
    .get<HealthReport>('/health', { params: { include_network: includeNetwork } })
    .then((r) => r.data);

export const getHealthCheck = (id: string) =>
  http.get<HealthCheck>(`/health/${encodeURIComponent(id)}`).then((r) => r.data);

export const pauseSession = (id: string) =>
  http.post<SessionResponse>(`/sessions/${id}/pause`).then((r) => r.data);

export const resumeSession = (id: string) =>
  http.post<SessionResponse>(`/sessions/${id}/resume`).then((r) => r.data);

export const cancelSession = (id: string) =>
  http.post<SessionResponse>(`/sessions/${id}/cancel`).then((r) => r.data);

// Runtime Manager (V1.2)
export const getProviders = () =>
  http.get<ProvidersResponse>('/providers').then((r) => r.data);

export const refreshProviders = () =>
  http.post<ProvidersResponse>('/providers/refresh').then((r) => r.data);

export const getProvider = (name: string) =>
  http.get<ProviderInfo>(`/providers/${encodeURIComponent(name)}`).then((r) => r.data);

export const testProvider = (name: string) =>
  http.post<ProviderHealth>(`/providers/${encodeURIComponent(name)}/test`).then((r) => r.data);

export const setDefaultProvider = (name: string) =>
  http.post<{ default: string }>('/providers/default', { name }).then((r) => r.data);

export const getRuntimeStatus = () =>
  http.get<RuntimeStatusResponse>('/runtime/status').then((r) => r.data);

export const getRuntimeLogs = (limit = 200) =>
  http.get<RuntimeLogsResponse>('/runtime/logs', { params: { limit } }).then((r) => r.data);

// Model Manager (V1.2)
export const getModelCatalog = () =>
  http.get<ModelCatalogResponse>('/models/catalog').then((r) => r.data);

export const getModelDetail = (provider: string, name: string) =>
  http.get<ModelDetail>('/models/detail', { params: { provider, name } }).then((r) => r.data);

export const deleteModel = (provider: string, name: string) =>
  http
    .delete<{ deleted: boolean; provider: string; name: string }>('/models/instance', {
      params: { provider, name },
    })
    .then((r) => r.data);

// Onboarding (V1.2.1) — hardware-aware recommendations + model download
export const getRecommendations = () =>
  http.get<OnboardingRecommendations>('/onboarding/recommendations').then((r) => r.data);

export const startModelPull = (model: string) =>
  http.post<PullStatus>('/onboarding/models/pull', { model }).then((r) => r.data);

export const getModelPullStatus = (model: string) =>
  http
    .get<PullStatus>('/onboarding/models/pull', { params: { model } })
    .then((r) => r.data);

// Leaderboard & history (existing)
export const getLeaderboard = () =>
  http.get<LeaderboardEntry[]>('/leaderboard').then((r) => r.data);

export const getHistory = (model: string) =>
  http.get<HistoryResponse>(`/history/${encodeURIComponent(model)}`).then((r) => r.data);
