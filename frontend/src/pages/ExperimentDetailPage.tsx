/**
 * Experiment dashboard (RedForge V3, Epic 4).
 *
 * The full workspace for a single line of inquiry: configuration + reproducibility
 * snapshot, live metrics, and tabbed panels for the auto-populated timeline,
 * referenced artifacts, jobs, and Markdown notes. Actions: clone, re-snapshot,
 * conclude, archive, delete.
 */
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Activity,
  ArrowLeft,
  Camera,
  CheckCircle2,
  Clock,
  Copy,
  FileText,
  GitBranch,
  Layers,
  Microscope,
  Tag as TagIcon,
  Trash2,
  X,
} from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Spinner,
  Stat,
  StatusBadge,
} from '../components/ui';
import {
  useAddExperimentNote,
  useCloneExperiment,
  useDeleteExperiment,
  useExperiment,
  useExperimentArtifacts,
  useExperimentJobs,
  useExperimentNotes,
  useExperimentTimeline,
  useSnapshotExperiment,
  useUpdateExperiment,
} from '../hooks/queries';
import { errorMessage } from '../api/client';
import { formatDuration, relativeTime } from '../lib/format';
import { toast } from '../lib/toast';
import type { Experiment } from '../api/types';

const INPUT = 'w-full rounded-lg border border-border bg-base px-3 py-2 text-xs text-content rf-focus';

// A running experiment publishes to its timeline via events — poll lightly.
const POLL = 4_000;

type Tab = 'timeline' | 'artifacts' | 'jobs' | 'notes';

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-border bg-surface p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <p className="text-sm font-semibold text-content">{title}</p>
          <button className="rounded p-1 text-content-subtle hover:bg-overlay hover:text-content rf-focus" onClick={onClose} aria-label="Close">
            <X size={15} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// --- Clone dialog ----------------------------------------------------------

function CloneDialog({ exp, onClose, onCloned }: { exp: Experiment; onClose: () => void; onCloned: (e: Experiment) => void }) {
  const [name, setName] = useState(`${exp.name} (clone)`);
  const [includeNotes, setIncludeNotes] = useState(false);
  const clone = useCloneExperiment();

  const submit = async () => {
    try {
      const created = await clone.mutate({ id: exp.id, body: { name: name.trim() || undefined, include_notes: includeNotes } });
      if (created) {
        toast.success('Experiment cloned', created.name);
        onCloned(created);
      }
    } catch (err) {
      toast.error('Clone failed', errorMessage(err));
    }
  };

  return (
    <Modal title="Clone experiment" onClose={onClose}>
      <p className="mb-4 text-xs text-content-subtle">
        A clone copies the configuration, subject references, and tags into a fresh line of inquiry. Artifacts are
        referenced from the parent, never duplicated.
      </p>
      <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-content-subtle">New name</label>
      <input className={INPUT} value={name} autoFocus onChange={(e) => setName(e.target.value)} />
      <label className="mt-3 flex items-center gap-2 text-xs text-content">
        <input type="checkbox" checked={includeNotes} onChange={(e) => setIncludeNotes(e.target.checked)} className="accent-red-600" />
        Copy notes as well
      </label>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button size="sm" onClick={submit} disabled={clone.isPending}>
          {clone.isPending ? 'Cloning…' : 'Clone'}
        </Button>
      </div>
    </Modal>
  );
}

// --- Panels ----------------------------------------------------------------

function TimelinePanel({ id }: { id: string }) {
  const timeline = useExperimentTimeline(id, POLL);
  const events = timeline.data ?? [];
  if (timeline.isLoading) return <Spinner label="Loading timeline…" />;
  if (events.length === 0) return <EmptyState icon={<Clock size={26} />} title="No activity yet" description="Training, exports, and artifacts appear here automatically." />;
  return (
    <ol className="relative ml-2 space-y-4 border-l border-border pl-5">
      {events.map((e) => (
        <li key={e.id} className="relative">
          <span className="absolute -left-[27px] top-1 h-2.5 w-2.5 rounded-full border-2 border-surface bg-red-500" />
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-sm text-content">{e.title}</p>
            <span className="shrink-0 text-[11px] text-content-faint">{relativeTime(e.at)}</span>
          </div>
          <div className="mt-0.5 flex items-center gap-2">
            <Badge tone={e.source === 'user' ? 'grey' : 'neutral'}>{e.kind}</Badge>
          </div>
        </li>
      ))}
    </ol>
  );
}

