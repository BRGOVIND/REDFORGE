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

export function useTrainingDiagnostics() {
  return useQuery({
    queryKey: ['training-diagnostics'],
    queryFn: () => api.trainingDiagnostics(),
    staleTime: 30_000,
  });
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

// --- RedForge V2 · Evaluation Workbench (Phase 4) --------------------------

export function useSimilarityProviders() {
  return useQuery({ queryKey: ['wb-similarity'], queryFn: api.similarityProviders, staleTime: 60_000 });
}

export function useCollections(projectId?: string) {
  return useQuery({
    queryKey: ['wb-collections', projectId ?? 'all'],
    queryFn: () => api.listCollections(projectId),
    staleTime: 3_000,
  });
}

export function useCollection(id: string | null) {
  return useQuery({
    queryKey: ['wb-collection', id],
    queryFn: () => api.getCollection(id as string),
    enabled: !!id,
    staleTime: 2_000,
  });
}

export function useCreateCollection() {
  return useMutation({
    mutationFn: (body: Parameters<typeof api.createCollection>[0]) => api.createCollection(body),
    onSuccess: () => queryClient.invalidate(['wb-collections']),
  });
}

export function useDeleteCollection() {
  return useMutation({
    mutationFn: (id: string) => api.deleteCollection(id),
    onSuccess: () => queryClient.invalidate(['wb-collections']),
  });
}

export function usePromptSet(id: string | null) {
  return useQuery({
    queryKey: ['wb-prompt-set', id],
    queryFn: () => api.getPromptSet(id as string),
    enabled: !!id,
    staleTime: 2_000,
  });
}

export function useCreatePromptSet() {
  return useMutation({
    mutationFn: (body: Parameters<typeof api.createPromptSet>[0]) => api.createPromptSet(body),
    onSuccess: (s) => {
      queryClient.invalidate(['wb-collection', s.collection_id]);
      queryClient.invalidate(['wb-collections']);
    },
  });
}

export function useDeletePromptSet() {
  return useMutation({
    mutationFn: (id: string) => api.deletePromptSet(id),
    onSuccess: () => {
      queryClient.invalidate(['wb-collection']);
      queryClient.invalidate(['wb-collections']);
    },
  });
}

export function useCreatePrompt() {
  return useMutation({
    mutationFn: (body: Parameters<typeof api.createPrompt>[0]) => api.createPrompt(body),
    onSuccess: (p) => queryClient.invalidate(['wb-prompt-set', p.prompt_set_id]),
  });
}

export function useUpdatePrompt() {
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof api.updatePrompt>[1] }) =>
      api.updatePrompt(id, body),
    onSuccess: (p) => {
      queryClient.invalidate(['wb-prompt-set', p.prompt_set_id]);
      queryClient.invalidate(['wb-prompt-versions', p.id]);
    },
  });
}

export function useDeletePrompt() {
  return useMutation({
    mutationFn: (id: string) => api.deletePrompt(id),
    onSuccess: () => queryClient.invalidate(['wb-prompt-set']),
  });
}

export function usePromptVersions(id: string | null) {
  return useQuery({
    queryKey: ['wb-prompt-versions', id],
    queryFn: () => api.promptVersions(id as string),
    enabled: !!id,
    staleTime: 2_000,
  });
}

export function useWorkbenchSessions(params?: { project_id?: string; run_id?: string }, refetchInterval = 0) {
  return useQuery({
    queryKey: ['wb-sessions', params?.project_id ?? 'all', params?.run_id ?? 'all'],
    queryFn: () => api.listWorkbenchSessions(params),
    refetchInterval,
    staleTime: 2_000,
  });
}

export function useWorkbenchSession(id: string | null, refetchInterval = 0) {
  return useQuery({
    queryKey: ['wb-session', id],
    queryFn: () => api.getWorkbenchSession(id as string),
    enabled: !!id,
    refetchInterval,
    staleTime: 2_000,
  });
}

export function useCreateWorkbenchSession() {
  return useMutation({
    mutationFn: (body: Parameters<typeof api.createWorkbenchSession>[0]) => api.createWorkbenchSession(body),
    onSuccess: () => queryClient.invalidate(['wb-sessions']),
  });
}

export function useCancelWorkbenchSession() {
  return useMutation({
    mutationFn: (id: string) => api.cancelWorkbenchSession(id),
    onSuccess: () => queryClient.invalidate(['wb-sessions']),
  });
}

export function useSessionResults(id: string | null) {
  return useQuery({
    queryKey: ['wb-results', id],
    queryFn: () => api.sessionResults(id as string),
    enabled: !!id,
    staleTime: 2_000,
  });
}

