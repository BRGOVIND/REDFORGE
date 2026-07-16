import { useMemo } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  BarChart3,
  Boxes,
  Database,
  FileText,
  Layers,
  Lightbulb,
  Rocket,
  ShieldCheck,
  Sparkles,
  Trophy,
} from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  ErrorState,
  PageHeader,
  Skeleton,
} from '../components/ui';
import {
  useBenchmarkHistory,
  useBenchmarkLeaderboard,
  useDatasets,
  useProject,
  useProjectRecommendations,
  useRecommendationAccuracy,
  useRegisteredModels,
  useTrainingRuns,
} from '../hooks/queries';
import type { TrainingRun } from '../api/types';

/**
 * Project Overview (Phase 2.5, Part 6) — the central dashboard for a single
 * project. Composes existing data (models, datasets, training runs, checkpoints,
 * recommendations, registered models) and links out to the pages that own each
 * area. It stores nothing and duplicates no page.
 */
export default function ProjectOverviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const project = useProject(id ?? null);
  const datasets = useDatasets(id);
  const runs = useTrainingRuns(id);
  const registered = useRegisteredModels(id ? { project_id: id } : undefined);
  const recs = useProjectRecommendations(id);
  const accuracy = useRecommendationAccuracy(id);
  const benchmarks = useBenchmarkHistory(id ? { project_id: id } : undefined);
  const leaderboard = useBenchmarkLeaderboard(id ? { project_id: id } : undefined);

  const runList = runs.data ?? [];
  const datasetList = datasets.data ?? [];
  const regList = registered.data ?? [];
  const recList = recs.data ?? [];
  const benchList = benchmarks.data ?? [];
  const bestModel = (leaderboard.data ?? [])[0] ?? null;
  const models = project.data?.models ?? [];

  const completedRuns = useMemo(
    () => runList.filter((r) => r.status === 'completed').length,
    [runList],
  );

  if (project.isLoading) {
    return (
      <div>
        <Skeleton className="mb-6 h-16" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      </div>
    );
  }

  if (project.error || !project.data) {
    return (
      <div>
        <PageHeader title="Project" />
        <ErrorState message="Could not load this project." onRetry={() => project.refetch?.()} />
      </div>
    );
  }

  const p = project.data;

  return (
    <div>
      <PageHeader
        title={p.name}
        description={p.description || 'Local workspace — models, datasets, training, and reports in one place.'}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => navigate('/studio')}>
              <ArrowLeft size={14} /> All Projects
            </Button>
            <Button size="sm" onClick={() => navigate('/training')}>
              <Rocket size={14} /> Training Lab
            </Button>
          </div>
        }
      />

      {/* Overview tiles */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat icon={<Boxes size={14} />} label="Models" value={models.length} />
        <Stat icon={<Database size={14} />} label="Datasets" value={datasetList.length} />
        <Stat icon={<Layers size={14} />} label="Training runs" value={runList.length} />
        <Stat icon={<ShieldCheck size={14} />} label="Completed" value={completedRuns} />
        <Stat icon={<Sparkles size={14} />} label="Checkpoints" value={regList.length} />
        <Stat icon={<BarChart3 size={14} />} label="Benchmarks" value={benchList.length} />
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Models */}
        <SectionCard title="Models" icon={<Boxes size={15} />} to="/models" cta="Manage">
          {models.length === 0 ? (
            <Muted>No models in this project yet.</Muted>
          ) : (
            <ul className="space-y-1.5">
              {models.map((m) => (
                <li key={m} className="truncate rounded-lg border border-border bg-surface px-3 py-2 text-xs text-content">
                  {m}
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        {/* Datasets */}
        <SectionCard title="Datasets" icon={<Database size={15} />} to="/datasets" cta="Dataset Lab">
          {datasetList.length === 0 ? (
            <Muted>No datasets. Build one in the Dataset Lab.</Muted>
          ) : (
            <ul className="space-y-1.5">
              {datasetList.slice(0, 6).map((d) => (
                <li key={d.id} className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2 text-xs">
                  <span className="truncate text-content">{d.name}</span>
                  <span className="shrink-0 text-content-subtle">{d.record_count ?? 0} rows</span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        {/* Training runs */}
        <SectionCard title="Training runs" icon={<Layers size={15} />} to="/training" cta="Training Lab">
          {runList.length === 0 ? (
            <Muted>No training runs yet.</Muted>
          ) : (
            <ul className="space-y-1.5">
              {runList.slice(0, 6).map((r) => (
                <RunRow key={r.id} run={r} />
              ))}
            </ul>
          )}
        </SectionCard>

        {/* Final / registered models */}
        <SectionCard title="Runnable checkpoints" icon={<Sparkles size={15} />} to="/playground" cta="Playground">
          {regList.length === 0 ? (
            <Muted>Checkpoints appear here once a run registers them with the Runtime Manager.</Muted>
          ) : (
            <ul className="space-y-1.5">
              {regList.slice(0, 6).map((m) => (
                <li key={m.id} className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2 text-xs">
                  <span className="min-w-0">
                    <span className="block truncate text-content">{m.label}</span>
                    <span className="block truncate text-[11px] text-content-subtle">{m.runtime_model}</span>
                  </span>
                  {m.fallback && <Badge tone="grey">base</Badge>}
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        {/* Benchmarks — best model + performance history */}
        <SectionCard title="Benchmarks" icon={<BarChart3 size={15} />} to="/benchmarks" cta="Benchmark Center">
          {bestModel && (
            <div className="mb-3 flex items-center justify-between rounded-lg border border-border bg-base p-3 text-xs">
              <span className="flex items-center gap-2 text-content">
                <Trophy size={13} className="text-uncertain" /> Best model
                <span className="font-medium">{bestModel.label ?? bestModel.target_model}</span>
              </span>
              <span className="font-semibold text-pass">{bestModel.rank_score ?? '—'}</span>
            </div>
          )}
          {benchList.length === 0 ? (
            <Muted>No benchmarks yet. Compare models in the Benchmark Center.</Muted>
          ) : (
            <ul className="space-y-1.5">
              {benchList.slice(0, 6).map((b) => (
                <li key={b.id} className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2 text-xs">
                  <span className="min-w-0">
                    <span className="block truncate text-content">{b.label ?? b.target_model}</span>
                    <span className="block truncate text-[11px] text-content-subtle">{b.suites.join(', ')}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    {b.overall_score != null && <span className="font-semibold text-content">{b.overall_score}</span>}
                    <Badge tone={b.status === 'completed' ? 'green' : b.status === 'failed' ? 'red' : 'amber'}>
                      {b.status}
                    </Badge>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        {/* Recommendations + accuracy */}
        <SectionCard title="Recommendations" icon={<Lightbulb size={15} />} to="/training" cta="Training Lab">
          {accuracy.data && accuracy.data.count > 0 && (
            <div className="mb-3 rounded-lg border border-border bg-base p-3 text-xs text-content">
              Mean recommendation accuracy{' '}
              <span className="font-semibold text-pass">
                {accuracy.data.mean_accuracy != null ? `${Math.round(accuracy.data.mean_accuracy * 100)}%` : '—'}
              </span>{' '}
              across {accuracy.data.count} applied recommendation(s).
            </div>
          )}
          {recList.length === 0 ? (
            <Muted>No recommendations yet. Analyze a completed run to generate one.</Muted>
          ) : (
            <ul className="space-y-1.5">
              {recList.slice(0, 6).map((r) => (
                <li key={r.id} className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2 text-xs">
                  <span className="truncate text-content">{r.target_model}</span>
                  <Badge tone={r.status === 'accepted' || r.status === 'applied' ? 'green' : r.status === 'rejected' ? 'grey' : 'amber'}>
                    {r.status}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        {/* Reports */}
        <SectionCard title="Reports" icon={<FileText size={15} />} to="/reports" cta="Reports">
          <Muted>
            Security evaluation and training reports for this project. Training reports are generated
            per run from existing data — nothing is duplicated.
          </Muted>
        </SectionCard>
      </div>
    </div>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <Card className="p-3">
      <div className="flex items-center gap-1.5 text-[11px] text-content-subtle">
        {icon} {label}
      </div>
      <p className="mt-1 text-xl font-semibold text-content">{value}</p>
    </Card>
  );
}

function SectionCard({
  title,
  icon,
  to,
  cta,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  to: string;
  cta: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="flex flex-col p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="flex items-center gap-2 text-sm font-semibold text-content">
          {icon} {title}
        </p>
        <Link to={to} className="text-xs text-red-400 hover:underline rf-focus">
          {cta} →
        </Link>
      </div>
      <div className="flex-1">{children}</div>
    </Card>
  );
}

function RunRow({ run }: { run: TrainingRun }) {
  const tone =
    run.status === 'completed' ? 'green' : run.status === 'failed' || run.status === 'cancelled' ? 'red' : 'amber';
  return (
    <li className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2 text-xs">
      <span className="min-w-0">
        <span className="block truncate text-content">{run.name}</span>
        <span className="block truncate text-[11px] text-content-subtle">
          {run.method.toUpperCase()} · {run.base_model}
        </span>
      </span>
      <Badge tone={tone as 'green' | 'red' | 'amber'}>{run.status}</Badge>
    </li>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <p className="px-1 py-3 text-center text-xs text-content-subtle">{children}</p>;
}
