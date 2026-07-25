import { useEffect, useState } from 'react';
import { Activity, Play, RotateCcw, ScrollText, X, XCircle } from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Progress,
  Skeleton,
} from '../components/ui';
import {
  useCancelJob,
  useJobLogs,
  useJobTypes,
  useJobs,
  useRetryJob,
  useSubmitJob,
} from '../hooks/queries';
import { toast } from '../lib/toast';
import type { Job } from '../api/types';

const STATUS_TONE: Record<string, 'green' | 'red' | 'amber' | 'grey'> = {
  completed: 'green',
  running: 'amber',
  failed: 'red',
  queued: 'grey',
  cancelled: 'grey',
  interrupted: 'amber',
  paused: 'amber',
};

const ACTIVE = new Set(['queued', 'running', 'paused']);

export default function JobsPage() {
  const [pollMs, setPollMs] = useState(0);
  const jobs = useJobs(undefined, pollMs);
  const list = jobs.data ?? [];
  const active = list.some((j) => ACTIVE.has(j.status));
  useEffect(() => setPollMs(active ? 1500 : 0), [active]);

  const [logsFor, setLogsFor] = useState<string | null>(null);

  const running = list.filter((j) => j.status === 'running' || j.status === 'paused');
  const queued = list.filter((j) => j.status === 'queued');
  const finished = list.filter((j) => !ACTIVE.has(j.status));

  return (
    <div>
      <PageHeader
        title="Jobs"
        description="The unified execution platform — every long-running task (training, export, benchmark, evaluation, security, imports) runs as a tracked, cancellable, recoverable Job."
        actions={<SubmitJob />}
      />

      {/* Queue summary */}
      <div className="mb-4 grid grid-cols-3 gap-3">
        <Stat label="Running" value={running.length} tone="amber" />
        <Stat label="Queued" value={queued.length} />
        <Stat label="Completed" value={list.filter((j) => j.status === 'completed').length} tone="green" />
      </div>

      {jobs.isLoading ? (
        <Skeleton className="h-40" />
      ) : list.length === 0 ? (
        <Card className="p-4">
          <EmptyState
            icon={<Activity size={24} />}
            title="No jobs yet"
            description="Submit a job above (e.g. model discovery or diagnostics). Future engines will run all their work here."
          />
        </Card>
      ) : (
        <div className="space-y-5">
          {(running.length > 0 || queued.length > 0) && (
            <Section title="Active">
              {[...running, ...queued].map((j) => (
                <JobCard key={j.id} job={j} onLogs={() => setLogsFor(j.id)} />
              ))}
            </Section>
          )}
          {finished.length > 0 && (
            <Section title="History">
              {finished.slice(0, 40).map((j) => (
                <JobCard key={j.id} job={j} onLogs={() => setLogsFor(j.id)} />
              ))}
            </Section>
          )}
        </div>
      )}

      {logsFor && <LogsDrawer jobId={logsFor} onClose={() => setLogsFor(null)} />}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: 'green' | 'amber' }) {
  return (
    <Card className="p-3">
      <p className="text-[11px] text-content-subtle">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${tone === 'green' ? 'text-pass' : tone === 'amber' ? 'text-uncertain' : 'text-content'}`}>
        {value}
      </p>
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-content-subtle">{title}</p>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function JobCard({ job, onLogs }: { job: Job; onLogs: () => void }) {
  const cancel = useCancelJob();
  const retry = useRetryJob();
  const isActive = ACTIVE.has(job.status);

  return (
    <Card className="p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {job.status === 'running' && <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-red-500" />}
          <span className="min-w-0">
            <span className="block truncate text-xs font-medium text-content">{job.type}</span>
            <span className="block truncate text-[10px] text-content-subtle">
              {job.id.slice(0, 8)}
              {job.attempts > 1 && ` · attempt ${job.attempts}/${job.max_attempts}`}
              {job.result?.artifact_ids?.length ? ` · ${job.result.artifact_ids.length} artifact(s)` : ''}
            </span>
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Badge tone={STATUS_TONE[job.status] ?? 'grey'}>{job.status}</Badge>
          <button className="rounded p-1 text-content-subtle hover:bg-overlay hover:text-content rf-focus" title="Logs" onClick={onLogs}>
            <ScrollText size={13} />
          </button>
          {isActive && (
            <button
              className="rounded p-1 text-content-subtle hover:text-fail rf-focus"
              title="Cancel"
              onClick={async () => {
                await cancel.mutate(job.id);
                toast.success('Job cancelled');
              }}
            >
              <XCircle size={13} />
            </button>
          )}
          {(job.status === 'failed' || job.status === 'interrupted' || job.status === 'cancelled') && (
            <button
              className="rounded p-1 text-content-subtle hover:text-content rf-focus"
              title="Retry"
              onClick={async () => {
                await retry.mutate(job.id);
                toast.success('Job re-queued');
              }}
            >
              <RotateCcw size={13} />
            </button>
          )}
        </div>
      </div>

      {(job.status === 'running' || job.status === 'paused') && (
        <div className="mt-2">
          <Progress value={job.progress.fraction} />
          <p className="mt-1 text-[10px] text-content-subtle">{job.progress.message || '…'}</p>
        </div>
      )}
      {job.status === 'failed' && job.error && (
        <p className="mt-2 truncate text-[10px] text-fail" title={job.error.message}>{job.error.message}</p>
      )}
    </Card>
  );
}

function SubmitJob() {
  const types = useJobTypes();
  const submit = useSubmitJob();
  const [type, setType] = useState('diagnostics');

  return (
    <div className="flex items-center gap-2">
      <select
        className="rounded-lg border border-border bg-base px-3 py-1.5 text-xs text-content rf-focus"
        value={type}
        onChange={(e) => setType(e.target.value)}
      >
        {(types.data ?? []).map((t) => (
          <option key={t.key} value={t.key}>{t.label}</option>
        ))}
      </select>
      <Button
        size="sm"
        loading={submit.isPending}
        onClick={async () => {
          const res = await submit.mutate({ type });
          if (res) toast.success('Job submitted', `${type} queued`);
        }}
      >
        <Play size={14} /> Submit
      </Button>
    </div>
  );
}

function LogsDrawer({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  const logs = useJobLogs(jobId);
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div className="h-full w-full max-w-md overflow-y-auto border-l border-border bg-surface p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <p className="flex items-center gap-2 text-sm font-semibold text-content">
            <ScrollText size={15} /> Job logs
          </p>
          <button className="rounded p-1 text-content-subtle hover:bg-overlay hover:text-content rf-focus" onClick={onClose}>
            <X size={15} />
          </button>
        </div>
        {logs.isLoading ? (
          <Skeleton className="h-40" />
        ) : (logs.data?.logs ?? []).length === 0 ? (
          <p className="text-xs text-content-subtle">No logs for this job.</p>
        ) : (
          <pre className="whitespace-pre-wrap rounded-lg border border-border bg-base p-3 text-[11px] text-content-muted">
            {(logs.data?.logs ?? []).join('\n')}
          </pre>
        )}
      </div>
    </div>
  );
}