export function useSessionRegressions(id: string | null) {
  return useQuery({
    queryKey: ['wb-regressions', id],
    queryFn: () => api.sessionRegressions(id as string),
    enabled: !!id,
    staleTime: 2_000,
  });
}

// --- RedForge V3 · Foundation Platform (Epic 1) ----------------------------

export function useFoundationModels(params?: { status?: string; source?: string }) {
  return useQuery({
    queryKey: ['foundation-models', params?.status ?? 'all', params?.source ?? 'all'],
    queryFn: () => api.listFoundationModels(params),
    staleTime: 3_000,
  });
}

export function useFoundationModel(id: string | null) {
  return useQuery({
    queryKey: ['foundation-model', id],
    queryFn: () => api.getFoundationModel(id as string),
    enabled: !!id,
    staleTime: 2_000,
  });
}

export function useFoundationModelRuntimes(id: string | null) {
  return useQuery({
    queryKey: ['foundation-model-runtimes', id],
    queryFn: () => api.foundationModelRuntimes(id as string),
    enabled: !!id,
    staleTime: 3_000,
  });
}

export function useFoundationDiscovery(enabled: boolean) {
  return useQuery({
    queryKey: ['foundation-discovery'],
    queryFn: api.discoverFoundationModels,
    enabled,
    staleTime: 10_000,
  });
}

export function useRegisterFoundationModel() {
  return useMutation({
    mutationFn: (body: Parameters<typeof api.registerFoundationModel>[0]) =>
      api.registerFoundationModel(body),
    onSuccess: () => queryClient.invalidate(['foundation-models']),
  });
}

export function useDeleteFoundationModel() {
  return useMutation({
    mutationFn: (id: string) => api.deleteFoundationModel(id),
    onSuccess: () => queryClient.invalidate(['foundation-models']),
  });
}

export function useResolveRuntimeModel() {
  return useMutation({
    mutationFn: (runtimeRef: string) => api.resolveRuntimeModel(runtimeRef),
  });
}

export function useSyncFoundationModel() {
  return useMutation({
    mutationFn: (id: string) => api.syncFoundationModel(id),
    onSuccess: () => queryClient.invalidate(['foundation-models']),
  });
}

// --- RedForge V3 · Automatic Model Discovery (Epic 4.5) --------------------

export function useRuntimeModels(refetchInterval = 0) {
  return useQuery({
    queryKey: ['runtime-models'],
    queryFn: () => api.listRuntimeModels(),
    refetchInterval,
    staleTime: 3_000,
  });
}
export function useUnresolvedRuntimeModels() {
  return useQuery({
    queryKey: ['runtime-models-unresolved'],
    queryFn: api.listUnresolvedRuntimeModels,
    staleTime: 3_000,
  });
}
function invalidateDiscovery() {
  queryClient.invalidate(['runtime-models']);
  queryClient.invalidate(['runtime-models-unresolved']);
  queryClient.invalidate(['foundation-models']);
}
export function useDiscoverModels() {
  return useMutation({ mutationFn: (_: void) => api.discoverAndRegisterModels(), onSuccess: invalidateDiscovery });
}
export function useSyncRuntimeModels() {
  return useMutation({ mutationFn: (_: void) => api.syncRuntimeModels(), onSuccess: invalidateDiscovery });
}
export function useResolveRuntimeModelEntry() {
  return useMutation({
    mutationFn: ({ id, hfRepo }: { id: string; hfRepo?: string }) => api.resolveRuntimeModelEntry(id, hfRepo),
    onSuccess: invalidateDiscovery,
  });
}

// --- RedForge V3 · Artifact Registry (Epic 2) ------------------------------

export function useArtifactTypes() {
  return useQuery({ queryKey: ['artifact-types'], queryFn: api.listArtifactTypes, staleTime: 60_000 });
}

export function useArtifacts(params?: { type?: string; status?: string; project_id?: string; tag?: string; q?: string }) {
  return useQuery({
    queryKey: ['artifacts', params?.type ?? 'all', params?.status ?? 'all', params?.q ?? ''],
    queryFn: () => api.searchArtifacts(params),
    staleTime: 3_000,
  });
}

export function useArtifact(id: string | null) {
  return useQuery({
    queryKey: ['artifact', id],
    queryFn: () => api.getArtifact(id as string),
    enabled: !!id,
    staleTime: 2_000,
  });
}

export function useArtifactLineage(id: string | null) {
  return useQuery({
    queryKey: ['artifact-lineage', id],
    queryFn: () => api.artifactLineage(id as string),
    enabled: !!id,
    staleTime: 3_000,
  });
}

export function useArtifactVersions(id: string | null) {
  return useQuery({
    queryKey: ['artifact-versions', id],
    queryFn: () => api.artifactVersions(id as string),
    enabled: !!id,
    staleTime: 3_000,
  });
}

