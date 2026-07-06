import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Ban,
  Brain,
  CheckCircle2,
  ClipboardList,
  FileText,
  Pause,
  Play,
  Shuffle,
  Target,
  UserSearch,
  Zap,
} from 'lucide-react';
import { Button, Card, CardHeader, ErrorState, PageHeader, Progress, Spinner, StatusBadge } from '../components/ui';
import { ScoreDonut, VerdictBadge } from '../components/shared';
import { useSessionStream } from '../hooks/useSessionStream';
import { useTerminalStream } from '../hooks/useTerminalStream';
import { Terminal } from '../components/Terminal';
import { useSessionControl } from '../hooks/queries';
import { toast } from '../lib/toast';
import { formatDuration, formatTime, titleCase } from '../lib/format';
import { cn } from '../lib/cn';
import type { EvaluationEvent } from '../api/types';

const STAGES = [
  { key: 'created', label: 'Created', event: 'session_created', icon: <ClipboardList size={14} /> },
  { key: 'profiled', label: 'Profiler', event: 'model_profiled', icon: <UserSearch size={14} /> },
  { key: 'planned', label: 'Planner', event: 'plan_generated', icon: <Brain size={14} /> },
  { key: 'execution', label: 'Execution', event: 'attack_started', icon: <Target size={14} /> },
  { key: 'analysis', label: 'Analysis', event: 'analysis_completed', icon: <Zap size={14} /> },
  { key: 'report', label: 'Report', event: 'report_generated', icon: <FileText size={14} /> },
] as const;

