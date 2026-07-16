import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Boxes,
  Copy,
  FolderPlus,
  MoreHorizontal,
  Pencil,
  Rocket,
  Trash2,
} from 'lucide-react';
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
} from '../components/ui';
import {
  useProjects,
  useCreateProject,
  useDuplicateProject,
  useDeleteProject,
  useUpdateProject,
} from '../hooks/queries';
import * as api from '../api/endpoints';
import { toast } from '../lib/toast';
import type { Project } from '../api/types';

function timeAgo(iso: string | null): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function StudioPage() {
  const navigate = useNavigate();
  const projects = useProjects();
  const create = useCreateProject();
  const duplicate = useDuplicateProject();
  const del = useDeleteProject();
  const update = useUpdateProject();
  const [menuFor, setMenuFor] = useState<string | null>(null);

  const open = async (p: Project) => {
    try {
      await api.openProject(p.id);
    } catch {
      /* opening only bumps recency; non-fatal */
    }
    navigate(`/projects/${p.id}`);
  };

  const newProject = async () => {
    const name = window.prompt('Project name', 'Untitled Project');
    if (name === null) return;
    try {
      const p = await create.mutate({ name: name.trim() || 'Untitled Project' });
      if (p) {
        toast.success('Project created', p.name);
        void open(p);
      }
    } catch {
      toast.error('Could not create project');
    }
  };

  const rename = async (p: Project) => {
    setMenuFor(null);
    const name = window.prompt('Rename project', p.name);
    if (name === null || !name.trim()) return;
    await update.mutate({ id: p.id, body: { name: name.trim() } });
    void projects.refetch?.();
    toast.success('Renamed', name.trim());
  };

  const onDuplicate = async (p: Project) => {
    setMenuFor(null);
    await duplicate.mutate(p.id);
    toast.success('Duplicated', `${p.name} (copy)`);
  };

  const onDelete = async (p: Project) => {
    setMenuFor(null);
    if (!window.confirm(`Delete "${p.name}"? This cannot be undone.`)) return;
    await del.mutate(p.id);
    toast.success('Deleted', p.name);
  };

  const list = projects.data ?? [];

  return (
    <div onClick={() => setMenuFor(null)}>
      <PageHeader
        title="AI Studio"
        description="Local workspaces — group models, evaluations, and reports. Nothing leaves your machine."
        actions={
          <Button onClick={newProject} loading={create.isPending}>
            <FolderPlus size={16} /> New Project
          </Button>
        }
      />

      {projects.isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      ) : projects.error ? (
        <ErrorState message="Could not load projects." onRetry={() => projects.refetch?.()} />
      ) : list.length === 0 ? (
        <EmptyState
          icon={<Boxes size={28} />}
          title="No projects yet"
          description="Create your first workspace to organize models, evaluations, and reports."
          action={
            <Button onClick={newProject}>
              <FolderPlus size={16} /> New Project
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((p) => (
            <Card key={p.id} hover className="group relative flex flex-col p-5">
              <div className="flex items-start justify-between gap-2">
                <button
                  onClick={() => open(p)}
                  className="min-w-0 flex-1 text-left rf-focus"
                  title={`Open ${p.name}`}
                >
                  <h3 className="truncate text-sm font-semibold text-content">{p.name}</h3>
                  <p className="mt-1 line-clamp-2 min-h-[2rem] text-xs text-content-subtle">
                    {p.description || 'No description'}
                  </p>
                </button>
                <div className="relative shrink-0">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuFor(menuFor === p.id ? null : p.id);
                    }}
                    className="rounded p-1 text-content-subtle hover:bg-overlay hover:text-content rf-focus"
                    aria-label="Project actions"
                  >
                    <MoreHorizontal size={16} />
                  </button>
                  {menuFor === p.id && (
                    <div
                      onClick={(e) => e.stopPropagation()}
                      className="absolute right-0 z-20 mt-1 w-40 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg"
                    >
                      <MenuItem icon={<Pencil size={13} />} label="Rename" onClick={() => rename(p)} />
                      <MenuItem icon={<Copy size={13} />} label="Duplicate" onClick={() => onDuplicate(p)} />
                      <MenuItem
                        icon={<Trash2 size={13} />}
                        label="Delete"
                        danger
                        onClick={() => onDelete(p)}
                      />
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between text-[11px] text-content-faint">
                <span className="flex items-center gap-1">
                  <Boxes size={12} /> {p.models.length} model{p.models.length !== 1 ? 's' : ''}
                </span>
                <span>opened {timeAgo(p.opened_at)}</span>
              </div>

              <div className="mt-3 border-t border-border pt-3">
                <Button variant="secondary" size="sm" onClick={() => open(p)} className="w-full">
                  <Rocket size={13} /> Open
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
  danger,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-xs rf-focus ${
        danger ? 'text-fail hover:bg-red-soft' : 'text-content-muted hover:bg-overlay hover:text-content'
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
