import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Download, Layers, Package, Rocket, ScrollText, XCircle } from 'lucide-react';
import { Badge, Button, Card, ErrorState, PageHeader, Progress, Skeleton } from '../components/ui';
import * as api from '../api/endpoints';
import {
  useCancelTrainingRun,
  useJob,
  useLaunchTrainingRun,
  useV3TrainingCheckpoints,
  useV3TrainingRun,
} from '../hooks/queries';
import { toast } from '../lib/toast';

const STATUS_TONE: Record<string, 'green' | 'red' | 'amber' | 'grey'> = {
  completed: 'green', running: 'amber', queued: 'grey', created: 'grey', failed: 'red', cancelled: 'grey',
};
const ACTIVE = new Set(['queued', 'running']);

export default function PipelineTrainingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [pollMs, setPollMs] = useState(0);
  const run = useV3TrainingRun(id ?? null, pollMs);
  const checkpoints = useV3TrainingCheckpoints(id ?? null, pollMs);
  const launch = useLaunchTrainingRun();
  const cancel = useCancelTrainingRun();

  const isActive = run.data ? ACTIVE.has(run.data.status) : false;
  useEffect(() => setPollMs(isActive ? 1500 : 0), [isActive]);

  const job = useJob(run.data?.job_id ?? null, isActive ? 1500 : 0);

  if (run.isLoading) return <div><Skeleton className="mb-4 h-16" /><Skeleton className="h-64" /></div>;
  if (run.error || !run.data) return <div><PageHeader title="Training run" /><ErrorState message="Could not load run." onRetry={() => run.refetch?.()} /></div>;

  const r = run.data;
  const c = r.configuration;

  return (
    <div>
      <PageHeader
        title={r.name}
        description={`${c.strategy.toUpperCase()} · ${c.provider} · ${c.base_model}`}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => navigate('/pipeline/train')}><ArrowLeft size={14} /> All runs</Button>
            {r.status === 'created' && (
              <Button size="sm" loading={launch.isPending} onClick={async () => { const res = await launch.mutate(r.id); if (res) toast.success('Launched'); }}>
                <Rocket size={14} /> Launch
              </Button>
            )}
            {isActive && (
              <Button variant="ghost" size="sm" onClick={async () => { await cancel.mutate(r.id); toast.success('Cancel requested'); }}>
                <XCircle size={14} /> Cancel
              </Button>
            )}
          </div>
        }
      />

      <div className="mb-4 flex items-center gap-2">
        {r.status === 'running' && <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />}
        <Badge tone={STATUS_TONE[r.status] ?? 'grey'}>{r.status}</Badge>
        {r.error && <span className="truncate text-xs text-fail" title={r.error}>{r.error}</span>}
      </div>

      {isActive && job.data && (
        <Card className="mb-4 p-3">
          <Progress value={job.data.progress.fraction} />
          <p className="mt-1 text-[11px] text-content-subtle">{job.data.progress.message || '…'}</p>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Config + artifacts */}
        <Card className="p-4">
          <p className="mb-2 text-sm font-semibold text-content">Configuration</p>
          <dl className="space-y-1.5 text-xs">
            <Row k="Strategy" v={c.strategy} />
            <Row k="Provider" v={c.provider} />
            <Row k="Base model" v={c.base_model} />
            <Row k="Epochs" v={String((c.hyperparameters as Record<string, unknown>).epochs ?? '—')} />
            <Row k="Rank / Alpha" v={`${c.adapter.rank} / ${c.adapter.alpha}`} />
          </dl>
          <p className="mb-2 mt-4 text-sm font-semibold text-content">Artifacts</p>
          <div className="space-y-1.5">
            {r.run_artifact_id && <ArtifactLink id={r.run_artifact_id} label="Training run" icon={<Layers size={13} />} />}
            {r.adapter_artifact_id && <ArtifactLink id={r.adapter_artifact_id} label="Adapter" icon={<Package size={13} />} />}
            {!r.run_artifact_id && !r.adapter_artifact_id && <p className="text-[11px] text-content-subtle">Artifacts appear as the run produces them.</p>}
          </div>
          {r.adapter_artifact_id && r.status === 'completed' && (
            <ExportButton artifactId={r.adapter_artifact_id} baseModel={c.base_model} />
          )}
        </Card>

        {/* Checkpoints */}
        <Card className="overflow-hidden lg:col-span-2">
          <div className="border-b border-border px-4 py-3">
            <p className="text-sm font-semibold text-content">Checkpoints</p>
          </div>
          <div className="p-3">
            {checkpoints.isLoading ? <Skeleton className="h-24" /> : (checkpoints.data ?? []).length === 0 ? (
              <p className="px-2 py-4 text-center text-xs text-content-subtle">No checkpoints yet.</p>
            ) : (
              <table className="w-full text-xs">
                <thead><tr className="border-b border-border text-content-subtle">
                  <th className="px-3 py-2 text-left font-medium">Step</th>
                  <th className="px-3 py-2 text-right font-medium">Loss</th>
                  <th className="px-3 py-2 text-right font-medium">Val loss</th>
                  <th className="px-3 py-2 text-center font-medium">Best</th>
                  <th className="px-3 py-2 text-right font-medium">Artifact</th>
                </tr></thead>
                <tbody>
                  {(checkpoints.data ?? []).map((cp) => (
                    <tr key={cp.id} className="border-b border-border/60 last:border-0">
                      <td className="px-3 py-2 text-content">{cp.step}</td>
                      <td className="px-3 py-2 text-right text-content-muted">{cp.loss?.toFixed(3) ?? '—'}</td>
                      <td className="px-3 py-2 text-right text-content-muted">{cp.val_loss?.toFixed(3) ?? '—'}</td>
                      <td className="px-3 py-2 text-center">{cp.is_best && <Badge tone="green">best</Badge>}</td>
                      <td className="px-3 py-2 text-right">
                        {cp.artifact_id && <Link to={`/artifacts/${cp.artifact_id}`} className="text-red-400 hover:underline">view</Link>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>
      </div>

      {/* Logs */}
      {r.logs.length > 0 && (
        <Card className="mt-5 p-4">
          <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-content"><ScrollText size={15} /> Logs</p>
          <pre className="max-h-56 overflow-auto rounded-lg border border-border bg-base p-2 text-[10px] text-content-muted">{r.logs.join('\n')}</pre>
        </Card>
      )}
    </div>
  );
}

function ArtifactLink({ id, label, icon }: { id: string; label: string; icon: React.ReactNode }) {
  return (
    <Link to={`/artifacts/${id}`} className="flex items-center justify-between rounded-lg border border-border bg-base px-3 py-2 text-xs hover:border-border-strong rf-focus">
      <span className="flex items-center gap-2 text-content">{icon} {label}</span>
      <span className="text-red-400">view →</span>
    </Link>
  );
}

function ExportButton({ artifactId, baseModel }: { artifactId: string; baseModel: string }) {
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  return (
    <Button
      className="mt-3 w-full"
      size="sm"
      loading={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await api.exSubmit({ source_artifact_id: artifactId, target: 'ollama', base_model: baseModel, quantization: 'q4_k_m' });
          toast.success('Export submitted', 'Merge → GGUF → Ollama, tracked in Exports');
          navigate('/pipeline/exports');
        } finally { setBusy(false); }
      }}
    >
      <Download size={14} /> Export to Ollama
    </Button>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return <div className="flex justify-between gap-3"><dt className="text-content-subtle">{k}</dt><dd className="min-w-0 truncate text-right text-content" title={v}>{v}</dd></div>;
}
