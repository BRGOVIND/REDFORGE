/** Typed data hooks. Components consume these — never the endpoints directly. */
import { useMutation, useQuery, queryClient } from '../lib/query';
import * as api from '../api/endpoints';
import type { ProvidersResponse } from '../api/types';

export function useModels() {
  return useQuery({ queryKey: ['models'], queryFn: api.getModels, staleTime: 15_000 });
}

export function useProfiles() {
  return useQuery({ queryKey: ['profiles'], queryFn: api.getProfiles, staleTime: 60_000 });
}

export function usePlanPreview(profile: string | null, models: string[]) {
  const enabled = !!profile && models.length > 0;
  return useQuery({
    queryKey: ['plan-preview', profile, models.join(',')],
    queryFn: () => api.previewPlan(profile as string, models),
    enabled,
    staleTime: 10_000,
  });
}

export function useSessions(status?: string) {
  return useQuery({
    queryKey: ['sessions', status ?? 'all'],
    queryFn: () => api.listSessions(status ? { status, limit: 100 } : { limit: 100 }),
    staleTime: 4_000,
  });
}

export function useSession(id: string | null, refetchInterval = 0) {
  return useQuery({
    queryKey: ['session', id],
    queryFn: () => api.getSession(id as string),
    enabled: !!id,
    refetchInterval,
  });
}

export function useReport(id: string | null, refetchInterval = 0) {
  return useQuery({
    queryKey: ['report', id],
    queryFn: () => api.getReport(id as string),
    enabled: !!id,
    refetchInterval,
    staleTime: 30_000,
  });
}

export function usePlan(id: string | null, refetchInterval = 0) {
  return useQuery({
    queryKey: ['plan', id],
    queryFn: () => api.getPlan(id as string),
    enabled: !!id,
    refetchInterval,
  });
}

export function useFindings(id: string | null, refetchInterval = 0) {
  return useQuery({
    queryKey: ['findings', id],
    queryFn: () => api.getFindings(id as string),
    enabled: !!id,
    refetchInterval,
  });
}

export function useLeaderboard() {
  return useQuery({ queryKey: ['leaderboard'], queryFn: api.getLeaderboard, staleTime: 15_000 });
}

export function useHistory(model: string | null) {
  return useQuery({
    queryKey: ['history', model],
    queryFn: () => api.getHistory(model as string),
    enabled: !!model,
    staleTime: 15_000,
  });
}

export function useSystemChecks(refetchInterval = 2500) {
  return useQuery({
    queryKey: ['system-checks'],
    queryFn: api.getSystemChecks,
    refetchInterval,
    staleTime: 1500,
  });
}

// System Health Engine (V1.2) — API consumer hook (no dedicated UI yet).
export function useHealth(includeNetwork = false, refetchInterval = 0) {
  return useQuery({
    queryKey: ['health', includeNetwork],
    queryFn: () => api.getHealth(includeNetwork),
    staleTime: 5_000,
    refetchInterval,
  });
}

// Onboarding recommendations (V1.2.1) — hardware, runtime, and model advice.
export function useRecommendations(enabled = true) {
  return useQuery({
    queryKey: ['onboarding-recommendations'],
    queryFn: api.getRecommendations,
    enabled,
    staleTime: 10_000,
  });
}

// --- Runtime Manager (V1.2) ------------------------------------------------

export function useProviders(refetchInterval = 0, enabled = true) {
  return useQuery({
    queryKey: ['providers'],
    queryFn: api.getProviders,
    staleTime: 5_000,
    refetchInterval,
    enabled,
  });
}

export function useRuntimeStatus(refetchInterval = 0) {
  return useQuery({
    queryKey: ['runtime-status'],
    queryFn: api.getRuntimeStatus,
    staleTime: 4_000,
    refetchInterval,
  });
}

