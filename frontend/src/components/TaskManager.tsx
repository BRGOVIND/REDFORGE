/**
 * Global Task Manager — the app-wide execution surface (like Docker Desktop).
 *
 * ONE source of truth: it polls `/api/tasks`, which projects the backend Job System.
 * There is no page-specific progress state here — every long-running operation that
 * runs as a Job appears automatically. Provides:
 *   • TaskManagerProvider — polling + transition toasts + panel open-state (context)
 *   • TaskBarButton        — the top-bar "Running (N)" indicator
 *   • TaskPanel            — the slide-over panel (active + history, cancel/retry/logs/delete)
 */
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react';
import { Activity, ChevronRight, RotateCw, Trash2, X, XCircle } from 'lucide-react';
import * as api from '../api/endpoints';
import type { Task, TaskSummary } from '../api/types';
import { useQuery } from '../lib/query';
import { queryClient } from '../lib/query';
import { toast } from '../lib/toast';
import { cn } from '../lib/cn';

const ACTIVE = new Set(['running', 'queued', 'paused']);
const EMPTY_SUMMARY: TaskSummary = {
  running: 0, queued: 0, paused: 0, active: 0, failed: 0, completed: 0, by_status: {},
};

interface TaskCtx {
  tasks: Task[];
  summary: TaskSummary;
  open: boolean;
  setOpen: (b: boolean) => void;
  cancel: (id: string) => void;
  retry: (id: string) => void;
  remove: (id: string) => void;
  refetch: () => void;
}

const Ctx = createContext<TaskCtx | null>(null);
export const useTaskManager = () => {
  const c = useContext(Ctx);
  if (!c) throw new Error('useTaskManager must be used within TaskManagerProvider');
  return c;
};

