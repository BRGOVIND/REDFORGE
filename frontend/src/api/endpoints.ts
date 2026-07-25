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
  TrainingDiagnostics,
  TrainingParams,
  TrainingProgress,
  TrainingRun,
} from './types';

export const trainingBackends = () =>
  http.get<{ backends: TrainingBackend[]; default: string }>('/training/backends').then((r) => r.data);

export const trainingDiagnostics = (refresh = false) =>
  http
    .get<TrainingDiagnostics>('/training/diagnostics', { params: refresh ? { refresh: true } : undefined })
    .then((r) => r.data);

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

// --- RedForge V2 · Evaluation Workbench (Phase 4) --------------------------
import type {
  EvaluationCollection,
  EvaluationResult,
  GoldenDiff,
  Prompt,
  PromptSet,
  PromptVersion,
  SessionCreateRequest,
  SessionRegressions,
  SimilarityProviderInfo,
  WorkbenchSession,
} from './types';

const WB = '/evaluation-workbench';

export const similarityProviders = () =>
  http.get<SimilarityProviderInfo[]>(`${WB}/similarity-providers`).then((r) => r.data);

export const regressionTypes = () =>
  http.get<{ type: string; label: string }[]>(`${WB}/regression-types`).then((r) => r.data);

// Collections
export const listCollections = (projectId?: string) =>
  http
    .get<EvaluationCollection[]>(`${WB}/collections`, { params: projectId ? { project_id: projectId } : undefined })
    .then((r) => r.data);

export const getCollection = (id: string) =>
  http.get<EvaluationCollection>(`${WB}/collections/${id}`).then((r) => r.data);

export const createCollection = (body: {
  name: string; project_id?: string; category?: string; description?: string; tags?: string[]; notes?: string;
}) => http.post<EvaluationCollection>(`${WB}/collections`, body).then((r) => r.data);

export const updateCollection = (id: string, body: Partial<EvaluationCollection>) =>
  http.patch<EvaluationCollection>(`${WB}/collections/${id}`, body).then((r) => r.data);

export const deleteCollection = (id: string) =>
  http.delete<{ deleted: boolean; id: string }>(`${WB}/collections/${id}`).then((r) => r.data);

// Prompt sets
export const listPromptSets = (params?: { collection_id?: string; project_id?: string }) =>
  http.get<PromptSet[]>(`${WB}/prompt-sets`, { params }).then((r) => r.data);

export const getPromptSet = (id: string) =>
  http.get<PromptSet>(`${WB}/prompt-sets/${id}`).then((r) => r.data);

export const createPromptSet = (body: {
  collection_id: string; title: string; description?: string; category?: string;
  tags?: string[]; notes?: string; priority?: string; owner?: string; project_id?: string;
}) => http.post<PromptSet>(`${WB}/prompt-sets`, body).then((r) => r.data);

export const updatePromptSet = (id: string, body: Partial<PromptSet>) =>
  http.patch<PromptSet>(`${WB}/prompt-sets/${id}`, body).then((r) => r.data);

export const deletePromptSet = (id: string) =>
  http.delete<{ deleted: boolean; id: string }>(`${WB}/prompt-sets/${id}`).then((r) => r.data);

// Prompts
export const getPrompt = (id: string) =>
  http.get<Prompt>(`${WB}/prompts/${id}`).then((r) => r.data);

export const createPrompt = (body: Partial<Prompt> & { prompt_set_id: string; prompt: string }) =>
  http.post<Prompt>(`${WB}/prompts`, body).then((r) => r.data);

export const updatePrompt = (id: string, body: Partial<Prompt> & { version_note?: string }) =>
  http.patch<Prompt>(`${WB}/prompts/${id}`, body).then((r) => r.data);

export const deletePrompt = (id: string) =>
  http.delete<{ deleted: boolean; id: string }>(`${WB}/prompts/${id}`).then((r) => r.data);

export const promptVersions = (id: string) =>
  http.get<PromptVersion[]>(`${WB}/prompts/${id}/versions`).then((r) => r.data);

export const comparePromptVersions = (id: string, a: number, b: number) =>
  http
    .get<{ changed_fields: string[]; diff: Record<string, { a: unknown; b: unknown }> }>(
      `${WB}/prompts/${id}/versions/compare`, { params: { a, b } })
    .then((r) => r.data);

