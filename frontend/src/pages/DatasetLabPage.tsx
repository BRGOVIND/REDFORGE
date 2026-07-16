import { useEffect, useMemo, useRef, useState } from 'react';
import { VirtualTable, type Column } from '../components/VirtualTable';
import {
  BarChart3,
  Copy,
  Database,
  Download,
  FileUp,
  History,
  MoreHorizontal,
  Scissors,
  Search,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Progress,
  Skeleton,
} from '../components/ui';
import {
  useDatasets,
  useDatasetPreview,
  useDatasetAnalysis,
  useDatasetVersions,
  useImportDataset,
  useDeleteDataset,
  useDuplicateDataset,
  useCleanDataset,
  useRestoreDatasetVersion,
} from '../hooks/queries';
import { datasetExportUrl, splitDataset } from '../api/endpoints';
import { toast } from '../lib/toast';
import type { Dataset } from '../api/types';

type Tab = 'preview' | 'quality' | 'clean' | 'split' | 'versions';

export default function DatasetLabPage() {
  const datasets = useDatasets();
  const importer = useImportDataset();
  const [selected, setSelected] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const list = datasets.data ?? [];
  const active = useMemo(() => list.find((d) => d.id === selected) ?? null, [list, selected]);

  const doImport = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    for (const file of Array.from(files)) {
      try {
        const ds = await importer.mutate({ file });
        if (ds) {
          toast.success('Dataset imported', ds.name);
          setSelected(ds.id);
        }
      } catch {
        toast.error('Import failed', file.name);
      }
    }
  };

  return (
    <div>
      <PageHeader
        title="Dataset Lab"
        description="Local datasets — import, preview, analyze quality, clean, split, and version. Nothing leaves your machine."
        actions={
          <Button onClick={() => fileRef.current?.click()} loading={importer.isPending}>
            <FileUp size={16} /> Import Dataset
          </Button>
        }
      />
      <input
        ref={fileRef}
        type="file"
        multiple
        accept=".csv,.json,.jsonl,.txt,.md,.markdown,.pdf,.docx"
        className="hidden"
        onChange={(e) => doImport(e.target.files)}
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[300px_1fr]">
        {/* Dataset browser */}
        <div className="space-y-3">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              void doImport(e.dataTransfer.files);
            }}
            onClick={() => fileRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed px-4 py-6 text-center transition-colors ${
              dragging ? 'border-red-500 bg-red-soft' : 'border-border hover:border-border-strong'
            }`}
          >
            <Upload size={20} className="text-content-faint" />
            <p className="text-xs text-content-muted">
              Drag & drop or <span className="text-red-400">browse</span>
            </p>
            <p className="text-[10px] text-content-faint">CSV · JSON · JSONL · TXT · MD · PDF · DOCX</p>
          </div>

          {datasets.isLoading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : list.length === 0 ? (
            <p className="px-2 py-4 text-center text-xs text-content-subtle">No datasets yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {list.map((d) => (
                <li key={d.id}>
                  <button
                    onClick={() => setSelected(d.id)}
                    className={`w-full rounded-lg border px-3 py-2.5 text-left transition-colors rf-focus ${
                      selected === d.id
                        ? 'border-red-700/40 bg-red-soft'
                        : 'border-border bg-surface hover:border-border-strong'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium text-content">{d.name}</span>
                      <Badge tone="grey">{d.source_format}</Badge>
                    </div>
                    <p className="mt-0.5 text-[11px] text-content-subtle">
                      {d.record_count} records · v{d.current_version}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Detail */}
        {active ? (
          <DatasetDetail key={active.id} dataset={active} onDeleted={() => setSelected(null)} />
        ) : (
          <Card className="flex items-center justify-center p-10">
            <EmptyState
              icon={<Database size={28} />}
              title="Select a dataset"
              description="Import a file or choose a dataset to preview, analyze, clean, split, and version it."
            />
          </Card>
        )}
      </div>
    </div>
  );
}