export function useRuntimeLogs(limit = 200, refetchInterval = 0) {
  return useQuery({
    queryKey: ['runtime-logs', limit],
    queryFn: () => api.getRuntimeLogs(limit),
    staleTime: 2_000,
    refetchInterval,
  });
}

export function useRefreshProviders() {
  return useMutation<void, ProvidersResponse>({
    mutationFn: () => api.refreshProviders(),
    onSuccess: () => queryClient.invalidate(['providers']),
  });
}

export function useTestProvider() {
  return useMutation({
    mutationFn: (name: string) => api.testProvider(name),
    onSuccess: () => queryClient.invalidate(['providers']),
  });
}

export function useSetDefaultProvider() {
  return useMutation({
    mutationFn: (name: string) => api.setDefaultProvider(name),
    onSuccess: () => {
      queryClient.invalidate(['providers']);
      queryClient.invalidate(['runtime-status']);
    },
  });
}

// --- Model Manager (V1.2) --------------------------------------------------

export function useModelCatalog(refetchInterval = 0, enabled = true) {
  return useQuery({
    queryKey: ['model-catalog'],
    queryFn: api.getModelCatalog,
    staleTime: 8_000,
    refetchInterval,
    enabled,
  });
}

export function useDeleteModel() {
  return useMutation({
    mutationFn: ({ provider, name }: { provider: string; name: string }) =>
      api.deleteModel(provider, name),
    onSuccess: () => queryClient.invalidate(['model-catalog']),
  });
}

export function useStartEvaluation() {
  return useMutation({
    mutationFn: ({ profile, models }: { profile: string; models: string[] }) =>
      api.startEvaluation(profile, models),
    onSuccess: () => queryClient.invalidate(['sessions']),
  });
}

export function useSessionControl() {
  const pause = useMutation({ mutationFn: api.pauseSession });
  const resume = useMutation({ mutationFn: api.resumeSession });
  const cancel = useMutation({ mutationFn: api.cancelSession });
  return { pause, resume, cancel };
}

// --- RedForge V2 · AI Studio (projects) ------------------------------------

export function useProjects(limit?: number) {
  return useQuery({
    queryKey: ['projects', limit ?? 'all'],
    queryFn: () => api.listProjects(limit),
    staleTime: 4_000,
  });
}

export function useProject(id: string | null) {
  return useQuery({
    queryKey: ['project', id],
    queryFn: () => api.getProject(id as string),
    enabled: !!id,
  });
}

export function useCreateProject() {
  return useMutation({
    mutationFn: (body: import('../api/types').ProjectCreate) => api.createProject(body),
    onSuccess: () => queryClient.invalidate(['projects']),
  });
}

export function useUpdateProject() {
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.updateProject(id, body),
    onSuccess: () => queryClient.invalidate(['project']),
  });
}

export function useDuplicateProject() {
  return useMutation({
    mutationFn: (id: string) => api.duplicateProject(id),
    onSuccess: () => queryClient.invalidate(['projects']),
  });
}

export function useDeleteProject() {
  return useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onSuccess: () => queryClient.invalidate(['projects']),
  });
}

// --- RedForge V2 · Playground ----------------------------------------------

export function usePlaygroundChat() {
  return useMutation({
    mutationFn: ({
      model,
      messages,
      params,
    }: {
      model: string;
      messages: import('../api/types').ChatMessage[];
      params?: import('../api/types').ChatParams;
    }) => api.playgroundChat(model, messages, params),
  });
}

// --- RedForge V2 · Assistant -----------------------------------------------

export function useAssistant() {
  return useMutation({
    mutationFn: ({ question, context }: { question: string; context?: string }) =>
      api.assistantAsk(question, context),
  });
}

// --- RedForge V2 · Dataset Lab ---------------------------------------------

export function useDatasets(projectId?: string) {
  return useQuery({
    queryKey: ['datasets', projectId ?? 'all'],
    queryFn: () => api.listDatasets(projectId),
    staleTime: 4_000,
  });
}