function ArtifactsPanel({ id }: { id: string }) {
  const navigate = useNavigate();
  const artifacts = useExperimentArtifacts(id, POLL);
  const list = artifacts.data ?? [];
  if (artifacts.isLoading) return <Spinner label="Loading artifacts…" />;
  if (list.length === 0) return <EmptyState icon={<Layers size={26} />} title="No artifacts yet" description="Checkpoints, adapters, and exports produced under this experiment are referenced here." />;
  return (
    <div className="divide-y divide-border/60">
      {list.map((a) => (
        <button
          key={a.id}
          className="flex w-full items-center justify-between gap-3 py-2.5 text-left hover:bg-overlay/40 rf-focus"
          onClick={() => navigate(`/artifacts/${a.id}`)}
        >
          <div className="flex min-w-0 items-center gap-2">
            <Layers size={14} className="shrink-0 text-content-muted" />
            <span className="truncate text-sm text-content">{a.name}</span>
            <Badge tone="grey">{a.type}</Badge>
          </div>
          <span className="shrink-0 text-[11px] text-content-faint">{relativeTime(a.created_at)}</span>
        </button>
      ))}
    </div>
  );
}

function JobsPanel({ id }: { id: string }) {
  const jobs = useExperimentJobs(id, POLL);
  const list = jobs.data ?? [];
  if (jobs.isLoading) return <Spinner label="Loading jobs…" />;
  if (list.length === 0) return <EmptyState icon={<Activity size={26} />} title="No jobs yet" description="Training and export jobs launched for this experiment appear here." />;
  return (
    <div className="divide-y divide-border/60">
      {list.map((j) => (
        <div key={j.job_id} className="flex items-center justify-between gap-3 py-2.5">
          <div className="flex min-w-0 items-center gap-2">
            <Activity size={14} className="shrink-0 text-content-muted" />
            <span className="truncate font-mono text-xs text-content">{j.job_type || 'job'}</span>
            <span className="truncate text-[11px] text-content-faint">{j.job_id.slice(0, 8)}</span>
          </div>
          <StatusBadge status={j.status || 'pending'} />
        </div>
      ))}
    </div>
  );
}