// Sessions
export const listWorkbenchSessions = (params?: { project_id?: string; run_id?: string }) =>
  http.get<WorkbenchSession[]>(`${WB}/sessions`, { params }).then((r) => r.data);

export const getWorkbenchSession = (id: string) =>
  http.get<WorkbenchSession>(`${WB}/sessions/${id}`).then((r) => r.data);

export const createWorkbenchSession = (body: SessionCreateRequest) =>
  http.post<{ id: string; status: string; total_tasks: number }>(`${WB}/sessions`, body).then((r) => r.data);

export const cancelWorkbenchSession = (id: string) =>
  http.delete<{ cancelled: boolean }>(`${WB}/sessions/${id}`).then((r) => r.data);

export const sessionResults = (id: string, params?: { verdict?: string; regression_type?: string }) =>
  http.get<EvaluationResult[]>(`${WB}/sessions/${id}/results`, { params }).then((r) => r.data);

export const sessionRegressions = (id: string) =>
  http.get<SessionRegressions>(`${WB}/sessions/${id}/regressions`).then((r) => r.data);

export const compareResults = (ids: string[]) =>
  http.get<{ results: EvaluationResult[] }>(`${WB}/compare`, { params: { ids: ids.join(',') } }).then((r) => r.data);

export const responseDiff = (reference: string, candidate: string) =>
  http.post<GoldenDiff>(`${WB}/diff`, { reference, candidate }).then((r) => r.data);

export const workbenchQueue = () =>
  http.get<{ pending: string[]; running: string | null; queued: number }>(`${WB}/queue`).then((r) => r.data);

// --- RedForge V3 · Foundation Platform (Epic 1) ----------------------------
import type {
  FoundationDiscovery,
  FoundationModel,
  FoundationRuntimeLink,
  ResolutionResult,
} from './types';

const FM = '/foundation-models';

export const listFoundationModels = (params?: { status?: string; source?: string }) =>
  http.get<FoundationModel[]>(FM, { params }).then((r) => r.data);

export const getFoundationModel = (id: string) =>
  http.get<FoundationModel>(`${FM}/${id}`).then((r) => r.data);

export const registerFoundationModel = (body: {
  hf_repo: string; revision?: string; architecture?: string; parameter_count?: number;
  format?: string; quantization?: string; source?: string; license?: string;
  cache_path?: string; metadata?: Record<string, unknown>;
}) => http.post<FoundationModel>(FM, body).then((r) => r.data);

export const deleteFoundationModel = (id: string) =>
  http.delete<{ deleted: boolean; id: string }>(`${FM}/${id}`).then((r) => r.data);

export const resolveRuntimeModel = (runtimeRef: string) =>
  http.post<ResolutionResult>(`${FM}/resolve`, { runtime_ref: runtimeRef }).then((r) => r.data);

export const discoverFoundationModels = () =>
  http.get<FoundationDiscovery[]>(`${FM}/discover`).then((r) => r.data);

export const foundationModelStatus = (id: string) =>
  http
    .get<{ id: string; status: string; is_local: boolean; cache_path: string | null; checksum: string | null }>(
      `${FM}/${id}/status`)
    .then((r) => r.data);

export const foundationModelRuntimes = (id: string) =>
  http.get<FoundationRuntimeLink[]>(`${FM}/${id}/runtimes`).then((r) => r.data);

export const syncFoundationModel = (id: string) =>
  http.post<FoundationModel>(`${FM}/${id}/sync`).then((r) => r.data);

export const cacheFoundationModel = (id: string, cachePath: string) =>
  http.post<FoundationModel>(`${FM}/${id}/cache`, { cache_path: cachePath }).then((r) => r.data);

export const ensureFoundationForBaseModel = (baseModel: string) =>
  http.post<FoundationModel>(`${FM}/ensure`, { base_model: baseModel }).then((r) => r.data);

// --- RedForge V3 · Automatic Model Discovery (Epic 4.5) --------------------
import type { DiscoverySummary, RuntimeModel, RuntimeResolveResult } from './types';

const RM = '/runtime-models';

export const discoverAndRegisterModels = () =>
  http.post<DiscoverySummary>(`${FM}/discover`).then((r) => r.data);
