import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  KeyRound,
  Plug,
  RefreshCw,
  ScrollText,
  Server,
  Star,
} from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  PageHeader,
  Spinner,
} from '../components/ui';
import {
  useProviders,
  useRefreshProviders,
  useRuntimeLogs,
  useRuntimeStatus,
  useSetDefaultProvider,
  useTestProvider,
} from '../hooks/queries';
import { toast } from '../lib/toast';
import { errorMessage } from '../api/client';
import { cn } from '../lib/cn';
import type { ProviderHealth, ProviderInfo } from '../api/types';

function fmtTime(iso: string | null): string {
  if (!iso) return 'never';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? 'never' : d.toLocaleTimeString();
}

type HealthState = 'healthy' | 'degraded' | 'offline' | 'unknown';

function healthState(h: ProviderHealth | null): HealthState {
  if (!h || h.checked_at === null) return 'unknown';
  if (!h.online) return 'offline';
  return h.healthy ? 'healthy' : 'degraded';
}

const HEALTH_META: Record<HealthState, { tone: 'green' | 'amber' | 'red' | 'grey'; dot: string; label: string }> = {
  healthy: { tone: 'green', dot: 'bg-pass', label: 'Online' },
  degraded: { tone: 'amber', dot: 'bg-uncertain', label: 'Degraded' },
  offline: { tone: 'red', dot: 'bg-red-500', label: 'Offline' },
  unknown: { tone: 'grey', dot: 'bg-content-faint', label: 'Unknown' },
};

function StatusDot({ state }: { state: HealthState }) {
  const meta = HEALTH_META[state];
  return (
    <span className="inline-flex items-center gap-2">
      <span className={cn('h-2 w-2 rounded-full', meta.dot, state === 'healthy' && 'animate-pulse-dot')} />
      <Badge tone={meta.tone}>{meta.label}</Badge>
    </span>
  );
}

