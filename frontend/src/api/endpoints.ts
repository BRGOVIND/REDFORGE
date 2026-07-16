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

// --- RedForge V2 · AI Studio (projects) ------------------------------------
import type {
  AssistantAnswer,
  ChatMessage,
  ChatParams,
  ChatResponse,
  Project,
  ProjectCreate,
} from './types';

export const listProjects = (limit?: number) =>
  http.get<Project[]>('/projects', { params: limit ? { limit } : undefined }).then((r) => r.data);

export const getProject = (id: string) =>
  http.get<Project>(`/projects/${id}`).then((r) => r.data);

export const createProject = (body: ProjectCreate) =>
  http.post<Project>('/projects', body).then((r) => r.data);

export const updateProject = (id: string, body: Partial<ProjectCreate> & { last_scan?: unknown }) =>
  http.patch<Project>(`/projects/${id}`, body).then((r) => r.data);

export const openProject = (id: string) =>
  http.post<Project>(`/projects/${id}/open`).then((r) => r.data);

export const duplicateProject = (id: string) =>
  http.post<Project>(`/projects/${id}/duplicate`).then((r) => r.data);

export const deleteProject = (id: string) =>
  http.delete<{ deleted: boolean; id: string }>(`/projects/${id}`).then((r) => r.data);

// --- RedForge V2 · Playground ----------------------------------------------
export const playgroundChat = (model: string, messages: ChatMessage[], params: ChatParams = {}) =>
  http.post<ChatResponse>('/playground/chat', { model, messages, ...params }).then((r) => r.data);

// --- RedForge V2 · Assistant -----------------------------------------------
export const assistantAsk = (question: string, context?: string, datasetId?: string) =>
  http
    .post<AssistantAnswer>('/assistant/ask', { question, context, dataset_id: datasetId })
    .then((r) => r.data);

export const assistantSuggestions = () =>
  http.get<{ suggestions: string[] }>('/assistant/suggestions').then((r) => r.data);

// --- RedForge V2 · Dataset Lab ---------------------------------------------
import type {
  CleanResult,
  Dataset,
  DatasetAnalysis,
  DatasetPreview,
  DatasetVersionInfo,
  SplitStats,
} from './types';

export const listDatasets = (projectId?: string) =>
  http
    .get<Dataset[]>('/datasets', { params: projectId ? { project_id: projectId } : undefined })
    .then((r) => r.data);

export const getDataset = (id: string) =>
  http.get<Dataset>(`/datasets/${id}`).then((r) => r.data);

export const importDataset = (file: File, name?: string, projectId?: string) => {
  const form = new FormData();
  form.append('file', file);
  if (name) form.append('name', name);
  if (projectId) form.append('project_id', projectId);
  return http
    .post<Dataset>('/datasets/import', form, { headers: { 'Content-Type': 'multipart/form-data' } })
    .then((r) => r.data);
};

export const renameDataset = (id: string, name: string) =>
  http.patch<Dataset>(`/datasets/${id}`, { name }).then((r) => r.data);

export const duplicateDataset = (id: string) =>
  http.post<Dataset>(`/datasets/${id}/duplicate`).then((r) => r.data);

export const deleteDataset = (id: string) =>
  http.delete<{ deleted: boolean; id: string }>(`/datasets/${id}`).then((r) => r.data);

export const previewDataset = (id: string, offset = 0, limit = 50, search = '') =>
  http
    .get<DatasetPreview>(`/datasets/${id}/preview`, { params: { offset, limit, search } })
    .then((r) => r.data);

export const analyzeDataset = (id: string) =>
  http.get<DatasetAnalysis>(`/datasets/${id}/analyze`).then((r) => r.data);

export const cleanDataset = (id: string, operations: string[], save: boolean) =>
  http.post<CleanResult>(`/datasets/${id}/clean`, { operations, save }).then((r) => r.data);

export const splitDataset = (id: string, train: number, val: number, test: number) =>
  http.post<SplitStats>(`/datasets/${id}/split`, { train, val, test }).then((r) => r.data);

export const datasetVersions = (id: string) =>
  http.get<DatasetVersionInfo[]>(`/datasets/${id}/versions`).then((r) => r.data);

export const restoreDatasetVersion = (id: string, version: number) =>
  http.post<Dataset>(`/datasets/${id}/restore`, { version }).then((r) => r.data);

export const datasetExportUrl = (id: string, fmt = 'jsonl') =>
  `/api/datasets/${id}/export?fmt=${fmt}`;

// --- RedForge V2 · Training Lab --------------------------------------------
import type {
  TrainingBackend,
  TrainingCheckpoint,
  TrainingParams,
  TrainingProgress,
  TrainingRun,
} from './types';

export const trainingBackends = () =>
  http.get<{ backends: TrainingBackend[]; default: string }>('/training/backends').then((r) => r.data);

export const listTrainingRuns = (projectId?: string, limit?: number) =>
  http
    .get<TrainingRun[]>('/training', { params: { project_id: projectId, limit } })
    .then((r) => r.data);

export const getTrainingRun = (id: string) =>
  http.get<TrainingRun>(`/training/${id}`).then((r) => r.data);

export const launchTraining = (body: {
  name: string;
  base_model: string;
  dataset_id?: string | null;
  method: 'lora' | 'qlora';
  backend?: string;
  params: Partial<TrainingParams>;
  project_id?: string | null;
  continuous_security?: boolean;
  security_profile?: 'quick' | 'standard' | 'full' | 'custom';
}) => http.post<{ run: TrainingRun; backend: string }>('/training/launch', body).then((r) => r.data);

