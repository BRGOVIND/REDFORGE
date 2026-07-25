import { useMemo, useState } from 'react';
import { Cpu, Download, HardDrive, MemoryStick, Package, Sparkles } from 'lucide-react';
import { Badge, Button, Card, PageHeader, Skeleton } from '../components/ui';
import { useQuery, queryClient } from '../lib/query';
import { toast } from '../lib/toast';
import * as api from '../api/endpoints';
import type { ModelHubModel } from '../api/types';
import { useTaskManager } from '../components/TaskManager';

const BADGE_TONE: Record<string, 'green' | 'amber' | 'grey'> = {
  'Great for Training': 'green',
  'Great for Benchmarking': 'green',
  'CPU Friendly': 'amber',
  '8GB GPU': 'grey',
};

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-content-subtle">
      {icon}
      <span className="text-content-faint">{label}</span>
      <span className="text-content">{value}</span>
    </div>
  );
}

function ModelCard({ m }: { m: ModelHubModel }) {
  const taskMgr = useTaskManager();
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState<'huggingface' | 'ollama'>(
    m.hf_repo ? 'huggingface' : 'ollama',
  );

  const download = async () => {
    setBusy(true);
    try {
      await api.modelHubDownload(m.id, source);
      toast.success('Download started', `${m.name} — track it in the task panel`);
      queryClient.invalidate(['tasks']);
      taskMgr.setOpen(true);
    } catch {
      toast.error('Could not start download', m.name);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-content">{m.name}</p>
          <p className="truncate text-[11px] text-content-subtle">
            {m.family} · {m.parameters_b}B · {m.quantization}
          </p>
        </div>
        <span className="shrink-0 text-[10px] text-content-faint">{m.sources.join(' · ')}</span>
      </div>

      {m.description && <p className="line-clamp-2 text-[11px] text-content-muted">{m.description}</p>}

      <div className="flex flex-wrap gap-1">
        {m.badges.map((b) => (
          <Badge key={b} tone={BADGE_TONE[b] ?? 'grey'}>✓ {b}</Badge>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 rounded-lg bg-base p-2.5">
        <Stat icon={<Cpu size={12} />} label="VRAM" value={`~${m.required_vram_gb} GB`} />
        <Stat icon={<MemoryStick size={12} />} label="RAM" value={`~${m.estimated_ram_gb} GB`} />
        <Stat icon={<HardDrive size={12} />} label="Size" value={`${m.download_size_gb} GB`} />
        <Stat icon={<Sparkles size={12} />} label="Train" value={m.training_suitability} />
      </div>

      <p className="text-[10px] text-content-faint">Recommended: {m.recommended_hardware}</p>

      <div className="mt-auto flex items-center gap-2">
        {m.sources.length > 1 && (
          <select
            value={source}
            onChange={(e) => setSource(e.target.value as 'huggingface' | 'ollama')}
            className="rounded-md border border-border bg-base px-2 py-1 text-[11px] text-content rf-focus"
          >
            <option value="huggingface">Hugging Face</option>
            <option value="ollama">Ollama</option>
          </select>
        )}
        <Button size="sm" onClick={download} loading={busy} className="flex-1">
          <Download size={14} /> Download
        </Button>
      </div>
    </Card>
  );
}

export default function ModelHubPage() {
  const catalog = useQuery({ queryKey: ['model-hub'], queryFn: api.modelHubCatalog });
  const categories = catalog.data?.categories ?? [];
  const [cat, setCat] = useState<string>('all');

  const filtered = useMemo(
    () => (cat === 'all' ? categories : categories.filter((c) => c.key === cat)),
    [categories, cat],
  );

  return (
    <div>
      <PageHeader
        title="Model Hub"
        description="Browse and download models directly — no terminal, no huggingface-cli, no ollama pull. Downloads run as tasks; each model is verified and registered as a Foundation Model automatically."
      />

      {/* Category filter */}
      <div className="mb-4 flex flex-wrap gap-1.5">
        {[{ key: 'all', label: 'All' }, ...categories.map((c) => ({ key: c.key, label: c.label }))].map((c) => (
          <button
            key={c.key}
            onClick={() => setCat(c.key)}
            className={`rounded-full px-2.5 py-1 text-[11px] rf-focus ${
              cat === c.key ? 'bg-red-500 text-white' : 'bg-base text-content-subtle hover:text-content'
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {catalog.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-56" />)}
        </div>
      ) : (
        <div className="space-y-6">
          {filtered.map((c) => (
            <section key={c.key}>
              <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-content">
                <Package size={15} /> {c.label}
                <span className="text-[11px] font-normal text-content-faint">({c.models.length})</span>
              </h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {c.models.map((m) => <ModelCard key={m.id} m={m} />)}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