export const syncRuntimeModels = () =>
  http.post<DiscoverySummary>(`${FM}/sync`).then((r) => r.data);
export const listRuntimeModels = (params?: { provider?: string; resolution?: string; available?: boolean }) =>
  http.get<RuntimeModel[]>(RM, { params }).then((r) => r.data);
export const listUnresolvedRuntimeModels = () =>
  http.get<RuntimeModel[]>(`${RM}/unresolved`).then((r) => r.data);
export const resolveRuntimeModelEntry = (id: string, hfRepo?: string) =>
  http.post<RuntimeResolveResult>(`${RM}/${id}/resolve`, { hf_repo: hfRepo ?? null }).then((r) => r.data);

// --- RedForge V3 · Artifact Registry (Epic 2) ------------------------------
import type {
  Artifact,
  ArtifactLineage,
  ArtifactReference,
  ArtifactTypeInfo,
  Job,
  JobTypeInfo,
} from './types';

const ART = '/artifacts';

export const listArtifactTypes = () =>
  http.get<ArtifactTypeInfo[]>(`${ART}/types`).then((r) => r.data);

export const searchArtifacts = (params?: {
  type?: string; status?: string; project_id?: string; tag?: string; q?: string;
}) => http.get<Artifact[]>(ART, { params }).then((r) => r.data);

export const getArtifact = (id: string) =>
  http.get<Artifact>(`${ART}/${id}`).then((r) => r.data);

export const registerArtifact = (body: {
  type: string; name: string; producer?: string; project_id?: string; description?: string;
  file_path?: string; table?: string; row_id?: string; tags?: string[];
  metadata?: Record<string, unknown>; parents?: { parent_id: string; relationship?: string }[];
  status?: string;
}) => http.post<Artifact>(ART, body).then((r) => r.data);

export const artifactLineage = (id: string) =>
  http.get<ArtifactLineage>(`${ART}/${id}/lineage`).then((r) => r.data);

export const artifactParents = (id: string) =>
  http.get<ArtifactReference[]>(`${ART}/${id}/parents`).then((r) => r.data);

export const artifactChildren = (id: string) =>
  http.get<ArtifactReference[]>(`${ART}/${id}/children`).then((r) => r.data);

export const artifactVersions = (id: string) =>
  http.get<Artifact[]>(`${ART}/${id}/versions`).then((r) => r.data);

export const createArtifactVersion = (id: string, body: { description?: string; metadata?: Record<string, unknown> }) =>
  http.post<Artifact>(`${ART}/${id}/version`, body).then((r) => r.data);

export const publishArtifact = (id: string) =>
  http.post<Artifact>(`${ART}/${id}/publish`).then((r) => r.data);

export const tagArtifact = (id: string, tags: string[]) =>
  http.post<Artifact>(`${ART}/${id}/tag`, { tags }).then((r) => r.data);

export const archiveArtifact = (id: string) =>
  http.post<Artifact>(`${ART}/${id}/archive`).then((r) => r.data);

export const validateArtifact = (id: string) =>
  http.post<{ id: string; valid: boolean; reason: string }>(`${ART}/${id}/validate`).then((r) => r.data);

export const deleteArtifact = (id: string) =>
  http.delete<{ deleted: boolean; id: string }>(`${ART}/${id}`).then((r) => r.data);

// --- RedForge V3 · Job System (Epic 2) -------------------------------------

const JOBS = '/jobs';

export const listJobTypes = () =>
  http.get<JobTypeInfo[]>(`${JOBS}/types`).then((r) => r.data);

export const jobQueue = () =>
  http.get<{ pending: string[]; running: string[]; queued: number; active: number }>(`${JOBS}/queue`).then((r) => r.data);

export const listJobs = (params?: { status?: string; type?: string; project_id?: string; limit?: number }) =>
  http.get<Job[]>(JOBS, { params }).then((r) => r.data);

export const getJob = (id: string) =>
  http.get<Job>(`${JOBS}/${id}`).then((r) => r.data);

export const submitJob = (body: {
  type: string; params?: Record<string, unknown>; target_ref?: string; project_id?: string;
  priority?: number; max_attempts?: number;
}) => http.post<Job>(JOBS, body).then((r) => r.data);

export const jobProgress = (id: string) =>
  http.get<{ id: string; status: string; fraction: number; message: string }>(`${JOBS}/${id}/progress`).then((r) => r.data);

