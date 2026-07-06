/** Typed data hooks. Components consume these — never the endpoints directly. */
import { useMutation, useQuery, queryClient } from '../lib/query';
import * as api from '../api/endpoints';

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