// --- time formatting -------------------------------------------------------
function fmtDuration(sec?: number | null): string {
  if (sec == null || !isFinite(sec) || sec < 0) return '—';
  const s = Math.round(sec);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  if (m < 60) return `${m}m ${rem}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

// --- provider --------------------------------------------------------------
export function TaskManagerProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  // Poll fast while work is active, slowly when idle (visibility-paused by useQuery).
  const prevActiveRef = useRef(false);
  const q = useQuery({
    queryKey: ['tasks'],
    queryFn: () => api.listTasks({ limit: 100 }),
    refetchInterval: prevActiveRef.current ? 1500 : 5000,
    staleTime: 1000,
  });
  const tasks = q.data?.tasks ?? [];
  const summary = q.data?.summary ?? EMPTY_SUMMARY;
  prevActiveRef.current = summary.active > 0;

  const refetch = useCallback(() => queryClient.invalidate(['tasks']), []);

  // Fire toasts on real status transitions (not on the first snapshot).
  const seeded = useRef(false);
  const prev = useRef<Map<string, string>>(new Map());
  useEffect(() => {
    if (!q.data) return;
    const names = (t: Task) => `${t.label}${t.title && t.title !== t.label ? ` · ${t.title}` : ''}`;
    if (!seeded.current) {
      tasks.forEach((t) => prev.current.set(t.id, t.status));
      seeded.current = true;
      return;
    }
    const seen = new Set<string>();
    for (const t of tasks) {
      seen.add(t.id);
      const was = prev.current.get(t.id);
      if (was === t.status) continue;
      prev.current.set(t.id, t.status);
      if (was === undefined) {
        if (t.status === 'running') toast.info('Task started', names(t));
        else if (t.status === 'queued') toast.info('Task waiting', names(t));
        continue;
      }
      if (t.status === 'running' && was === 'queued') toast.info('Task started', names(t));
      else if (t.status === 'completed') toast.success('Task completed', names(t));
      else if (t.status === 'failed') toast.error('Task failed', t.error || names(t));
      else if (t.status === 'cancelled') toast.info('Task cancelled', names(t));
      else if (t.status === 'queued') toast.info('Task waiting', names(t));
    }
    for (const id of [...prev.current.keys()]) if (!seen.has(id)) prev.current.delete(id);
  }, [q.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const cancel = useCallback((id: string) => { void api.cancelTask(id).then(refetch); }, [refetch]);
  const retry = useCallback((id: string) => { void api.retryTask(id).then(refetch); }, [refetch]);
  const remove = useCallback((id: string) => { void api.deleteTask(id).then(refetch); }, [refetch]);

  const value = useMemo<TaskCtx>(
    () => ({ tasks, summary, open, setOpen, cancel, retry, remove, refetch }),
    [tasks, summary, open, cancel, retry, remove, refetch],
  );
  return (
    <Ctx.Provider value={value}>
      {children}
      <TaskPanel />
    </Ctx.Provider>
  );
}

// --- top-bar indicator -----------------------------------------------------
export function TaskBarButton() {
  const { summary, setOpen } = useTaskManager();
  const running = summary.running;
  const active = summary.active;
  const failed = summary.failed;
  return (
    <button
      onClick={() => setOpen(true)}
      className={cn(
        'flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[12px] transition-colors rf-focus',
        active > 0 ? 'text-content hover:border-border-strong' : 'text-content-muted hover:border-border-strong',
      )}
      title="Open the task panel"
    >
      <Activity size={13} className={active > 0 ? 'text-red-400' : ''} />
      {active > 0 ? (
        <span className="flex items-center gap-1">
          {running > 0 && <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-red-500" />}
          Running ({active})
        </span>
      ) : (
        <span>Tasks</span>
      )}
      {failed > 0 && (
        <span className="ml-0.5 rounded bg-fail/15 px-1 text-[10px] font-medium text-fail">{failed}</span>
      )}
    </button>
  );
}

// --- panel -----------------------------------------------------------------
const STATUS_TONE: Record<string, string> = {
  running: 'text-red-400', queued: 'text-content-muted', paused: 'text-uncertain',
  completed: 'text-pass', failed: 'text-fail', cancelled: 'text-content-subtle',
  interrupted: 'text-uncertain',
};

function LiveElapsed({ task }: { task: Task }) {
  const [, tick] = useState(0);
  useEffect(() => {
    if (task.status !== 'running') return;
    const id = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [task.status]);
  const elapsed =
    task.status === 'running' && task.started_at
      ? (Date.now() - Date.parse(task.started_at)) / 1000
      : task.elapsed_seconds ?? undefined;
  return <span>{fmtDuration(elapsed)}</span>;
}

function TaskRow({ task }: { task: Task }) {
  const { cancel, retry, remove } = useTaskManager();
  const [showLogs, setShowLogs] = useState(false);
  const isActive = ACTIVE.has(task.status);
  return (
    <div className="rounded-lg border border-border bg-base p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-content">{task.label}</p>
          <p className="truncate text-[11px] text-content-subtle">{task.title}</p>
        </div>
        <span className={cn('shrink-0 text-[11px] font-medium capitalize', STATUS_TONE[task.status])}>
          {task.status}
        </span>
      </div>

      {isActive && (
        <div className="mt-2">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-overlay">
            <div
              className={cn('h-full rounded-full transition-[width] duration-500',
                task.status === 'running' ? 'bg-red-500' : 'bg-content-faint')}
              style={{ width: `${Math.max(2, task.progress)}%` }}
            />
          </div>
          <div className="mt-1 flex items-center justify-between text-[11px] text-content-subtle">
            <span className="truncate">{task.current_step || `${task.progress}%`}</span>
            <span className="shrink-0 tabular-nums">
              {task.progress}% · <LiveElapsed task={task} />
              {task.eta_seconds != null && task.status === 'running' && <> · ETA {fmtDuration(task.eta_seconds)}</>}
            </span>
          </div>
        </div>
      )}

      {!isActive && (task.error || task.status === 'completed') && (
        <p className={cn('mt-1.5 truncate text-[11px]', task.status === 'failed' ? 'text-fail' : 'text-content-subtle')}>
          {task.error || `Completed in ${fmtDuration(task.elapsed_seconds)}`}
        </p>
      )}

      <div className="mt-2 flex items-center gap-1.5">
        {task.cancellable && (
          <button onClick={() => cancel(task.id)}
            className="flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[11px] text-content-subtle hover:text-fail rf-focus">
            <XCircle size={11} /> Cancel
          </button>
        )}
        {task.retryable && (
          <button onClick={() => retry(task.id)}
            className="flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[11px] text-content-subtle hover:text-content rf-focus">
            <RotateCw size={11} /> Retry
          </button>
        )}
        {(task.logs_tail?.length ?? 0) > 0 && (
          <button onClick={() => setShowLogs((s) => !s)}
            className="rounded border border-border px-1.5 py-0.5 text-[11px] text-content-subtle hover:text-content rf-focus">
            Logs
          </button>
        )}
        {!isActive && (
          <button onClick={() => remove(task.id)}
            className="ml-auto rounded border border-border px-1.5 py-0.5 text-[11px] text-content-subtle hover:text-fail rf-focus"
            title="Delete from history">
            <Trash2 size={11} />
          </button>
        )}
      </div>

      {showLogs && (
        <pre className="mt-2 max-h-40 overflow-auto rounded bg-surface p-2 text-[10px] leading-relaxed text-content-muted">
          {(task.logs_tail ?? []).join('\n') || 'No logs.'}
        </pre>
      )}
    </div>
  );
}

export function TaskPanel() {
  const { tasks, summary, open, setOpen } = useTaskManager();
  const active = tasks.filter((t) => ACTIVE.has(t.status));
  const history = tasks.filter((t) => !ACTIVE.has(t.status)).slice(0, 40);

  if (!open) return null;
  return (
    <>
      <div className="fixed inset-0 z-[90] bg-black/30" onClick={() => setOpen(false)} aria-hidden />
      <aside className="fixed right-0 top-0 z-[95] flex h-screen w-[380px] max-w-[calc(100vw-1rem)] flex-col border-l border-border bg-surface shadow-2xl shadow-black/40">
        <header className="flex h-11 shrink-0 items-center justify-between border-b border-border px-4">
          <div className="flex items-center gap-2 text-[13px] font-medium text-content">
            <Activity size={15} /> Tasks
            {summary.active > 0 && (
              <span className="rounded bg-red-soft px-1.5 text-[11px] text-content">{summary.active} running</span>
            )}
          </div>
          <button onClick={() => setOpen(false)} className="rounded p-1 text-content-subtle hover:text-content rf-focus" aria-label="Close">
            <X size={16} />
          </button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto p-3">
          <section>
            <p className="mb-1.5 flex items-center gap-1 px-1 text-[10px] font-semibold uppercase tracking-wider text-content-faint">
              Active {active.length > 0 && <span className="text-content-subtle">({active.length})</span>}
            </p>
            {active.length === 0 ? (
              <p className="px-1 py-6 text-center text-[12px] text-content-subtle">No active tasks.</p>
            ) : (
              <div className="space-y-2">{active.map((t) => <TaskRow key={t.id} task={t} />)}</div>
            )}
          </section>

          {history.length > 0 && (
            <section>
              <p className="mb-1.5 flex items-center gap-1 px-1 text-[10px] font-semibold uppercase tracking-wider text-content-faint">
                <ChevronRight size={11} /> History
              </p>
              <div className="space-y-2">{history.map((t) => <TaskRow key={t.id} task={t} />)}</div>
            </section>
          )}
        </div>
      </aside>
    </>
  );
}
