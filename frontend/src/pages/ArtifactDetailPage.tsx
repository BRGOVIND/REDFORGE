import { ArrowLeft, ArrowDown, CheckCircle2, GitBranch, Layers, ShieldCheck, Trash2 } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Badge,
  Button,
  Card,
  ErrorState,
  PageHeader,
  Skeleton,
} from '../components/ui';
import {
  useArchiveArtifact,
  useArtifact,
  useArtifactLineage,
  useArtifactVersions,
  useDeleteArtifact,
  useValidateArtifact,
} from '../hooks/queries';
import { toast } from '../lib/toast';
import type { ArtifactReference } from '../api/types';

const STATUS_TONE: Record<string, 'green' | 'red' | 'amber' | 'grey'> = {
  ready: 'green', draft: 'grey', invalid: 'red', archived: 'amber',
};

export default function ArtifactDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const artifact = useArtifact(id ?? null);
  const lineage = useArtifactLineage(id ?? null);
  const versions = useArtifactVersions(id ?? null);
  const validate = useValidateArtifact();
  const archive = useArchiveArtifact();
  const del = useDeleteArtifact();

  if (artifact.isLoading) {
    return (
      <div>
        <Skeleton className="mb-4 h-16" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (artifact.error || !artifact.data) {
    return (
      <div>
        <PageHeader title="Artifact" />
        <ErrorState message="Could not load this artifact." onRetry={() => artifact.refetch?.()} />
      </div>
    );
  }

  const a = artifact.data;
  const lin = lineage.data;

  return (
    <div>
      <PageHeader
        title={a.name}
        description={`${a.type} · ${a.location.kind}-backed · produced by ${a.producer || 'unknown'}`}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => navigate('/artifacts')}>
              <ArrowLeft size={14} /> All artifacts
            </Button>
            <Button
              variant="ghost"
              size="sm"
              loading={validate.isPending}
              onClick={async () => {
                const r = await validate.mutate(a.id);
                if (r) toast[r.valid ? 'success' : 'error'](r.valid ? 'Artifact valid' : 'Invalid', r.reason);
              }}
            >
              <ShieldCheck size={14} /> Validate
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Metadata */}
        <Card className="p-4 lg:col-span-1">
          <div className="mb-3 flex items-center gap-2">
            <Badge tone={STATUS_TONE[a.status] ?? 'grey'}>{a.status}</Badge>
            <Badge tone="grey">v{a.version}</Badge>
            {a.tags.map((t) => (
              <span key={t} className="rounded bg-base px-1.5 py-0.5 text-[10px] text-content-subtle">{t}</span>
            ))}
          </div>
          <dl className="space-y-2 text-xs">
            <Row k="Type" v={a.type} />
            <Row k="Status" v={a.status} />
            <Row k="Producer" v={a.producer || '—'} />
            <Row k="Location" v={a.location.file_path ?? (a.location.table ? `${a.location.table}#${a.location.row_id}` : '—')} mono />
            <Row k="Size" v={a.size_bytes != null ? `${a.size_bytes.toLocaleString()} B` : '—'} />
            <Row k="Checksum" v={a.checksum?.value ?? '—'} mono />
            <Row k="Lineage id" v={a.lineage_id} mono />
          </dl>

          {a.metadata && Object.keys(a.metadata).length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-content-subtle">Metadata</p>
              <pre className="max-h-40 overflow-auto rounded-lg border border-border bg-base p-2 text-[10px] text-content-muted">
                {JSON.stringify(a.metadata, null, 2)}
              </pre>
            </div>
          )}

          <div className="mt-4 flex items-center justify-between">
            <Button
              variant="ghost"
              size="sm"
              loading={archive.isPending}
              disabled={a.status === 'archived'}
              onClick={async () => {
                if (await archive.mutate(a.id)) toast.success('Artifact archived');
              }}
            >
              Archive
            </Button>
            <button
              className="flex items-center gap-1 text-xs text-fail hover:underline rf-focus"
              onClick={async () => {
                if (await del.mutate(a.id)) {
                  toast.success('Artifact deleted');
                  navigate('/artifacts');
                }
              }}
            >
              <Trash2 size={13} /> Delete
            </button>
          </div>
        </Card>

        {/* Lineage + versions */}
        <div className="space-y-5 lg:col-span-2">
          <Card className="p-4">
            <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-content">
              <GitBranch size={15} /> Lineage
            </p>
            {lineage.isLoading || !lin ? (
              <Skeleton className="h-40" />
            ) : (
              <LineageGraph
                parents={lin.parents}
                self={{ id: a.id, type: a.type, name: a.name, version: a.version, status: a.status }}
                children={lin.children}
                ancestorCount={lin.ancestors.length}
                descendantCount={lin.descendants.length}
              />
            )}
          </Card>

          <Card className="overflow-hidden">
            <div className="border-b border-border px-4 py-3">
              <p className="flex items-center gap-2 text-sm font-semibold text-content">
                <Layers size={15} /> Versions
              </p>
            </div>
            <div className="p-3">
              {(versions.data ?? []).length <= 1 ? (
                <p className="px-2 py-3 text-center text-xs text-content-subtle">
                  Only one version. New versions are created as work supersedes this artifact.
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {(versions.data ?? []).map((v) => (
                    <li key={v.id}>
                      <Link
                        to={`/artifacts/${v.id}`}
                        className={`flex items-center justify-between rounded-lg border px-3 py-2 text-xs rf-focus ${
                          v.id === a.id ? 'border-red-500 bg-red-soft' : 'border-border hover:border-border-strong'
                        }`}
                      >
                        <span className="text-content">Version {v.version}</span>
                        <Badge tone={STATUS_TONE[v.status] ?? 'grey'}>{v.status}</Badge>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function LineageGraph({
  parents,
  self,
  children,
  ancestorCount,
  descendantCount,
}: {
  parents: ArtifactReference[];
  self: { id: string; type: string; name: string; version: number; status: string };
  children: ArtifactReference[];
  ancestorCount: number;
  descendantCount: number;
}) {
  return (
    <div className="flex flex-col items-center gap-2">
      {ancestorCount > parents.length && (
        <p className="text-[10px] text-content-faint">+{ancestorCount - parents.length} more ancestor(s) above</p>
      )}
      {parents.length > 0 && (
        <>
          <div className="flex flex-wrap justify-center gap-2">
            {parents.map((p) => <LineageNode key={p.id} node={p} />)}
          </div>
          <ArrowDown size={16} className="text-content-faint" />
        </>
      )}
      <div className="rounded-lg border-2 border-red-500 bg-red-soft px-3 py-2 text-center">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-content">
          <CheckCircle2 size={13} className="text-red-400" /> {self.name}
        </p>
        <p className="text-[10px] text-content-subtle">{self.type} · v{self.version}</p>
      </div>
      {children.length > 0 && (
        <>
          <ArrowDown size={16} className="text-content-faint" />
          <div className="flex flex-wrap justify-center gap-2">
            {children.map((c) => <LineageNode key={c.id} node={c} />)}
          </div>
        </>
      )}
      {descendantCount > children.length && (
        <p className="text-[10px] text-content-faint">+{descendantCount - children.length} more descendant(s) below</p>
      )}
      {parents.length === 0 && children.length === 0 && (
        <p className="text-[11px] text-content-subtle">Root artifact — no lineage recorded yet.</p>
      )}
    </div>
  );
}

function LineageNode({ node }: { node: ArtifactReference }) {
  return (
    <Link
      to={`/artifacts/${node.id}`}
      className="rounded-lg border border-border bg-surface px-3 py-1.5 text-center hover:border-border-strong rf-focus"
    >
      <p className="max-w-[140px] truncate text-[11px] text-content">{node.name}</p>
      <p className="text-[9px] text-content-subtle">{node.type}</p>
    </Link>
  );
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-content-subtle">{k}</dt>
      <dd className={`min-w-0 truncate text-right text-content ${mono ? 'font-mono text-[10px]' : ''}`} title={v}>{v}</dd>
    </div>
  );
}
