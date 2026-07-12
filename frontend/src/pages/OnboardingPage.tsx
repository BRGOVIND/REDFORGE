import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Boxes,
  CheckCircle2,
  Copy,
  Cpu,
  Download,
  ExternalLink,
  HardDrive,
  Loader2,
  MemoryStick,
  Rocket,
  Server,
  ShieldCheck,
  Sparkles,
  XCircle,
} from 'lucide-react';
import { Badge, Button, Card } from '../components/ui';
import { useHealth, useModelCatalog, useProviders, useRecommendations } from '../hooks/queries';
import { getModelPullStatus, startModelPull } from '../api/endpoints';
import { toast } from '../lib/toast';
import { cn } from '../lib/cn';
import type {
  HealthCheck,
  HealthStatus,
  ModelRecommendation,
  OnboardingRecommendations,
  PullStatus,
} from '../api/types';

/** LocalStorage key that records first-run completion. Remove it to re-run. */
export const ONBOARDED_KEY = 'redforge_onboarded';

const STEPS = ['Welcome', 'System Scan', 'Runtime', 'Models', 'Ready'];

const SUPPORTED_RUNTIMES = [
  { name: 'Ollama', url: 'https://ollama.com/download', hint: 'Recommended · install, then run: ollama serve' },
  { name: 'LM Studio', url: 'https://lmstudio.ai', hint: 'Enable its local server (port 1234)' },
  { name: 'llama.cpp', url: 'https://github.com/ggml-org/llama.cpp', hint: 'Run llama-server (port 8080)' },
  { name: 'vLLM', url: 'https://docs.vllm.ai', hint: 'Start its OpenAI-compatible server (port 8000)' },
];

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success('Copied', text);
  } catch {
    toast.error('Could not copy');
  }
}

function StatusDot({ status }: { status?: HealthStatus }) {
  if (status === 'healthy') return <CheckCircle2 size={17} className="text-pass" />;
  if (status === 'warning') return <AlertTriangle size={17} className="text-uncertain" />;
  if (status === 'error') return <XCircle size={17} className="text-fail" />;
  return <Loader2 size={17} className="animate-spin text-content-faint" />;
}

function CommandRow({ command }: { command: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-black/40 px-3 py-2 font-mono text-[13px] text-content">
      <span className="truncate">
        <span className="text-content-faint">$ </span>
        {command}
      </span>
      <button
        onClick={() => copy(command)}
        className="rf-focus shrink-0 rounded p-1 text-content-subtle hover:text-content"
        aria-label={`Copy: ${command}`}
      >
        <Copy size={13} />
      </button>
    </div>
  );
}