export function useArchiveArtifact() {
  return useMutation({
    mutationFn: (id: string) => api.archiveArtifact(id),
    onSuccess: () => queryClient.invalidate(['artifacts']),
  });
}

export function useValidateArtifact() {
  return useMutation({
    mutationFn: (id: string) => api.validateArtifact(id),
    onSuccess: () => queryClient.invalidate(['artifacts']),
  });
}

export function useDeleteArtifact() {
  return useMutation({
    mutationFn: (id: string) => api.deleteArtifact(id),
    onSuccess: () => queryClient.invalidate(['artifacts']),
  });
}

// --- RedForge V3 · Job System (Epic 2) -------------------------------------

export function useJobTypes() {
  return useQuery({ queryKey: ['job-types'], queryFn: api.listJobTypes, staleTime: 60_000 });
}

export function useJobs(params?: { status?: string; type?: string }, refetchInterval = 0) {
  return useQuery({
    queryKey: ['jobs', params?.status ?? 'all', params?.type ?? 'all'],
    queryFn: () => api.listJobs(params),
    refetchInterval,
    staleTime: 2_000,
  });
}

export function useJob(id: string | null, refetchInterval = 0) {
  return useQuery({
    queryKey: ['job', id],
    queryFn: () => api.getJob(id as string),
    enabled: !!id,
    refetchInterval,
    staleTime: 1_000,
  });
}

export function useJobLogs(id: string | null) {
  return useQuery({
    queryKey: ['job-logs', id],
    queryFn: () => api.jobLogs(id as string),
    enabled: !!id,
    staleTime: 2_000,
  });
}

export function useSubmitJob() {
  return useMutation({
    mutationFn: (body: Parameters<typeof api.submitJob>[0]) => api.submitJob(body),
    onSuccess: () => queryClient.invalidate(['jobs']),
  });
}

export function useCancelJob() {
  return useMutation({
    mutationFn: (id: string) => api.cancelJob(id),
    onSuccess: () => queryClient.invalidate(['jobs']),
  });
}

export function useRetryJob() {
  return useMutation({
    mutationFn: (id: string) => api.retryJob(id),
    onSuccess: () => queryClient.invalidate(['jobs']),
  });
}

// --- RedForge V3 · Dataset Platform (Epic 3) -------------------------------

export function useV3Datasets(projectId?: string) {
  return useQuery({ queryKey: ['dp-list', projectId ?? 'all'], queryFn: () => api.dpList(projectId), staleTime: 3_000 });
}
export function useV3Dataset(id: string | null) {
  return useQuery({ queryKey: ['dp-get', id], queryFn: () => api.dpGet(id as string), enabled: !!id, staleTime: 2_000 });
}
export function useV3DatasetPreview(id: string | null) {
  return useQuery({ queryKey: ['dp-preview', id], queryFn: () => api.dpPreview(id as string), enabled: !!id, staleTime: 3_000 });
}
export function useV3DatasetValidate(id: string | null) {
  return useQuery({ queryKey: ['dp-validate', id], queryFn: () => api.dpValidate(id as string), enabled: !!id, staleTime: 5_000 });
}
export function useImportV3Dataset() {
  return useMutation({
    mutationFn: ({ file, name, projectId }: { file: File; name?: string; projectId?: string }) => api.dpImport(file, name, projectId),
    onSuccess: () => queryClient.invalidate(['dp-list']),
  });
}
export function useDeleteV3Dataset() {
  return useMutation({ mutationFn: (id: string) => api.dpDelete(id), onSuccess: () => queryClient.invalidate(['dp-list']) });
}

// --- RedForge V3 · Training Platform (Epic 3) ------------------------------

export function useTrainingStrategies() {
  return useQuery({ queryKey: ['tp-strategies'], queryFn: api.tpStrategies, staleTime: 60_000 });
}
export function useTrainingProviders() {
  return useQuery({ queryKey: ['tp-providers'], queryFn: api.tpProviders, staleTime: 30_000 });
}
export function useV3TrainingRuns(projectId?: string, refetchInterval = 0) {
  return useQuery({ queryKey: ['tp-list', projectId ?? 'all'], queryFn: () => api.tpList(projectId), refetchInterval, staleTime: 2_000 });
}
export function useV3TrainingRun(id: string | null, refetchInterval = 0) {
  return useQuery({ queryKey: ['tp-get', id], queryFn: () => api.tpGet(id as string), enabled: !!id, refetchInterval, staleTime: 1_500 });
}
export function useV3TrainingCheckpoints(id: string | null, refetchInterval = 0) {
  return useQuery({ queryKey: ['tp-checkpoints', id], queryFn: () => api.tpCheckpoints(id as string), enabled: !!id, refetchInterval, staleTime: 2_000 });
}
export function useEstimateTraining() {
  return useMutation({ mutationFn: (body: Record<string, unknown>) => api.tpEstimate(body) });
}
export function useCreateTrainingRun() {
  return useMutation({ mutationFn: (body: Record<string, unknown>) => api.tpCreate(body), onSuccess: () => queryClient.invalidate(['tp-list']) });
}
export function useLaunchTrainingRun() {
  return useMutation({ mutationFn: (id: string) => api.tpLaunch(id), onSuccess: () => queryClient.invalidate(['tp-list']) });
}
export function useCancelTrainingRun() {
  return useMutation({ mutationFn: (id: string) => api.tpCancel(id), onSuccess: () => queryClient.invalidate(['tp-list']) });
}

