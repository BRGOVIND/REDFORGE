import { Link, useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Download,
  Loader2,
  Rocket,
  ShieldCheck,
  TerminalSquare,
  XCircle,
} from 'lucide-react';
import { Badge, Button, Card, CardHeader } from '../components/ui';
import { useSystemChecks } from '../hooks/queries';
import { toast } from '../lib/toast';
import { cn } from '../lib/cn';
import type { CheckStatus, SystemCheck } from '../api/types';

const EXPECTED: { key: string; label: string }[] = [
  { key: 'ollama_installed', label: 'Ollama Installed' },
  { key: 'ollama_running', label: 'Ollama Running' },
  { key: 'gpu', label: 'GPU Detected' },
  { key: 'database', label: 'SQLite Ready' },
  { key: 'dataset', label: 'Dataset Loaded' },
  { key: 'models', label: 'Models Installed' },
];

function StatusIcon({ status }: { status: CheckStatus | 'waiting' }) {
  if (status === 'waiting')
    return <Loader2 size={17} className="animate-spin text-content-faint" />;
  if (status === 'ok') return <CheckCircle2 size={17} className="text-pass" />;
  if (status === 'warning') return <AlertTriangle size={17} className="text-uncertain" />;
  return <XCircle size={17} className="text-fail" />;
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success('Copied', text);
  } catch {
    toast.error('Could not copy');
  }
}

function CopyRow({ command }: { command: string }) {
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

export default function SetupPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useSystemChecks();

  const byKey = new Map<string, SystemCheck>((data?.checks ?? []).map((c) => [c.key, c]));
  const rows = EXPECTED.map((e) => ({ ...e, check: byKey.get(e.key) }));

  const get = (key: string) => byKey.get(key);
  const ollamaInstalled = get('ollama_installed')?.status === 'ok';
  const ollamaRunning = get('ollama_running')?.status === 'ok';
  const hasModels = get('models')?.status === 'ok';
  const ready = data?.ready ?? false;

  const launch = () => {
    localStorage.setItem('redforge_launched', '1');
    navigate('/');
  };

  return (
    <div className="mx-auto max-w-2xl">
      {/* Header */}
      <div className="mb-8 text-center">
        <span className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-red-600 text-white">
          <ShieldCheck size={22} />
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-content">Welcome to RedForge</h1>
        <p className="mt-2 text-sm text-content-muted">
          Let's make sure everything's ready before your first evaluation.
        </p>
      </div>

      {/* System check */}
      <Card>
        <CardHeader
          title="System Check"
          icon={<TerminalSquare size={15} />}
          action={
            <span className="flex items-center gap-1.5 text-xs text-content-subtle">
              {isLoading && !data ? (
                <>
                  <Loader2 size={12} className="animate-spin" /> checking
                </>
              ) : (
                <span className="flex items-center gap-1.5">
                  <span className={cn('h-1.5 w-1.5 rounded-full', ready ? 'bg-pass' : 'bg-uncertain')} />
                  {ready ? 'ready' : 'action needed'}
                </span>
              )}
            </span>
          }
        />
        <ul className="divide-y divide-border">
          {rows.map((r) => (
            <li key={r.key} className="flex items-center justify-between gap-3 px-5 py-3.5">
              <div className="flex items-center gap-3">
                <StatusIcon status={r.check?.status ?? 'waiting'} />
                <span className="text-sm text-content">{r.label}</span>
              </div>
              {r.check?.detail && (
                <span className="truncate text-right text-xs text-content-subtle">{r.check.detail}</span>
              )}
            </li>
          ))}
        </ul>
      </Card>

      {/* Guidance */}
      <div className="mt-5 space-y-5">
        {data && !ollamaInstalled && (
          <Card className="p-5">
            <h3 className="text-sm font-semibold text-content">Install Ollama</h3>
            <p className="mt-1 text-sm text-content-muted">
              RedForge runs models locally through Ollama. Install it, then this page updates on its own.
            </p>
            <a href={data.ollama_download_url} target="_blank" rel="noreferrer" className="mt-3 inline-block">
              <Button>
                <Download size={16} /> Download Ollama
              </Button>
            </a>
          </Card>
        )}

        {data && ollamaInstalled && !ollamaRunning && (
          <Card className="p-5">
            <h3 className="text-sm font-semibold text-content">Start Ollama</h3>
            <p className="mb-3 mt-1 text-sm text-content-muted">
              Ollama is installed but not running. Start it, then come back — the check flips to green automatically.
            </p>
            <CopyRow command={get('ollama_running')?.hint || 'ollama serve'} />
          </Card>
        )}

        {data && ollamaRunning && !hasModels && (
          <Card className="p-5">
            <h3 className="text-sm font-semibold text-content">Pull a model</h3>
            <p className="mb-3 mt-1 text-sm text-content-muted">
              You'll need at least one model. These are good places to start:
            </p>
            <div className="space-y-2">
              {data.recommended_models.map((m) => (
                <CopyRow key={m} command={`ollama pull ${m}`} />
              ))}
            </div>
          </Card>
        )}
      </div>

      {/* Ready */}
      <div className="mt-8 flex flex-col items-center gap-3">
        {ready ? (
          <>
            <Badge tone="green">
              <CheckCircle2 size={13} /> System Ready
            </Badge>
            <Button size="md" onClick={launch}>
              <Rocket size={16} /> Launch RedForge
            </Button>
          </>
        ) : (
          <Link to="/" className="text-xs text-content-subtle hover:text-content rf-focus">
            Skip for now →
          </Link>
        )}
      </div>
    </div>
  );
}