export default function RuntimeManagerPage() {
  const providers = useProviders();
  const status = useRuntimeStatus(5_000);
  const refresh = useRefreshProviders();
  const test = useTestProvider();
  const setDefault = useSetDefaultProvider();

  const [selected, setSelected] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [autoLogs, setAutoLogs] = useState(false);
  const logs = useRuntimeLogs(200, autoLogs ? 5_000 : 0);

  // Populate live health once on mount (GET /providers only returns cached health).
  const didRefresh = useRef(false);
  useEffect(() => {
    if (!didRefresh.current) {
      didRefresh.current = true;
      void refresh.mutate();
    }
  }, [refresh]);

  const rows = useMemo(() => providers.data?.providers ?? [], [providers.data]);
  const detail = rows.find((p) => p.name === selected) ?? null;

  const onRefresh = async () => {
    const res = await refresh.mutate();
    if (res) toast.success('Providers refreshed');
  };

  const onTest = async (p: ProviderInfo) => {
    setTesting(p.name);
    const res = await test.mutate(p.name);
    setTesting(null);
    if (!res) return;
    if (res.online) toast.success(`${p.label} online`, res.version ? `version ${res.version}` : undefined);
    else toast.error(`${p.label} offline`, res.error ?? undefined);
  };

  const onSetDefault = async (p: ProviderInfo) => {
    const res = await setDefault.mutate(p.name);
    if (res) toast.success(`Default provider set to ${p.label}`);
    else toast.error('Could not set default', errorMessage(setDefault.error));
  };

  return (
    <div>
      <PageHeader
        title="Runtime Manager"
        description="Inspect and manage the LLM providers behind the unified runtime."
        actions={
          <Button variant="secondary" size="sm" onClick={onRefresh} loading={refresh.isPending}>
            <RefreshCw size={14} />
            Refresh
          </Button>
        }
      />

      {/* Runtime status strip */}
      <Card className="mb-5 flex flex-wrap items-center gap-x-8 gap-y-2 px-5 py-4">
        <div className="flex items-center gap-2 text-sm">
          <Server size={15} className="text-content-muted" />
          <span className="text-content-subtle">Active provider</span>
          <span className="font-mono font-medium text-content">{status.data?.provider ?? '—'}</span>
        </div>
        <div className="text-sm text-content-subtle">
          Concurrency/model <span className="text-content">{status.data?.concurrency_per_model ?? '—'}</span>
        </div>
        <div className="text-sm text-content-subtle">
          Active requests <span className="text-content">{status.data?.metrics?.active_requests ?? 0}</span>
        </div>
        <div className="text-sm text-content-subtle">
          Avg latency <span className="text-content">{Math.round(status.data?.metrics?.avg_latency_ms ?? 0)} ms</span>
        </div>
      </Card>

      {providers.isLoading ? (
        <Spinner label="Loading providers…" />
      ) : rows.length === 0 ? (
        <EmptyState icon={<Plug size={26} />} title="No providers registered" />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-content-subtle">
                  <th className="px-4 py-3 font-medium">Provider</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Models</th>
                  <th className="px-4 py-3 font-medium">Version</th>
                  <th className="px-4 py-3 font-medium">Runtime URL</th>
                  <th className="px-4 py-3 font-medium">Last check</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => {
                  const state = healthState(p.health);
                  return (
                    <tr
                      key={p.name}
                      className={cn(
                        'border-b border-border/60 last:border-0 hover:bg-overlay cursor-pointer',
                        selected === p.name && 'bg-overlay'
                      )}
                      onClick={() => setSelected(selected === p.name ? null : p.name)}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-content">{p.label}</span>
                          {p.is_default && (
                            <Badge tone="red">
                              <Star size={11} /> default
                            </Badge>
                          )}
                        </div>
                        <div className="font-mono text-[11px] text-content-faint">{p.name}</div>
                      </td>
                      <td className="px-4 py-3">
                        <StatusDot state={state} />
                      </td>
                      <td className="px-4 py-3 tabular-nums text-content-muted">
                        {p.health?.model_count ?? '—'}
                      </td>
                      <td className="px-4 py-3 font-mono text-[12px] text-content-muted">
                        {p.health?.version ?? '—'}
                      </td>
                      <td className="px-4 py-3 font-mono text-[12px] text-content-subtle">
                        {p.base_url ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-content-subtle">{fmtTime(p.health?.checked_at ?? null)}</td>
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onTest(p)}
                            loading={testing === p.name}
                          >
                            <Plug size={13} />
                            Test
                          </Button>
                          <Button
                            variant={p.is_default ? 'secondary' : 'primary'}
                            size="sm"
                            disabled={p.is_default || setDefault.isPending}
                            onClick={() => onSetDefault(p)}
                          >
                            {p.is_default ? 'Active' : 'Set default'}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Provider details */}
      {detail && (
        <Card className="mt-5">
          <CardHeader
            title={`${detail.label} — details`}
            subtitle={detail.name}
            icon={<Server size={16} />}
            action={
              <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>
                Close
              </Button>
            }
          />
          <div className="grid grid-cols-2 gap-x-8 gap-y-3 px-5 py-4 text-sm md:grid-cols-3">
            <Detail label="Runtime URL" value={detail.base_url ?? '—'} mono />
            <Detail label="Health latency" value={detail.health?.latency_ms != null ? `${detail.health.latency_ms} ms` : '—'} />
            <Detail label="Installed models" value={String(detail.health?.model_count ?? '—')} />
            <Detail label="Version" value={detail.health?.version ?? '—'} mono />
            <Detail
              label="API key"
              value={
                !detail.requires_api_key
                  ? 'not required'
                  : detail.api_key_present
                    ? `configured (${detail.api_key_env})`
                    : `missing (${detail.api_key_env})`
              }
            />
            <Detail label="Last check" value={fmtTime(detail.health?.checked_at ?? null)} />
          </div>

          {detail.requires_api_key && !detail.api_key_present && (
            <div className="mx-5 mb-4 flex items-center gap-2 rounded-lg border border-uncertain/20 bg-uncertain/10 px-3 py-2 text-xs text-uncertain">
              <KeyRound size={13} />
              Set <span className="font-mono">{detail.api_key_env}</span> in the environment, then restart RedForge.
            </div>
          )}
          {detail.health?.error && (
            <div className="mx-5 mb-4 flex items-center gap-2 rounded-lg border border-red-700/30 bg-red-soft px-3 py-2 text-xs text-fail">
              <AlertTriangle size={13} />
              {detail.health.error}
            </div>
          )}

          {(detail.health?.models?.length ?? 0) > 0 && (
            <div className="border-t border-border px-5 py-4">
              <p className="mb-2 text-xs text-content-subtle">Available models</p>
              <div className="flex flex-wrap gap-1.5">
                {detail.health!.models.map((m) => (
                  <span key={m} className="rounded-md bg-elevated px-2 py-0.5 font-mono text-[11px] text-content-muted">
                    {m}
                  </span>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Runtime logs (read-only) */}
      <Card className="mt-5 overflow-hidden">
        <CardHeader
          title="Runtime logs"
          subtitle="Read-only · most recent activity"
          icon={<ScrollText size={16} />}
          action={
            <div className="flex items-center gap-2">
              <Button
                variant={autoLogs ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => setAutoLogs((v) => !v)}
              >
                {autoLogs ? 'Auto · on' : 'Auto · off'}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => logs.refetch()} loading={logs.isFetching}>
                <RefreshCw size={13} />
                Refresh
              </Button>
            </div>
          }
        />
        <div className="max-h-80 overflow-auto bg-base/60 px-4 py-3 font-mono text-[11.5px] leading-relaxed">
          {(logs.data?.lines?.length ?? 0) === 0 ? (
            <p className="text-content-faint">No log lines captured yet.</p>
          ) : (
            logs.data!.lines.map((ln, i) => (
              <div key={i} className="flex gap-2 whitespace-pre-wrap">
                <span className="shrink-0 text-content-faint">{fmtTime(ln.ts)}</span>
                <span
                  className={cn(
                    'shrink-0 w-14',
                    ln.level === 'ERROR' || ln.level === 'CRITICAL'
                      ? 'text-fail'
                      : ln.level === 'WARNING'
                        ? 'text-uncertain'
                        : 'text-content-faint'
                  )}
                >
                  {ln.level}
                </span>
                <span className="shrink-0 text-content-subtle">{ln.logger.replace(/^redforge\./, '')}</span>
                <span className="text-content-muted">{ln.message}</span>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}

function Detail({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-content-subtle">{label}</span>
      <span className={cn('text-content', mono && 'font-mono text-[12px]')}>{value}</span>
    </div>
  );
}