// --- RedForge V3 · Export Engine (Epic 3) ----------------------------------

export function useExportProviders() {
  return useQuery({ queryKey: ['ex-providers'], queryFn: api.exProviders, staleTime: 30_000 });
}
export function useExportHistory(refetchInterval = 0) {
  return useQuery({ queryKey: ['ex-history'], queryFn: api.exHistory, refetchInterval, staleTime: 2_000 });
}
export function useSubmitExport() {
  return useMutation({ mutationFn: (body: Parameters<typeof api.exSubmit>[0]) => api.exSubmit(body), onSuccess: () => queryClient.invalidate(['ex-history']) });
}

// --- RedForge V3 · Experiment Platform (Epic 4) ----------------------------

export function useExperiments(params?: { project_id?: string; status?: string }) {
  return useQuery({ queryKey: ['xp-list', params?.project_id ?? 'all', params?.status ?? 'all'], queryFn: () => api.xpList(params), staleTime: 3_000 });
}
export function useExperiment(id: string | null, refetchInterval = 0) {
  return useQuery({ queryKey: ['xp-get', id], queryFn: () => api.xpGet(id as string), enabled: !!id, refetchInterval, staleTime: 2_000 });
}
export function useExperimentTimeline(id: string | null, refetchInterval = 0) {
  return useQuery({ queryKey: ['xp-timeline', id], queryFn: () => api.xpTimeline(id as string), enabled: !!id, refetchInterval, staleTime: 2_000 });
}
export function useExperimentArtifacts(id: string | null, refetchInterval = 0) {
  return useQuery({ queryKey: ['xp-artifacts', id], queryFn: () => api.xpArtifacts(id as string), enabled: !!id, refetchInterval, staleTime: 2_000 });
}
export function useExperimentJobs(id: string | null, refetchInterval = 0) {
  return useQuery({ queryKey: ['xp-jobs', id], queryFn: () => api.xpJobs(id as string), enabled: !!id, refetchInterval, staleTime: 2_000 });
}
export function useExperimentNotes(id: string | null) {
  return useQuery({ queryKey: ['xp-notes', id], queryFn: () => api.xpNotes(id as string), enabled: !!id, staleTime: 2_000 });
}
export function useExperimentComparison(ids: string[]) {
  return useQuery({ queryKey: ['xp-compare', ids.join(',')], queryFn: () => api.xpCompare(ids), enabled: ids.length > 0, staleTime: 2_000 });
}
export function useCreateExperiment() {
  return useMutation({ mutationFn: (body: Parameters<typeof api.xpCreate>[0]) => api.xpCreate(body), onSuccess: () => queryClient.invalidate(['xp-list']) });
}
export function useUpdateExperiment() {
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof api.xpUpdate>[1] }) => api.xpUpdate(id, body),
    onSuccess: (_r, v) => { queryClient.invalidate(['xp-list']); queryClient.invalidate(['xp-get', v.id]); },
  });
}
export function useDeleteExperiment() {
  return useMutation({ mutationFn: (id: string) => api.xpDelete(id), onSuccess: () => queryClient.invalidate(['xp-list']) });
}
export function useCloneExperiment() {
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof api.xpClone>[1] }) => api.xpClone(id, body),
    onSuccess: () => queryClient.invalidate(['xp-list']),
  });
}
export function useSnapshotExperiment() {
  return useMutation({
    mutationFn: (id: string) => api.xpSnapshot(id),
    onSuccess: (_r, id) => { queryClient.invalidate(['xp-get', id]); queryClient.invalidate(['xp-timeline', id]); },
  });
}
export function useAddExperimentNote() {
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) => api.xpAddNote(id, body),
    onSuccess: (_r, v) => { queryClient.invalidate(['xp-notes', v.id]); queryClient.invalidate(['xp-timeline', v.id]); },
  });
}
