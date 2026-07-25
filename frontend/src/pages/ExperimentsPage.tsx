/**
 * Experiments — the operator's primary unit of work (RedForge V3, Epic 4).
 *
 * Lists every experiment, launches the creation wizard, and drives side-by-side
 * comparison. Each experiment references (never owns) the runs/jobs/artifacts
 * produced under it; this page is the entry point into that workspace.
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  GitBranch,
  Microscope,
  Plus,
  Tag as TagIcon,
  X,
} from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
  StatusBadge,
} from '../components/ui';
import {
  useCreateExperiment,
  useExperiments,
  useExperimentComparison,
  useFoundationModels,
  useTrainingStrategies,
  useUnresolvedRuntimeModels,
  useV3Datasets,
} from '../hooks/queries';
import { errorMessage } from '../api/client';
import { relativeTime } from '../lib/format';
import { toast } from '../lib/toast';
import type { Experiment } from '../api/types';

const INPUT =
  'w-full rounded-lg border border-border bg-base px-3 py-2 text-xs text-content rf-focus';
const LABEL = 'mb-1 block text-[11px] font-medium uppercase tracking-wide text-content-subtle';

const STATUSES = ['active', 'concluded', 'archived', 'draft'];

// --- Modal shell -----------------------------------------------------------

function Modal({
  title,
  onClose,
  children,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className={`w-full ${wide ? 'max-w-4xl' : 'max-w-lg'} rounded-xl border border-border bg-surface p-5 shadow-xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <p className="text-sm font-semibold text-content">{title}</p>
          <button
            className="rounded p-1 text-content-subtle hover:bg-overlay hover:text-content rf-focus"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={15} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// --- Creation wizard -------------------------------------------------------

interface WizardState {
  name: string;
  description: string;
  tags: string[];
  foundation_model_id: string;
  base_model: string;
  dataset_id: string;
  strategy: string;
  provider: string;
  epochs: string;
  learning_rate: string;
  batch_size: string;
}

const EMPTY: WizardState = {
  name: '',
  description: '',
  tags: [],
  foundation_model_id: '',
  base_model: '',
  dataset_id: '',
  strategy: 'lora',
  provider: 'simulation',
  epochs: '1',
  learning_rate: '0.0002',
  batch_size: '4',
};

function CreateWizard({ onClose, onCreated }: { onClose: () => void; onCreated: (e: Experiment) => void }) {
  const [step, setStep] = useState(0);
  const [s, setS] = useState<WizardState>(EMPTY);
  const [tagInput, setTagInput] = useState('');
  const models = useFoundationModels();
  const datasets = useV3Datasets();
  const strategies = useTrainingStrategies();
  const unresolved = useUnresolvedRuntimeModels();
  const create = useCreateExperiment();

  const set = <K extends keyof WizardState>(k: K, v: WizardState[K]) => setS((p) => ({ ...p, [k]: v }));
  const strategy = strategies.data?.find((x) => x.key === s.strategy);
  const providerOptions = strategy?.providers ?? ['simulation'];

  const addTag = () => {
    const t = tagInput.trim();
    if (t && !s.tags.includes(t)) set('tags', [...s.tags, t]);
    setTagInput('');
  };

  const submit = async () => {
    if (!s.name.trim()) {
      setStep(0);
      toast.error('Name is required');
      return;
    }
    const fm = models.data?.find((m) => m.id === s.foundation_model_id);
    const configuration: Record<string, unknown> = {
      foundation_model_id: s.foundation_model_id || null,
      base_model: s.base_model || fm?.hf_repo || '',
      dataset_id: s.dataset_id || null,
      strategy: s.strategy,
      provider: s.provider,
      hyperparameters: {
        epochs: Number(s.epochs) || 1,
        learning_rate: Number(s.learning_rate) || 0.0002,
        batch_size: Number(s.batch_size) || 4,
      },
    };
    try {
      const created = await create.mutate({
        name: s.name.trim(),
        description: s.description.trim(),
        tags: s.tags,
        configuration,
      });
      if (created) {
        toast.success('Experiment created', created.name);
        onCreated(created);
      }
    } catch (err) {
      toast.error('Could not create experiment', errorMessage(err));
    }
  };

  const steps = ['Identity', 'Subject', 'Plan'];

  return (
    <Modal title="New experiment" onClose={onClose} wide>
      {/* Step indicator */}
      <div className="mb-5 flex items-center gap-2">
        {steps.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold ${
                i === step ? 'bg-red-600 text-white' : i < step ? 'bg-overlay text-content' : 'bg-overlay text-content-faint'
              }`}
            >
              {i + 1}
            </span>
            <span className={`text-xs ${i === step ? 'text-content' : 'text-content-subtle'}`}>{label}</span>
            {i < steps.length - 1 && <span className="mx-1 h-px w-6 bg-border" />}
          </div>
        ))}
      </div>

      {step === 0 && (
        <div className="space-y-4">
          <div>
            <label className={LABEL}>Name</label>
            <input
              className={INPUT}
              autoFocus
              value={s.name}
              placeholder="Llama-3 refusal hardening"
              onChange={(e) => set('name', e.target.value)}
            />
          </div>
          <div>
            <label className={LABEL}>Description</label>
            <textarea
              className={`${INPUT} min-h-[72px] resize-y`}
              value={s.description}
              placeholder="What are you trying to learn?"
              onChange={(e) => set('description', e.target.value)}
            />
          </div>
          <div>
            <label className={LABEL}>Tags</label>
            <div className="mb-2 flex flex-wrap gap-1.5">
              {s.tags.map((t) => (
                <Badge key={t} tone="grey">
                  {t}
                  <button className="ml-0.5 hover:text-content" onClick={() => set('tags', s.tags.filter((x) => x !== t))}>
                    <X size={11} />
                  </button>
                </Badge>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                className={INPUT}
                value={tagInput}
                placeholder="Add a tag and press Enter"
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTag())}
              />
              <Button variant="secondary" size="sm" onClick={addTag}>
                Add
              </Button>
            </div>
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-4">
          {(unresolved.data ?? []).length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-uncertain/5 px-3 py-2 text-[11px] text-content-subtle">
              ⚠ {(unresolved.data ?? []).length} local model
              {(unresolved.data ?? []).length === 1 ? '' : 's'} require manual resolution.{' '}
              <a href="/foundation-models" className="text-content underline hover:text-red-400">Resolve them</a> to
              use them here. Already-resolved models are listed below and ready to train.
            </div>
          )}
          <div>
            <label className={LABEL}>Foundation model</label>
            <select
              className={INPUT}
              value={s.foundation_model_id}
              onChange={(e) => {
                const fm = models.data?.find((m) => m.id === e.target.value);
                set('foundation_model_id', e.target.value);
                if (fm) set('base_model', fm.hf_repo);
              }}
            >
              <option value="">— none / specify base model —</option>
              {(models.data ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.hf_repo} ({m.status})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL}>Base model identifier</label>
            <input
              className={INPUT}
              value={s.base_model}
              placeholder="meta-llama/Llama-3.1-8B or llama3:8b"
              onChange={(e) => set('base_model', e.target.value)}
            />
          </div>
          <div>
            <label className={LABEL}>Dataset</label>
            <select className={INPUT} value={s.dataset_id} onChange={(e) => set('dataset_id', e.target.value)}>
              <option value="">— none —</option>
              {(datasets.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} · v{d.current_version}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL}>Strategy</label>
              <select
                className={INPUT}
                value={s.strategy}
                onChange={(e) => {
                  set('strategy', e.target.value);
                  const st = strategies.data?.find((x) => x.key === e.target.value);
                  if (st && !st.providers.includes(s.provider)) set('provider', st.providers[0] ?? 'simulation');
                }}
              >
                {(strategies.data ?? [{ key: 'lora', label: 'LoRA', implemented: true } as never]).map((st) => (
                  <option key={st.key} value={st.key}>
                    {st.label}
                    {st.implemented ? '' : ' (planned)'}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL}>Provider</label>
              <select className={INPUT} value={s.provider} onChange={(e) => set('provider', e.target.value)}>
                {providerOptions.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className={LABEL}>Epochs</label>
              <input className={INPUT} value={s.epochs} onChange={(e) => set('epochs', e.target.value)} />
            </div>
            <div>
              <label className={LABEL}>Learning rate</label>
              <input className={INPUT} value={s.learning_rate} onChange={(e) => set('learning_rate', e.target.value)} />
            </div>
            <div>
              <label className={LABEL}>Batch size</label>
              <input className={INPUT} value={s.batch_size} onChange={(e) => set('batch_size', e.target.value)} />
            </div>
          </div>
          <p className="text-[11px] text-content-subtle">
            A reproducibility snapshot (foundation model, dataset version, environment, resource estimate) is captured
            automatically when the experiment is created.
          </p>
        </div>
      )}

      {/* Footer */}
      <div className="mt-6 flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={() => (step === 0 ? onClose() : setStep(step - 1))}>
          {step === 0 ? 'Cancel' : 'Back'}
        </Button>
        {step < steps.length - 1 ? (
          <Button size="sm" onClick={() => setStep(step + 1)} disabled={step === 0 && !s.name.trim()}>
            Next <ArrowRight size={14} />
          </Button>
        ) : (
          <Button size="sm" onClick={submit} disabled={create.isPending}>
            {create.isPending ? 'Creating…' : 'Create experiment'}
          </Button>
        )}
      </div>
    </Modal>
  );
}

// --- Compare dialog --------------------------------------------------------

function CompareDialog({ ids, onClose }: { ids: string[]; onClose: () => void }) {
  const cmp = useExperimentComparison(ids);
  const cols = cmp.data?.experiments ?? [];

  const rows: { label: string; get: (c: (typeof cols)[number]) => React.ReactNode }[] = [
    { label: 'Status', get: (c) => <StatusBadge status={c.status} /> },
    { label: 'Strategy', get: (c) => c.strategy },
    { label: 'Provider', get: (c) => c.provider ?? '—' },
    { label: 'Base model', get: (c) => c.base_model || '—' },
    { label: 'Final loss', get: (c) => (c.final_loss != null ? c.final_loss.toFixed(4) : '—') },
    { label: 'Train duration', get: (c) => (c.training_duration != null ? `${c.training_duration}s` : '—') },
    { label: 'Artifacts', get: (c) => c.artifacts_total },
    { label: 'Jobs', get: (c) => c.jobs_total },
  ];

  return (
    <Modal title={`Compare ${ids.length} experiments`} onClose={onClose} wide>
      {cmp.isLoading ? (
        <Spinner label="Loading comparison…" />
      ) : cols.length === 0 ? (
        <EmptyState title="Nothing to compare" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                <th className="border-b border-border px-3 py-2 text-left text-content-subtle">Metric</th>
                {cols.map((c) => (
                  <th key={c.id} className="border-b border-border px-3 py-2 text-left font-semibold text-content">
                    {c.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.label}>
                  <td className="border-b border-border/60 px-3 py-2 text-content-subtle">{r.label}</td>
                  {cols.map((c) => (
                    <td key={c.id} className="border-b border-border/60 px-3 py-2 text-content">
                      {r.get(c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}

// --- Experiment card -------------------------------------------------------

function ExperimentCard({
  exp,
  selected,
  compareMode,
  onToggle,
  onOpen,
}: {
  exp: Experiment;
  selected: boolean;
  compareMode: boolean;
  onToggle: () => void;
  onOpen: () => void;
}) {
  return (
    <Card
      hover
      className={`cursor-pointer p-4 ${selected ? 'ring-1 ring-red-500' : ''}`}
      onClick={compareMode ? onToggle : onOpen}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {compareMode && (
            <input type="checkbox" checked={selected} readOnly className="accent-red-600" onClick={(e) => e.stopPropagation()} />
          )}
          <Microscope size={15} className="shrink-0 text-red-400" />
          <span className="truncate text-sm font-semibold text-content">{exp.name}</span>
        </div>
        <StatusBadge status={exp.status} />
      </div>
      {exp.description && <p className="mb-2 line-clamp-2 text-xs text-content-subtle">{exp.description}</p>}
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <Badge tone="grey">{exp.configuration.strategy}</Badge>
        {exp.configuration.base_model && <Badge tone="grey">{exp.configuration.base_model}</Badge>}
        {exp.parent_experiment_id && (
          <Badge tone="grey">
            <GitBranch size={11} /> clone
          </Badge>
        )}
      </div>
      {exp.tags.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1 text-content-subtle">
          <TagIcon size={11} />
          {exp.tags.map((t) => (
            <span key={t} className="text-[11px]">
              {t}
            </span>
          ))}
        </div>
      )}
      <p className="text-[11px] text-content-faint">Updated {relativeTime(exp.updated_at)}</p>
    </Card>
  );
}

// --- Page ------------------------------------------------------------------

export default function ExperimentsPage() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [wizardOpen, setWizardOpen] = useState(false);
  const [compareMode, setCompareMode] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);

  const experiments = useExperiments(statusFilter ? { status: statusFilter } : undefined);
  const list = experiments.data ?? [];

  const grouped = useMemo(() => list, [list]);

  const toggle = (id: string) =>
    setSelected((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  return (
    <div>
      <PageHeader
        title="Experiments"
        description="Your unit of work — each experiment references the runs, jobs, and artifacts produced under it."
        actions={
          <>
            <Button
              variant={compareMode ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => {
                setCompareMode((v) => !v);
                setSelected([]);
              }}
            >
              {compareMode ? `Comparing (${selected.length})` : 'Compare'}
            </Button>
            {compareMode && selected.length >= 2 && (
              <Button size="sm" onClick={() => setCompareOpen(true)}>
                View comparison
              </Button>
            )}
            <Button size="sm" onClick={() => setWizardOpen(true)}>
              <Plus size={14} /> New experiment
            </Button>
          </>
        }
      />

      {/* Status filter */}
      <div className="mb-4 flex items-center gap-1.5">
        <button
          className={`rounded-md px-2.5 py-1 text-xs ${statusFilter === '' ? 'bg-overlay text-content' : 'text-content-subtle hover:text-content'}`}
          onClick={() => setStatusFilter('')}
        >
          All
        </button>
        {STATUSES.map((st) => (
          <button
            key={st}
            className={`rounded-md px-2.5 py-1 text-xs capitalize ${statusFilter === st ? 'bg-overlay text-content' : 'text-content-subtle hover:text-content'}`}
            onClick={() => setStatusFilter(st)}
          >
            {st}
          </button>
        ))}
      </div>

      {experiments.isLoading ? (
        <Spinner label="Loading experiments…" />
      ) : experiments.isError ? (
        <ErrorState message={errorMessage(experiments.error)} onRetry={experiments.refetch} />
      ) : grouped.length === 0 ? (
        <EmptyState
          icon={<Microscope size={28} />}
          title="No experiments yet"
          description="Create an experiment to start tracking a line of inquiry end-to-end."
          action={
            <Button size="sm" onClick={() => setWizardOpen(true)}>
              <Plus size={14} /> New experiment
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {grouped.map((exp) => (
            <ExperimentCard
              key={exp.id}
              exp={exp}
              compareMode={compareMode}
              selected={selected.includes(exp.id)}
              onToggle={() => toggle(exp.id)}
              onOpen={() => navigate(`/experiments/${exp.id}`)}
            />
          ))}
        </div>
      )}

      {wizardOpen && (
        <CreateWizard
          onClose={() => setWizardOpen(false)}
          onCreated={(e) => {
            setWizardOpen(false);
            navigate(`/experiments/${e.id}`);
          }}
        />
      )}
      {compareOpen && <CompareDialog ids={selected} onClose={() => setCompareOpen(false)} />}
    </div>
  );
}
