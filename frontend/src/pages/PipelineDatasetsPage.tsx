import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Database, Layers, ScrollText, ShieldCheck, Split, Trash2, Upload, X } from 'lucide-react';
import { Badge, Button, Card, EmptyState, PageHeader, Skeleton } from '../components/ui';
import * as api from '../api/endpoints';
import {
  useDeleteV3Dataset,
  useImportV3Dataset,
  useV3DatasetPreview,
  useV3DatasetValidate,
  useV3Datasets,
} from '../hooks/queries';
import { queryClient } from '../lib/query';
import { toast } from '../lib/toast';
import type { V3Dataset } from '../api/types';

const STATUS_TONE: Record<string, 'green' | 'red' | 'amber' | 'grey'> = {
  ready: 'green', registered: 'grey', importing: 'amber', invalid: 'red', archived: 'grey',
};

export default function PipelineDatasetsPage() {
  const datasets = useV3Datasets();
  const importer = useImportV3Dataset();
  const fileRef = useRef<HTMLInputElement>(null);
  const [detail, setDetail] = useState<V3Dataset | null>(null);

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const res = await importer.mutate({ file, name: file.name });
    if (res) toast.success('Dataset imported', `${res.statistics.record_count} records`);
    if (fileRef.current) fileRef.current.value = '';
  };

  const list = datasets.data ?? [];

  return (
    <div>
      <PageHeader
        title="Datasets"
        description="First-class, versioned datasets — every version published to the Artifact Registry with lineage. Import locally; nothing is uploaded."
        actions={
          <>
            <input ref={fileRef} type="file" className="hidden" onChange={onFile}
              accept=".json,.jsonl,.csv,.txt,.md" />
            <Button size="sm" loading={importer.isPending} onClick={() => fileRef.current?.click()}>
              <Upload size={14} /> Import
            </Button>
          </>
        }
      />

      {datasets.isLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-28" />)}
        </div>
      ) : list.length === 0 ? (
        <Card className="p-4">
          <EmptyState icon={<Database size={24} />} title="No datasets yet"
            description="Import a JSON/JSONL/CSV file to create your first versioned dataset." />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((d) => (
            <button key={d.id} onClick={() => setDetail(d)}
              className="flex flex-col rounded-xl border border-border bg-surface p-4 text-left transition-colors hover:border-border-strong rf-focus">
              <div className="mb-2 flex items-start justify-between gap-2">
                <span className="flex items-center gap-2 text-sm font-semibold text-content">
                  <Database size={15} className="text-red-400" />
                  <span className="truncate">{d.name}</span>
                </span>
                <Badge tone={STATUS_TONE[d.status] ?? 'grey'}>{d.status}</Badge>
              </div>
              <div className="mb-2 flex flex-wrap gap-1.5 text-[10px]">
                <Badge tone="grey">{d.format}</Badge>
                <Badge tone="amber">v{d.current_version}</Badge>
                <Badge tone="grey">{d.statistics.record_count} rows</Badge>
              </div>
              <p className="mt-auto text-[11px] text-content-subtle">~{d.statistics.estimated_tokens.toLocaleString()} tokens</p>
            </button>
          ))}
        </div>
      )}

      {detail && <DatasetDrawer dataset={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function DatasetDrawer({ dataset, onClose }: { dataset: V3Dataset; onClose: () => void }) {
  const preview = useV3DatasetPreview(dataset.id);
  const validation = useV3DatasetValidate(dataset.id);
  const del = useDeleteV3Dataset();
  const [splitting, setSplitting] = useState(false);

  const doSplit = async () => {
    setSplitting(true);
    try {
      await api.dpProcess(dataset.id, { operation: 'split', train: 0.8, val: 0.1, test: 0.1 });
      toast.success('Split job submitted', 'Track it in Jobs; a new version will appear');
      queryClient.invalidate(['dp-list']);
    } finally {
      setSplitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div className="h-full w-full max-w-lg overflow-y-auto border-l border-border bg-surface p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between">
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-sm font-semibold text-content">
              <Database size={15} className="text-red-400" /><span className="truncate">{dataset.name}</span>
            </p>
            <p className="text-[11px] text-content-subtle">{dataset.format} · v{dataset.current_version} · {dataset.statistics.record_count} rows</p>
          </div>
          <button className="rounded p-1 text-content-subtle hover:bg-overlay hover:text-content rf-focus" onClick={onClose}><X size={15} /></button>
        </div>

        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Button variant="ghost" size="sm" onClick={doSplit} loading={splitting}><Split size={13} /> Split (job)</Button>
          {dataset.artifact_id && (
            <Link to={`/artifacts/${dataset.artifact_id}`} className="flex items-center gap-1 text-xs text-red-400 hover:underline rf-focus">
              <Layers size={13} /> Artifact
            </Link>
          )}
          <button className="ml-auto flex items-center gap-1 text-xs text-fail hover:underline rf-focus"
            onClick={async () => { if (await del.mutate(dataset.id)) { toast.success('Dataset deleted'); onClose(); } }}>
            <Trash2 size={13} /> Delete
          </button>
        </div>

        {/* Validation */}
        <Card className="mb-3 p-3">
          <p className="mb-2 flex items-center gap-2 text-xs font-semibold text-content-subtle"><ShieldCheck size={13} /> Quality</p>
          {validation.isLoading ? <Skeleton className="h-10" /> : validation.data && (
            <div className="text-xs">
              <div className="mb-1 flex items-center gap-2">
                <Badge tone={validation.data.valid ? 'green' : 'red'}>{validation.data.grade}</Badge>
                <span className="text-content">{validation.data.score}/100</span>
              </div>
              {validation.data.suggestions.slice(0, 3).map((s, i) => (
                <p key={i} className="text-[11px] text-content-subtle">• {s}</p>
              ))}
            </div>
          )}
        </Card>

        {/* Preview */}
        <Card className="p-3">
          <p className="mb-2 flex items-center gap-2 text-xs font-semibold text-content-subtle"><ScrollText size={13} /> Preview</p>
          {preview.isLoading ? <Skeleton className="h-24" /> : (
            <pre className="max-h-64 overflow-auto rounded bg-base p-2 text-[10px] text-content-muted">
              {JSON.stringify((preview.data?.rows ?? []).slice(0, 10), null, 2)}
            </pre>
          )}
        </Card>
      </div>
    </div>
  );
}
