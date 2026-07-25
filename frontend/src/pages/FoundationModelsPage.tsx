import { useState } from 'react';
import {
  CheckCircle2,
  Cpu,
  Package,
  Plus,
  RadioTower,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Wand2,
  X,
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
  useDeleteFoundationModel,
  useDiscoverModels,
  useFoundationModelRuntimes,
  useFoundationModels,
  useRegisterFoundationModel,
  useResolveRuntimeModel,
  useResolveRuntimeModelEntry,
  useRuntimeModels,
  useSyncFoundationModel,
  useSyncRuntimeModels,
  useUnresolvedRuntimeModels,
} from '../hooks/queries';
import { errorMessage } from '../api/client';
import { relativeTime } from '../lib/format';
import { toast } from '../lib/toast';
import type { DiscoverySummary, FoundationModel, ResolutionCandidate, ResolutionResult, RuntimeModel } from '../api/types';

const INPUT =
  'w-full rounded-lg border border-border bg-base px-3 py-2 text-xs text-content placeholder:text-content-faint focus:border-red-500 rf-focus';

const STATUS_TONE: Record<string, 'green' | 'red' | 'amber' | 'grey'> = {
  local: 'green',
  referenced: 'grey',
  downloading: 'amber',
  invalid: 'red',
};

const SOURCE_LABEL: Record<string, string> = {
  hf_hub: 'Hugging Face',
  local_import: 'Local import',
  resolved_from_runtime: 'Resolved from runtime',
};

