import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Cpu, Dumbbell, Plus, Rocket } from 'lucide-react';
import { Badge, Button, Card, EmptyState, PageHeader, Skeleton } from '../components/ui';
import {
  useCreateTrainingRun,
  useEstimateTraining,
  useFoundationModels,
  useLaunchTrainingRun,
  useTrainingProviders,
  useTrainingStrategies,
  useV3Datasets,
  useV3TrainingRuns,
} from '../hooks/queries';
import { toast } from '../lib/toast';
import type { TrainingEstimate, V3TrainingRun } from '../api/types';

const INPUT = 'w-full rounded-lg border border-border bg-base px-3 py-2 text-xs text-content rf-focus';
const STATUS_TONE: Record<string, 'green' | 'red' | 'amber' | 'grey'> = {
  completed: 'green', running: 'amber', queued: 'grey', created: 'grey', failed: 'red', cancelled: 'grey',
};
const ACTIVE = new Set(['queued', 'running']);

export default function PipelineTrainingPage() {
  const navigate = useNavigate();
  const [pollMs, setPollMs] = useState(0);
  const runs = useV3TrainingRuns(undefined, pollMs);
  const list = runs.data ?? [];
  const active = list.some((r) => ACTIVE.has(r.status));
  useEffect(() => setPollMs(active ? 2000 : 0), [active]);
  const [wizard, setWizard] = useState(false);

  if (wizard) return <TrainingWizard onClose={() => setWizard(false)} onLaunched={(id) => navigate(`/pipeline/train/${id}`)} />;

  return (
    <div>
      <PageHeader
        title="Fine-Tune"
        description="Take a Foundation Model through local LoRA/QLoRA/SFT training. Runs execute as Jobs; checkpoints and adapters become Artifacts with full lineage."
        actions={<Button size="sm" onClick={() => setWizard(true)}><Plus size={14} /> New run</Button>}
      />

      {runs.isLoading ? (
        <Skeleton className="h-40" />
      ) : list.length === 0 ? (
        <Card className="p-4">
          <EmptyState icon={<Dumbbell size={24} />} title="No training runs yet"
            description="Start a run with the wizard — pick a foundation model, a dataset, and a strategy." />
        </Card>
      ) : (
        <div className="space-y-2">
          {list.map((r) => (
            <Card key={r.id} className="flex items-center justify-between gap-2 p-3">
              <button className="flex min-w-0 items-center gap-3 text-left rf-focus" onClick={() => navigate(`/pipeline/train/${r.id}`)}>
                {r.status === 'running' && <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-red-500" />}
                <span className="min-w-0">
                  <span className="block truncate text-sm text-content">{r.name}</span>
                  <span className="block truncate text-[11px] text-content-subtle">
                    {r.configuration.strategy.toUpperCase()} · {r.configuration.provider} · {r.configuration.base_model}
                  </span>
                </span>
              </button>
              <div className="flex shrink-0 items-center gap-2">
                {r.adapter_artifact_id && <Badge tone="green">adapter</Badge>}
                <Badge tone={STATUS_TONE[r.status] ?? 'grey'}>{r.status}</Badge>
                <Button variant="ghost" size="sm" onClick={() => navigate(`/pipeline/train/${r.id}`)}>Open</Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

const STEPS = ['Foundation Model', 'Dataset', 'Strategy', 'Provider', 'Hyperparameters', 'Estimate', 'Review', 'Launch'];

function TrainingWizard({ onClose, onLaunched }: { onClose: () => void; onLaunched: (id: string) => void }) {
  const foundations = useFoundationModels();
  const datasets = useV3Datasets();
  const strategies = useTrainingStrategies();
  const providers = useTrainingProviders();
  const estimateM = useEstimateTraining();
  const create = useCreateTrainingRun();
  const launch = useLaunchTrainingRun();

  const [step, setStep] = useState(0);
  const [f, setF] = useState({
    name: 'Untitled run',
    foundation_model_id: '' as string,
    base_model: '',
    dataset_id: '' as string,
    strategy: 'lora',
    provider: '' as string,
    epochs: 3,
    learning_rate: 0.0002,
    batch_size: 2,
    rank: 16,
    alpha: 32,
  });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));
  const [estimate, setEstimate] = useState<TrainingEstimate | null>(null);

  const strat = (strategies.data ?? []).find((s) => s.key === f.strategy);
  const compatibleProviders = (providers.data ?? []).filter((p) => !strat || strat.providers.includes(p.name));

  const runEstimate = async () => {
    const est = await estimateM.mutate({
      foundation_model_id: f.foundation_model_id || undefined,
      base_model: f.base_model || undefined, dataset_id: f.dataset_id || undefined,
      strategy: f.strategy, provider: f.provider || undefined,
      hyperparameters: { epochs: f.epochs, learning_rate: f.learning_rate, batch_size: f.batch_size },
      adapter: { rank: f.rank, alpha: f.alpha },
    });
    if (est) setEstimate(est);
  };

  const launchRun = async () => {
    if (!f.foundation_model_id && !f.base_model) return toast.error('Pick a foundation model or enter a base model');
    const run = await create.mutate({
      name: f.name, foundation_model_id: f.foundation_model_id || undefined,
      base_model: f.base_model || undefined, dataset_id: f.dataset_id || undefined,
      strategy: f.strategy, provider: f.provider || undefined,
      hyperparameters: { epochs: f.epochs, learning_rate: f.learning_rate, batch_size: f.batch_size },
      adapter: { rank: f.rank, alpha: f.alpha },
    });
    if (!run) return;
    const res = await launch.mutate((run as V3TrainingRun).id);
    if (res) {
      toast.success('Training launched', `${f.strategy.toUpperCase()} run queued`);
      onLaunched((run as V3TrainingRun).id);
    }
  };

  const next = () => {
    if (step === 4) void runEstimate();
    setStep((s) => Math.min(STEPS.length - 1, s + 1));
  };

  return (
    <div>
      <PageHeader
        title="New training run"
        description={`Step ${step + 1} of ${STEPS.length} — ${STEPS[step]}`}
        actions={<Button variant="ghost" size="sm" onClick={onClose}><ArrowLeft size={14} /> Cancel</Button>}
      />

      {/* Stepper */}
      <div className="mb-4 flex flex-wrap gap-1.5">
        {STEPS.map((s, i) => (
          <span key={s} className={`rounded-full px-2.5 py-1 text-[10px] ${
            i === step ? 'bg-red-500 text-white' : i < step ? 'bg-red-soft text-content' : 'bg-base text-content-subtle'
          }`}>{i + 1}. {s}</span>
        ))}
      </div>

      <Card className="p-5">
        {step === 0 && (
          <Section title="Foundation Model">
            <Field label="Registered foundation model">
              <select className={INPUT} value={f.foundation_model_id} onChange={(e) => set('foundation_model_id', e.target.value)}>
                <option value="">— none —</option>
                {(foundations.data ?? []).map((m) => <option key={m.id} value={m.id}>{m.hf_repo}</option>)}
              </select>
            </Field>
            {/* Only ask for a base-model string when NO foundation model is chosen —
                otherwise RedForge already knows the model (avoids re-entering it). */}
            {!f.foundation_model_id && (
              <Field label="…or base model string (Ollama tag / HF repo)">
                <input className={INPUT} value={f.base_model} placeholder="llama3.1:8b" onChange={(e) => set('base_model', e.target.value)} />
              </Field>
            )}
            {f.foundation_model_id && (
              <p className="text-[11px] text-content-subtle">
                Using{' '}
                <span className="text-content">{(foundations.data ?? []).find((m) => m.id === f.foundation_model_id)?.hf_repo}</span>{' '}
                — RedForge already has its identity, so there's nothing else to enter here.
              </p>
            )}
          </Section>
        )}
        {step === 1 && (
          <Section title="Dataset">
            <Field label="Training dataset (optional for a dry run)">
              <select className={INPUT} value={f.dataset_id} onChange={(e) => set('dataset_id', e.target.value)}>
                <option value="">— none —</option>
                {(datasets.data ?? []).map((d) => <option key={d.id} value={d.id}>{d.name} ({d.statistics.record_count} rows)</option>)}
              </select>
            </Field>
          </Section>
        )}
        {step === 2 && (
          <Section title="Training Strategy">
            <div className="grid gap-2 sm:grid-cols-2">
              {(strategies.data ?? []).map((s) => (
                <button key={s.key} disabled={!s.implemented} onClick={() => set('strategy', s.key)}
                  className={`rounded-lg border px-3 py-2 text-left text-xs rf-focus ${
                    f.strategy === s.key ? 'border-red-500 bg-red-soft' : 'border-border hover:border-border-strong'
                  } ${!s.implemented ? 'opacity-50' : ''}`}>
                  <span className="flex items-center justify-between text-content">{s.label}
                    {!s.implemented && <Badge tone="grey">soon</Badge>}</span>
                  <span className="block text-[10px] text-content-subtle">{s.dataset_shape}{s.adapter_based ? ' · adapter' : ' · full'}</span>
                </button>
              ))}
            </div>
          </Section>
        )}
        {step === 3 && (
          <Section title="Training Provider">
            <div className="space-y-2">
              {compatibleProviders.map((p) => (
                <button key={p.name} onClick={() => set('provider', p.name)}
                  className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-xs rf-focus ${
                    f.provider === p.name ? 'border-red-500 bg-red-soft' : 'border-border hover:border-border-strong'
                  }`}>
                  <span className="text-content">{p.label}</span>
                  <span className="flex items-center gap-1.5">
                    {p.dev_only && <Badge tone="amber">dev</Badge>}
                    <Badge tone={p.available ? 'green' : 'grey'}>{p.available ? 'available' : 'unavailable'}</Badge>
                  </span>
                </button>
              ))}
              <p className="text-[10px] text-content-faint">Leave unset to auto-select the best compatible available provider.</p>
            </div>
          </Section>
        )}
        {step === 4 && (
          <Section title="Hyperparameters">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Epochs"><input type="number" className={INPUT} value={f.epochs} onChange={(e) => set('epochs', +e.target.value)} /></Field>
              <Field label="Learning rate"><input type="number" step="0.0001" className={INPUT} value={f.learning_rate} onChange={(e) => set('learning_rate', +e.target.value)} /></Field>
              <Field label="Batch size"><input type="number" className={INPUT} value={f.batch_size} onChange={(e) => set('batch_size', +e.target.value)} /></Field>
              {strat?.adapter_based && (
                <>
                  <Field label="LoRA rank"><input type="number" className={INPUT} value={f.rank} onChange={(e) => set('rank', +e.target.value)} /></Field>
                  <Field label="LoRA alpha"><input type="number" className={INPUT} value={f.alpha} onChange={(e) => set('alpha', +e.target.value)} /></Field>
                </>
              )}
            </div>
          </Section>
        )}
        {step === 5 && (
          <Section title="Resource Estimate">
            {estimateM.isPending || !estimate ? <Skeleton className="h-32" /> : <EstimatePanel estimate={estimate} />}
          </Section>
        )}
        {step === 6 && (
          <Section title="Review">
            <Field label="Run name"><input className={INPUT} value={f.name} onChange={(e) => set('name', e.target.value)} /></Field>
            <dl className="mt-2 space-y-1 text-xs">
              <Row k="Foundation" v={f.foundation_model_id ? (foundations.data ?? []).find((m) => m.id === f.foundation_model_id)?.hf_repo ?? '' : f.base_model} />
              <Row k="Dataset" v={f.dataset_id ? (datasets.data ?? []).find((d) => d.id === f.dataset_id)?.name ?? '' : 'none'} />
              <Row k="Strategy" v={f.strategy.toUpperCase()} />
              <Row k="Provider" v={f.provider || 'auto'} />
              <Row k="Epochs / LR / Batch" v={`${f.epochs} / ${f.learning_rate} / ${f.batch_size}`} />
            </dl>
          </Section>
        )}
        {step === 7 && (
          <Section title="Launch">
            {f.provider && f.provider !== 'simulation' && (
              <div className="mb-3 rounded-lg border border-amber-500/30 bg-uncertain/5 px-3 py-2 text-[11px] text-content-subtle">
                ⚠ First-run real training <span className="text-content">downloads the base model
                (often several GB)</span> from Hugging Face before training starts. You'll see live
                “Downloading… / Loading… / Training…” progress on the run page — it isn't frozen.
              </div>
            )}
            <p className="mb-3 text-xs text-content-subtle">Ready to launch. Training executes as a Job; follow live progress on the run page.</p>
            <Button onClick={launchRun} loading={create.isPending || launch.isPending}><Rocket size={15} /> Launch training</Button>
          </Section>
        )}

        <div className="mt-5 flex items-center justify-between border-t border-border pt-4">
          <Button variant="ghost" size="sm" disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}>
            <ArrowLeft size={14} /> Back
          </Button>
          {step < STEPS.length - 1 && (
            <Button size="sm" onClick={next}>Next <ArrowRight size={14} /></Button>
          )}
        </div>
      </Card>
    </div>
  );
}

function EstimatePanel({ estimate }: { estimate: TrainingEstimate }) {
  return (
    <div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="VRAM" value={`${(estimate.vram_mb / 1024).toFixed(1)} GB`} />
        <Stat label="Disk" value={`${(estimate.disk_mb / 1024).toFixed(1)} GB`} />
        <Stat label="Duration" value={`~${Math.round(estimate.duration_seconds / 60)} min`} />
        <Stat label="Adapter" value={`${estimate.adapter_size_mb} MB`} />
      </div>
      <div className={`mt-3 rounded-lg px-3 py-2 text-xs ${estimate.fits_hardware ? 'bg-pass/10 text-pass' : 'bg-fail/10 text-fail'}`}>
        {estimate.fits_hardware ? 'Fits detected hardware.' : 'May not fit detected hardware.'}
      </div>
      {estimate.warnings.map((w, i) => <p key={i} className="mt-1 text-[11px] text-uncertain">⚠ {w}</p>)}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-2.5">
      <p className="flex items-center gap-1 text-[10px] text-content-subtle"><Cpu size={11} /> {label}</p>
      <p className="mt-0.5 text-sm font-semibold text-content">{value}</p>
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <div><p className="mb-3 text-sm font-semibold text-content">{title}</p><div className="grid gap-3">{children}</div></div>;
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block"><span className="mb-1 block text-[11px] font-medium text-content-subtle">{label}</span>{children}</label>;
}
function Row({ k, v }: { k: string; v: string }) {
  return <div className="flex justify-between gap-3"><dt className="text-content-subtle">{k}</dt><dd className="truncate text-right text-content" title={v}>{v}</dd></div>;
}