export function useDatasetPreview(id: string | null, offset: number, limit: number, search: string) {
  return useQuery({
    queryKey: ['dataset-preview', id, offset, limit, search],
    queryFn: () => api.previewDataset(id as string, offset, limit, search),
    enabled: !!id,
    staleTime: 2_000,
  });
}

export function useDatasetAnalysis(id: string | null) {
  return useQuery({
    queryKey: ['dataset-analysis', id],
    queryFn: () => api.analyzeDataset(id as string),
    enabled: !!id,
    staleTime: 10_000,
  });
}

export function useDatasetVersions(id: string | null) {
  return useQuery({
    queryKey: ['dataset-versions', id],
    queryFn: () => api.datasetVersions(id as string),
    enabled: !!id,
    staleTime: 2_000,
  });
}

export function useImportDataset() {
  return useMutation({
    mutationFn: ({ file, name, projectId }: { file: File; name?: string; projectId?: string }) =>
      api.importDataset(file, name, projectId),
    onSuccess: () => queryClient.invalidate(['datasets']),
  });
}

export function useDeleteDataset() {
  return useMutation({
    mutationFn: (id: string) => api.deleteDataset(id),
    onSuccess: () => queryClient.invalidate(['datasets']),
  });
}

export function useDuplicateDataset() {
  return useMutation({
    mutationFn: (id: string) => api.duplicateDataset(id),
    onSuccess: () => queryClient.invalidate(['datasets']),
  });
}

export function useCleanDataset() {
  return useMutation({
    mutationFn: ({ id, operations, save }: { id: string; operations: string[]; save: boolean }) =>
      api.cleanDataset(id, operations, save),
    onSuccess: () => {
      queryClient.invalidate(['datasets']);
      queryClient.invalidate(['dataset-preview']);
      queryClient.invalidate(['dataset-versions']);
      queryClient.invalidate(['dataset-analysis']);
    },
  });
}

export function useRestoreDatasetVersion() {
  return useMutation({
    mutationFn: ({ id, version }: { id: string; version: number }) =>
      api.restoreDatasetVersion(id, version),
    onSuccess: () => {
      queryClient.invalidate(['datasets']);
      queryClient.invalidate(['dataset-versions']);
      queryClient.invalidate(['dataset-preview']);
    },
  });
}

// --- RedForge V2 · Training Lab --------------------------------------------

export function useTrainingBackends() {
  return useQuery({ queryKey: ['training-backends'], queryFn: api.trainingBackends, staleTime: 30_000 });
}

export function useTrainingRuns(projectId?: string, limit?: number) {
  return useQuery({
    queryKey: ['training-runs', projectId ?? 'all', limit ?? 'n'],
    queryFn: () => api.listTrainingRuns(projectId, limit),
    staleTime: 3_000,
  });
}

export function useTrainingProgress(id: string | null, refetchInterval = 0) {
  return useQuery({
    queryKey: ['training-progress', id],
    queryFn: () => api.trainingProgress(id as string),
    enabled: !!id,
    refetchInterval,
  });
}

export function useTrainingCheckpoints(id: string | null, refetchInterval = 0) {
  return useQuery({
    queryKey: ['training-checkpoints', id],
    queryFn: () => api.trainingCheckpoints(id as string),
    enabled: !!id,
    refetchInterval,
  });
}

export function useLaunchTraining() {
  return useMutation({
    mutationFn: (body: Parameters<typeof api.launchTraining>[0]) => api.launchTraining(body),
    onSuccess: () => queryClient.invalidate(['training-runs']),
  });
}

export function useCancelTraining() {
  return useMutation({
    mutationFn: (id: string) => api.cancelTraining(id),
    onSuccess: () => queryClient.invalidate(['training-runs']),
  });
}