function DatasetDetail({ dataset, onDeleted }: { dataset: Dataset; onDeleted: () => void }) {
  const [tab, setTab] = useState<Tab>('preview');
  const del = useDeleteDataset();
  const dup = useDuplicateDataset();
  const [menu, setMenu] = useState(false);

  const onDelete = async () => {
    if (!window.confirm(`Delete "${dataset.name}"? This cannot be undone.`)) return;
    await del.mutate(dataset.id);
    toast.success('Deleted', dataset.name);
    onDeleted();
  };

  const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'preview', label: 'Preview', icon: <Search size={13} /> },
    { id: 'quality', label: 'Quality', icon: <BarChart3 size={13} /> },
    { id: 'clean', label: 'Clean', icon: <Sparkles size={13} /> },
    { id: 'split', label: 'Split', icon: <Scissors size={13} /> },
    { id: 'versions', label: 'Versions', icon: <History size={13} /> },
  ];

  return (
    <Card className="flex flex-col overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold text-content">{dataset.name}</h2>
          <p className="text-xs text-content-subtle">
            {dataset.record_count} records · {dataset.kind} · v{dataset.current_version}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a href={datasetExportUrl(dataset.id, 'jsonl')} target="_blank" rel="noreferrer">
            <Button variant="secondary" size="sm">
              <Download size={13} /> Export
            </Button>
          </a>
          <div className="relative">
            <button
              onClick={() => setMenu((m) => !m)}
              className="rounded p-1.5 text-content-subtle hover:bg-overlay hover:text-content rf-focus"
              aria-label="Dataset actions"
            >
              <MoreHorizontal size={16} />
            </button>
            {menu && (
              <div
                onClick={() => setMenu(false)}
                className="absolute right-0 z-20 mt-1 w-40 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg"
              >
                <button
                  onClick={() => dup.mutate(dataset.id).then(() => toast.success('Duplicated'))}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-content-muted hover:bg-overlay hover:text-content"
                >
                  <Copy size={13} /> Duplicate
                </button>
                <button
                  onClick={onDelete}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-fail hover:bg-red-soft"
                >
                  <Trash2 size={13} /> Delete
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border px-3 py-1.5">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs transition-colors rf-focus ${
              tab === t.id ? 'bg-overlay text-content' : 'text-content-muted hover:text-content'
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      <div className="p-5">
        {tab === 'preview' && <PreviewTab dataset={dataset} />}
        {tab === 'quality' && <QualityTab datasetId={dataset.id} />}
        {tab === 'clean' && <CleanTab datasetId={dataset.id} />}
        {tab === 'split' && <SplitTab datasetId={dataset.id} />}
        {tab === 'versions' && <VersionsTab datasetId={dataset.id} />}
      </div>
    </Card>
  );
}

function useDebounced<T>(value: T, delay = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return v;
}

function PreviewTab({ dataset }: { dataset: Dataset }) {
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  // Debounce the query so a server-side scan doesn't run on every keystroke.
  const debouncedSearch = useDebounced(search, 300);
  const limit = 200; // one virtualized page — only visible rows are rendered
  const preview = useDatasetPreview(dataset.id, offset, limit, debouncedSearch);
  const rows = preview.data?.rows ?? [];
  const total = preview.data?.total ?? 0;
  const cols = dataset.columns;

  const columns: Column<unknown>[] = useMemo(() => {
    const idxCol: Column<unknown> = {
      key: '#', header: '#', className: 'w-14 text-content-faint',
      cell: (_r, i) => offset + i + 1,
    };
    if (dataset.kind === 'records' && cols.length > 0) {
      return [
        idxCol,
        ...cols.map((c) => ({
          key: c,
          header: c,
          cell: (r: unknown) => formatCell((r as Record<string, unknown>)?.[c]),
          sortValue: (r: unknown) => String((r as Record<string, unknown>)?.[c] ?? ''),
        })),
      ];
    }
    return [
      idxCol,
      { key: 'value', header: 'value', className: 'flex-1 font-mono',
        cell: (r: unknown) => (typeof r === 'string' ? r : JSON.stringify(r)) },
    ];
  }, [cols, dataset.kind, offset]);

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-content-faint" />
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
            placeholder="Search records…"
            className="w-full rounded-lg border border-border bg-base py-2 pl-8 pr-3 text-sm text-content placeholder:text-content-faint rf-focus"
          />
        </div>
        <span className="text-xs text-content-subtle">{total} rows</span>
      </div>

      {preview.isLoading && rows.length === 0 ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <VirtualTable
          rows={rows}
          columns={columns}
          rowKey={(_r, i) => String(offset + i)}
          height={420}
          empty={<EmptyState title="No matching records" />}
        />
      )}

      {total > limit && (
        <div className="mt-3 flex items-center justify-between">
          <Button variant="ghost" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
            Previous
          </Button>
          <span className="text-xs text-content-subtle">
            {offset + 1}–{Math.min(offset + limit, total)} of {total}
          </span>
          <Button
            variant="ghost"
            size="sm"
            disabled={offset + limit >= total}
            onClick={() => setOffset(offset + limit)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}

function QualityTab({ datasetId }: { datasetId: string }) {
  const analysis = useDatasetAnalysis(datasetId);
  if (analysis.isLoading) return <Skeleton className="h-64 w-full" />;
  if (!analysis.data) return <EmptyState title="No analysis available" />;
  const { score, grade, issues, statistics, suggestions } = analysis.data;
  const scoreTone = score >= 75 ? 'text-pass' : score >= 50 ? 'text-uncertain' : 'text-fail';

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-6">
        <div className="text-center">
          <p className={`text-4xl font-semibold ${scoreTone}`}>{score}</p>
          <p className="text-xs capitalize text-content-subtle">{grade}</p>
        </div>
        <div className="flex-1">
          <Progress value={score / 100} />
          <p className="mt-2 text-xs text-content-subtle">Overall quality score</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MiniStat label="Records" value={statistics.record_count} />
        <MiniStat label="Est. tokens" value={statistics.estimated_tokens.toLocaleString()} />
        <MiniStat label="Avg length" value={statistics.avg_length} />
        <MiniStat label="Max length" value={statistics.max_length} />
      </div>

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">Issues</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {Object.entries(issues).map(([k, v]) => (
            <div
              key={k}
              className={`flex items-center justify-between rounded-lg border px-3 py-2 text-xs ${
                v > 0 ? 'border-red-700/30 bg-red-soft' : 'border-border bg-surface'
              }`}
            >
              <span className="capitalize text-content-muted">{k.replace(/_/g, ' ')}</span>
              <span className={v > 0 ? 'font-semibold text-fail' : 'text-content-faint'}>{v}</span>
            </div>
          ))}
        </div>
      </div>

      {Object.keys(statistics.languages).length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">Languages (heuristic)</p>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(statistics.languages).map(([lang, n]) => (
              <Badge key={lang} tone="grey">
                {lang}: {n}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">Suggestions</p>
        <ul className="space-y-1">
          {suggestions.map((s, i) => (
            <li key={i} className="flex items-start gap-2 text-xs text-content-muted">
              <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-red-500" />
              {s}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

const CLEAN_OPS = [
  { id: 'remove_duplicates', label: 'Remove duplicates' },
  { id: 'remove_empty', label: 'Remove empty records' },
  { id: 'trim_whitespace', label: 'Trim whitespace' },
  { id: 'normalize_unicode', label: 'Normalize unicode (NFKC)' },
];

function CleanTab({ datasetId }: { datasetId: string }) {
  const clean = useCleanDataset();
  const [ops, setOps] = useState<string[]>([]);
  const [result, setResult] = useState<{ before: number; after: number; notes: string[] } | null>(null);

  const toggle = (id: string) =>
    setOps((o) => (o.includes(id) ? o.filter((x) => x !== id) : [...o, id]));

  const run = async (save: boolean) => {
    if (ops.length === 0) return;
    const r = await clean.mutate({ id: datasetId, operations: ops, save });
    if (r) {
      setResult({ before: r.before_count, after: r.after_count, notes: r.notes });
      toast[save ? 'success' : 'info'](save ? 'Saved as new version' : 'Preview ready', `${r.after_count} records`);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-content-subtle">
        Select operations, preview the result, then save. Saving creates a new version — nothing is
        overwritten, so every clean is reversible.
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {CLEAN_OPS.map((op) => (
          <label
            key={op.id}
            className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-content hover:border-border-strong"
          >
            <input
              type="checkbox"
              checked={ops.includes(op.id)}
              onChange={() => toggle(op.id)}
              className="accent-red-500"
            />
            {op.label}
          </label>
        ))}
      </div>

      <div className="flex gap-2">
        <Button variant="secondary" size="sm" onClick={() => run(false)} disabled={!ops.length} loading={clean.isPending}>
          Preview
        </Button>
        <Button size="sm" onClick={() => run(true)} disabled={!ops.length} loading={clean.isPending}>
          Apply & Save Version
        </Button>
      </div>

      {result && (
        <div className="rounded-lg border border-border bg-base p-3 text-xs">
          <p className="text-content">
            {result.before} → <span className="font-semibold text-pass">{result.after}</span> records
          </p>
          <ul className="mt-1.5 space-y-0.5 text-content-subtle">
            {result.notes.map((n, i) => (
              <li key={i}>· {n}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function SplitTab({ datasetId }: { datasetId: string }) {
  const [train, setTrain] = useState(80);
  const [val, setVal] = useState(10);
  const test = Math.max(0, 100 - train - val);
  const [stats, setStats] = useState<Record<string, number> | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const r = await splitDataset(datasetId, train / 100, val / 100, test / 100);
      setStats(r.statistics as unknown as Record<string, number>);
    } catch {
      toast.error('Split failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-content-subtle">Generate train / validation / test splits (seeded, reproducible).</p>
      <div className="space-y-3">
        <RangeRow label="Train" value={train} onChange={(v) => setTrain(Math.min(v, 100 - val))} />
        <RangeRow label="Validation" value={val} onChange={(v) => setVal(Math.min(v, 100 - train))} />
        <div className="flex items-center justify-between text-sm">
          <span className="text-content-subtle">Test</span>
          <span className="font-mono text-content">{test}%</span>
        </div>
      </div>
      <Button size="sm" onClick={run} loading={busy}>
        <Scissors size={14} /> Compute Split
      </Button>
      {stats && (
        <div className="grid grid-cols-3 gap-2">
          <MiniStat label="Train" value={stats.train} />
          <MiniStat label="Validation" value={stats.validation} />
          <MiniStat label="Test" value={stats.test} />
        </div>
      )}
    </div>
  );
}

function VersionsTab({ datasetId }: { datasetId: string }) {
  const versions = useDatasetVersions(datasetId);
  const restore = useRestoreDatasetVersion();
  if (versions.isLoading) return <Skeleton className="h-48 w-full" />;
  const list = versions.data ?? [];

  return (
    <div>
      <p className="mb-3 text-xs text-content-subtle">
        Every save is a version. Restore copies an old version forward — history is never lost.
      </p>
      <ul className="space-y-2">
        {list.map((v) => (
          <li
            key={v.version}
            className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface px-3 py-2.5"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-content">v{v.version}</span>
                {v.is_current && <Badge tone="green">current</Badge>}
              </div>
              <p className="truncate text-[11px] text-content-subtle">
                {v.record_count} records · {v.note}
              </p>
            </div>
            {!v.is_current && (
              <Button
                variant="secondary"
                size="sm"
                loading={restore.isPending}
                onClick={() =>
                  restore.mutate({ id: datasetId, version: v.version }).then(() => toast.success(`Restored v${v.version}`))
                }
              >
                Restore
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

// -- small helpers ----------------------------------------------------------

function MiniStat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-content-faint">{label}</p>
      <p className="mt-0.5 text-sm font-semibold text-content">{value}</p>
    </div>
  );
}

function RangeRow({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="text-content-subtle">{label}</span>
        <span className="font-mono text-content">{value}%</span>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-red-500"
      />
    </div>
  );
}

function formatCell(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}
