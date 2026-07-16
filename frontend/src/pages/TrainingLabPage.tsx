import { useMemo, useState } from 'react';
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Boxes,
  Cpu,
  Download,
  FileText,
  Gauge,
  Layers,
  Lightbulb,
  Loader2,
  Play,
  Rocket,
  Shield,
  Square,
  Trash2,
} from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Progress,
  Skeleton,
  StatusBadge,
} from '../components/ui';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import {
  useTrainingBackends,
  useTrainingRuns,
  useTrainingProgress,
  useTrainingCheckpoints,
  useSecurityTimeline,
  useAnalyzeRecommendation,
  useDecideRecommendation,
  useLaunchTraining,
  useCancelTraining,
  useDeleteTraining,
  useModels,
  useDatasets,
  useTrainingReport,
} from '../hooks/queries';
import { toast } from '../lib/toast';
import type { Recommendation, TrainingParams, TrainingRun } from '../api/types';

/** Prefill for the wizard — used by one-click "Apply" from a recommendation.
 * Nothing launches automatically; the user still reviews and edits every field. */
export type WizardPrefill = {
  name?: string;
  baseModel?: string;
  datasetId?: string;
  method?: 'lora' | 'qlora';
  params?: Partial<TrainingParams>;
};

function prefillFromRecommendation(rec: Recommendation): WizardPrefill {
  const hp = rec.payload.hyperparameters;
  const proj = rec.payload.datasets.project[0];
  return {
    name: `${rec.target_model} — improved`,
    baseModel: rec.target_model,
    datasetId: proj?.id,
    method: rec.payload.strategy.method.toLowerCase() === 'qlora' ? 'qlora' : 'lora',
    params: {
      rank: hp.rank,
      alpha: hp.alpha,
      epochs: hp.epochs,
      learning_rate: hp.learning_rate,
      batch_size: hp.batch_size,
      gradient_accumulation: hp.gradient_accumulation,
      scheduler: hp.scheduler,
      optimizer: hp.optimizer,
      warmup_steps: hp.warmup_steps,
    },
  };
}

const DEFAULT_PARAMS: TrainingParams = {
  epochs: 3,
  learning_rate: 0.0002,
  batch_size: 2,
  gradient_accumulation: 4,
  rank: 16,
  alpha: 32,
  dropout: 0.05,
  scheduler: 'cosine',
  optimizer: 'adamw_8bit',
  warmup_steps: 10,
  max_seq_length: 2048,
  seed: 42,
  validation_split: 0.1,
  output_dir: '',
};