export function useDeleteTraining() {
  return useMutation({
    mutationFn: (id: string) => api.deleteTraining(id),
    onSuccess: () => queryClient.invalidate(['training-runs']),
  });
}

// --- RedForge V2 · Continuous Security -------------------------------------

export function useSecurityTimeline(runId: string | null, refetchInterval = 0) {
  return useQuery({
    queryKey: ['security-timeline', runId],
    queryFn: () => api.securityTimeline(runId as string),
    enabled: !!runId,
    refetchInterval,
    staleTime: 2_000,
  });
}

// --- RedForge V2 · Recommendation Engine -----------------------------------

export function useAnalyzeRecommendation() {
  return useMutation({
    mutationFn: (body: { target_model: string; run_id?: string; project_id?: string }) =>
      api.analyzeRecommendation(body),
  });
}

export function useDecideRecommendation() {
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'accepted' | 'rejected' | 'applied' }) =>
      api.decideRecommendation(id, status),
  });
}

export function useProjectRecommendations(projectId?: string) {
  return useQuery({
    queryKey: ['project-recommendations', projectId ?? 'all'],
    queryFn: () => api.listRecommendations(projectId),
    staleTime: 5_000,
  });
}

export function useRecommendationAccuracy(projectId?: string) {
  return useQuery({
    queryKey: ['recommendation-accuracy', projectId ?? 'all'],
    queryFn: () => api.recommendationAccuracy(projectId),
    staleTime: 10_000,
  });
}

// --- RedForge V2 · Runtime Registry (Phase 2.5) ----------------------------

export function useRegisteredModels(params?: { run_id?: string; project_id?: string }) {
  return useQuery({
    queryKey: ['registered-models', params?.run_id ?? 'all', params?.project_id ?? 'all'],
    queryFn: () => api.listRegisteredModels(params),
    staleTime: 5_000,
  });
}

// --- RedForge V2 · Training report (Phase 2.5) -----------------------------

export function useTrainingReport(runId: string | null) {
  return useQuery({
    queryKey: ['training-report', runId],
    queryFn: () => api.trainingReport(runId as string),
    enabled: !!runId,
    staleTime: 5_000,
  });
}

// --- RedForge V2 · Benchmark Center (Phase 3) ------------------------------

export function useBenchmarkSuites() {
  return useQuery({
    queryKey: ['benchmark-suites'],
    queryFn: api.benchmarkSuites,
    staleTime: 60_000,
  });
}

export function useBenchmarkHistory(
  params?: { project_id?: string; run_id?: string; model?: string },
  refetchInterval = 0,
) {
  return useQuery({
    queryKey: ['benchmark-history', params?.project_id ?? 'all', params?.run_id ?? 'all', params?.model ?? 'all'],
    queryFn: () => api.benchmarkHistory(params),
    refetchInterval,
    staleTime: 2_000,
  });
}

export function useScheduleBenchmark() {
  return useMutation({
    mutationFn: (body: import('../api/types').BenchmarkRequest) => api.scheduleBenchmark(body),
    onSuccess: () => queryClient.invalidate(['benchmark-history']),
  });
}

export function useCancelBenchmark() {
  return useMutation({
    mutationFn: (id: string) => api.cancelBenchmark(id),
    onSuccess: () => queryClient.invalidate(['benchmark-history']),
  });
}

export function useBenchmarkLeaderboard(params?: { project_id?: string; suite?: string }) {
  return useQuery({
    queryKey: ['benchmark-leaderboard', params?.project_id ?? 'all', params?.suite ?? 'overall'],
    queryFn: () => api.benchmarkLeaderboard(params),
    staleTime: 3_000,
  });
}

export function useBenchmarkTrends(projectId: string | null, suite?: string) {
  return useQuery({
    queryKey: ['benchmark-trends', projectId, suite ?? 'overall'],
    queryFn: () => api.benchmarkTrends(projectId as string, suite),
    enabled: !!projectId,
    staleTime: 5_000,
  });
}