export const jobLogs = (id: string) =>
  http.get<{ id: string; logs: string[] }>(`${JOBS}/${id}/logs`).then((r) => r.data);

export const cancelJob = (id: string) =>
  http.post<{ cancelled: boolean; id: string }>(`${JOBS}/${id}/cancel`).then((r) => r.data);

export const retryJob = (id: string) =>
  http.post<Job>(`${JOBS}/${id}/retry`).then((r) => r.data);

// --- Model Hub -------------------------------------------------------------
import type { ModelHubCatalog, Task as HubTask } from './types';

const HUB = '/model-hub';
export const modelHubCatalog = () => http.get<ModelHubCatalog>(HUB).then((r) => r.data);
export const modelHubDownload = (id: string, source?: 'huggingface' | 'ollama') =>
  http.post<{ task: HubTask; message: string }>(`${HUB}/${id}/download`, { source }).then((r) => r.data);

// --- Global Task Manager (unified over the Job System) ---------------------
import type { Task, TaskList } from './types';

const TASKS = '/tasks';

export const listTasks = (params?: { active_only?: boolean; kind?: string; status?: string; limit?: number }) =>
  http.get<TaskList>(TASKS, { params }).then((r) => r.data);
export const getTask = (id: string) => http.get<Task>(`${TASKS}/${id}`).then((r) => r.data);
export const cancelTask = (id: string) =>
  http.post<{ cancelled: boolean; id: string }>(`${TASKS}/${id}/cancel`).then((r) => r.data);
export const retryTask = (id: string) => http.post<Task>(`${TASKS}/${id}/retry`).then((r) => r.data);
export const deleteTask = (id: string) =>
  http.delete<{ deleted: boolean; id: string }>(`${TASKS}/${id}`).then((r) => r.data);

// --- RedForge V3 · Dataset Platform (Epic 3) -------------------------------
import type {
  ExportProviderInfo,
  TrainingEstimate,
  TrainingProviderInfo,
  TrainingStrategyInfo,
  V3Dataset,
  V3DatasetValidation,
  V3DatasetVersion,
  V3TrainingCheckpoint,
  V3TrainingRun,
} from './types';

const DP = '/dataset-platform';

export const dpFormats = () => http.get<string[]>(`${DP}/formats`).then((r) => r.data);
export const dpList = (projectId?: string) =>
  http.get<V3Dataset[]>(DP, { params: projectId ? { project_id: projectId } : undefined }).then((r) => r.data);
export const dpGet = (id: string) => http.get<V3Dataset>(`${DP}/${id}`).then((r) => r.data);
export const dpRegister = (body: { name: string; records: unknown[]; format?: string; kind?: string; project_id?: string; description?: string }) =>
  http.post<V3Dataset>(DP, body).then((r) => r.data);
export const dpImport = (file: File, name?: string, projectId?: string) => {
  const form = new FormData();
  form.append('file', file);
  if (name) form.append('name', name);
  if (projectId) form.append('project_id', projectId);
  return http.post<V3Dataset>(`${DP}/import`, form, { headers: { 'Content-Type': 'multipart/form-data' } }).then((r) => r.data);
};
export const dpVersions = (id: string) => http.get<V3DatasetVersion[]>(`${DP}/${id}/versions`).then((r) => r.data);
export const dpPreview = (id: string, offset = 0, limit = 50) =>
  http.get<{ rows: unknown[]; total: number; offset: number }>(`${DP}/${id}/preview`, { params: { offset, limit } }).then((r) => r.data);
export const dpValidate = (id: string) => http.get<V3DatasetValidation>(`${DP}/${id}/validate`).then((r) => r.data);
export const dpProcess = (id: string, body: { operation: string; train?: number; val?: number; test?: number }) =>
  http.post<{ id: string }>(`${DP}/${id}/process`, body).then((r) => r.data);
export const dpDelete = (id: string) => http.delete<{ deleted: boolean }>(`${DP}/${id}`).then((r) => r.data);

// --- RedForge V3 · Training Platform (Epic 3) ------------------------------
const TP = '/training-platform';

