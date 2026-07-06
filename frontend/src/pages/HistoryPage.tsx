import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Clock, Filter } from 'lucide-react';
import { Card, EmptyState, PageHeader, Spinner, StatusBadge } from '../components/ui';
import { useSessions } from '../hooks/queries';
import { formatDate, relativeTime, titleCase } from '../lib/format';
import { cn } from '../lib/cn';

const STATUSES = ['all', 'completed', 'running', 'failed', 'cancelled'];

export default function HistoryPage() {
  const sessions = useSessions();
  const [status, setStatus] = useState('all');
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    let data = sessions.data ?? [];
    if (status !== 'all') data = data.filter((s) => s.status === status);
    if (query.trim()) {
      const q = query.toLowerCase();
      data = data.filter(
        (s) =>
          s.selected_models.some((m) => m.toLowerCase().includes(q)) ||
          (s.selected_tier ?? '').toLowerCase().includes(q)
      );
    }
    return data;
  }, [sessions.data, status, query]);

  return (
    <div>
      <PageHeader title="History" description="Every evaluation, newest first." />

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 rounded-lg border border-border bg-surface p-1">
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={cn(
                'rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors rf-focus',
                status === s ? 'bg-red-soft text-red-400' : 'text-content-subtle hover:text-content'
              )}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Filter size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-content-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by model or profile…"
            className="h-9 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm text-content placeholder:text-content-faint rf-focus"
          />
        </div>
      </div>

      {sessions.isLoading ? (
        <Spinner />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<Clock size={26} />}
          title="No matching evaluations"
          description="Adjust the filters or start a new evaluation."
        />
      ) : (
        <Card>
          <ul className="divide-y divide-border">
            {filtered.map((s) => (
              <li key={s.id}>
                <Link
                  to={s.status === 'completed' ? `/reports/${s.id}` : `/live/${s.id}`}
                  className="flex items-center justify-between gap-4 px-4 py-3.5 hover:bg-overlay rf-focus"
                >
                  <div className="min-w-0">
                    <p className="truncate font-mono text-[13px] text-content">
                      {s.selected_models.join(', ') || 'Evaluation'}
                    </p>
                    <p className="mt-0.5 text-xs text-content-subtle">
                      {titleCase(s.selected_tier ?? s.session_type)} · {s.completed_tasks}/{s.total_tasks} tasks ·{' '}
                      {formatDate(s.created_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="hidden text-xs text-content-faint sm:block">{relativeTime(s.created_at)}</span>
                    <StatusBadge status={s.status} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
