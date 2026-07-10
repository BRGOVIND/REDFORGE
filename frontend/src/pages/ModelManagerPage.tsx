import { useEffect, useMemo, useState } from 'react';
import {
  Boxes,
  Cpu,
  HardDrive,
  Layers,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from '../components/ui';
import { useDeleteModel, useModelCatalog } from '../hooks/queries';
import { getModelDetail } from '../api/endpoints';
import { toast } from '../lib/toast';
import { errorMessage } from '../api/client';
import { cn } from '../lib/cn';
import type { CatalogModel, ModelDetail } from '../api/types';

function fmtBytes(n: number | null): string {
  if (!n || n <= 0) return '—';
  const gb = n / 1e9;
  if (gb >= 1) return `${gb.toFixed(gb >= 10 ? 0 : 1)} GB`;
  return `${Math.max(1, Math.round(n / 1e6))} MB`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString();
}

type SortKey = 'name' | 'size' | 'provider' | 'modified';

const SORTS: { key: SortKey; label: string }[] = [
  { key: 'name', label: 'Name' },
  { key: 'size', label: 'Size' },
  { key: 'provider', label: 'Provider' },
  { key: 'modified', label: 'Recently modified' },
];

export default function ModelManagerPage() {
  const catalog = useModelCatalog();
  const del = useDeleteModel();

  const [query, setQuery] = useState('');
  const [providerFilter, setProviderFilter] = useState<string>('all');
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [selected, setSelected] = useState<CatalogModel | null>(null);

  const groups = catalog.data?.providers ?? [];
  // Provider filter options are derived from the catalog — never hardcoded.
  const providerOptions = useMemo(
    () => groups.filter((g) => g.model_count > 0).map((g) => ({ value: g.provider, label: g.label })),
    [groups]
  );

  const allModels = useMemo(() => groups.flatMap((g) => g.models), [groups]);

  const rows = useMemo(() => {
    let list = allModels;
    if (providerFilter !== 'all') list = list.filter((m) => m.provider === providerFilter);
    const q = query.trim().toLowerCase();
    if (q) list = list.filter((m) => m.name.toLowerCase().includes(q) || m.provider_label.toLowerCase().includes(q));
    const sorted = [...list];
    sorted.sort((a, b) => {
      switch (sortKey) {
        case 'size':
          return (b.size ?? 0) - (a.size ?? 0);
        case 'provider':
          return a.provider_label.localeCompare(b.provider_label) || a.name.localeCompare(b.name);
        case 'modified':
          return (b.modified_at ?? '').localeCompare(a.modified_at ?? '');
        default:
          return a.name.localeCompare(b.name);
      }
    });
    return sorted;
  }, [allModels, providerFilter, query, sortKey]);

  const onDelete = async (m: CatalogModel) => {
    if (!window.confirm(`Delete “${m.name}” from ${m.provider_label}? This cannot be undone.`)) return;
    const res = await del.mutate({ provider: m.provider, name: m.name });
    if (res) {
      toast.success(`Deleted ${m.name}`);
      if (selected?.name === m.name) setSelected(null);
    } else {
      toast.error('Delete failed', errorMessage(del.error));
    }
  };

  const onlineProviders = groups.filter((g) => g.online).length;

  return (
    <div>
      <PageHeader
        title="Model Manager"
        description="Browse and manage models across every provider."
        actions={
          <Button variant="secondary" size="sm" onClick={() => catalog.refetch()} loading={catalog.isFetching}>
            <RefreshCw size={14} />
            Refresh
          </Button>
        }
      />

      {/* Summary + controls */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 text-sm text-content-subtle">
          <Boxes size={15} />
          {catalog.data?.total ?? 0} models · {onlineProviders}/{groups.length} providers online
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-content-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search models…"
              className="h-8 w-56 rounded-lg border border-border bg-surface pl-8 pr-3 text-xs text-content placeholder:text-content-faint rf-focus"
            />
          </div>
          <select
            value={providerFilter}
            onChange={(e) => setProviderFilter(e.target.value)}
            className="h-8 rounded-lg border border-border bg-surface px-2 text-xs text-content rf-focus"
          >
            <option value="all">All providers</option>
            {providerOptions.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="h-8 rounded-lg border border-border bg-surface px-2 text-xs text-content rf-focus"
          >
            {SORTS.map((s) => (
              <option key={s.key} value={s.key}>
                Sort: {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {catalog.isLoading ? (
        <Spinner label="Loading models…" />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<Boxes size={26} />}
          title={allModels.length === 0 ? 'No models found' : 'No models match your filters'}
          description={
            allModels.length === 0
              ? 'Ensure a provider is running (e.g. Ollama) and pull a model, then refresh.'
              : undefined
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((m) => (
            <ModelCard
              key={`${m.provider}/${m.name}`}
              model={m}
              onOpen={() => setSelected(m)}
              onDelete={() => onDelete(m)}
              deleting={del.isPending}
            />
          ))}
        </div>
      )}

      {selected && (
        <ModelDetailPanel
          model={selected}
          onClose={() => setSelected(null)}
          onDelete={() => onDelete(selected)}
        />
      )}
    </div>
  );
}

function ModelCard({
  model,
  onOpen,
  onDelete,
  deleting,
}: {
  model: CatalogModel;
  onOpen: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  const healthy = model.status === 'available';
  return (
    <Card hover className="flex flex-col gap-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-mono text-[13px] font-medium text-content" title={model.name}>
            {model.name}
          </p>
          <div className="mt-1 flex items-center gap-1.5">
            <Badge tone="neutral">{model.provider_label}</Badge>
            <span
              className={cn('h-2 w-2 rounded-full', healthy ? 'bg-pass' : 'bg-content-faint')}
              title={healthy ? 'available' : model.status}
            />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        <Meta icon={<HardDrive size={12} />} label="Size" value={fmtBytes(model.size)} />
        <Meta icon={<Layers size={12} />} label="Quant" value={model.quantization ?? '—'} />
        <Meta icon={<Cpu size={12} />} label="Family" value={model.family ?? '—'} />
        <Meta label="Modified" value={fmtDate(model.modified_at)} />
      </div>

      <div className="mt-auto flex items-center gap-2 pt-1">
        <Button variant="secondary" size="sm" onClick={onOpen} className="flex-1">
          View details
        </Button>
        {model.capabilities.supports_delete && (
          <Button variant="danger" size="sm" onClick={onDelete} loading={deleting} title="Delete model">
            <Trash2 size={13} />
          </Button>
        )}
      </div>
    </Card>
  );
}

function Meta({ icon, label, value }: { icon?: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="flex items-center gap-1 text-content-subtle">
        {icon}
        {label}
      </span>
      <span className="truncate text-content" title={value}>
        {value}
      </span>
    </div>
  );
}

function ModelDetailPanel({
  model,
  onClose,
  onDelete,
}: {
  model: CatalogModel;
  onClose: () => void;
  onDelete: () => void;
}) {
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Extended metadata is fetched only when the panel opens (lazy).
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    setDetail(null);
    getModelDetail(model.provider, model.name)
      .then((d) => alive && setDetail(d))
      .catch((e) => alive && setError(errorMessage(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [model.provider, model.name]);

  const caps = model.capabilities;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div
        className="h-full w-full max-w-md overflow-y-auto border-l border-border bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 flex items-start justify-between gap-3 border-b border-border bg-surface px-5 py-4">
          <div className="min-w-0">
            <p className="truncate font-mono text-sm font-semibold text-content">{model.name}</p>
            <p className="mt-0.5 text-xs text-content-subtle">{model.provider_label}</p>
          </div>
          <button onClick={onClose} className="rf-focus rounded p-1 text-content-subtle hover:text-content" aria-label="Close">
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4">
          {/* Capabilities */}
          <div className="mb-4 flex flex-wrap gap-1.5">
            {Object.entries(caps).map(([k, v]) => (
              <Badge key={k} tone={v ? 'green' : 'grey'}>
                {k.replace('supports_', '')}
              </Badge>
            ))}
          </div>

          {loading ? (
            <Spinner label="Loading metadata…" />
          ) : error ? (
            <p className="rounded-lg border border-red-700/30 bg-red-soft px-3 py-2 text-xs text-fail">{error}</p>
          ) : detail ? (
            <>
              <Section title="Overview">
                <Row label="Size" value={fmtBytes(detail.size)} />
                {caps.supports_context_length && (
                  <Row label="Context length" value={detail.context_length ? detail.context_length.toLocaleString() : '—'} />
                )}
                <Row label="Parameters" value={detail.parameter_count ?? '—'} />
                <Row label="Quantization" value={detail.quantization ?? '—'} />
                <Row label="Architecture" value={detail.architecture ?? '—'} />
                <Row label="Family" value={(detail.families ?? []).join(', ') || detail.family || '—'} />
                <Row label="Tokenizer" value={detail.tokenizer ?? '—'} />
                <Row label="Modified" value={fmtDate(detail.modified_at)} />
                {detail.license && <Row label="License" value={detail.license} />}
              </Section>

              {!caps.supports_metadata && (
                <p className="mb-4 text-xs text-content-subtle">
                  This provider exposes limited model metadata.
                </p>
              )}

              {detail.stop_tokens.length > 0 && (
                <Section title="Stop tokens">
                  <div className="flex flex-wrap gap-1.5">
                    {detail.stop_tokens.map((t) => (
                      <span key={t} className="rounded bg-elevated px-1.5 py-0.5 font-mono text-[11px] text-content-muted">
                        {t}
                      </span>
                    ))}
                  </div>
                </Section>
              )}

              {detail.template && <CodeSection title="Template" text={detail.template} />}
              {detail.modelfile && <CodeSection title="Modelfile" text={detail.modelfile} />}

              {Object.keys(detail.provider_metadata).length > 0 && (
                <CodeSection title="Provider metadata" text={JSON.stringify(detail.provider_metadata, null, 2)} />
              )}
            </>
          ) : null}

          {caps.supports_delete && (
            <div className="mt-6 border-t border-border pt-4">
              <Button variant="danger" size="sm" onClick={onDelete}>
                <Trash2 size={13} />
                Delete model
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-content-subtle">{title}</p>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 text-sm">
      <span className="text-content-subtle">{label}</span>
      <span className="max-w-[60%] truncate text-right text-content" title={value}>
        {value}
      </span>
    </div>
  );
}

function CodeSection({ title, text }: { title: string; text: string }) {
  return (
    <div className="mb-4">
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-content-subtle">{title}</p>
      <pre className="max-h-48 overflow-auto rounded-lg border border-border bg-base/60 p-3 font-mono text-[11px] leading-relaxed text-content-muted">
        {text}
      </pre>
    </div>
  );
}
