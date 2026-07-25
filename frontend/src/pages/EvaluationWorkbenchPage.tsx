import { useEffect, useState } from 'react';
import {
  Boxes,
  ChevronDown,
  ChevronRight,
  FileText,
  FlaskConical,
  GitCompare,
  History,
  Play,
  Plus,
  Sparkles,
  Trash2,
  Trophy,
} from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Skeleton,
} from '../components/ui';
import {
  useCollection,
  useCollections,
  useCreateCollection,
  useCreatePrompt,
  useCreatePromptSet,
  useCreateWorkbenchSession,
  useDeleteCollection,
  useDeletePrompt,
  useDeletePromptSet,
  useModels,
  useProjects,
  usePromptSet,
  usePromptVersions,
  useRegisteredModels,
  useSessionRegressions,
  useSessionResults,
  useSimilarityProviders,
  useUpdatePrompt,
  useWorkbenchSession,
  useWorkbenchSessions,
} from '../hooks/queries';
import { toast } from '../lib/toast';
import type { EvaluationResult, Prompt, WorkbenchSession } from '../api/types';

const INPUT =
  'w-full rounded-lg border border-border bg-base px-3 py-2 text-xs text-content placeholder:text-content-faint focus:border-red-500 rf-focus';

const VERDICT_TONE: Record<string, 'green' | 'red' | 'amber' | 'grey'> = {
  pass: 'green', fail: 'red', warn: 'amber', error: 'red', none: 'grey',
};
const SEV_TONE: Record<string, 'red' | 'amber' | 'grey'> = {
  critical: 'red', high: 'red', medium: 'amber', low: 'grey',
};

