import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, Layers, Package } from 'lucide-react';
import { Badge, Button, Card, EmptyState, PageHeader, Progress, Skeleton } from '../components/ui';
import { useArtifacts, useExportHistory, useExportProviders, useSubmitExport } from '../hooks/queries';
import { toast } from '../lib/toast';
import type { Job } from '../api/types';

const INPUT = 'w-full rounded-lg border border-border bg-base px-3 py-2 text-xs text-content rf-focus';
const STATUS_TONE: Record<string, 'green' | 'red' | 'amber' | 'grey'> = {
  completed: 'green', running: 'amber', queued: 'grey', failed: 'red', cancelled: 'grey', interrupted: 'amber',
};
const ACTIVE = new Set(['queued', 'running']);

export default function PipelineExportsPage() {
  const providers = useExportProviders();
  const [pollMs, setPollMs] = useState(0);
  const history = useExportHistory(pollMs);
  const list = history.data ?? [];
  const active = list.some((j) => ACTIVE.has(j.status));
  useEffect(() => setPollMs(active ? 1500 : 0), [active]);

  // Adapters + checkpoints are the exportable artifacts.
  const adapters = useArtifacts({ type: 'adapter', status: 'ready' });
  const checkpoints = useArtifacts({ type: 'checkpoint', status: 'ready' });
  const exportable = [...(adapters.data ?? []), ...(checkpoints.data ?? [])];

  const submit = useSubmitExport();
  const [source, setSource] = useState('');
  const [target, setTarget] = useState('ollama');
  const [modelName, setModelName] = useState('');

  const run = async () => {
    if (!source) return toast.error('Select a source artifact');
    const res = await submit.mutate({ source_artifact_id: source, target, base_model: '', quantization: 'q4_k_m', model_name: modelName || undefined });
    if (res) toast.success('Export submitted', 'Merge → GGUF → runtime model');
  };

  return (
    <div>
      <PageHeader
        title="Exports"
        description="Turn a trained adapter or checkpoint into a runtime model — merge → GGUF → Ollama import. Runs as a Job; every stage becomes an Artifact with lineage."
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[360px_1fr]">
        {/* Export form */}
        <Card className="space-y-3 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-content"><Download size={15} /> New export</p>
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-content-subtle">Source artifact</span>
            <select className={INPUT} value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">— select adapter / checkpoint —</option>
              {exportable.map((a) => <option key={a.id} value={a.id}>{a.type}: {a.name}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-content-subtle">Target</span>
            <select className={INPUT} value={target} onChange={(e) => setTarget(e.target.value)}>
              {(providers.data ?? []).map((p) => (
                <option key={p.target} value={p.target} disabled={p.target !== 'gguf' && p.target !== 'ollama'}>
                  {p.name}{p.available ? '' : ' (simulated)'}
                </option>
              ))}
            </select>
          </label>
          {target === 'ollama' && (
            <label className="block">
              <span className="mb-1 block text-[11px] font-medium text-content-subtle">Ollama model name (optional)</span>
              <input className={INPUT} value={modelName} placeholder="my-model" onChange={(e) => setModelName(e.target.value)} />
            </label>
          )}
          <Button className="w-full" size="sm" loading={submit.isPending} onClick={run}>
            <Download size={14} /> Export
          </Button>
          <p className="text-[10px] text-content-faint">
            Without the local toolchain, export runs in honest simulated mode — real files + lineage, clearly flagged.
          </p>
        </Card>

        {/* History */}
        <Card className="overflow-hidden">
          <div className="border-b border-border px-4 py-3"><p className="text-sm font-semibold text-content">Export history</p></div>
          <div className="p-3">
            {history.isLoading ? <Skeleton className="h-24" /> : list.length === 0 ? (
              <EmptyState icon={<Package size={22} />} title="No exports yet" description="Submit an export to produce a runtime model." />
            ) : (
              <ul className="space-y-2">
                {list.map((j) => <ExportRow key={j.id} job={j} />)}
              </ul>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function ExportRow({ job }: { job: Job }) {
  const exp = (job.result?.data as { export?: { runtime_model_name?: string; simulated?: boolean; runtime_model_artifact_id?: string } } | undefined)?.export;
  return (
    <li className="rounded-lg border border-border bg-base p-3 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0">
          <span className="block truncate text-content">
            {exp?.runtime_model_name ?? 'export'}
            {exp?.simulated && <Badge tone="amber">simulated</Badge>}
          </span>
          <span className="block truncate text-[10px] text-content-subtle">{job.id.slice(0, 8)}</span>
        </span>
        <Badge tone={STATUS_TONE[job.status] ?? 'grey'}>{job.status}</Badge>
      </div>
      {ACTIVE.has(job.status) && (
        <div className="mt-2"><Progress value={job.progress.fraction} /><p className="mt-1 text-[10px] text-content-subtle">{job.progress.message}</p></div>
      )}
      {exp?.runtime_model_artifact_id && (
        <Link to={`/artifacts/${exp.runtime_model_artifact_id}`} className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-red-400 hover:underline">
          <Layers size={12} /> runtime model artifact
        </Link>
      )}
    </li>
  );
}
