import { Link } from 'react-router-dom';
import { Plus, Zap } from 'lucide-react';
import { Button, Card, EmptyState, PageHeader, Progress, Spinner, StatusBadge } from '../components/ui';
import { useSessions } from '../hooks/queries';
import { relativeTime, titleCase } from '../lib/format';

export default function LiveListPage() {
  const sessions = useSessions();
  const active = sessions.data?.filter((s) => s.status === 'running' || s.status === 'pending' || s.status === 'paused') ?? [];
  const others = sessions.data?.filter((s) => !active.includes(s)) ?? [];

  return (
    <div>
      <PageHeader
        title="Live"
        description="Active and recent evaluation sessions."
        actions={
          <Link to="/new">
            <Button>
              <Plus size={16} /> New Evaluation
            </Button>
          </Link>
        }
      />

      {sessions.isLoading ? (
        <Spinner />
      ) : (sessions.data?.length ?? 0) === 0 ? (
        <EmptyState
          icon={<Zap size={26} />}
          title="No sessions yet"
          description="Start an evaluation to watch it stream live."
          action={
            <Link to="/new">
              <Button size="sm">
                <Plus size={14} /> New Evaluation
              </Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-6">
          {active.length > 0 && (
            <section>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">Active</h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {active.map((s) => (
                  <Link key={s.id} to={`/live/${s.id}`}>
                    <Card hover className="p-4">
                      <div className="mb-2 flex items-center justify-between">
                        <span className="truncate font-mono text-[13px] text-content">{s.selected_models.join(', ')}</span>
                        <StatusBadge status={s.status} />
                      </div>
                      <Progress value={s.total_tasks ? s.completed_tasks / s.total_tasks : 0} />
                      <p className="mt-2 text-xs text-content-subtle">
                        {titleCase(s.selected_tier ?? s.session_type)} · {s.completed_tasks}/{s.total_tasks}
                      </p>
                    </Card>
                  </Link>
                ))}
              </div>
            </section>
          )}

          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">Recent</h2>
            <Card>
              <ul className="divide-y divide-border">
                {others.slice(0, 20).map((s) => (
                  <li key={s.id}>
                    <Link
                      to={s.status === 'completed' ? `/reports/${s.id}` : `/live/${s.id}`}
                      className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-overlay rf-focus"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm text-content">{s.selected_models.join(', ')}</p>
                        <p className="text-xs text-content-subtle">
                          {titleCase(s.selected_tier ?? s.session_type)} · {relativeTime(s.created_at)}
                        </p>
                      </div>
                      <StatusBadge status={s.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          </section>
        </div>
      )}
    </div>
  );
}