export default function TrainingLabPage() {
  const runs = useTrainingRuns();
  const [selected, setSelected] = useState<string | null>(null);
  const [wizard, setWizard] = useState(false);
  const [prefill, setPrefill] = useState<WizardPrefill | null>(null);

  const list = runs.data ?? [];

  const openWizard = (pf: WizardPrefill | null) => {
    setPrefill(pf);
    setWizard(true);
  };

  if (wizard) {
    return (
      <TrainingWizard
        prefill={prefill}
        onCancel={() => {
          setWizard(false);
          setPrefill(null);
        }}
        onLaunched={(id) => {
          setWizard(false);
          setPrefill(null);
          setSelected(id);
        }}
      />
    );
  }

  if (selected) {
    return (
      <RunDashboard
        runId={selected}
        onBack={() => setSelected(null)}
        onApply={(pf) => {
          setSelected(null);
          openWizard(pf);
        }}
      />
    );
  }

  return (
    <div>
      <PageHeader
        title="Training Lab"
        description="Fine-tune local models with LoRA / QLoRA. Everything runs and stays on your machine."
        actions={
          <Button onClick={() => setWizard(true)}>
            <Rocket size={16} /> New Training Run
          </Button>
        }
      />

      {runs.isLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <EmptyState
          icon={<Layers size={28} />}
          title="No training runs yet"
          description="Launch a LoRA or QLoRA fine-tune. Runs, metrics, and checkpoints are stored locally."
          action={
            <Button onClick={() => openWizard(null)}>
              <Rocket size={16} /> New Training Run
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((r) => (
            <RunCard key={r.id} run={r} onOpen={() => setSelected(r.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function RunCard({ run, onOpen }: { run: TrainingRun; onOpen: () => void }) {
  return (
    <Card hover className="cursor-pointer p-4" onClick={onOpen}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-content">{run.name}</h3>
          <p className="truncate text-xs text-content-subtle">{run.base_model}</p>
        </div>
        <StatusBadge status={run.status} />
      </div>
      <div className="mt-3 flex items-center gap-2">
        <Badge tone="neutral">{run.method.toUpperCase()}</Badge>
        <Badge tone="grey">{run.backend}</Badge>
        {run.metrics?.final_loss != null && (
          <span className="text-xs text-content-subtle">loss {Number(run.metrics.final_loss).toFixed(3)}</span>
        )}
      </div>
    </Card>
  );
}

// --- Wizard ----------------------------------------------------------------

const STEPS = ['Base Model', 'Dataset', 'Method', 'Parameters', 'Review'];

function TrainingWizard({
  prefill,
  onCancel,
  onLaunched,
}: {
  prefill?: WizardPrefill | null;
  onCancel: () => void;
  onLaunched: (id: string) => void;
}) {
  const models = useModels();
  const datasets = useDatasets();
  const backends = useTrainingBackends();
  const launch = useLaunchTraining();

  const [step, setStep] = useState(0);
  const [name, setName] = useState(prefill?.name ?? 'Untitled run');
  const [baseModel, setBaseModel] = useState(prefill?.baseModel ?? '');
  const [datasetId, setDatasetId] = useState<string>(prefill?.datasetId ?? '');
  const [method, setMethod] = useState<'lora' | 'qlora'>(prefill?.method ?? 'lora');
  const [backend, setBackend] = useState('');
  const [params, setParams] = useState<TrainingParams>(
    prefill?.params ? { ...DEFAULT_PARAMS, ...prefill.params } : DEFAULT_PARAMS,
  );
  const [continuousSecurity, setContinuousSecurity] = useState(false);
  const [securityProfile, setSecurityProfile] = useState<'quick' | 'standard' | 'full'>('quick');

  const modelList = models.data?.models ?? [];
  const datasetList = datasets.data ?? [];
  const backendList = backends.data?.backends ?? [];
  const activeBackend = backend || backends.data?.default || 'simulation';
  const activeModel = baseModel || modelList[0]?.name || '';

  const canNext =
    (step === 0 && !!activeModel) ||
    (step === 1) ||
    step === 2 ||
    step === 3 ||
    step === 4;

  const doLaunch = async () => {
    try {
      const res = await launch.mutate({
        name,
        base_model: activeModel,
        dataset_id: datasetId || null,
        method,
        backend: activeBackend,
        params,
        continuous_security: continuousSecurity,
        security_profile: securityProfile,
      });
      if (res?.run) {
        toast.success('Training launched', `${res.run.name} · ${res.backend}`);
        onLaunched(res.run.id);
      }
    } catch {
      toast.error('Could not launch training');
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="New Training Run"
        description={`Step ${step + 1} of ${STEPS.length} · ${STEPS[step]}`}
        actions={
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        }
      />
      <div className="mb-6 flex gap-1.5">
        {STEPS.map((s, i) => (
          <div key={s} className={`h-1 flex-1 rounded-full ${i <= step ? 'bg-red-500' : 'bg-overlay'}`} />
        ))}
      </div>

      <Card className="p-6">
        {step === 0 && (
          <Field label="Run name">
            <input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
            <label className="mb-1 mt-4 block text-xs text-content-subtle">Base model</label>
            <select value={activeModel} onChange={(e) => setBaseModel(e.target.value)} className={inputCls}>
              {modelList.length === 0 && <option value="">No models — install one first</option>}
              {modelList.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name}
                </option>
              ))}
            </select>
          </Field>
        )}

        {step === 1 && (
          <Field label="Dataset (optional)">
            <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)} className={inputCls}>
              <option value="">None</option>
              {datasetList.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.record_count} records)
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-content-subtle">
              Datasets come from the Dataset Lab. Records are read locally at launch.
            </p>
          </Field>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              {(['lora', 'qlora'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMethod(m)}
                  className={`rounded-xl border px-4 py-4 text-left transition-colors ${
                    method === m ? 'border-red-500 bg-red-soft' : 'border-border hover:border-border-strong'
                  }`}
                >
                  <p className="text-sm font-semibold text-content">{m.toUpperCase()}</p>
                  <p className="mt-1 text-xs text-content-subtle">
                    {m === 'lora' ? 'Adapters on a full-precision base.' : '4-bit base + adapters — low VRAM.'}
                  </p>
                </button>
              ))}
            </div>
            <div>
              <label className="mb-1 block text-xs text-content-subtle">Backend</label>
              <select value={activeBackend} onChange={(e) => setBackend(e.target.value)} className={inputCls}>
                {backendList.map((b) => (
                  <option key={b.name} value={b.name}>
                    {b.label} {b.available ? '' : '— unavailable'}
                  </option>
                ))}
              </select>
              {backendList.find((b) => b.name === activeBackend && !b.available) && (
                <p className="mt-1.5 text-xs text-uncertain">
                  {backendList.find((b) => b.name === activeBackend)?.reason}
                </p>
              )}
            </div>

            {/* Continuous Security — auto-evaluate each checkpoint */}
            <div className="rounded-xl border border-border p-4">
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="checkbox"
                  checked={continuousSecurity}
                  onChange={(e) => setContinuousSecurity(e.target.checked)}
                  className="mt-0.5 accent-red-500"
                />
                <div>
                  <p className="text-sm font-medium text-content">Continuous Security</p>
                  <p className="mt-0.5 text-xs text-content-subtle">
                    Automatically run a security evaluation at every checkpoint and build a
                    security timeline — no manual evaluations needed.
                  </p>
                </div>
              </label>
              {continuousSecurity && (
                <div className="mt-3 pl-7">
                  <label className="mb-1 block text-xs text-content-subtle">Attack profile</label>
                  <select
                    value={securityProfile}
                    onChange={(e) => setSecurityProfile(e.target.value as 'quick' | 'standard' | 'full')}
                    className={inputCls}
                  >
                    <option value="quick">Quick — fastest, core attacks</option>
                    <option value="standard">Standard — broader coverage</option>
                    <option value="full">Full — all attack categories</option>
                  </select>
                </div>
              )}
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="grid grid-cols-2 gap-3">
            <Num label="Epochs" v={params.epochs} set={(x) => setParams({ ...params, epochs: x })} />
            <Num label="Learning rate" v={params.learning_rate} step={0.0001} set={(x) => setParams({ ...params, learning_rate: x })} />
            <Num label="Batch size" v={params.batch_size} set={(x) => setParams({ ...params, batch_size: x })} />
            <Num label="Grad accumulation" v={params.gradient_accumulation} set={(x) => setParams({ ...params, gradient_accumulation: x })} />
            <Num label="Rank (r)" v={params.rank} set={(x) => setParams({ ...params, rank: x })} />
            <Num label="Alpha" v={params.alpha} set={(x) => setParams({ ...params, alpha: x })} />
            <Num label="Dropout" v={params.dropout} step={0.01} set={(x) => setParams({ ...params, dropout: x })} />
            <Num label="Warmup steps" v={params.warmup_steps} set={(x) => setParams({ ...params, warmup_steps: x })} />
            <Num label="Max seq length" v={params.max_seq_length} set={(x) => setParams({ ...params, max_seq_length: x })} />
            <Num label="Seed" v={params.seed} set={(x) => setParams({ ...params, seed: x })} />
            <Field label="Scheduler">
              <select value={params.scheduler} onChange={(e) => setParams({ ...params, scheduler: e.target.value })} className={inputCls}>
                {['cosine', 'linear', 'constant'].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label="Output directory">
              <input value={params.output_dir} onChange={(e) => setParams({ ...params, output_dir: e.target.value })} placeholder="outputs/run-1" className={inputCls} />
            </Field>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-2 text-sm">
            <ReviewRow k="Name" v={name} />
            <ReviewRow k="Base model" v={activeModel} />
            <ReviewRow k="Dataset" v={datasetList.find((d) => d.id === datasetId)?.name ?? 'None'} />
            <ReviewRow k="Method" v={method.toUpperCase()} />
            <ReviewRow k="Backend" v={activeBackend} />
            <ReviewRow k="Epochs / LR" v={`${params.epochs} · ${params.learning_rate}`} />
            <ReviewRow k="Rank / Alpha" v={`${params.rank} / ${params.alpha}`} />
            <ReviewRow k="Batch × Accum" v={`${params.batch_size} × ${params.gradient_accumulation}`} />
          </div>
        )}
      </Card>

      <div className="mt-5 flex items-center justify-between">
        {step > 0 ? (
          <Button variant="ghost" size="sm" onClick={() => setStep((s) => s - 1)}>
            <ArrowLeft size={14} /> Back
          </Button>
        ) : (
          <span />
        )}
        {step < STEPS.length - 1 ? (
          <Button onClick={() => setStep((s) => s + 1)} disabled={!canNext}>
            Continue <ArrowRight size={15} />
          </Button>
        ) : (
          <Button onClick={doLaunch} loading={launch.isPending} disabled={!activeModel}>
            <Play size={15} /> Launch Training
          </Button>
        )}
      </div>
    </div>
  );
}

// --- Live dashboard --------------------------------------------------------

function RunDashboard({
  runId,
  onBack,
  onApply,
}: {
  runId: string;
  onBack: () => void;
  onApply: (pf: WizardPrefill) => void;
}) {
  const run = useTrainingRuns();
  const runInfo = useMemo(() => (run.data ?? []).find((r) => r.id === runId), [run.data, runId]);
  const [live, setLive] = useState(true);
  const progress = useTrainingProgress(runId, live ? 800 : 0);
  const checkpoints = useTrainingCheckpoints(runId, live ? 2000 : 0);
  const cancel = useCancelTraining();
  const del = useDeleteTraining();

  const p = progress.data;
  const status = p?.status ?? runInfo?.status ?? 'idle';
  const terminal = ['completed', 'failed', 'cancelled', 'idle'].includes(status);
  if (terminal && live) setLive(false);

  const latest = p?.latest ?? {};
  const stepPct = latest.total_steps ? (latest.step ?? 0) / latest.total_steps : 0;
  const chartData = (p?.history ?? []).map((h) => ({
    step: h.step,
    loss: h.loss,
    val_loss: h.val_loss,
  }));

  return (
    <div>
      <PageHeader
        title={runInfo?.name ?? 'Training run'}
        description={`${runInfo?.method?.toUpperCase() ?? ''} · ${runInfo?.base_model ?? ''} · ${runInfo?.backend ?? ''}`}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onBack}>
              <ArrowLeft size={14} /> Back
            </Button>
            {!terminal && (
              <Button variant="danger" size="sm" onClick={() => cancel.mutate(runId)}>
                <Square size={13} /> Stop
              </Button>
            )}
            {terminal && (
              <Button
                variant="danger"
                size="sm"
                onClick={() => {
                  if (window.confirm('Delete this run and its checkpoints?')) {
                    del.mutate(runId).then(onBack);
                  }
                }}
              >
                <Trash2 size={13} /> Delete
              </Button>
            )}
          </div>
        }
      />

      <div className="mb-4 flex items-center gap-3">
        <StatusBadge status={status} />
        {latest.message && <span className="text-xs text-content-subtle">{latest.message}</span>}
      </div>

      {/* Metric tiles */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric icon={<Layers size={13} />} label="Epoch" value={`${(latest.epoch ?? 0).toFixed(2)} / ${latest.total_epochs ?? runInfo?.config?.epochs ?? '-'}`} />
        <Metric icon={<Activity size={13} />} label="Step" value={`${latest.step ?? 0} / ${latest.total_steps ?? '-'}`} />
        <Metric icon={<Gauge size={13} />} label="Loss" value={latest.loss != null ? latest.loss.toFixed(4) : '—'} />
        <Metric icon={<Gauge size={13} />} label="Val loss" value={latest.val_loss != null ? latest.val_loss.toFixed(4) : '—'} />
      </div>

      <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric icon={<Cpu size={13} />} label="LR" value={latest.learning_rate != null ? latest.learning_rate.toExponential(2) : '—'} />
        <Metric icon={<Activity size={13} />} label="Speed" value={latest.steps_per_sec != null ? `${latest.steps_per_sec}/s` : '—'} />
        <Metric icon={<Activity size={13} />} label="ETA" value={latest.eta_seconds != null ? `${Math.round(latest.eta_seconds)}s` : '—'} />
        <Metric icon={<Boxes size={13} />} label="Checkpoints" value={String(checkpoints.data?.length ?? 0)} />
      </div>

      <div className="mt-3">
        <Progress value={stepPct} />
      </div>

      {/* Loss chart */}
      <Card className="mt-5 p-4">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-content-subtle">Loss</p>
        {chartData.length < 2 ? (
          <div className="flex h-56 items-center justify-center text-sm text-content-subtle">
            {live ? (
              <span className="flex items-center gap-2">
                <Loader2 size={14} className="animate-spin" /> waiting for data…
              </span>
            ) : (
              'No metrics recorded.'
            )}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chartData}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="step" stroke="#7a7a85" fontSize={11} />
              <YAxis stroke="#7a7a85" fontSize={11} domain={['auto', 'auto']} />
              <Tooltip
                contentStyle={{ background: '#17171b', border: '1px solid #2a2a31', borderRadius: 8, fontSize: 12 }}
              />
              <Line type="monotone" dataKey="loss" stroke="#e5484d" dot={false} strokeWidth={2} isAnimationActive={false} />
              <Line type="monotone" dataKey="val_loss" stroke="#f5a623" dot={false} strokeWidth={1.5} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Continuous Security timeline (only when the run has security results) */}
      <SecurityTimelineCard runId={runId} live={live} />

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Checkpoints */}
        <Card>
          <div className="border-b border-border px-5 py-3">
            <h3 className="text-sm font-semibold text-content">Checkpoints</h3>
          </div>
          <div className="p-3">
            {(checkpoints.data?.length ?? 0) === 0 ? (
              <p className="px-2 py-4 text-center text-xs text-content-subtle">No checkpoints yet.</p>
            ) : (
              <ul className="space-y-1.5">
                {checkpoints.data!.map((c) => (
                  <li key={c.id} className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2 text-xs">
                    <span className="flex items-center gap-2 text-content">
                      step {c.step}
                      {c.is_best && <Badge tone="green">best</Badge>}
                    </span>
                    <span className="text-content-subtle">
                      loss {c.loss?.toFixed(3) ?? '—'} · val {c.val_loss?.toFixed(3) ?? '—'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>

        {/* Logs */}
        <Card>
          <div className="border-b border-border px-5 py-3">
            <h3 className="text-sm font-semibold text-content">Training Logs</h3>
          </div>
          <div className="max-h-64 overflow-y-auto p-4 font-mono text-[11px] text-content-muted">
            {(p?.logs ?? []).length === 0 ? (
              <p className="text-content-subtle">No logs yet.</p>
            ) : (
              p!.logs.map((l, i) => <div key={i}>{l}</div>)
            )}
          </div>
        </Card>
      </div>

      {/* Improvement recommendations (only meaningful once the run + security exist) */}
      {runInfo && <RecommendationsCard runId={runId} baseModel={runInfo.base_model} onApply={onApply} />}

      {terminal && <ReportCard runId={runId} />}

      {runInfo?.backend === 'simulation' && (
        <p className="mt-4 text-[11px] text-content-faint">
          This run uses the <span className="text-content-muted">Simulation</span> backend (no GPU
          required). Install the Unsloth stack and select it in the wizard for real LoRA/QLoRA training.
        </p>
      )}
    </div>
  );
}

// --- Improvement recommendations -------------------------------------------

function RecommendationsCard({
  runId,
  baseModel,
  onApply,
}: {
  runId: string;
  baseModel: string;
  onApply: (pf: WizardPrefill) => void;
}) {
  const analyze = useAnalyzeRecommendation();
  const decide = useDecideRecommendation();
  const [rec, setRec] = useState<Recommendation | null>(null);

  const apply = () => {
    if (!rec) return;
    onApply(prefillFromRecommendation(rec));
  };

  const run = async () => {
    const r = await analyze.mutate({ target_model: baseModel, run_id: runId });
    if (r) setRec(r);
  };

  const setDecision = async (status: 'accepted' | 'rejected') => {
    if (!rec) return;
    const r = await decide.mutate({ id: rec.id, status });
    if (r) {
      setRec(r);
      toast[status === 'accepted' ? 'success' : 'info'](`Recommendation ${status}`);
    }
  };

  if (!rec) {
    return (
      <Card className="mt-5 flex items-center justify-between p-4">
        <div>
          <p className="flex items-center gap-2 text-sm font-medium text-content">
            <Lightbulb size={15} className="text-uncertain" /> Improvement recommendations
          </p>
          <p className="mt-0.5 text-xs text-content-subtle">
            Analyze this run's security, config, and dataset for exactly how to improve the model.
          </p>
        </div>
        <Button size="sm" onClick={run} loading={analyze.isPending}>
          Analyze
        </Button>
      </Card>
    );
  }

  const p = rec.payload;
  const hp = p.hyperparameters;
  return (
    <Card className="mt-5 p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <p className="flex items-center gap-2 text-sm font-semibold text-content">
          <Lightbulb size={15} className="text-uncertain" /> Recommendations
        </p>
        <Badge tone={rec.status === 'accepted' ? 'green' : rec.status === 'rejected' ? 'grey' : 'amber'}>
          {rec.status}
        </Badge>
      </div>
      <p className="text-sm text-content-muted">{p.summary}</p>

      {p.weaknesses.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-content-subtle">Weaknesses</p>
          <div className="flex flex-wrap gap-1.5">
            {p.weaknesses.map((w) => (
              <Badge key={w.category} tone={w.severity === 'critical' || w.severity === 'high' ? 'red' : 'amber'}>
                {w.category} · {w.severity}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-content-subtle">Strategy & hyperparameters</p>
          <p className="text-xs text-content"><span className="font-medium">{p.strategy.method.toUpperCase()}</span> — {p.strategy.reason}</p>
          <ul className="mt-2 space-y-1 text-[11px] text-content-muted">
            <li>rank {hp.rank} / alpha {hp.alpha} — {hp.rationale.rank}</li>
            <li>{hp.epochs} epochs, lr {hp.learning_rate} — {hp.rationale.learning_rate}</li>
            <li>batch {hp.batch_size} × accum {hp.gradient_accumulation}, {hp.scheduler}, warmup {hp.warmup_steps}</li>
          </ul>
        </div>
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-content-subtle">Recommended datasets</p>
          {p.datasets.public.map((d) => (
            <a key={d.name} href={d.url} target="_blank" rel="noreferrer"
               className="block text-xs text-red-400 hover:underline">{d.name}</a>
          ))}
          <p className="mt-1 text-[11px] text-content-subtle">Suggestions only — never downloaded automatically.</p>
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-border bg-base p-3">
        <p className="text-xs text-content">
          Estimated <span className="font-semibold text-pass">+{p.prediction.expected_security_gain}</span> security
          points (benchmark ≈ +{p.prediction.expected_benchmark_gain}) · confidence {p.prediction.confidence}
        </p>
        <p className="mt-1 text-[11px] text-content-subtle">{p.prediction.disclaimer}</p>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={apply}>
          <Rocket size={13} /> Apply
        </Button>
        <Button variant="secondary" size="sm" onClick={() => setDecision('accepted')} loading={decide.isPending} disabled={rec.status === 'accepted'}>
          Accept
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setDecision('rejected')} disabled={rec.status === 'rejected'}>
          Reject
        </Button>
        <Button variant="ghost" size="sm" onClick={run} loading={analyze.isPending}>
          Re-analyze
        </Button>
      </div>
      <p className="mt-2 text-[11px] text-content-faint">
        Apply opens the training wizard prefilled with these settings — nothing launches until you review and confirm.
      </p>
    </Card>
  );
}

// --- Engineering report (composed from existing data) ----------------------

function ReportCard({ runId }: { runId: string }) {
  const report = useTrainingReport(runId);
  const r = report.data;

  const exportReport = () => {
    if (!r) return;
    const blob = new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `redforge-report-${runId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (report.isLoading || !r) {
    return (
      <Card className="mt-5 p-4">
        <p className="flex items-center gap-2 text-sm font-medium text-content">
          <FileText size={15} /> Engineering report
        </p>
        <p className="mt-1 text-xs text-content-subtle">Composing from run, security, and recommendation data…</p>
      </Card>
    );
  }

  const cmp = r.checkpoint_comparison;
  return (
    <Card className="mt-5 p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <p className="flex items-center gap-2 text-sm font-semibold text-content">
          <FileText size={15} /> Engineering report
        </p>
        <Button variant="secondary" size="sm" onClick={exportReport}>
          <Download size={13} /> Export JSON
        </Button>
      </div>
      <p className="text-sm text-content-muted">{r.executive_summary}</p>

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <ReportStat label="Security delta" value={cmp?.delta != null ? `${cmp.delta > 0 ? '+' : ''}${cmp.delta}` : '—'} />
        <ReportStat label="Checkpoints" value={String(r.security_timeline.length)} />
        <ReportStat
          label="Recommendations"
          value={`${r.accepted_recommendations.length} accepted · ${r.rejected_recommendations.length} rejected`}
        />
      </div>

      {r.benchmarks.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-content-subtle">Benchmarks</p>
          <ul className="space-y-1.5">
            {r.benchmarks.map((b) => (
              <li key={b.id} className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2 text-xs">
                <span className="min-w-0">
                  <span className="block truncate text-content">{b.label}</span>
                  <span className="block truncate text-[11px] text-content-subtle">{b.suites.join(', ')}</span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {b.id === r.best_benchmark?.id && <Badge tone="green">best</Badge>}
                  {b.overall_score != null && <span className="font-semibold text-content">{b.overall_score}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {r.remaining_risks.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-content-subtle">Remaining risks</p>
          <div className="flex flex-wrap gap-1.5">
            {r.remaining_risks.map((c) => (
              <Badge key={c} tone="amber">{c}</Badge>
            ))}
          </div>
        </div>
      )}

      <p className="mt-4 text-[11px] text-content-faint">
        Composed from existing run, dataset, security, and recommendation data — nothing is stored or uploaded.
      </p>
    </Card>
  );
}

function ReportStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-base p-3">
      <p className="text-[11px] text-content-subtle">{label}</p>
      <p className="mt-0.5 text-sm font-medium text-content">{value}</p>
    </div>
  );
}

// --- Continuous Security timeline ------------------------------------------

function SecurityTimelineCard({ runId, live }: { runId: string; live: boolean }) {
  const timeline = useSecurityTimeline(runId, live ? 3000 : 0);
  const rows = timeline.data ?? [];
  if (rows.length === 0) return null; // only shown when the run has security results

  const done = rows.filter((r) => r.score != null);
  const pending = rows.filter((r) => r.status === 'pending' || r.status === 'running').length;
  const data = done.map((r) => ({ step: r.step, score: r.score }));
  const first = done[0]?.score ?? null;
  const last = done[done.length - 1]?.score ?? null;
  const trend = first != null && last != null ? last - first : null;

  return (
    <Card className="mt-5 p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">
          <Shield size={13} className="text-red-400" /> Security Timeline
        </p>
        <div className="flex items-center gap-2 text-xs text-content-subtle">
          {pending > 0 && (
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-uncertain" /> {pending} queued
            </span>
          )}
          {trend != null && (
            <span className={trend >= 0 ? 'text-pass' : 'text-fail'}>
              {trend >= 0 ? '▲' : '▼'} {Math.abs(trend).toFixed(0)}
            </span>
          )}
        </div>
      </div>
      {data.length < 1 ? (
        <p className="py-6 text-center text-xs text-content-subtle">Evaluating checkpoints…</p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={data}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="step" stroke="#7a7a85" fontSize={11} />
              <YAxis stroke="#7a7a85" fontSize={11} domain={[0, 100]} />
              <Tooltip contentStyle={{ background: '#17171b', border: '1px solid #2a2a31', borderRadius: 8, fontSize: 12 }} />
              <Line type="monotone" dataKey="score" stroke="#3fb950" dot strokeWidth={2} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {done.map((r) => (
              <span key={r.id} className="rounded-md border border-border bg-surface px-2 py-0.5 text-[11px] text-content-muted">
                step {r.step}: <span className="font-semibold text-content">{r.score}</span>
              </span>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

// --- small helpers ---------------------------------------------------------

const inputCls =
  'w-full rounded-lg border border-border bg-base px-3 py-2 text-sm text-content placeholder:text-content-faint rf-focus';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs text-content-subtle">{label}</label>
      {children}
    </div>
  );
}

function Num({ label, v, set, step }: { label: string; v: number; set: (x: number) => void; step?: number }) {
  return (
    <Field label={label}>
      <input type="number" step={step} value={v} onChange={(e) => set(Number(e.target.value))} className={inputCls} />
    </Field>
  );
}

function ReviewRow({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2">
      <span className="text-content-subtle">{k}</span>
      <span className="font-medium text-content">{v}</span>
    </div>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2.5">
      <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-content-faint">
        {icon}
        {label}
      </span>
      <p className="mt-1 text-sm font-semibold text-content">{value}</p>
    </div>
  );
}