export const tpStrategies = () => http.get<TrainingStrategyInfo[]>(`${TP}/strategies`).then((r) => r.data);
export const tpProviders = () => http.get<TrainingProviderInfo[]>(`${TP}/providers`).then((r) => r.data);
export const tpEstimate = (body: Record<string, unknown>) => http.post<TrainingEstimate>(`${TP}/estimate`, body).then((r) => r.data);
export const tpList = (projectId?: string) =>
  http.get<V3TrainingRun[]>(TP, { params: projectId ? { project_id: projectId } : undefined }).then((r) => r.data);
export const tpGet = (id: string) => http.get<V3TrainingRun>(`${TP}/${id}`).then((r) => r.data);
export const tpCreate = (body: Record<string, unknown>) => http.post<V3TrainingRun>(TP, body).then((r) => r.data);
export const tpLaunch = (id: string) => http.post<{ run: V3TrainingRun; job: { id: string } }>(`${TP}/${id}/launch`).then((r) => r.data);
export const tpCheckpoints = (id: string) => http.get<V3TrainingCheckpoint[]>(`${TP}/${id}/checkpoints`).then((r) => r.data);
export const tpLogs = (id: string) => http.get<{ id: string; logs: string[] }>(`${TP}/${id}/logs`).then((r) => r.data);
export const tpCancel = (id: string) => http.post<{ cancelled: boolean }>(`${TP}/${id}/cancel`).then((r) => r.data);
export const tpDelete = (id: string) => http.delete<{ deleted: boolean }>(`${TP}/${id}`).then((r) => r.data);

// --- RedForge V3 · Export Engine (Epic 3) ----------------------------------
const EX = '/export';

export const exProviders = () => http.get<ExportProviderInfo[]>(`${EX}/providers`).then((r) => r.data);
export const exHistory = () => http.get<import('./types').Job[]>(`${EX}/history`).then((r) => r.data);
export const exSubmit = (body: { source_artifact_id: string; target?: string; base_model?: string; quantization?: string; model_name?: string }) =>
  http.post<import('./types').Job>(EX, body).then((r) => r.data);

// --- RedForge V3 · Experiment Platform (Epic 4) ----------------------------
import type {
  Experiment,
  ExperimentComparison,
  ExperimentJobRef,
  ExperimentNote,
  ExperimentSnapshot,
  ExperimentTimelineEvent,
} from './types';

const XP = '/experiments';

export const xpList = (params?: { project_id?: string; status?: string }) =>
  http.get<Experiment[]>(XP, { params }).then((r) => r.data);
export const xpGet = (id: string) => http.get<Experiment>(`${XP}/${id}`).then((r) => r.data);
export const xpCreate = (body: { name: string; description?: string; configuration?: Record<string, unknown>; tags?: string[]; project_id?: string }) =>
  http.post<Experiment>(XP, body).then((r) => r.data);
export const xpUpdate = (id: string, body: { name?: string; description?: string; tags?: string[]; status?: string }) =>
  http.patch<Experiment>(`${XP}/${id}`, body).then((r) => r.data);
export const xpDelete = (id: string) => http.delete<{ deleted: boolean }>(`${XP}/${id}`).then((r) => r.data);
export const xpClone = (id: string, body: { name?: string; include_notes?: boolean }) =>
  http.post<Experiment>(`${XP}/${id}/clone`, body).then((r) => r.data);
export const xpSnapshot = (id: string) => http.post<ExperimentSnapshot>(`${XP}/${id}/snapshot`).then((r) => r.data);
export const xpTimeline = (id: string) => http.get<ExperimentTimelineEvent[]>(`${XP}/${id}/timeline`).then((r) => r.data);
export const xpArtifacts = (id: string) => http.get<Artifact[]>(`${XP}/${id}/artifacts`).then((r) => r.data);
export const xpJobs = (id: string) => http.get<ExperimentJobRef[]>(`${XP}/${id}/jobs`).then((r) => r.data);
export const xpNotes = (id: string) => http.get<ExperimentNote[]>(`${XP}/${id}/notes`).then((r) => r.data);
export const xpAddNote = (id: string, body: string) => http.post<ExperimentNote>(`${XP}/${id}/notes`, { body }).then((r) => r.data);
export const xpCompare = (ids: string[]) =>
  http.get<ExperimentComparison>(`${XP}/compare`, { params: { ids: ids.join(',') } }).then((r) => r.data);
