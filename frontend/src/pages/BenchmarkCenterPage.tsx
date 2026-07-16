import { useMemo, useState } from 'react';
import {
  Legend,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from 'recharts';
import { BarChart3, Boxes, Play, Sparkles, Trophy } from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Skeleton,
  StatusBadge,
} from '../components/ui';
import {
  useBenchmarkHistory,
  useBenchmarkLeaderboard,
  useBenchmarkSuites,
  useModels,
  useRegisteredModels,
  useScheduleBenchmark,
} from '../hooks/queries';
import { toast } from '../lib/toast';
import type { BenchmarkResult } from '../api/types';

const RADAR_COLORS = ['#e5484d', '#f5a623', '#30a46c', '#5b8def', '#a259ff', '#e0679b'];

export default function BenchmarkCenterPage() {
  const suites = useBenchmarkSuites();
  const models = useModels();
  const registered = useRegisteredModels();
  const schedule = useScheduleBenchmark();

  const suiteList = suites.data ?? [];
  const modelList = models.data?.models ?? [];
  const checkpoints = registered.data ?? [];

  const [selModels, setSelModels] = useState<Set<string>>(new Set());
  const [selCheckpoints, setSelCheckpoints] = useState<Set<string>>(new Set());
  const [selSuites, setSelSuites] = useState<Set<string>>(new Set(['performance', 'security']));
  const [compare, setCompare] = useState<Set<string>>(new Set());

  // Poll while any job is active so the UI updates without a refresh.
  const history = useBenchmarkHistory(undefined, 2500);
  const results = history.data ?? [];
  const active = results.some((r) => r.status === 'pending' || r.status === 'running');
  const leaderboard = useBenchmarkLeaderboard();

  const toggle = (set: Set<string>, setter: (s: Set<string>) => void, key: string) => {
    const next = new Set(set);
    next.has(key) ? next.delete(key) : next.add(key);
    setter(next);
  };

  const run = async () => {
    if (selSuites.size === 0) {
      toast.error('Select at least one suite');
      return;
    }
    if (selModels.size === 0 && selCheckpoints.size === 0) {
      toast.error('Select at least one model or checkpoint');
      return;
    }
    const res = await schedule.mutate({
      models: [...selModels],
      registry_ids: [...selCheckpoints],
      suites: [...selSuites],
    });
    if (res) {
      toast.success('Benchmark scheduled', `${res.count} model(s) queued`);
      void history.refetch?.();
    }
  };

  // Comparison set: explicitly selected completed results, else the latest few.
  const completed = results.filter((r) => r.status === 'completed');
  const comparison = useMemo(() => {
    const picked = completed.filter((r) => compare.has(r.id));
    return picked.length >= 1 ? picked : completed.slice(0, 4);
  }, [completed, compare]);

  return (
    <div>
      <PageHeader
        title="Benchmark Center"
        description="Objectively compare base models, checkpoints, and final models across pluggable suites. Everything runs locally."
        actions={
          <Button onClick={run} loading={schedule.isPending} disabled={active}>
            <Play size={15} /> Run Benchmark
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[340px_1fr]">
        {/* Setup column */}
        <div className="space-y-4">
          <Card className="p-4">
            <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">
              <BarChart3 size={13} /> Suites
            </p>
            {suites.isLoading ? (
              <Skeleton className="h-24" />
            ) : (
              <div className="space-y-1.5">
                {suiteList.map((s) => (
                  <CheckRow
                    key={s.key}
                    checked={selSuites.has(s.key)}
                    onToggle={() => toggle(selSuites, setSelSuites, s.key)}
                    label={s.label}
                    hint={s.real ? undefined : 'architecture'}
                    title={s.description}
                  />
                ))}
              </div>
            )}
          </Card>

          <Card className="p-4">
            <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">
              <Boxes size={13} /> Base models
            </p>
            {modelList.length === 0 ? (
              <p className="py-2 text-xs text-content-subtle">No models available.</p>
            ) : (
              <div className="max-h-44 space-y-1.5 overflow-y-auto">
                {modelList.map((m) => (
                  <CheckRow
                    key={m.name}
                    checked={selModels.has(m.name)}
                    onToggle={() => toggle(selModels, setSelModels, m.name)}
                    label={m.name}
                  />
                ))}
              </div>
            )}
          </Card>

          <Card className="p-4">
            <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">
              <Sparkles size={13} /> Checkpoints
            </p>
            {checkpoints.length === 0 ? (
              <p className="py-2 text-xs text-content-subtle">
                No registered checkpoints. Train a model to register one.
              </p>
            ) : (
              <div className="max-h-44 space-y-1.5 overflow-y-auto">
                {checkpoints.map((c) => (
                  <CheckRow
                    key={c.id}
                    checked={selCheckpoints.has(c.id)}
                    onToggle={() => toggle(selCheckpoints, setSelCheckpoints, c.id)}
                    label={c.label}
                    hint={c.fallback ? 'base' : undefined}
                    title={c.runtime_model}
                  />
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Results column */}
        <div className="space-y-5">
          {active && (
            <Card className="flex items-center gap-2 p-3 text-xs text-content-subtle">
              <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
              Running benchmarks… results appear as each model finishes.
            </Card>
          )}

          <RadarCompare comparison={comparison} suiteList={suiteList} />

          <ComparisonTable comparison={comparison} suiteList={suiteList} />

          <LeaderboardCard entries={leaderboard.data ?? []} loading={leaderboard.isLoading} />

          <HistoryCard
            results={results}
            loading={history.isLoading}
            compare={compare}
            onToggleCompare={(id) => toggle(compare, setCompare, id)}
          />
        </div>
      </div>
    </div>
  );
}

function CheckRow({
  checked,
  onToggle,
  label,
  hint,
  title,
}: {
  checked: boolean;
  onToggle: () => void;
  label: string;
  hint?: string;
  title?: string;
}) {
  return (
    <button
      onClick={onToggle}
      title={title}
      className={`flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-xs rf-focus ${
        checked ? 'border-red-500 bg-red-soft' : 'border-border hover:border-border-strong'
      }`}
    >
      <span className="flex min-w-0 items-center gap-2">
        <span
          className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border ${
            checked ? 'border-red-500 bg-red-500 text-white' : 'border-border'
          }`}
        >
          {checked && <span className="text-[9px] leading-none">✓</span>}
        </span>
        <span className="truncate text-content">{label}</span>
      </span>
      {hint && <Badge tone="grey">{hint}</Badge>}
    </button>
  );
}

function RadarCompare({
  comparison,
  suiteList,
}: {
  comparison: BenchmarkResult[];
  suiteList: { key: string; label: string }[];
}) {
  const suiteLabel = (k: string) => suiteList.find((s) => s.key === k)?.label ?? k;
  const suiteKeys = useMemo(() => {
    const keys = new Set<string>();
    comparison.forEach((r) => Object.keys(r.scores ?? {}).forEach((k) => keys.add(k)));
    return [...keys];
  }, [comparison]);

  if (comparison.length === 0) {
    return (
      <Card className="p-4">
        <SectionTitle icon={<BarChart3 size={15} />} title="Dimension comparison" />
        <EmptyState
          icon={<BarChart3 size={24} />}
          title="No results yet"
          description="Run a benchmark to compare models across dimensions."
        />
      </Card>
    );
  }

  const data = suiteKeys.map((k) => {
    const row: Record<string, number | string> = { suite: suiteLabel(k) };
    comparison.forEach((r) => {
      const v = r.scores?.[k];
      if (v != null) row[r.label ?? r.target_model] = v;
    });
    return row;
  });

  return (
    <Card className="p-4">
      <SectionTitle icon={<BarChart3 size={15} />} title="Dimension comparison" />
      <ResponsiveContainer width="100%" height={320}>
        <RadarChart data={data}>
          <PolarGrid stroke="rgba(255,255,255,0.08)" />
          <PolarAngleAxis dataKey="suite" tick={{ fill: '#9a9aa5', fontSize: 11 }} />
          {comparison.map((r, i) => {
            const name = r.label ?? r.target_model;
            return (
              <Radar
                key={r.id}
                name={name}
                dataKey={name}
                stroke={RADAR_COLORS[i % RADAR_COLORS.length]}
                fill={RADAR_COLORS[i % RADAR_COLORS.length]}
                fillOpacity={0.15}
                isAnimationActive={false}
              />
            );
          })}
          <Legend wrapperStyle={{ fontSize: 11 }} />
        </RadarChart>
      </ResponsiveContainer>
    </Card>
  );
}

function ComparisonTable({
  comparison,
  suiteList,
}: {
  comparison: BenchmarkResult[];
  suiteList: { key: string; label: string }[];
}) {
  if (comparison.length === 0) return null;
  const suiteLabel = (k: string) => suiteList.find((s) => s.key === k)?.label ?? k;
  const suiteKeys = [...new Set(comparison.flatMap((r) => Object.keys(r.scores ?? {})))];

  return (
    <Card className="overflow-hidden">
      <div className="border-b border-border px-5 py-3">
        <SectionTitle icon={<BarChart3 size={15} />} title="Comparison table" />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-content-subtle">
              <th className="px-4 py-2 text-left font-medium">Model</th>
              <th className="px-4 py-2 text-right font-medium">Overall</th>
              {suiteKeys.map((k) => (
                <th key={k} className="px-4 py-2 text-right font-medium">
                  {suiteLabel(k)}
                </th>
              ))}
              <th className="px-4 py-2 text-right font-medium">Latency</th>
              <th className="px-4 py-2 text-right font-medium">Tok/s</th>
            </tr>
          </thead>
          <tbody>
            {comparison.map((r) => {
              const perf = (r.metrics?.performance ?? {}) as Record<string, unknown>;
              return (
                <tr key={r.id} className="border-b border-border/60 last:border-0">
                  <td className="px-4 py-2 text-content">{r.label ?? r.target_model}</td>
                  <td className="px-4 py-2 text-right font-semibold text-content">
                    {r.overall_score ?? '—'}
                  </td>
                  {suiteKeys.map((k) => (
                    <td key={k} className="px-4 py-2 text-right text-content-muted">
                      {r.scores?.[k] ?? '—'}
                    </td>
                  ))}
                  <td className="px-4 py-2 text-right text-content-muted">
                    {perf.avg_latency_ms != null ? `${perf.avg_latency_ms as number} ms` : '—'}
                  </td>
                  <td className="px-4 py-2 text-right text-content-muted">
                    {perf.tokens_per_sec != null ? String(perf.tokens_per_sec) : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function LeaderboardCard({
  entries,
  loading,
}: {
  entries: { id: string; label: string | null; target_model: string; rank_score: number | null }[];
  loading: boolean;
}) {
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-border px-5 py-3">
        <SectionTitle icon={<Trophy size={15} />} title="Leaderboard" />
      </div>
      <div className="p-3">
        {loading ? (
          <Skeleton className="h-24" />
        ) : entries.length === 0 ? (
          <p className="px-2 py-4 text-center text-xs text-content-subtle">No ranked results yet.</p>
        ) : (
          <ol className="space-y-1.5">
            {entries.map((e, i) => (
              <li
                key={e.id}
                className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2 text-xs"
              >
                <span className="flex items-center gap-2">
                  <span className="w-5 text-content-faint">#{i + 1}</span>
                  <span className="text-content">{e.label ?? e.target_model}</span>
                </span>
                <span className="font-semibold text-content">{e.rank_score ?? '—'}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Card>
  );
}

function HistoryCard({
  results,
  loading,
  compare,
  onToggleCompare,
}: {
  results: BenchmarkResult[];
  loading: boolean;
  compare: Set<string>;
  onToggleCompare: (id: string) => void;
}) {
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-border px-5 py-3">
        <SectionTitle icon={<BarChart3 size={15} />} title="History" />
      </div>
      <div className="p-3">
        {loading ? (
          <Skeleton className="h-24" />
        ) : results.length === 0 ? (
          <p className="px-2 py-4 text-center text-xs text-content-subtle">No benchmarks run yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {results.map((r) => (
              <li
                key={r.id}
                className="flex items-center justify-between gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-xs"
              >
                <label className="flex min-w-0 items-center gap-2">
                  <input
                    type="checkbox"
                    className="accent-red-500"
                    checked={compare.has(r.id)}
                    disabled={r.status !== 'completed'}
                    onChange={() => onToggleCompare(r.id)}
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-content">{r.label ?? r.target_model}</span>
                    <span className="block truncate text-[11px] text-content-subtle">
                      {r.suites.join(', ')}
                    </span>
                  </span>
                </label>
                <span className="flex shrink-0 items-center gap-2">
                  {r.overall_score != null && (
                    <span className="font-semibold text-content">{r.overall_score}</span>
                  )}
                  <StatusBadge status={r.status} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function SectionTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <p className="flex items-center gap-2 text-sm font-semibold text-content">
      {icon} {title}
    </p>
  );
}