export default function OnboardingPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);

  // Consume the existing services — no detection logic is re-implemented.
  const scanning = step >= 1 && step <= 3;
  const health = useHealth(false, scanning ? 4000 : 0);
  const providers = useProviders(step >= 2 ? 6000 : 0, step >= 2);
  const models = useModelCatalog(step >= 3 ? 5000 : 0, step >= 3);
  // Hardware-aware recommendations (runtime + models) once past the scan.
  const recs = useRecommendations(step >= 2);

  const checks = health.data?.checks ?? [];
  const check = (id: string): HealthCheck | undefined => checks.find((c) => c.id === id);

  // Runtime detection comes from the Health Engine's live provider probe; the
  // provider list (Runtime Manager) gives the registered count.
  const providerHealth = check('provider_health');
  const runtimeDetected = providerHealth?.status === 'healthy';
  const detectedName = runtimeDetected
    ? ((providerHealth?.metadata?.provider as string | undefined) ?? 'runtime')
    : null;
  const providerTotal = (providers.data?.providers ?? []).length;
  const rawCount = check('installed_models')?.metadata?.count;
  const modelTotal = models.data?.total ?? (typeof rawCount === 'number' ? rawCount : 0);

  const complete = () => {
    localStorage.setItem(ONBOARDED_KEY, '1');
    navigate('/', { replace: true });
  };

  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));

  return (
    <div className="min-h-screen bg-base">
      <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col px-6 py-10">
        {/* Brand + progress */}
        <div className="mb-8 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img src="/logo-mark.png" alt="RedForge" width={28} height={28} className="h-7 w-7 rounded-lg" />
            <span className="text-sm font-semibold text-content">RedForge</span>
          </div>
          <span className="font-mono text-[11px] text-content-faint">
            {step + 1} / {STEPS.length}
          </span>
        </div>
        <div className="mb-8 flex gap-1.5" aria-hidden>
          {STEPS.map((s, i) => (
            <div
              key={s}
              className={cn(
                'h-1 flex-1 rounded-full transition-colors',
                i <= step ? 'bg-red-500' : 'bg-overlay'
              )}
            />
          ))}
        </div>

        {/* Step body */}
        <div className="flex-1">
          {step === 0 && <Welcome />}
          {step === 1 && <SystemScan loading={health.isLoading && !health.data} check={check} />}
          {step === 2 && (
            <RuntimeDetection
              detected={runtimeDetected}
              detectedName={detectedName}
              recommendation={recs.data?.runtime}
              hardware={recs.data?.hardware}
            />
          )}
          {step === 3 && (
            <ModelDetection
              total={modelTotal}
              groups={models.data?.providers ?? []}
              loading={models.isLoading && !models.data}
              recommendations={recs.data?.models}
              canPull={recs.data?.runtime.state === 'running'}
              onPulled={() => models.refetch?.()}
            />
          )}
          {step === 4 && (
            <Ready
              status={health.data?.status}
              ready={health.data?.ready ?? false}
              detectedName={detectedName}
              providerTotal={providerTotal}
              modelTotal={modelTotal}
            />
          )}
        </div>

        {/* Nav */}
        <div className="mt-10 flex items-center justify-between">
          {step > 0 ? (
            <Button variant="ghost" size="sm" onClick={back}>
              <ArrowLeft size={14} /> Back
            </Button>
          ) : (
            <span />
          )}
          {step < STEPS.length - 1 ? (
            <Button onClick={next}>
              {step === 0 ? 'Get started' : 'Continue'} <ArrowRight size={15} />
            </Button>
          ) : (
            <Button onClick={complete}>
              <Rocket size={16} /> Launch RedForge
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Step 1: Welcome -------------------------------------------------------

function Welcome() {
  const points = [
    'A local red-teaming laboratory for large language models.',
    'Everything runs on your own machine — models, prompts, and findings.',
    'No cloud dependency, no API keys, nothing leaves your computer.',
    'Open source and yours to run, fork, and audit.',
  ];
  return (
    <div>
      <span className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-red-600 text-white">
        <ShieldCheck size={22} />
      </span>
      <h1 className="text-2xl font-semibold tracking-tight text-content">Welcome to RedForge</h1>
      <p className="mt-2 text-sm text-content-muted">
        Let's get you set up. This takes about a minute and only happens once.
      </p>
      <ul className="mt-6 space-y-3">
        {points.map((p) => (
          <li key={p} className="flex items-start gap-2.5 text-sm text-content">
            <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-pass" />
            {p}
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- Step 2: System Scan (Health Engine) -----------------------------------

function SystemScan({
  loading,
  check,
}: {
  loading: boolean;
  check: (id: string) => HealthCheck | undefined;
}) {
  const rows: { label: string; id: string }[] = [
    { label: 'Operating System', id: 'os' },
    { label: 'CPU', id: 'cpu' },
    { label: 'GPU', id: 'gpu' },
    { label: 'Memory', id: 'ram' },
    { label: 'Disk', id: 'disk' },
    { label: 'Runtime', id: 'provider_health' },
    { label: 'Installed Providers', id: 'runtime_providers' },
    { label: 'Models', id: 'installed_models' },
    { label: 'Backend', id: 'backend_status' },
  ];
  return (
    <div>
      <h2 className="text-xl font-semibold tracking-tight text-content">System scan</h2>
      <p className="mt-1 text-sm text-content-muted">
        Checking your environment via the health engine.
      </p>
      <Card className="mt-6 overflow-hidden">
        <ul className="divide-y divide-border">
          {rows.map((r) => {
            const c = check(r.id);
            return (
              <li key={r.id} className="flex items-center justify-between gap-3 px-5 py-3">
                <div className="flex items-center gap-3">
                  <StatusDot status={loading ? undefined : c?.status} />
                  <span className="text-sm text-content">{r.label}</span>
                </div>
                <span className="max-w-[55%] truncate text-right text-xs text-content-subtle">
                  {loading ? 'scanning…' : c?.message ?? '—'}
                </span>
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}

// --- Step 3: Runtime Detection (Runtime Manager) ---------------------------

function HardwareStrip({ hardware }: { hardware: OnboardingRecommendations['hardware'] }) {
  const gb = (mb: number | null | undefined) =>
    typeof mb === 'number' ? `${(mb / 1024).toFixed(1)} GB` : '—';
  const gpu = hardware.gpu.available
    ? hardware.gpu.name ?? 'GPU'
    : 'CPU only';
  const tiles: { icon: ReactNode; label: string; value: string }[] = [
    { icon: <Cpu size={14} />, label: 'CPU', value: `${hardware.cpu_count ?? '—'} cores` },
    { icon: <MemoryStick size={14} />, label: 'RAM', value: gb(hardware.ram_total_mb) },
    {
      icon: <HardDrive size={14} />,
      label: hardware.gpu.available ? 'VRAM' : 'GPU',
      value: hardware.gpu.available ? gb(hardware.gpu.vram_total_mb) : 'none',
    },
    { icon: <Server size={14} />, label: 'Accelerator', value: gpu },
  ];
  return (
    <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-lg border border-border bg-surface px-3 py-2">
          <span className="flex items-center gap-1.5 text-[11px] text-content-subtle">
            {t.icon}
            {t.label}
          </span>
          <p className="mt-0.5 truncate text-xs font-medium text-content" title={t.value}>
            {t.value}
          </p>
        </div>
      ))}
    </div>
  );
}

function RuntimeDetection({
  detected,
  detectedName,
  recommendation,
  hardware,
}: {
  detected: boolean;
  detectedName: string | null;
  recommendation?: OnboardingRecommendations['runtime'];
  hardware?: OnboardingRecommendations['hardware'];
}) {
  return (
    <div>
      <h2 className="text-xl font-semibold tracking-tight text-content">Runtime detection</h2>
      <p className="mt-1 text-sm text-content-muted">
        RedForge runs models through a local runtime provider.
      </p>

      {hardware && <HardwareStrip hardware={hardware} />}

      {recommendation && (
        <div className="mt-5 flex items-start gap-2.5 rounded-lg border border-red-500/30 bg-red-soft px-4 py-3">
          <Sparkles size={16} className="mt-0.5 shrink-0 text-red-400" />
          <div>
            <p className="text-sm font-medium text-content">
              Recommended runtime: <span className="font-mono">{recommendation.provider}</span>
            </p>
            <p className="mt-0.5 text-xs text-content-muted">{recommendation.reason}</p>
            {recommendation.action && (
              <p className="mt-1 text-xs text-content-subtle">{recommendation.action}</p>
            )}
          </div>
        </div>
      )}

      {detected ? (
        <Card className="mt-6 p-5">
          <div className="flex items-center gap-2">
            <Badge tone="green">
              <CheckCircle2 size={13} /> Runtime detected
            </Badge>
          </div>
          <p className="mt-3 text-sm text-content">
            Active runtime: <span className="font-mono text-content">{detectedName ?? 'runtime'}</span> is reachable.
          </p>
        </Card>
      ) : (
        <Card className="mt-6 p-5">
          <div className="flex items-center gap-2 text-uncertain">
            <AlertTriangle size={16} />
            <span className="text-sm font-medium">No runtime detected</span>
          </div>
          <p className="mt-2 text-sm text-content-muted">
            Install one of the supported runtimes below, then this step updates on its own. RedForge
            never installs anything for you.
          </p>
        </Card>
      )}

      <p className="mb-3 mt-6 text-xs uppercase tracking-wide text-content-subtle">Supported runtimes</p>
      <div className="space-y-3">
        {SUPPORTED_RUNTIMES.map((rt) => (
          <div key={rt.name} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-3">
            <div className="flex items-center gap-3">
              <Server size={16} className="text-content-muted" />
              <div>
                <p className="text-sm font-medium text-content">{rt.name}</p>
                <p className="text-xs text-content-subtle">{rt.hint}</p>
              </div>
            </div>
            <a href={rt.url} target="_blank" rel="noreferrer">
              <Button variant="secondary" size="sm">
                <Download size={13} /> Install
                <ExternalLink size={12} />
              </Button>
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Step 4: Model Detection (Model Manager) -------------------------------

function ModelPullRow({
  model,
  installed,
  canPull,
  onPulled,
}: {
  model: ModelRecommendation;
  installed: boolean;
  canPull: boolean;
  onPulled: () => void;
}) {
  const [pull, setPull] = useState<PullStatus | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current);
  }, []);

  const start = async () => {
    try {
      const s = await startModelPull(model.name);
      setPull(s);
      timer.current = setInterval(async () => {
        try {
          const st = await getModelPullStatus(model.name);
          setPull(st);
          if (st.done) {
            if (timer.current) clearInterval(timer.current);
            if (st.error) toast.error(`Download failed: ${model.name}`, st.error);
            else {
              toast.success(`Downloaded ${model.name}`);
              onPulled();
            }
          }
        } catch {
          if (timer.current) clearInterval(timer.current);
        }
      }, 1200);
    } catch {
      toast.error('Could not start download', model.name);
    }
  };

  const pulling = pull !== null && !pull.done;
  const pct = pull?.percent ?? null;

  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate font-mono text-[13px] text-content">{model.name}</span>
            {model.recommended && (
              <Badge tone="green">
                <Sparkles size={11} /> Best fit
              </Badge>
            )}
            {!model.fits && <Badge tone="amber">Heavy</Badge>}
          </div>
          <p className="mt-0.5 text-xs text-content-subtle">
            {model.note} · ~{(model.estimated_ram_mb / 1024).toFixed(1)} GB
          </p>
        </div>
        {installed ? (
          <Badge tone="green">
            <CheckCircle2 size={12} /> Installed
          </Badge>
        ) : canPull ? (
          <Button variant="secondary" size="sm" onClick={start} disabled={pulling} loading={pulling}>
            {!pulling && <Download size={13} />}
            {pulling ? (pct !== null ? `${pct}%` : 'Downloading…') : 'Download'}
          </Button>
        ) : (
          <span className="text-[11px] text-content-faint">start the runtime to download</span>
        )}
      </div>
      {pulling && (
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-overlay">
          <div
            className="h-full bg-red-500 transition-all duration-500 ease-out"
            style={{ width: pct !== null ? `${pct}%` : '35%' }}
          />
        </div>
      )}
    </div>
  );
}

function RecommendedModels({
  recommendations,
  installedNames,
  canPull,
  onPulled,
}: {
  recommendations: OnboardingRecommendations['models'];
  installedNames: Set<string>;
  canPull: boolean;
  onPulled: () => void;
}) {
  const fitting = recommendations.models.filter((m) => m.fits);
  const list = (fitting.length ? fitting : recommendations.models).slice(0, 4);
  return (
    <Card className="mt-6 p-5">
      <div className="flex items-center gap-2">
        <Sparkles size={15} className="text-red-400" />
        <span className="text-sm font-medium text-content">Recommended for your hardware</span>
      </div>
      <p className="mt-1 text-xs text-content-subtle">
        Based on {recommendations.budget_source}
        {recommendations.budget_mb ? ` (~${(recommendations.budget_mb / 1024).toFixed(1)} GB)` : ''}.
        {canPull ? ' Download runs through your local runtime.' : ''}
      </p>
      <div className="mt-3 space-y-2">
        {list.map((m) => (
          <ModelPullRow
            key={m.name}
            model={m}
            installed={installedNames.has(m.name)}
            canPull={canPull}
            onPulled={onPulled}
          />
        ))}
      </div>
    </Card>
  );
}

function ModelDetection({
  total,
  groups,
  loading,
  recommendations,
  canPull,
  onPulled,
}: {
  total: number;
  groups: { label: string; models: { name: string }[] }[];
  loading: boolean;
  recommendations?: OnboardingRecommendations['models'];
  canPull: boolean;
  onPulled: () => void;
}) {
  const withModels = groups.filter((g) => g.models.length > 0);
  const installedNames = new Set(groups.flatMap((g) => g.models.map((m) => m.name)));
  return (
    <div>
      <h2 className="text-xl font-semibold tracking-tight text-content">Model detection</h2>
      <p className="mt-1 text-sm text-content-muted">Looking for models across your providers.</p>

      {recommendations && (
        <RecommendedModels
          recommendations={recommendations}
          installedNames={installedNames}
          canPull={canPull}
          onPulled={onPulled}
        />
      )}

      {loading ? (
        <Card className="mt-6 flex items-center gap-2 p-5 text-sm text-content-muted">
          <Loader2 size={15} className="animate-spin" /> Scanning providers…
        </Card>
      ) : total === 0 ? (
        <Card className="mt-6 p-5">
          <div className="flex items-center gap-2">
            <Boxes size={16} className="text-content-muted" />
            <span className="text-sm font-medium text-content">No models were found.</span>
          </div>
          <p className="mb-3 mt-2 text-sm text-content-muted">
            {canPull
              ? 'Download one of the recommended models above, then continue.'
              : 'Add at least one model to your runtime, then continue. Loading a model differs by runtime — see your runtime’s docs.'}
          </p>
          {canPull && (
            <div className="space-y-2">
              {['ollama pull llama3.2:3b', 'ollama pull llama3.1:8b'].map((c) => (
                <CommandRow key={c} command={c} />
              ))}
            </div>
          )}
          <a
            href="https://ollama.com/library"
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-flex items-center gap-1 text-xs text-content-subtle hover:text-content rf-focus"
          >
            Browse the Ollama model library <ExternalLink size={12} />
          </a>
        </Card>
      ) : (
        <Card className="mt-6 p-5">
          <div className="flex items-center gap-2">
            <Badge tone="green">
              <CheckCircle2 size={13} /> {total} model{total !== 1 ? 's' : ''} found
            </Badge>
          </div>
          <div className="mt-4 space-y-3">
            {withModels.map((g) => (
              <div key={g.label}>
                <p className="text-xs text-content-subtle">{g.label}</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {g.models.slice(0, 8).map((m) => (
                    <span key={m.name} className="rounded-md bg-elevated px-2 py-0.5 font-mono text-[11px] text-content-muted">
                      {m.name}
                    </span>
                  ))}
                  {g.models.length > 8 && (
                    <span className="text-[11px] text-content-faint">+{g.models.length - 8} more</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

// --- Step 5: Ready ---------------------------------------------------------

function Ready({
  status,
  ready,
  detectedName,
  providerTotal,
  modelTotal,
}: {
  status?: HealthStatus;
  ready: boolean;
  detectedName: string | null;
  providerTotal: number;
  modelTotal: number;
}) {
  const tone = status === 'error' ? 'red' : status === 'warning' ? 'amber' : 'green';
  return (
    <div>
      <span className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-red-600 text-white">
        <Rocket size={22} />
      </span>
      <h2 className="text-2xl font-semibold tracking-tight text-content">
        {ready ? 'System ready' : 'Almost there'}
      </h2>
      <p className="mt-2 text-sm text-content-muted">
        {ready
          ? "You're all set — RedForge is ready for your first evaluation."
          : 'You can launch now and finish any remaining setup from the app.'}
      </p>

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SummaryTile icon={<Server size={15} />} label="Runtime" value={detectedName ?? 'None'} />
        <SummaryTile icon={<Boxes size={15} />} label="Models" value={String(modelTotal)} />
        <SummaryTile icon={<Cpu size={15} />} label="Health" value={<Badge tone={tone}>{status ?? '—'}</Badge>} />
      </div>
      <p className="mt-3 text-xs text-content-subtle">{providerTotal} runtime providers available.</p>
    </div>
  );
}

function SummaryTile({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-xl border border-border bg-surface p-4">
      <span className="flex items-center gap-1.5 text-xs text-content-subtle">
        {icon}
        {label}
      </span>
      <span className="text-lg font-semibold text-content">{value}</span>
    </div>
  );
}