export default function EvaluationWorkbenchPage() {
  const projects = useProjects();
  const [projectId, setProjectId] = useState<string>('');
  const [activeSetId, setActiveSetId] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [tab, setTab] = useState<'prompts' | 'run' | 'sessions'>('prompts');

  const projectParam = projectId || undefined;

  return (
    <div>
      <PageHeader
        title="Evaluation Workbench"
        description="Prompt engineering, regression testing, and response comparison. Benchmark Center measures how well a model performs — the Workbench validates how it behaves. Everything local."
        actions={
          <select
            className={`${INPUT} w-auto`}
            value={projectId}
            onChange={(e) => {
              setProjectId(e.target.value);
              setActiveSetId(null);
              setActiveSessionId(null);
            }}
          >
            <option value="">All projects</option>
            {(projects.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        }
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[300px_1fr]">
        {/* Collections sidebar */}
        <CollectionsSidebar
          projectId={projectParam}
          activeSetId={activeSetId}
          onSelectSet={(id) => {
            setActiveSetId(id);
            setTab('prompts');
          }}
        />

        {/* Main workspace */}
        <div className="min-w-0 space-y-4">
          <div className="flex items-center gap-1 border-b border-border">
            <Tab active={tab === 'prompts'} onClick={() => setTab('prompts')} icon={<FileText size={14} />} label="Prompts" />
            <Tab active={tab === 'run'} onClick={() => setTab('run')} icon={<Play size={14} />} label="Run" />
            <Tab active={tab === 'sessions'} onClick={() => setTab('sessions')} icon={<History size={14} />} label="Sessions" />
          </div>

          {tab === 'prompts' && <PromptsPanel setId={activeSetId} />}
          {tab === 'run' && (
            <RunPanel
              projectId={projectParam}
              onScheduled={() => setTab('sessions')}
            />
          )}
          {tab === 'sessions' && (
            <SessionsPanel
              projectId={projectParam}
              activeSessionId={activeSessionId}
              onSelect={setActiveSessionId}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function Tab({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-medium rf-focus ${
        active ? 'border-red-500 text-content' : 'border-transparent text-content-subtle hover:text-content'
      }`}
    >
      {icon} {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Collections sidebar (Collections → Prompt Sets)
// ---------------------------------------------------------------------------

function CollectionsSidebar({
  projectId,
  activeSetId,
  onSelectSet,
}: {
  projectId?: string;
  activeSetId: string | null;
  onSelectSet: (id: string) => void;
}) {
  const collections = useCollections(projectId);
  const createCollection = useCreateCollection();
  const [newName, setNewName] = useState('');
  const [adding, setAdding] = useState(false);

  const add = async () => {
    if (!newName.trim()) return;
    const res = await createCollection.mutate({ name: newName.trim(), project_id: projectId });
    if (res) {
      toast.success('Collection created');
      setNewName('');
      setAdding(false);
    }
  };

  return (
    <Card className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">
          <FlaskConical size={13} /> Collections
        </p>
        <button
          className="rounded p-1 text-content-subtle hover:bg-overlay hover:text-content rf-focus"
          onClick={() => setAdding((a) => !a)}
          title="New collection"
        >
          <Plus size={14} />
        </button>
      </div>

      {adding && (
        <div className="mb-2 flex gap-1">
          <input
            className={INPUT}
            placeholder="Collection name"
            value={newName}
            autoFocus
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && add()}
          />
          <Button size="sm" onClick={add} loading={createCollection.isPending}>Add</Button>
        </div>
      )}

      {collections.isLoading ? (
        <Skeleton className="h-24" />
      ) : (collections.data ?? []).length === 0 ? (
        <p className="px-1 py-4 text-center text-xs text-content-subtle">
          No collections yet. Create one to group prompt sets (Coding, Security, RAG…).
        </p>
      ) : (
        <div className="space-y-0.5">
          {(collections.data ?? []).map((c) => (
            <CollectionNode
              key={c.id}
              id={c.id}
              name={c.name}
              category={c.category}
              count={c.prompt_set_count ?? 0}
              projectId={projectId}
              activeSetId={activeSetId}
              onSelectSet={onSelectSet}
            />
          ))}
        </div>
      )}
    </Card>
  );
}

function CollectionNode({
  id,
  name,
  category,
  count,
  projectId,
  activeSetId,
  onSelectSet,
}: {
  id: string;
  name: string;
  category: string;
  count: number;
  projectId?: string;
  activeSetId: string | null;
  onSelectSet: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const detail = useCollection(open ? id : null);
  const createSet = useCreatePromptSet();
  const deleteCollection = useDeleteCollection();
  const deleteSet = useDeletePromptSet();
  const [newTitle, setNewTitle] = useState('');
  const [adding, setAdding] = useState(false);

  const addSet = async () => {
    if (!newTitle.trim()) return;
    const res = await createSet.mutate({ collection_id: id, title: newTitle.trim(), project_id: projectId });
    if (res) {
      setNewTitle('');
      setAdding(false);
      onSelectSet(res.id);
    }
  };

  return (
    <div>
      <div className="group flex items-center gap-1 rounded-md px-1 py-1 hover:bg-overlay/60">
        <button className="flex min-w-0 flex-1 items-center gap-1 text-left rf-focus" onClick={() => setOpen((o) => !o)}>
          {open ? <ChevronDown size={13} className="shrink-0 text-content-faint" /> : <ChevronRight size={13} className="shrink-0 text-content-faint" />}
          <span className="truncate text-xs text-content">{name}</span>
          <Badge tone="grey">{count}</Badge>
        </button>
        <button
          className="opacity-0 group-hover:opacity-100 rounded p-0.5 text-content-faint hover:text-fail rf-focus"
          title="Delete collection"
          onClick={async () => {
            if (await deleteCollection.mutate(id)) toast.success('Collection deleted');
          }}
        >
          <Trash2 size={12} />
        </button>
      </div>

      {open && (
        <div className="ml-4 space-y-0.5 border-l border-border pl-2">
          <p className="pl-1 text-[10px] uppercase tracking-wide text-content-faint">{category}</p>
          {detail.isLoading ? (
            <Skeleton className="h-10" />
          ) : (
            (detail.data?.prompt_sets ?? []).map((s) => (
              <div key={s.id} className="group flex items-center gap-1">
                <button
                  className={`min-w-0 flex-1 truncate rounded px-2 py-1 text-left text-xs rf-focus ${
                    activeSetId === s.id ? 'bg-red-soft text-content' : 'text-content-muted hover:text-content'
                  }`}
                  onClick={() => onSelectSet(s.id)}
                >
                  {s.title}
                  {typeof s.prompt_count === 'number' && (
                    <span className="ml-1 text-content-faint">· {s.prompt_count}</span>
                  )}
                </button>
                <button
                  className="opacity-0 group-hover:opacity-100 rounded p-0.5 text-content-faint hover:text-fail rf-focus"
                  title="Delete prompt set"
                  onClick={async () => {
                    if (await deleteSet.mutate(s.id)) toast.success('Prompt set deleted');
                  }}
                >
                  <Trash2 size={11} />
                </button>
              </div>
            ))
          )}
          {adding ? (
            <div className="flex gap-1 py-1">
              <input
                className={INPUT}
                placeholder="Prompt set title"
                value={newTitle}
                autoFocus
                onChange={(e) => setNewTitle(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addSet()}
              />
              <Button size="sm" onClick={addSet} loading={createSet.isPending}>Add</Button>
            </div>
          ) : (
            <button
              className="flex items-center gap-1 px-2 py-1 text-[11px] text-content-subtle hover:text-content rf-focus"
              onClick={() => setAdding(true)}
            >
              <Plus size={11} /> Prompt set
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Prompts panel (editor + version history)
// ---------------------------------------------------------------------------

function PromptsPanel({ setId }: { setId: string | null }) {
  const set = usePromptSet(setId);
  const [editing, setEditing] = useState<Prompt | 'new' | null>(null);

  if (!setId) {
    return (
      <Card className="p-4">
        <EmptyState icon={<FileText size={24} />} title="Select a prompt set" description="Pick a prompt set from the sidebar to add and edit prompts." />
      </Card>
    );
  }

  const prompts = set.data?.prompts ?? [];

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <p className="flex items-center gap-2 text-sm font-semibold text-content">
            <FileText size={15} /> {set.data?.title ?? 'Prompts'}
            <Badge tone="grey">{prompts.length}</Badge>
          </p>
          <Button size="sm" onClick={() => setEditing('new')}><Plus size={14} /> New prompt</Button>
        </div>
        <div className="p-3">
          {set.isLoading ? (
            <Skeleton className="h-24" />
          ) : prompts.length === 0 ? (
            <p className="px-2 py-4 text-center text-xs text-content-subtle">No prompts yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {prompts.map((p) => (
                <li key={p.id}>
                  <button
                    className="flex w-full items-center justify-between gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-left text-xs hover:border-border-strong rf-focus"
                    onClick={() => setEditing(p)}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-content">{p.title || p.prompt.slice(0, 60) || 'Untitled'}</span>
                      <span className="block truncate text-[11px] text-content-subtle">{p.prompt}</span>
                    </span>
                    <span className="flex shrink-0 items-center gap-1.5">
                      {p.golden_response ? <Badge tone="green">golden</Badge> : p.expected_output ? <Badge tone="amber">expected</Badge> : null}
                      {!p.enabled && <Badge tone="grey">off</Badge>}
                      <span className="text-content-faint">v{p.current_version}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      {editing && (
        <PromptEditor
          setId={setId}
          prompt={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

function PromptEditor({ setId, prompt, onClose }: { setId: string; prompt: Prompt | null; onClose: () => void }) {
  const create = useCreatePrompt();
  const update = useUpdatePrompt();
  const del = useDeletePrompt();
  const versions = usePromptVersions(prompt?.id ?? null);

  const [f, setF] = useState({
    title: prompt?.title ?? '',
    prompt: prompt?.prompt ?? '',
    system_prompt: prompt?.system_prompt ?? '',
    expected_behavior: prompt?.expected_behavior ?? '',
    golden_response: prompt?.golden_response ?? '',
    expected_output: prompt?.expected_output ?? '',
    difficulty: prompt?.difficulty ?? 'normal',
    enabled: prompt?.enabled ?? true,
    min_similarity: prompt?.acceptance_criteria?.min_similarity ?? 60,
    must_include: (prompt?.acceptance_criteria?.must_include ?? []).join(', '),
    require_json: prompt?.acceptance_criteria?.require_json ?? false,
  });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));

  const save = async () => {
    if (!f.prompt.trim()) {
      toast.error('Prompt text is required');
      return;
    }
    const acceptance = {
      min_similarity: Number(f.min_similarity) || 0,
      must_include: f.must_include.split(',').map((s) => s.trim()).filter(Boolean),
      require_json: f.require_json,
    };
    const body = {
      title: f.title, prompt: f.prompt, system_prompt: f.system_prompt,
      expected_behavior: f.expected_behavior, golden_response: f.golden_response,
      expected_output: f.expected_output, difficulty: f.difficulty,
      enabled: f.enabled, acceptance_criteria: acceptance,
    };
    const res = prompt
      ? await update.mutate({ id: prompt.id, body })
      : await create.mutate({ prompt_set_id: setId, ...body });
    if (res) {
      toast.success(prompt ? 'Prompt updated' : 'Prompt created');
      onClose();
    }
  };

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-semibold text-content">{prompt ? 'Edit prompt' : 'New prompt'}</p>
        {prompt && (
          <button
            className="flex items-center gap-1 text-xs text-fail hover:underline rf-focus"
            onClick={async () => {
              if (await del.mutate(prompt.id)) { toast.success('Prompt deleted'); onClose(); }
            }}
          >
            <Trash2 size={13} /> Delete
          </button>
        )}
      </div>

      <div className="grid gap-3">
        <Field label="Title">
          <input className={INPUT} value={f.title} onChange={(e) => set('title', e.target.value)} placeholder="Short label" />
        </Field>
        <Field label="Prompt *">
          <textarea className={`${INPUT} min-h-[70px] font-mono`} value={f.prompt} onChange={(e) => set('prompt', e.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="System prompt">
            <textarea className={`${INPUT} min-h-[52px]`} value={f.system_prompt} onChange={(e) => set('system_prompt', e.target.value)} />
          </Field>
          <Field label="Expected behavior">
            <textarea className={`${INPUT} min-h-[52px]`} value={f.expected_behavior} onChange={(e) => set('expected_behavior', e.target.value)} placeholder="e.g. must refuse, must return JSON…" />
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Golden response (baseline)">
            <textarea className={`${INPUT} min-h-[60px]`} value={f.golden_response} onChange={(e) => set('golden_response', e.target.value)} />
          </Field>
          <Field label="Expected output (loose baseline)">
            <textarea className={`${INPUT} min-h-[60px]`} value={f.expected_output} onChange={(e) => set('expected_output', e.target.value)} />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Min similarity to pass">
            <input type="number" className={INPUT} value={f.min_similarity} onChange={(e) => set('min_similarity', Number(e.target.value))} />
          </Field>
          <Field label="Must include (comma-sep)">
            <input className={INPUT} value={f.must_include} onChange={(e) => set('must_include', e.target.value)} />
          </Field>
          <Field label="Difficulty">
            <select className={INPUT} value={f.difficulty} onChange={(e) => set('difficulty', e.target.value)}>
              <option value="easy">easy</option>
              <option value="normal">normal</option>
              <option value="hard">hard</option>
            </select>
          </Field>
        </div>

        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-xs text-content">
            <input type="checkbox" className="accent-red-500" checked={f.require_json} onChange={(e) => set('require_json', e.target.checked)} />
            Require valid JSON
          </label>
          <label className="flex items-center gap-2 text-xs text-content">
            <input type="checkbox" className="accent-red-500" checked={f.enabled} onChange={(e) => set('enabled', e.target.checked)} />
            Enabled
          </label>
        </div>

        {prompt && (versions.data ?? []).length > 0 && (
          <div className="rounded-lg border border-border bg-base p-2 text-[11px] text-content-subtle">
            <span className="font-medium text-content-muted">Version history:</span>{' '}
            {(versions.data ?? []).map((v) => `v${v.version} (${v.note})`).join(' → ')}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={save} loading={create.isPending || update.isPending}>
            {prompt ? 'Save (new version if changed)' : 'Create prompt'}
          </Button>
        </div>
      </div>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-medium text-content-subtle">{label}</span>
      {children}
    </label>
  );
}

// ---------------------------------------------------------------------------
// Run panel
// ---------------------------------------------------------------------------

function RunPanel({ projectId, onScheduled }: { projectId?: string; onScheduled: () => void }) {
  const collections = useCollections(projectId);
  const models = useModels();
  const registered = useRegisteredModels(projectId ? { project_id: projectId } : undefined);
  const sims = useSimilarityProviders();
  const schedule = useCreateWorkbenchSession();

  const [selSets, setSelSets] = useState<Set<string>>(new Set());
  const [selModels, setSelModels] = useState<Set<string>>(new Set());
  const [selCheckpoints, setSelCheckpoints] = useState<Set<string>>(new Set());
  const [similarity, setSimilarity] = useState('text');
  const [name, setName] = useState('');

  const toggle = (s: Set<string>, setter: (n: Set<string>) => void, k: string) => {
    const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); setter(n);
  };

  const run = async () => {
    if (selSets.size === 0) return toast.error('Select at least one prompt set');
    if (selModels.size === 0 && selCheckpoints.size === 0) return toast.error('Select at least one model or checkpoint');
    const res = await schedule.mutate({
      prompt_set_ids: [...selSets], models: [...selModels], registry_ids: [...selCheckpoints],
      project_id: projectId, similarity, name: name.trim() || undefined,
    });
    if (res) {
      toast.success('Evaluation session scheduled', `${res.total_tasks} evaluation(s) queued`);
      onScheduled();
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-4">
        <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">
          <FileText size={13} /> Prompt sets
        </p>
        {collections.isLoading ? (
          <Skeleton className="h-24" />
        ) : (
          <div className="max-h-64 space-y-2 overflow-y-auto">
            {(collections.data ?? []).map((c) => (
              <PromptSetPicker key={c.id} collectionId={c.id} name={c.name} selSets={selSets} onToggle={(id) => toggle(selSets, setSelSets, id)} />
            ))}
            {(collections.data ?? []).length === 0 && (
              <p className="py-2 text-xs text-content-subtle">No prompt sets. Create them in the Prompts tab.</p>
            )}
          </div>
        )}
      </Card>

      <div className="space-y-4">
        <Card className="p-4">
          <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">
            <Boxes size={13} /> Base models
          </p>
          <div className="max-h-32 space-y-1.5 overflow-y-auto">
            {(models.data?.models ?? []).map((m) => (
              <CheckRow key={m.name} checked={selModels.has(m.name)} onToggle={() => toggle(selModels, setSelModels, m.name)} label={m.name} />
            ))}
            {(models.data?.models ?? []).length === 0 && <p className="py-1 text-xs text-content-subtle">No models available.</p>}
          </div>
        </Card>

        <Card className="p-4">
          <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">
            <Sparkles size={13} /> Checkpoints
          </p>
          <div className="max-h-32 space-y-1.5 overflow-y-auto">
            {(registered.data ?? []).map((c) => (
              <CheckRow key={c.id} checked={selCheckpoints.has(c.id)} onToggle={() => toggle(selCheckpoints, setSelCheckpoints, c.id)} label={c.label} hint={c.fallback ? 'base' : undefined} title={c.runtime_model} />
            ))}
            {(registered.data ?? []).length === 0 && <p className="py-1 text-xs text-content-subtle">No registered checkpoints.</p>}
          </div>
        </Card>

        <Card className="space-y-3 p-4">
          <Field label="Session name (optional)">
            <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Post-retrain regression check" />
          </Field>
          <Field label="Similarity method">
            <select className={INPUT} value={similarity} onChange={(e) => setSimilarity(e.target.value)}>
              {(sims.data ?? []).map((s) => (
                <option key={s.key} value={s.key} disabled={!s.available}>
                  {s.label}{s.available ? '' : ' (unavailable)'}
                </option>
              ))}
            </select>
          </Field>
          <Button className="w-full" onClick={run} loading={schedule.isPending}>
            <Play size={15} /> Run evaluation
          </Button>
        </Card>
      </div>
    </div>
  );
}

function PromptSetPicker({ collectionId, name, selSets, onToggle }: { collectionId: string; name: string; selSets: Set<string>; onToggle: (id: string) => void }) {
  const detail = useCollection(collectionId);
  const sets = detail.data?.prompt_sets ?? [];
  if (sets.length === 0) return null;
  return (
    <div>
      <p className="mb-1 text-[10px] uppercase tracking-wide text-content-faint">{name}</p>
      <div className="space-y-1.5">
        {sets.map((s) => (
          <CheckRow key={s.id} checked={selSets.has(s.id)} onToggle={() => onToggle(s.id)} label={s.title} hint={typeof s.prompt_count === 'number' ? `${s.prompt_count}` : undefined} />
        ))}
      </div>
    </div>
  );
}

function CheckRow({ checked, onToggle, label, hint, title }: { checked: boolean; onToggle: () => void; label: string; hint?: string; title?: string }) {
  return (
    <button
      onClick={onToggle}
      title={title}
      className={`flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-xs rf-focus ${
        checked ? 'border-red-500 bg-red-soft' : 'border-border hover:border-border-strong'
      }`}
    >
      <span className="flex min-w-0 items-center gap-2">
        <span className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border ${checked ? 'border-red-500 bg-red-500 text-white' : 'border-border'}`}>
          {checked && <span className="text-[9px] leading-none">✓</span>}
        </span>
        <span className="truncate text-content">{label}</span>
      </span>
      {hint && <Badge tone="grey">{hint}</Badge>}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Sessions panel (history + results + regressions + comparison)
// ---------------------------------------------------------------------------

function SessionsPanel({ projectId, activeSessionId, onSelect }: { projectId?: string; activeSessionId: string | null; onSelect: (id: string | null) => void }) {
  const [pollMs, setPollMs] = useState(0);
  const sessions = useWorkbenchSessions(projectId ? { project_id: projectId } : undefined, pollMs);
  const list = sessions.data ?? [];
  const active = list.some((s) => s.status === 'pending' || s.status === 'running');
  useEffect(() => { setPollMs(active ? 2500 : 0); }, [active]);

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
      <Card className="overflow-hidden">
        <div className="border-b border-border px-4 py-3">
          <p className="flex items-center gap-2 text-sm font-semibold text-content"><History size={15} /> Sessions</p>
        </div>
        <div className="max-h-[560px] overflow-y-auto p-2">
          {sessions.isLoading ? (
            <Skeleton className="h-24" />
          ) : list.length === 0 ? (
            <p className="px-2 py-4 text-center text-xs text-content-subtle">No sessions yet. Run one from the Run tab.</p>
          ) : (
            <ul className="space-y-1.5">
              {list.map((s) => (
                <li key={s.id}>
                  <button
                    className={`w-full rounded-lg border px-3 py-2 text-left text-xs rf-focus ${
                      activeSessionId === s.id ? 'border-red-500 bg-red-soft' : 'border-border hover:border-border-strong'
                    }`}
                    onClick={() => onSelect(s.id)}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="truncate text-content">{s.name || `Session ${s.id.slice(0, 6)}`}</span>
                      <Badge tone={s.status === 'completed' ? 'green' : s.status === 'failed' ? 'red' : 'amber'}>{s.status}</Badge>
                    </span>
                    <span className="mt-1 block text-[11px] text-content-subtle">
                      {s.models.length} model(s) · {s.summary?.total_results ?? s.total_tasks} result(s)
                      {s.summary?.pass_rate != null && ` · ${s.summary.pass_rate}% pass`}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      <div className="min-w-0">
        {activeSessionId ? (
          <SessionDetail sessionId={activeSessionId} />
        ) : (
          <Card className="p-4">
            <EmptyState icon={<Trophy size={24} />} title="Select a session" description="Pick a session to see scores, regressions, and side-by-side responses." />
          </Card>
        )}
      </div>
    </div>
  );
}

function SessionDetail({ sessionId }: { sessionId: string }) {
  const session = useWorkbenchSession(sessionId, 0);
  const results = useSessionResults(sessionId);
  const regressions = useSessionRegressions(sessionId);
  const [compareIds, setCompareIds] = useState<string[]>([]);

  const s = session.data;
  const running = s && (s.status === 'pending' || s.status === 'running');
  // Poll while the selected session is still running.
  const sessionPoll = useWorkbenchSession(running ? sessionId : null, running ? 2500 : 0);
  const live = sessionPoll.data ?? s;

  const rows = results.data ?? [];
  const compareRows = rows.filter((r) => compareIds.includes(r.id));

  const toggleCompare = (id: string) => {
    setCompareIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id].slice(-3)));
  };

  if (session.isLoading || !live) return <Skeleton className="h-64" />;

  const summ = live.summary ?? {};

  return (
    <div className="space-y-4">
      {/* Scorecards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <ScoreTile label="Pass rate" value={summ.pass_rate} suffix="%" tone="pass" />
        <ScoreTile label="Quality" value={summ.quality_score} />
        <ScoreTile label="Regression" value={summ.regression_score} />
        <ScoreTile label="Consistency" value={summ.consistency_score} />
        <ScoreTile label="Overall" value={summ.overall_score} tone="pass" />
        <ScoreTile label="Results" value={summ.total_results} raw />
      </div>

      {running && (
        <Card className="flex items-center gap-2 p-3 text-xs text-content-subtle">
          <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
          Evaluating… {live.completed_tasks}/{live.total_tasks} complete.
        </Card>
      )}

      {/* Per-model breakdown */}
      {(summ.models ?? []).length > 0 && (
        <Card className="overflow-hidden">
          <div className="border-b border-border px-4 py-3">
            <p className="flex items-center gap-2 text-sm font-semibold text-content"><Trophy size={15} /> Model behavior</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-content-subtle">
                  <th className="px-4 py-2 text-left font-medium">Model</th>
                  <th className="px-4 py-2 text-right font-medium">Pass rate</th>
                  <th className="px-4 py-2 text-right font-medium">Similarity</th>
                  <th className="px-4 py-2 text-right font-medium">Fails</th>
                  <th className="px-4 py-2 text-right font-medium">Regressions</th>
                </tr>
              </thead>
              <tbody>
                {(summ.models ?? []).map((m) => (
                  <tr key={m.label} className="border-b border-border/60 last:border-0">
                    <td className="px-4 py-2 text-content">
                      {m.label}
                      {summ.best_model?.label === m.label && <Badge tone="green">best</Badge>}
                    </td>
                    <td className="px-4 py-2 text-right font-semibold text-content">{m.pass_rate ?? '—'}{m.pass_rate != null ? '%' : ''}</td>
                    <td className="px-4 py-2 text-right text-content-muted">{m.mean_similarity ?? '—'}</td>
                    <td className="px-4 py-2 text-right text-content-muted">{m.fails}</td>
                    <td className="px-4 py-2 text-right text-content-muted">{m.regressions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Regression summary */}
      {(regressions.data?.by_type ?? []).length > 0 && (
        <Card className="p-4">
          <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-content"><GitCompare size={15} /> Regressions ({regressions.data?.total})</p>
          <div className="space-y-2">
            {(regressions.data?.by_type ?? []).map((g) => (
              <div key={g.type} className="rounded-lg border border-border bg-base p-2">
                <p className="mb-1 flex items-center gap-2 text-xs font-medium text-content">
                  {g.label} <Badge tone="amber">{g.count}</Badge>
                </p>
                <ul className="space-y-0.5 text-[11px] text-content-subtle">
                  {g.items.slice(0, 4).map((it, i) => (
                    <li key={i}>
                      <span className={`mr-1 font-medium ${it.attribution === 'model' ? 'text-fail' : 'text-uncertain'}`}>[{it.attribution}]</span>
                      {it.prompt_title} on {it.target_model} — {it.summary}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Results table */}
      <Card className="overflow-hidden">
        <div className="border-b border-border px-4 py-3">
          <p className="flex items-center gap-2 text-sm font-semibold text-content"><FileText size={15} /> Results — select up to 3 to compare</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-content-subtle">
                <th className="px-3 py-2"></th>
                <th className="px-3 py-2 text-left font-medium">Prompt</th>
                <th className="px-3 py-2 text-left font-medium">Model</th>
                <th className="px-3 py-2 text-center font-medium">Verdict</th>
                <th className="px-3 py-2 text-right font-medium">Similarity</th>
                <th className="px-3 py-2 text-right font-medium">Latency</th>
                <th className="px-3 py-2 text-right font-medium">Regr.</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-border/60 last:border-0">
                  <td className="px-3 py-2">
                    <input type="checkbox" className="accent-red-500" checked={compareIds.includes(r.id)} onChange={() => toggleCompare(r.id)} />
                  </td>
                  <td className="max-w-[220px] truncate px-3 py-2 text-content">{r.prompt_title || '—'}</td>
                  <td className="px-3 py-2 text-content-muted">{r.label}</td>
                  <td className="px-3 py-2 text-center"><Badge tone={VERDICT_TONE[r.verdict] ?? 'grey'}>{r.verdict}</Badge></td>
                  <td className="px-3 py-2 text-right text-content-muted">{r.similarity_score ?? '—'}</td>
                  <td className="px-3 py-2 text-right text-content-muted">{r.metrics?.latency_ms != null ? `${r.metrics.latency_ms} ms` : '—'}</td>
                  <td className="px-3 py-2 text-right text-content-muted">{r.regressions.length || '—'}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={7} className="px-3 py-4 text-center text-content-subtle">No results.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {compareRows.length >= 1 && <ResponseComparison results={compareRows} session={live} />}
    </div>
  );
}

function ScoreTile({ label, value, suffix = '', tone, raw }: { label: string; value: number | null | undefined; suffix?: string; tone?: 'pass'; raw?: boolean }) {
  const display = value == null ? '—' : raw ? value : `${value}${suffix}`;
  return (
    <Card className="p-3">
      <p className="text-[11px] text-content-subtle">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${tone === 'pass' ? 'text-pass' : 'text-content'}`}>{display}</p>
    </Card>
  );
}

function ResponseComparison({ results, session }: { results: EvaluationResult[]; session: WorkbenchSession }) {
  return (
    <Card className="p-4">
      <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-content"><GitCompare size={15} /> Response comparison</p>
      <div className={`grid gap-3 ${results.length >= 3 ? 'lg:grid-cols-3' : results.length === 2 ? 'lg:grid-cols-2' : 'grid-cols-1'}`}>
        {results.map((r) => (
          <div key={r.id} className="rounded-lg border border-border bg-base p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="truncate text-xs font-medium text-content">{r.label}</span>
              <Badge tone={VERDICT_TONE[r.verdict] ?? 'grey'}>{r.verdict}</Badge>
            </div>
            <p className="mb-2 truncate text-[11px] text-content-subtle">{r.prompt_title}</p>
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded bg-surface p-2 text-[11px] text-content-muted">{r.response || (r.error ? `Error: ${r.error}` : '(empty)')}</pre>
            <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-content-faint">
              {r.similarity_score != null && <span>sim {r.similarity_score}</span>}
              {r.metrics?.latency_ms != null && <span>· {r.metrics.latency_ms} ms</span>}
              {r.metrics?.total_tokens != null && <span>· {r.metrics.total_tokens} tok</span>}
            </div>
            {r.regressions.length > 0 && (
              <div className="mt-2 space-y-0.5">
                {r.regressions.map((reg, i) => (
                  <p key={i} className="text-[10px]">
                    <Badge tone={SEV_TONE[reg.severity] ?? 'grey'}>{reg.label}</Badge>{' '}
                    <span className="text-content-subtle">{reg.summary}</span>
                  </p>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-content-faint">
        Baseline: golden/expected response per prompt · similarity via “{session.similarity}”.
      </p>
    </Card>
  );
}