function StageTimeline({ events, done }: { events: Set<string>; done: boolean }) {
  const reached = STAGES.map((s) => events.has(s.event));
  // Current = first not-yet-reached stage (or all done).
  const currentIdx = reached.findIndex((r) => !r);
  return (
    <div className="flex items-center gap-1 overflow-x-auto">
      {STAGES.map((s, i) => {
        const isDone = reached[i] || done;
        const isCurrent = i === currentIdx && !done;
        return (
          <div key={s.key} className="flex items-center">
            <div
              className={cn(
                'flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs whitespace-nowrap',
                isDone
                  ? 'border-pass/30 bg-pass/10 text-pass'
                  : isCurrent
                  ? 'border-red-600 bg-red-soft text-red-400'
                  : 'border-border bg-elevated text-content-subtle'
              )}
            >
              {isCurrent ? <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse-dot" /> : s.icon}
              {s.label}
            </div>
            {i < STAGES.length - 1 && <div className="mx-1 h-px w-4 bg-border" />}
          </div>
        );
      })}
    </div>
  );
}

const EVENT_META: Record<string, { label: string; icon: React.ReactNode }> = {
  session_created: { label: 'Session created', icon: <ClipboardList size={13} /> },
  model_profiled: { label: 'Model profile created', icon: <UserSearch size={13} /> },
  plan_generated: { label: 'Evaluation plan generated', icon: <Brain size={13} /> },
  model_started: { label: 'Model started', icon: <Play size={13} /> },
  attack_started: { label: 'Attack started', icon: <Target size={13} /> },
  attack_retried: { label: 'Retry', icon: <Shuffle size={13} /> },
  mutation_applied: { label: 'Mutation generated', icon: <Shuffle size={13} /> },
  response_received: { label: 'Response received', icon: <Zap size={13} /> },
  verdict_generated: { label: 'Verdict', icon: <CheckCircle2 size={13} /> },
  analysis_completed: { label: 'Analysis completed', icon: <Zap size={13} /> },
  report_generated: { label: 'Report generated', icon: <FileText size={13} /> },
  session_completed: { label: 'Session completed', icon: <CheckCircle2 size={13} /> },
  session_failed: { label: 'Session failed', icon: <Ban size={13} /> },
};

function EventRow({ e }: { e: EvaluationEvent }) {
  const meta = EVENT_META[e.event_type] ?? { label: titleCase(e.event_type), icon: <Zap size={13} /> };
  const md = (e.metadata ?? {}) as Record<string, unknown>;
  const reason = typeof md.reason === 'string' ? md.reason : null;
  const strategy = typeof md.strategy === 'string' ? md.strategy : null;
  const attempt = typeof md.attempt === 'number' ? md.attempt : null;

  return (
    <li className="flex gap-3 px-4 py-2.5 animate-fade-in">
      <span className="mt-0.5 font-mono text-[11px] tabular-nums text-content-faint">
        {formatTime(e.timestamp)}
      </span>
      <span className="mt-0.5 shrink-0 text-content-subtle">{meta.icon}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-medium text-content">{meta.label}</span>
          {e.event_type === 'verdict_generated' && <VerdictBadge verdict={e.verdict} />}
          {e.attack_name && e.event_type !== 'verdict_generated' && (
            <span className="truncate text-xs text-content-muted">{e.attack_name}</span>
          )}
          {strategy && <span className="text-xs text-content-subtle">· {strategy}{attempt ? ` (retry ${attempt})` : ''}</span>}
        </div>
        {reason && <p className="mt-0.5 truncate text-xs text-content-subtle">{reason}</p>}
        {e.category && !reason && (
          <p className="mt-0.5 text-xs text-content-subtle">{e.category}</p>
        )}
      </div>
    </li>
  );
}

export default function LiveSessionPage() {
  const { id } = useParams<{ id: string }>();
  const { session, events, metrics, isDone, error } = useSessionStream(id ?? null);
  const terminal = useTerminalStream(id ?? null);
  const { pause, resume, cancel } = useSessionControl();

  const eventTypes = useMemo(() => new Set(events.map((e) => e.event_type)), [events]);
  // Newest first, windowed; heartbeats belong in the terminal, not the feed.
  const feed = useMemo(
    () => [...events].reverse().filter((e) => e.event_type !== 'heartbeat').slice(0, 150),
    [events]
  );

  const latestFinding = events.find(
    (e) => e.event_type === 'verdict_generated' && e.verdict === 'FAIL'
  );

  if (!id) return null;
  if (error && !session) return <ErrorState message="Could not load session." />;
  if (!session) return <Spinner label="Connecting to session…" />;

  const running = session.status === 'running' || session.status === 'pending';

  const control = async (fn: typeof pause, label: string) => {
    const res = await fn.mutate(id);
    if (res) toast.info(`Session ${label}`);
  };

  return (
    <div>
      <PageHeader
        title="Live Evaluation"
        description={`${session.selected_models.join(', ')} · ${titleCase(session.selected_tier ?? session.session_type)}`}
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge status={session.status} />
            {running && (
              <>
                <Button variant="secondary" size="sm" onClick={() => control(pause, 'paused')} loading={pause.isPending}>
                  <Pause size={14} /> Pause
                </Button>
                <Button variant="danger" size="sm" onClick={() => control(cancel, 'cancelled')} loading={cancel.isPending}>
                  <Ban size={14} /> Cancel
                </Button>
              </>
            )}
            {session.status === 'paused' && (
              <Button variant="secondary" size="sm" onClick={() => control(resume, 'resumed')} loading={resume.isPending}>
                <Play size={14} /> Resume
              </Button>
            )}
            {isDone && session.status === 'completed' && (
              <Link to={`/reports/${id}`}>
                <Button size="sm">
                  <FileText size={14} /> View Report
                </Button>
              </Link>
            )}
          </div>
        }
      />

      {/* Stage timeline */}
      <Card className="mb-6 p-4">
        <StageTimeline events={eventTypes} done={session.status === 'completed'} />
      </Card>

      {/* Progress + score */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-4">
        <Card className="lg:col-span-3 p-5">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-medium text-content">
              {metrics.completed} / {metrics.total} attacks
            </span>
            <span className="text-xs text-content-subtle">
              ETA {formatDuration(metrics.etaSeconds)}
            </span>
          </div>
          <Progress value={metrics.progress} />
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <MiniStat label="Current Model" value={metrics.currentModel ?? '—'} mono />
            <MiniStat label="Current Category" value={metrics.currentCategory ? titleCase(metrics.currentCategory) : '—'} />
            <MiniStat label="Avg Latency" value={metrics.avgLatencyMs ? `${metrics.avgLatencyMs} ms` : '—'} />
            <MiniStat label="Remaining" value={String(metrics.remaining)} />
          </div>
        </Card>
        <Card className="flex flex-col items-center justify-center p-5">
          <ScoreDonut score={metrics.liveScore ?? 100} size={104} label="Live Score" />
        </Card>
      </div>

      {/* Feed + side */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Event Feed"
            icon={<Zap size={15} />}
            action={
              running ? (
                <span className="flex items-center gap-1.5 text-xs text-red-400">
                  <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse-dot" /> live
                </span>
              ) : (
                <span className="text-xs text-content-subtle">{events.length} events</span>
              )
            }
          />
          <div className="max-h-[560px] overflow-y-auto rf-scroll-fade">
            {feed.length === 0 ? (
              <Spinner label="Waiting for events…" />
            ) : (
              <ul className="divide-y divide-border/60">
                {feed.map((e) => (
                  <EventRow key={e.id} e={e} />
                ))}
              </ul>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Current Finding" icon={<Target size={15} />} />
          <div className="p-4">
            {latestFinding ? (
              <div className="space-y-2">
                <VerdictBadge verdict="FAIL" />
                <p className="text-sm font-medium text-content">{latestFinding.attack_name}</p>
                <p className="text-xs text-content-subtle">{titleCase(latestFinding.category ?? '')}</p>
                {typeof (latestFinding.metadata as any)?.reason === 'string' && (
                  <p className="rounded-lg border border-border bg-elevated p-2.5 text-xs text-content-muted">
                    {(latestFinding.metadata as any).reason}
                  </p>
                )}
              </div>
            ) : (
              <p className="py-6 text-center text-xs text-content-subtle">
                No successful attacks yet — the model is holding up.
              </p>
            )}
          </div>
        </Card>
      </div>

      {/* Live terminal — real, streamed backend output */}
      <div className="mt-6">
        <Terminal lines={terminal.lines} live={running} />
      </div>
    </div>
  );
}

function MiniStat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-xs text-content-subtle">{label}</p>
      <p className={cn('mt-0.5 truncate text-sm font-medium text-content', mono && 'font-mono text-[13px]')}>
        {value}
      </p>
    </div>
  );
}
