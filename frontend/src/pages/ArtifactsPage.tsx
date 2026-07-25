import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layers, Search } from 'lucide-react';
import { Badge, Card, EmptyState, PageHeader, Skeleton } from '../components/ui';
import { useArtifacts, useArtifactTypes } from '../hooks/queries';
import type { Artifact } from '../api/types';

const STATUS_TONE: Record<string, 'green' | 'red' | 'amber' | 'grey'> = {
  ready: 'green',
  draft: 'grey',
  invalid: 'red',
  archived: 'amber',
};

export default function ArtifactsPage() {
  const navigate = useNavigate();
  const types = useArtifactTypes();
  const [type, setType] = useState('');
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');

  const artifacts = useArtifacts({
    type: type || undefined,
    status: status || undefined,
    q: q || undefined,
  });
  const list = artifacts.data ?? [];

  return (
    <div>
      <PageHeader
        title="Artifacts"
        description="The platform spine — every produced unit (models, datasets, checkpoints, exports, results, reports) with full lineage. Everything local."
      />

      {/* Filters */}
      <Card className="mb-4 flex flex-wrap items-center gap-2 p-3">
        <div className="flex min-w-[200px] flex-1 items-center gap-2 rounded-lg border border-border bg-base px-2.5">
          <Search size={13} className="text-content-faint" />
          <input
            className="flex-1 bg-transparent py-2 text-xs text-content placeholder:text-content-faint focus:outline-none"
            placeholder="Search artifacts…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <select
          className="rounded-lg border border-border bg-base px-3 py-2 text-xs text-content rf-focus"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          <option value="">All types</option>
          {(types.data ?? []).map((t) => (
            <option key={t.key} value={t.key}>{t.label}</option>
          ))}
        </select>
        <select
          className="rounded-lg border border-border bg-base px-3 py-2 text-xs text-content rf-focus"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">All statuses</option>
          {['ready', 'draft', 'invalid', 'archived'].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </Card>

      {artifacts.isLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-24" />)}
        </div>
      ) : list.length === 0 ? (
        <Card className="p-4">
          <EmptyState
            icon={<Layers size={24} />}
            title="No artifacts yet"
            description="Artifacts are produced by jobs and engines (training, export, benchmark, evaluation). They'll appear here with lineage as work runs."
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((a) => (
            <ArtifactCard key={a.id} artifact={a} onOpen={() => navigate(`/artifacts/${a.id}`)} />
          ))}
        </div>
      )}
    </div>
  );
}

function ArtifactCard({ artifact, onOpen }: { artifact: Artifact; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className="flex flex-col rounded-xl border border-border bg-surface p-4 text-left transition-colors hover:border-border-strong rf-focus"
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-semibold text-content">
          <Layers size={15} className="text-red-400" />
          <span className="truncate">{artifact.name}</span>
        </span>
        <Badge tone={STATUS_TONE[artifact.status] ?? 'grey'}>{artifact.status}</Badge>
      </div>
      <div className="mb-2 flex flex-wrap gap-1.5 text-[10px]">
        <Badge tone="grey">{artifact.type}</Badge>
        {artifact.version > 1 && <Badge tone="amber">v{artifact.version}</Badge>}
        {artifact.location.kind === 'file' && <Badge tone="grey">file</Badge>}
      </div>
      <p className="mt-auto truncate text-[11px] text-content-subtle">
        {artifact.producer || 'unknown producer'}
      </p>
      {artifact.tags.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {artifact.tags.slice(0, 4).map((t) => (
            <span key={t} className="rounded bg-base px-1.5 py-0.5 text-[9px] text-content-subtle">{t}</span>
          ))}
        </div>
      )}
    </button>
  );
}
