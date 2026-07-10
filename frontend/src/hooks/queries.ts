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