export const trainingProgress = (id: string) =>
  http.get<TrainingProgress>(`/training/${id}/progress`).then((r) => r.data);

export const cancelTraining = (id: string) =>
  http.post<{ cancelled: boolean }>(`/training/${id}/cancel`).then((r) => r.data);

export const pauseTraining = (id: string, paused: boolean) =>
  http.post<{ paused: boolean }>(`/training/${id}/pause`, null, { params: { paused } }).then((r) => r.data);

export const deleteTraining = (id: string) =>
  http.delete<{ deleted: boolean }>(`/training/${id}`).then((r) => r.data);

export const setTrainingNotes = (id: string, notes: string) =>
  http.patch<TrainingRun>(`/training/${id}/notes`, { notes }).then((r) => r.data);

export const trainingCheckpoints = (id: string) =>
  http.get<TrainingCheckpoint[]>(`/training/${id}/checkpoints`).then((r) => r.data);

// --- RedForge V2 · Continuous Security -------------------------------------
import type { CheckpointSecurity, SecurityCompare } from './types';

export const securityTimeline = (runId: string) =>
  http
    .get<{ run_id: string; timeline: CheckpointSecurity[] }>(`/training/${runId}/security`)
    .then((r) => r.data.timeline);

export const securityCompare = (runId: string, a: number, b: number) =>
  http
    .get<SecurityCompare>(`/training/${runId}/security/compare`, { params: { a, b } })
    .then((r) => r.data);

// --- RedForge V2 · Recommendation Engine -----------------------------------
import type { Recommendation } from './types';

export const analyzeRecommendation = (body: {
  target_model: string; run_id?: string; project_id?: string;
}) => http.post<Recommendation>('/recommendations/analyze', body).then((r) => r.data);

export const listRecommendations = (projectId?: string) =>
  http
    .get<Recommendation[]>('/recommendations', { params: projectId ? { project_id: projectId } : undefined })
    .then((r) => r.data);

export const decideRecommendation = (id: string, status: 'accepted' | 'rejected' | 'applied') =>
  http.post<Recommendation>(`/recommendations/${id}/decision`, { status }).then((r) => r.data);

// --- RedForge V2 · Prediction feedback + accuracy (Phase 2.5) --------------
import type { RecommendationAccuracy } from './types';

export const recommendationFeedback = (id: string, appliedRunId: string) =>
  http
    .post<Recommendation>(`/recommendations/${id}/feedback`, { applied_run_id: appliedRunId })
    .then((r) => r.data);

export const recommendationAccuracy = (projectId?: string) =>
  http
    .get<RecommendationAccuracy>('/recommendations/accuracy', {
      params: projectId ? { project_id: projectId } : undefined,
    })
    .then((r) => r.data);

// --- RedForge V2 · Runtime Registry (Phase 2.5) ----------------------------
import type { RegisteredModel, TrainingReport } from './types';

export const listRegisteredModels = (params?: { run_id?: string; project_id?: string }) =>
  http.get<RegisteredModel[]>('/registry', { params }).then((r) => r.data);

export const getRegisteredModel = (id: string) =>
  http.get<RegisteredModel>(`/registry/${id}`).then((r) => r.data);

// --- RedForge V2 · Training report (Phase 2.5) -----------------------------

export const trainingReport = (runId: string) =>
  http.get<TrainingReport>(`/training/${runId}/report`).then((r) => r.data);

// --- RedForge V2 · Benchmark Center (Phase 3) ------------------------------
import type {
  BenchmarkComparison,
  BenchmarkLeaderboardEntry,
  BenchmarkRequest,
  BenchmarkResult,
  BenchmarkSuiteInfo,
  BenchmarkTrends,
} from './types';

export const benchmarkSuites = () =>
  http.get<BenchmarkSuiteInfo[]>('/benchmark-center/suites').then((r) => r.data);

export const benchmarkHistory = (params?: { project_id?: string; run_id?: string; model?: string }) =>
  http.get<BenchmarkResult[]>('/benchmark-center', { params }).then((r) => r.data);

export const scheduleBenchmark = (body: BenchmarkRequest) =>
  http
    .post<{ scheduled: { id: string }[]; count: number }>('/benchmark-center', body)
    .then((r) => r.data);

export const getBenchmark = (id: string) =>
  http.get<BenchmarkResult>(`/benchmark-center/${id}`).then((r) => r.data);

export const cancelBenchmark = (id: string) =>
  http.delete<{ cancelled: boolean }>(`/benchmark-center/${id}`).then((r) => r.data);

export const benchmarkLeaderboard = (params?: { project_id?: string; suite?: string }) =>
  http
    .get<BenchmarkLeaderboardEntry[]>('/benchmark-center/leaderboard', { params })
    .then((r) => r.data);

export const benchmarkTrends = (projectId: string, suite?: string) =>
  http
    .get<BenchmarkTrends>('/benchmark-center/trends', { params: { project_id: projectId, suite } })
    .then((r) => r.data);

export const benchmarkCompare = (ids: string[]) =>
  http
    .get<BenchmarkComparison>('/benchmark-center/compare', { params: { ids: ids.join(',') } })
    .then((r) => r.data);

export const benchmarkQueue = () =>
  http.get<{ pending: string[]; running: string | null; queued: number }>('/benchmark-center/queue').then((r) => r.data);
