import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  Cpu,
  HardDrive,
  MonitorCog,
  Plus,
  ShieldCheck,
  Trophy,
} from 'lucide-react';
import { Database, Dumbbell, FolderKanban, Sparkles, Server, Zap } from 'lucide-react';
import { Button, Card, CardHeader, EmptyState, PageHeader, Skeleton, Stat, StatusBadge } from '../components/ui';
import { ScoreDonut } from '../components/shared';
import { useDatasets, useModels, usePlanPreview, useProjects, useProviders, useReport, useSessions, useTrainingRuns } from '../hooks/queries';
import { formatMB, relativeTime, scoreColor, titleCase } from '../lib/format';
import type { SessionResponse } from '../api/types';

function latestCompleted(sessions: SessionResponse[] | undefined): SessionResponse | undefined {
  return sessions?.find((s) => s.status === 'completed' && (s.metadata as any)?.report);
}

export default function DashboardPage() {
  const models = useModels();
  const sessions = useSessions();
  const projects = useProjects(4);
  const datasets = useDatasets();
  const trainingRuns = useTrainingRuns(undefined, 4);
  const providers = useProviders();
  const activeProvider = providers.data?.providers.find((p) => p.is_default);
  const firstModel = models.data?.models?.[0]?.name ?? null;
  // One cached preview call gives us host resource + a cheap system snapshot.
  const preview = usePlanPreview(firstModel ? 'quick_scan' : null, firstModel ? [firstModel] : []);

  const latest = useMemo(() => latestCompleted(sessions.data), [sessions.data]);
  const report = useReport(latest?.id ?? null);
  const score = report.data?.report.security_score.overall ?? null;
  const findings = report.data?.report.findings ?? [];

  const recent = sessions.data?.slice(0, 6) ?? [];
  const resources = preview.data?.resources;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Your local LLM security control center."
        actions={
          <Link to="/new">
            <Button>
              <Plus size={16} />
              New Evaluation
            </Button>
          </Link>
        }
      />

      {/* Top stat row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-5">
          {report.isLoading && latest ? (
            <Skeleton className="h-14 w-full" />
          ) : score != null ? (
            <Stat
              label="Latest Security Score"
              value={<span className={scoreColor(score)}>{Math.round(score)}</span>}
              hint={latest?.selected_models?.[0]}
              icon={<ShieldCheck size={13} />}
            />
          ) : (
            <Stat label="Latest Security Score" value="—" hint="No evaluations yet" icon={<ShieldCheck size={13} />} />
          )}
        </Card>
        <Card className="p-5">
          {models.isLoading ? (
            <Skeleton className="h-14 w-full" />
          ) : (
            <Stat
              label="Installed Models"
              value={models.data?.models?.length ?? 0}
              hint={models.data?.error ? 'runtime offline' : 'via your runtime'}
              icon={<Cpu size={13} />}
            />
          )}
        </Card>
        <Card className="p-5">
          <Stat
            label="Available RAM"
            value={formatMB(resources?.ram_available_mb)}
            hint={resources ? `of ${formatMB(resources.ram_total_mb)}` : undefined}
            icon={<MonitorCog size={13} />}
          />
        </Card>
        <Card className="p-5">
          <Stat
            label="GPU"
            value={resources?.gpu.available ? (resources.gpu.backend ?? 'yes').toUpperCase() : 'CPU only'}
            hint={resources?.gpu.name ?? (resources ? 'no GPU detected' : undefined)}
            icon={<HardDrive size={13} />}
          />
        </Card>
      </div>

      {/* Workspace row (V2): recent projects + active runtime + quick actions */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Recent Projects"
            icon={<FolderKanban size={15} />}
            action={
              <Link to="/studio" className="text-xs text-content-muted hover:text-content rf-focus">
                Open Studio
              </Link>
            }
          />
          <div className="p-2">
            {projects.isLoading ? (
              <div className="space-y-2 p-3">
                {[0, 1].map((i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : (projects.data?.length ?? 0) === 0 ? (
              <div className="p-3">
                <EmptyState
                  icon={<FolderKanban size={24} />}
                  title="No projects yet"
                  description="Create a workspace to organize models, evaluations, and reports."
                  action={
                    <Link to="/studio">
                      <Button size="sm" variant="secondary">
                        <FolderKanban size={14} /> Open Studio
                      </Button>
                    </Link>
                  }
                />
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {projects.data!.map((p) => (
                  <li key={p.id}>
                    <Link
                      to={`/studio`}
                      className="flex items-center justify-between gap-3 rounded-lg px-3 py-3 hover:bg-overlay rf-focus"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-content">{p.name}</p>
                        <p className="truncate text-xs text-content-subtle">
                          {p.models.length} model{p.models.length !== 1 ? 's' : ''} · updated {relativeTime(p.updated_at)}
                        </p>
                      </div>
                      <Sparkles size={14} className="shrink-0 text-content-faint" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>

        <div className="space-y-6">
          <Card className="p-5">
            <Stat
              label="Active Runtime"
              value={activeProvider?.label ?? providers.data?.default ?? '—'}
              hint={
                activeProvider?.health?.online
                  ? 'reachable'
                  : providers.isLoading
                    ? 'checking…'
                    : 'offline / not checked'
              }
              icon={<Server size={13} />}
            />
          </Card>
          <Card className="p-5">
            <Stat
              label="Datasets"
              value={datasets.data?.length ?? 0}
              hint="local dataset assets"
              icon={<Database size={13} />}
            />
          </Card>
          <Card>
            <CardHeader
              title="Recent Training Runs"
              icon={<Dumbbell size={15} />}
              action={
                <Link to="/training" className="text-xs text-content-muted hover:text-content rf-focus">
                  Open Training Lab
                </Link>
              }
            />
            <div className="p-2">
              {(trainingRuns.data?.length ?? 0) === 0 ? (
                <p className="px-3 py-4 text-center text-xs text-content-subtle">
                  No training runs yet.
                </p>
              ) : (
                <ul className="divide-y divide-border">
                  {trainingRuns.data!.map((r) => (
                    <li key={r.id}>
                      <Link
                        to="/training"
                        className="flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 hover:bg-overlay rf-focus"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-content">{r.name}</p>
                          <p className="truncate text-[11px] text-content-subtle">
                            {r.method.toUpperCase()} · {r.base_model}
                          </p>
                        </div>
                        <StatusBadge status={r.status} />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
          <Card className="p-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-content-subtle">Quick Actions</p>
            <div className="grid grid-cols-2 gap-2">
              <Link to="/playground">
                <Button variant="secondary" size="sm" className="w-full">
                  <Sparkles size={14} /> Playground
                </Button>
              </Link>
              <Link to="/datasets">
                <Button variant="secondary" size="sm" className="w-full">
                  <Database size={14} /> Datasets
                </Button>
              </Link>
              <Link to="/training">
                <Button variant="secondary" size="sm" className="w-full">
                  <Dumbbell size={14} /> Train
                </Button>
              </Link>
              <Link to="/new">
                <Button variant="secondary" size="sm" className="w-full">
                  <Zap size={14} /> Evaluate
                </Button>
              </Link>
            </div>
          </Card>
        </div>
      </div>

      {/* Main grid */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Recent evaluations */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Recent Evaluations"
            icon={<Activity size={15} />}
            action={
              <Link to="/history" className="text-xs text-content-muted hover:text-content rf-focus">
                View all
              </Link>
            }
          />
          <div className="p-2">
            {sessions.isLoading ? (
              <div className="space-y-2 p-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : recent.length === 0 ? (
              <div className="p-3">
                <EmptyState
                  title="No evaluations yet"
                  description="Start your first evaluation to see it here."
                  action={
                    <Link to="/new">
                      <Button size="sm" variant="secondary">
                        <Plus size={14} /> New Evaluation
                      </Button>
                    </Link>
                  }
                />
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {recent.map((s) => {
                  const isDone = s.status === 'completed';
                  const to = isDone ? `/reports/${s.id}` : `/live/${s.id}`;
                  return (
                    <li key={s.id}>
                      <Link
                        to={to}
                        className="flex items-center justify-between gap-3 rounded-lg px-3 py-3 hover:bg-overlay rf-focus"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-content">
                            {s.selected_models.join(', ') || 'Evaluation'}
                          </p>
                          <p className="text-xs text-content-subtle">
                            {titleCase(s.selected_tier ?? s.session_type)} ·{' '}
                            {s.completed_tasks}/{s.total_tasks} tasks · {relativeTime(s.created_at)}
                          </p>
                        </div>
                        <StatusBadge status={s.status} />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </Card>

        {/* Latest score + findings */}
        <div className="space-y-6">
          <Card className="flex flex-col items-center p-6">
            {score != null ? (
              <>
                <ScoreDonut score={score} />
                <p className="mt-3 text-sm font-medium text-content">
                  {latest?.selected_models?.[0]}
                </p>
                <p className="text-xs text-content-subtle">{report.data?.report.security_score.risk_band} security</p>
              </>
            ) : (
              <EmptyState
                icon={<ShieldCheck size={26} />}
                title="No score yet"
                description="Run an evaluation to generate a security score."
              />
            )}
          </Card>

          <Card>
            <CardHeader title="Latest Findings" />
            <div className="p-3">
              {findings.length === 0 ? (
                <p className="px-2 py-4 text-center text-xs text-content-subtle">
                  No findings — nothing to report.
                </p>
              ) : (
                <ul className="space-y-2">
                  {findings.slice(0, 4).map((f) => (
                    <li key={f.id} className="flex items-center justify-between gap-2 px-2 py-1.5">
                      <span className="truncate text-sm text-content">{f.title}</span>
                      <span className="shrink-0 text-xs font-medium capitalize text-fail">
                        {f.severity}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>

          <Card className="p-4">
            <div className="flex gap-2">
              <Link to="/leaderboard" className="flex-1">
                <Button variant="secondary" size="sm" className="w-full">
                  <Trophy size={14} /> Leaderboard
                </Button>
              </Link>
              <Link to="/new" className="flex-1">
                <Button size="sm" className="w-full">
                  <Plus size={14} /> Evaluate
                </Button>
              </Link>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