export default function FoundationModelsPage() {
  const models = useFoundationModels();
  const runtimeModels = useRuntimeModels();
  const unresolved = useUnresolvedRuntimeModels();
  const discover = useDiscoverModels();
  const [registerOpen, setRegisterOpen] = useState(false);
  const [resolveOpen, setResolveOpen] = useState(false);
  const [prefill, setPrefill] = useState('');
  const [detail, setDetail] = useState<FoundationModel | null>(null);

  const list = models.data ?? [];
  const runtimeList = runtimeModels.data ?? [];
  const unresolvedCount = (unresolved.data ?? []).length;

  const openRegister = (hfRepo = '') => {
    setPrefill(hfRepo);
    setResolveOpen(false);
    setRegisterOpen(true);
  };

  const runDiscovery = async () => {
    try {
      const summary = await discover.mutate();
      if (summary) announceDiscovery(summary);
    } catch (err) {
      toast.error('Discovery failed', errorMessage(err));
    }
  };

  return (
    <div>
      <PageHeader
        title="Foundation Models"
        description="Training-domain model identities. RedForge discovers the models you already have installed and resolves them automatically — no Hugging Face knowledge required. Everything stays local."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setResolveOpen(true)}>
              <Search size={14} /> Resolve
            </Button>
            <Button variant="secondary" size="sm" onClick={() => openRegister()}>
              <Plus size={14} /> Register manually
            </Button>
            <Button size="sm" onClick={runDiscovery} loading={discover.isPending}>
              <Sparkles size={14} /> Discover local models
            </Button>
          </div>
        }
      />

      {/* First-run / needs-attention banner */}
      <WelcomeBanner
        foundationCount={list.length}
        runtimeCount={runtimeList.length}
        unresolvedCount={unresolvedCount}
        loading={runtimeModels.isLoading || models.isLoading}
        onDiscover={runDiscovery}
        discovering={discover.isPending}
      />

      {/* Local runtime models — the automatic-discovery surface */}
      <RuntimeModelsPanel
        models={runtimeList}
        loading={runtimeModels.isLoading}
        onImport={openRegister}
      />

      {/* Foundation Models (identities) */}
      <p className="mb-2 mt-6 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">
        <Package size={13} /> Foundation model identities
      </p>
      {models.isLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <Card className="p-4">
          <EmptyState
            icon={<Package size={24} />}
            title="No foundation models yet"
            description="Discover your local models above, or register a Hugging Face checkpoint manually."
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((m) => (
            <ModelCard key={m.id} model={m} onOpen={() => setDetail(m)} />
          ))}
        </div>
      )}

      {registerOpen && (
        <RegisterDialog
          defaultRepo={prefill}
          onClose={() => {
            setRegisterOpen(false);
            setPrefill('');
          }}
        />
      )}
      {resolveOpen && <ResolveDialog onClose={() => setResolveOpen(false)} onPrefill={openRegister} />}
      {detail && <MetadataDrawer model={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function announceDiscovery(s: DiscoverySummary) {
  if (s.error) {
    toast.error('Runtime unreachable', s.error);
    return;
  }
  if (s.discovered === 0) {
    toast.info(s.online ? 'No local models found' : 'Runtime offline',
      s.online ? 'No runtime models are installed yet.' : 'Could not reach the runtime provider.');
    return;
  }
  const parts = [`${s.resolved} resolved`];
  if (s.registered) parts.push(`${s.registered} newly imported`);
  if (s.needs_resolution) parts.push(`${s.needs_resolution} need attention`);
  toast.success(`Discovered ${s.discovered} local model${s.discovered === 1 ? '' : 's'}`, parts.join(' · '));
}

// ---------------------------------------------------------------------------
// Welcome / needs-attention banner (first-run experience)
// ---------------------------------------------------------------------------

function WelcomeBanner({
  foundationCount, runtimeCount, unresolvedCount, loading, onDiscover, discovering,
}: {
  foundationCount: number; runtimeCount: number; unresolvedCount: number;
  loading: boolean; onDiscover: () => void; discovering: boolean;
}) {
  const [dismissed, setDismissed] = useState(false);
  if (loading || dismissed) return null;

  // First run: nothing discovered or registered yet → invite discovery.
  const firstRun = runtimeCount === 0 && foundationCount === 0;
  if (firstRun) {
    return (
      <Card className="mb-4 border-red-700/30 bg-red-soft/40 p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Sparkles size={18} className="text-red-400" />
            <div>
              <p className="text-sm font-semibold text-content">Welcome to RedForge</p>
              <p className="text-xs text-content-subtle">
                Let RedForge find the AI models you already have installed and make them available for training.
              </p>
            </div>
          </div>
          <Button size="sm" onClick={onDiscover} loading={discovering}>
            <Sparkles size={14} /> Discover my models
          </Button>
        </div>
      </Card>
    );
  }

  // Some runtime models need an operator decision.
  if (unresolvedCount > 0) {
    return (
      <Card className="mb-4 border-amber-500/30 bg-uncertain/5 p-3">
        <div className="flex items-center justify-between gap-3">
          <p className="flex items-center gap-2 text-xs text-content">
            <RadioTower size={14} className="text-uncertain" />
            <span>
              <span className="font-semibold">{unresolvedCount}</span> local model
              {unresolvedCount === 1 ? '' : 's'} need manual resolution — confirm a match below.
            </span>
          </p>
          <button className="text-[11px] text-content-subtle hover:text-content" onClick={() => setDismissed(true)}>
            Dismiss
          </button>
        </div>
      </Card>
    );
  }
  return null;
}

// ---------------------------------------------------------------------------
// Runtime models panel — discovered, resolved, and unavailable local models
// ---------------------------------------------------------------------------

const RUNTIME_STATUS_TONE: Record<string, 'green' | 'amber' | 'grey'> = {
  resolved: 'green',
  needs_resolution: 'amber',
  unavailable: 'grey',
};

function RuntimeModelsPanel({
  models, loading, onImport,
}: {
  models: RuntimeModel[]; loading: boolean; onImport: (hfRepo: string) => void;
}) {
  const sync = useSyncRuntimeModels();

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="flex items-center gap-2 text-sm font-semibold text-content">
          <Cpu size={15} className="text-red-400" /> Local runtime models
        </p>
        <Button
          variant="ghost"
          size="sm"
          loading={sync.isPending}
          onClick={async () => {
            try {
              const s = await sync.mutate();
              if (s) announceDiscovery(s);
            } catch (err) {
              toast.error('Sync failed', errorMessage(err));
            }
          }}
        >
          <RefreshCw size={13} /> Sync
        </Button>
      </div>

      {loading ? (
        <Skeleton className="h-16" />
      ) : models.length === 0 ? (
        <p className="py-2 text-[11px] text-content-subtle">
          No runtime models discovered yet. Click <span className="text-content">Discover local models</span> above —
          if your runtime (e.g. Ollama) is offline, nothing will be found until it's reachable.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {models.map((m) => (
            <RuntimeModelRow key={m.id} model={m} onImport={onImport} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function RuntimeModelRow({ model, onImport }: { model: RuntimeModel; onImport: (hfRepo: string) => void }) {
  const resolve = useResolveRuntimeModelEntry();
  const top = model.candidates[0];

  const adopt = async () => {
    try {
      const res = await resolve.mutate({ id: model.id });
      if (res?.foundation_model) toast.success('Imported', res.foundation_model.hf_repo);
      else toast.info('Nothing to resolve', res?.note ?? 'No candidate available — search Hugging Face.');
    } catch (err) {
      toast.error('Resolve failed', errorMessage(err));
    }
  };

  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-border bg-base px-3 py-2 text-xs">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate text-content">{model.runtime_ref}</span>
          <Badge tone={RUNTIME_STATUS_TONE[model.status] ?? 'grey'}>
            {model.status === 'resolved' && <CheckCircle2 size={11} />}
            {model.status.replace('_', ' ')}
          </Badge>
          {!model.available && <Badge tone="grey">unavailable</Badge>}
        </div>
        <span className="mt-0.5 block truncate text-[11px] text-content-subtle">
          Detected from {model.provider}
          {top && model.status !== 'resolved' && ` · suggests ${top.hf_repo} (${Math.round(top.confidence * 100)}%)`}
          {model.last_synced_at && ` · synced ${relativeTime(model.last_synced_at)}`}
        </span>
      </div>
      {model.status === 'needs_resolution' && (
        <div className="flex shrink-0 items-center gap-1">
          {top && (
            <Button size="sm" onClick={adopt} loading={resolve.isPending}>
              <Wand2 size={13} /> Resolve
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => onImport(top?.hf_repo ?? '')}>
            Import…
          </Button>
        </div>
      )}
    </li>
  );
}

function StatusDot({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? 'grey';
  const color =
    tone === 'green' ? 'bg-pass' : tone === 'red' ? 'bg-fail' : tone === 'amber' ? 'bg-uncertain' : 'bg-content-faint';
  return <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${color}`} />;
}

function ModelCard({ model, onOpen }: { model: FoundationModel; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className="flex flex-col rounded-xl border border-border bg-surface p-4 text-left transition-colors hover:border-border-strong rf-focus"
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-semibold text-content">
          <Package size={15} className="text-red-400" />
          <span className="truncate">{model.hf_repo.split('/').pop()}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <StatusDot status={model.status} />
          <Badge tone={STATUS_TONE[model.status] ?? 'grey'}>{model.status}</Badge>
        </span>
      </div>
      <p className="mb-2 truncate text-[11px] text-content-subtle">{model.hf_repo}</p>
      <div className="mt-auto flex flex-wrap gap-1.5 text-[10px]">
        {model.architecture && <Badge tone="grey">{model.architecture}</Badge>}
        {model.quantization && model.quantization !== 'none' && <Badge tone="amber">{model.quantization}</Badge>}
        <Badge tone="grey">{model.format}</Badge>
      </div>
      <p className="mt-2 text-[10px] text-content-faint">{SOURCE_LABEL[model.source] ?? model.source}</p>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Register dialog
// ---------------------------------------------------------------------------

function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-xl border border-border bg-surface p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <p className="text-sm font-semibold text-content">{title}</p>
          <button className="rounded p-1 text-content-subtle hover:bg-overlay hover:text-content rf-focus" onClick={onClose}>
            <X size={15} />
          </button>
        </div>
        {children}
      </div>
    </div>
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

function RegisterDialog({ defaultRepo, onClose }: { defaultRepo: string; onClose: () => void }) {
  const register = useRegisterFoundationModel();
  const [f, setF] = useState({
    hf_repo: defaultRepo || '',
    revision: '',
    architecture: '',
    format: 'safetensors',
    quantization: 'none',
    license: '',
  });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));

  const save = async () => {
    if (!f.hf_repo.trim()) {
      toast.error('Hugging Face repo is required');
      return;
    }
    const res = await register.mutate({
      hf_repo: f.hf_repo.trim(),
      revision: f.revision.trim() || undefined,
      architecture: f.architecture.trim() || undefined,
      format: f.format,
      quantization: f.quantization,
      license: f.license.trim() || undefined,
    });
    if (res) {
      toast.success('Foundation model registered', res.hf_repo);
      onClose();
    }
  };

  return (
    <Dialog title="Register foundation model" onClose={onClose}>
      <div className="grid gap-3">
        <Field label="Hugging Face repo *">
          <input className={INPUT} value={f.hf_repo} autoFocus placeholder="meta-llama/Llama-3.1-8B" onChange={(e) => set('hf_repo', e.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Revision (optional)">
            <input className={INPUT} value={f.revision} placeholder="commit SHA" onChange={(e) => set('revision', e.target.value)} />
          </Field>
          <Field label="Architecture (optional)">
            <input className={INPUT} value={f.architecture} placeholder="llama, qwen2, mistral…" onChange={(e) => set('architecture', e.target.value)} />
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Weight format">
            <select className={INPUT} value={f.format} onChange={(e) => set('format', e.target.value)}>
              <option value="safetensors">safetensors</option>
              <option value="pytorch_bin">pytorch_bin</option>
              <option value="gguf">gguf</option>
            </select>
          </Field>
          <Field label="Quantization">
            <select className={INPUT} value={f.quantization} onChange={(e) => set('quantization', e.target.value)}>
              <option value="none">none</option>
              <option value="bnb_4bit">bnb_4bit</option>
              <option value="bnb_8bit">bnb_8bit</option>
              <option value="gguf_q4_k_m">gguf_q4_k_m</option>
              <option value="gguf_q8_0">gguf_q8_0</option>
            </select>
          </Field>
        </div>
        <Field label="License (optional)">
          <input className={INPUT} value={f.license} onChange={(e) => set('license', e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={save} loading={register.isPending}>Register</Button>
        </div>
      </div>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Resolve dialog — runtime model → foundation candidates (confidence-scored)
// ---------------------------------------------------------------------------

function ResolveDialog({ onClose, onPrefill }: { onClose: () => void; onPrefill: (hfRepo: string) => void }) {
  const resolve = useResolveRuntimeModel();
  const [ref, setRef] = useState('');
  const [result, setResult] = useState<ResolutionResult | null>(null);

  const run = async () => {
    if (!ref.trim()) return;
    const res = await resolve.mutate(ref.trim());
    if (res) setResult(res);
  };

  return (
    <Dialog title="Resolve runtime model → foundation model" onClose={onClose}>
      <div className="grid gap-3">
        <div className="flex gap-2">
          <input
            className={INPUT}
            value={ref}
            autoFocus
            placeholder="Runtime model tag, e.g. llama3.1:8b"
            onChange={(e) => setRef(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && run()}
          />
          <Button size="sm" onClick={run} loading={resolve.isPending}>Resolve</Button>
        </div>

        {result && (
          <div className="rounded-lg border border-border bg-base p-3">
            {result.resolved ? (
              <p className="mb-2 text-xs text-content">
                Confident match:{' '}
                <span className="font-semibold text-pass">{result.resolved.hf_repo}</span>{' '}
                <span className="text-content-subtle">({Math.round(result.resolved.confidence * 100)}%)</span>
              </p>
            ) : (
              <p className="mb-2 text-xs text-uncertain">
                {result.is_ambiguous ? 'Ambiguous — confirm a candidate below.' : 'No confident match found.'}
              </p>
            )}
            {result.candidates.length === 0 ? (
              <p className="text-[11px] text-content-subtle">No candidates. Register the repo manually if you know it.</p>
            ) : (
              <ul className="space-y-1.5">
                {result.candidates.map((c) => (
                  <CandidateRow key={c.hf_repo} candidate={c} onPick={() => onPrefill(c.hf_repo)} />
                ))}
              </ul>
            )}
          </div>
        )}
        <p className="text-[10px] text-content-faint">
          Resolution is confidence-scored from what the runtime exposes — never a silent guess. Confirm before registering.
        </p>
      </div>
    </Dialog>
  );
}

function CandidateRow({ candidate, onPick }: { candidate: ResolutionCandidate; onPick: () => void }) {
  const pct = Math.round(candidate.confidence * 100);
  return (
    <li className="rounded-lg border border-border bg-surface px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0">
          <span className="block truncate text-xs text-content">{candidate.hf_repo}</span>
          <span className="block truncate text-[10px] text-content-subtle">{candidate.reason}</span>
        </span>
        <Button size="sm" variant="ghost" onClick={onPick}>Use</Button>
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        <div className="h-1 flex-1 overflow-hidden rounded-full bg-base">
          <div className={`h-full ${pct >= 85 ? 'bg-pass' : pct >= 60 ? 'bg-uncertain' : 'bg-content-faint'}`} style={{ width: `${pct}%` }} />
        </div>
        <span className="w-8 text-right text-[10px] text-content-subtle">{pct}%</span>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Metadata drawer
// ---------------------------------------------------------------------------

function MetadataDrawer({ model, onClose }: { model: FoundationModel; onClose: () => void }) {
  const runtimes = useFoundationModelRuntimes(model.id);
  const sync = useSyncFoundationModel();
  const del = useDeleteFoundationModel();

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div
        className="h-full w-full max-w-md overflow-y-auto border-l border-border bg-surface p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-sm font-semibold text-content">
              <Package size={15} className="text-red-400" />
              <span className="truncate">{model.hf_repo.split('/').pop()}</span>
            </p>
            <p className="truncate text-[11px] text-content-subtle">{model.hf_repo}</p>
          </div>
          <button className="rounded p-1 text-content-subtle hover:bg-overlay hover:text-content rf-focus" onClick={onClose}>
            <X size={15} />
          </button>
        </div>

        <div className="mb-3 flex items-center gap-2">
          <StatusDot status={model.status} />
          <Badge tone={STATUS_TONE[model.status] ?? 'grey'}>{model.status}</Badge>
          <Badge tone="grey">{SOURCE_LABEL[model.source] ?? model.source}</Badge>
        </div>

        <dl className="space-y-2 text-xs">
          <Row k="Revision" v={model.revision ?? '—'} />
          <Row k="Architecture" v={model.architecture ?? '—'} />
          <Row k="Parameters" v={model.parameter_count ? model.parameter_count.toLocaleString() : '—'} />
          <Row k="Format" v={model.format} />
          <Row k="Quantization" v={model.quantization} />
          <Row k="License" v={model.license ?? '—'} />
          <Row k="Cache path" v={model.cache_path ?? 'not local'} mono />
          <Row k="Checksum" v={model.checksum ?? '—'} mono />
          <Row k="Identity" v={model.identity_key} mono />
        </dl>

        {/* Reverse lineage — runtime models derived from this foundation model */}
        <div className="mt-4">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-content-subtle">Derived runtime models</p>
          {runtimes.isLoading ? (
            <Skeleton className="h-10" />
          ) : (runtimes.data ?? []).length === 0 ? (
            <p className="text-[11px] text-content-subtle">
              None yet. Exported runtime models will appear here once the export pipeline records derivations.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {(runtimes.data ?? []).map((r) => (
                <li key={r.registry_id ?? r.runtime_model} className="rounded-lg border border-border bg-base px-3 py-2 text-xs">
                  <span className="block truncate text-content">{r.label ?? r.runtime_model}</span>
                  <span className="block truncate text-[10px] text-content-subtle">{r.provider} · {r.match}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {model.metadata && Object.keys(model.metadata).length > 0 && (
          <div className="mt-4">
            <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-content-subtle">Metadata</p>
            <pre className="max-h-40 overflow-auto rounded-lg border border-border bg-base p-2 text-[10px] text-content-muted">
              {JSON.stringify(model.metadata, null, 2)}
            </pre>
          </div>
        )}

        <div className="mt-5 flex items-center justify-between">
          <Button
            variant="ghost"
            size="sm"
            onClick={async () => {
              const res = await sync.mutate(model.id);
              if (res) toast.success('Synced', `status: ${res.status}`);
            }}
            loading={sync.isPending}
          >
            <RefreshCw size={13} /> Sync
          </Button>
          <button
            className="flex items-center gap-1 text-xs text-fail hover:underline rf-focus"
            onClick={async () => {
              if (await del.mutate(model.id)) {
                toast.success('Foundation model removed');
                onClose();
              }
            }}
          >
            <Trash2 size={13} /> Remove
          </button>
        </div>
      </div>
    </div>
  );
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-content-subtle">{k}</dt>
      <dd className={`min-w-0 truncate text-right text-content ${mono ? 'font-mono text-[10px]' : ''}`} title={v}>
        {v}
      </dd>
    </div>
  );
}