function NotesPanel({ id }: { id: string }) {
  const notes = useExperimentNotes(id);
  const add = useAddExperimentNote();
  const [body, setBody] = useState('');
  const list = notes.data ?? [];

  const submit = async () => {
    if (!body.trim()) return;
    try {
      await add.mutate({ id, body: body.trim() });
      setBody('');
    } catch (err) {
      toast.error('Could not add note', errorMessage(err));
    }
  };

  return (
    <div>
      <div className="mb-4">
        <textarea
          className={`${INPUT} min-h-[72px] resize-y`}
          value={body}
          placeholder="Add a note (Markdown supported)…"
          onChange={(e) => setBody(e.target.value)}
        />
        <div className="mt-2 flex justify-end">
          <Button size="sm" onClick={submit} disabled={add.isPending || !body.trim()}>
            {add.isPending ? 'Saving…' : 'Add note'}
          </Button>
        </div>
      </div>
      {list.length === 0 ? (
        <EmptyState icon={<FileText size={26} />} title="No notes yet" />
      ) : (
        <div className="space-y-3">
          {list.map((n) => (
            <Card key={n.id} className="p-3">
              <p className="whitespace-pre-wrap text-sm text-content">{n.body}</p>
              <p className="mt-2 text-[11px] text-content-faint">{relativeTime(n.created_at)}</p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Tags editor -----------------------------------------------------------

function TagsRow({ exp }: { exp: Experiment }) {
  const update = useUpdateExperiment();
  const [input, setInput] = useState('');
  const [editing, setEditing] = useState(false);

  const save = async (tags: string[]) => {
    try {
      await update.mutate({ id: exp.id, body: { tags } });
    } catch (err) {
      toast.error('Could not update tags', errorMessage(err));
    }
  };
  const add = () => {
    const t = input.trim();
    if (t && !exp.tags.includes(t)) save([...exp.tags, t]);
    setInput('');
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <TagIcon size={13} className="text-content-subtle" />
      {exp.tags.map((t) => (
        <Badge key={t} tone="grey">
          {t}
          <button className="ml-0.5 hover:text-content" onClick={() => save(exp.tags.filter((x) => x !== t))}>
            <X size={11} />
          </button>
        </Badge>
      ))}
      {editing ? (
        <input
          className="h-6 w-32 rounded-md border border-border bg-base px-2 text-xs text-content rf-focus"
          value={input}
          autoFocus
          placeholder="tag + Enter"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') add();
            if (e.key === 'Escape') setEditing(false);
          }}
          onBlur={() => setEditing(false)}
        />
      ) : (
        <button className="text-[11px] text-content-subtle hover:text-content" onClick={() => setEditing(true)}>
          + add tag
        </button>
      )}
    </div>
  );
}

// --- Page ------------------------------------------------------------------

export default function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('timeline');
  const [cloneOpen, setCloneOpen] = useState(false);

  const experiment = useExperiment(id ?? null, POLL);
  const update = useUpdateExperiment();
  const snapshot = useSnapshotExperiment();
  const del = useDeleteExperiment();
  const exp = experiment.data;

  const metrics = useMemo(() => {
    const m = (exp?.metrics ?? {}) as Record<string, unknown>;
    return {
      finalLoss: typeof m.final_loss === 'number' ? m.final_loss : null,
      duration: typeof m.training_duration_seconds === 'number' ? m.training_duration_seconds : null,
    };
  }, [exp]);

  if (experiment.isLoading) return <Spinner label="Loading experiment…" />;
  if (experiment.isError || !exp)
    return <ErrorState message={experiment.error ? errorMessage(experiment.error) : 'Experiment not found'} onRetry={experiment.refetch} />;

  const setStatus = async (status: string) => {
    try {
      await update.mutate({ id: exp.id, body: { status } });
      toast.success(`Experiment ${status}`);
    } catch (err) {
      toast.error('Could not update status', errorMessage(err));
    }
  };
  const doSnapshot = async () => {
    try {
      await snapshot.mutate(exp.id);
      toast.success('Snapshot captured');
    } catch (err) {
      toast.error('Snapshot failed', errorMessage(err));
    }
  };
  const doDelete = async () => {
    try {
      await del.mutate(exp.id);
      toast.success('Experiment deleted');
      navigate('/experiments');
    } catch (err) {
      toast.error('Delete failed', errorMessage(err));
    }
  };

  const snap = exp.snapshot;
  const est = (snap?.resource_estimate ?? {}) as Record<string, unknown>;

  return (
    <div>
      {/* Header */}
      <button className="mb-3 flex items-center gap-1.5 text-xs text-content-subtle hover:text-content" onClick={() => navigate('/experiments')}>
        <ArrowLeft size={14} /> Experiments
      </button>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <Microscope size={20} className="text-red-400" />
            <h1 className="truncate text-xl font-semibold tracking-tight text-content">{exp.name}</h1>
            <StatusBadge status={exp.status} />
            {exp.parent_experiment_id && (
              <button
                className="flex items-center gap-1 text-[11px] text-content-subtle hover:text-content"
                onClick={() => navigate(`/experiments/${exp.parent_experiment_id}`)}
                title="Open parent experiment"
              >
                <GitBranch size={11} /> from parent
              </button>
            )}
          </div>
          {exp.description && <p className="mt-1.5 max-w-2xl text-sm text-content-muted">{exp.description}</p>}
          <div className="mt-3">
            <TagsRow exp={exp} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => setCloneOpen(true)}>
            <Copy size={14} /> Clone
          </Button>
          <Button variant="secondary" size="sm" onClick={doSnapshot} disabled={snapshot.isPending}>
            <Camera size={14} /> Snapshot
          </Button>
          {exp.status !== 'concluded' && (
            <Button variant="secondary" size="sm" onClick={() => setStatus('concluded')}>
              <CheckCircle2 size={14} /> Conclude
            </Button>
          )}
          {exp.status !== 'archived' && (
            <Button variant="ghost" size="sm" onClick={() => setStatus('archived')}>
              Archive
            </Button>
          )}
          <Button variant="danger" size="sm" onClick={doDelete} disabled={del.isPending}>
            <Trash2 size={14} />
          </Button>
        </div>
      </div>

      {/* Metrics */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card className="p-4">
          <Stat label="Final loss" value={metrics.finalLoss != null ? metrics.finalLoss.toFixed(4) : '—'} />
        </Card>
        <Card className="p-4">
          <Stat label="Train duration" value={metrics.duration != null ? formatDuration(metrics.duration) : '—'} />
        </Card>
        <Card className="p-4">
          <Stat label="Strategy" value={<span className="text-lg">{exp.configuration.strategy}</span>} />
        </Card>
        <Card className="p-4">
          <Stat label="Provider" value={<span className="text-lg">{exp.configuration.provider ?? '—'}</span>} />
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left: config + snapshot */}
        <div className="space-y-6">
          <Card>
            <CardHeader title="Configuration" icon={<Microscope size={15} />} />
            <dl className="divide-y divide-border/60 px-5 py-1 text-sm">
              {[
                ['Base model', exp.configuration.base_model || '—'],
                ['Foundation model', exp.configuration.foundation_model_id ?? '—'],
                ['Dataset', exp.configuration.dataset_id ?? '—'],
                ['Strategy', exp.configuration.strategy],
                ['Provider', exp.configuration.provider ?? '—'],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between gap-3 py-2">
                  <dt className="text-content-subtle">{k}</dt>
                  <dd className="truncate text-right text-content">{v}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card>
            <CardHeader
              title="Reproducibility snapshot"
              subtitle={snap?.captured_at ? `Captured ${relativeTime(snap.captured_at)}` : 'Not captured'}
              icon={<Camera size={15} />}
            />
            <div className="px-5 py-3 text-sm">
              {snap ? (
                <dl className="divide-y divide-border/60">
                  {[
                    ['RedForge', snap.redforge_version || '—'],
                    ['Python', String((snap.platform as Record<string, unknown>)?.python ?? '—')],
                    ['System', String((snap.platform as Record<string, unknown>)?.system ?? '—')],
                    ['Dataset hash', snap.dataset_content_hash ? snap.dataset_content_hash.slice(0, 12) : '—'],
                    ['Est. VRAM', est.vram_mb ? `${est.vram_mb} MB` : '—'],
                    ['GPU', String((snap.gpu as Record<string, unknown>)?.name ?? 'none detected')],
                  ].map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between gap-3 py-2">
                      <dt className="text-content-subtle">{k}</dt>
                      <dd className="truncate text-right font-mono text-xs text-content">{v}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="py-2 text-xs text-content-subtle">No snapshot captured yet.</p>
              )}
            </div>
          </Card>
        </div>

        {/* Right: tabbed panels */}
        <div className="lg:col-span-2">
          <Card>
            <div className="flex items-center gap-1 border-b border-border px-3 py-2">
              {(
                [
                  ['timeline', 'Timeline', <Clock size={14} key="t" />],
                  ['artifacts', 'Artifacts', <Layers size={14} key="a" />],
                  ['jobs', 'Jobs', <Activity size={14} key="j" />],
                  ['notes', 'Notes', <FileText size={14} key="n" />],
                ] as [Tab, string, React.ReactNode][]
              ).map(([key, label, icon]) => (
                <button
                  key={key}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs transition-colors ${
                    tab === key ? 'bg-overlay text-content' : 'text-content-subtle hover:text-content'
                  }`}
                  onClick={() => setTab(key)}
                >
                  {icon}
                  {label}
                </button>
              ))}
            </div>
            <div className="p-5">
              {tab === 'timeline' && <TimelinePanel id={exp.id} />}
              {tab === 'artifacts' && <ArtifactsPanel id={exp.id} />}
              {tab === 'jobs' && <JobsPanel id={exp.id} />}
              {tab === 'notes' && <NotesPanel id={exp.id} />}
            </div>
          </Card>
        </div>
      </div>

      {cloneOpen && (
        <CloneDialog
          exp={exp}
          onClose={() => setCloneOpen(false)}
          onCloned={(e) => {
            setCloneOpen(false);
            navigate(`/experiments/${e.id}`);
          }}
        />
      )}
    </div>
  );
}
