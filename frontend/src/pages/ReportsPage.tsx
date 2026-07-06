import { Link } from 'react-router-dom';
import { FileText } from 'lucide-react';
import { Card, EmptyState, PageHeader, Spinner } from '../components/ui';
import { ScoreDonut } from '../components/shared';
import { useSessions } from '../hooks/queries';
import { relativeTime, titleCase } from '../lib/format';
import type { SessionResponse } from '../api/types';

function reportScore(s: SessionResponse): number | null {
  const report = (s.metadata as any)?.report;
  return report?.security_score?.overall ?? null;
}

export default function ReportsPage() {
  const sessions = useSessions();
  const withReports = sessions.data?.filter((s) => (s.metadata as any)?.report) ?? [];

  return (
    <div>
      <PageHeader title="Reports" description="Security reports from completed evaluations." />

      {sessions.isLoading ? (
        <Spinner />
      ) : withReports.length === 0 ? (
        <EmptyState
          icon={<FileText size={26} />}
          title="No reports yet"
          description="Reports appear here once an evaluation completes."
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {withReports.map((s) => {
            const score = reportScore(s);
            return (
              <Link key={s.id} to={`/reports/${s.id}`}>
                <Card hover className="flex items-center gap-4 p-5">
                  {score != null && <ScoreDonut score={score} size={84} label="score" />}
                  <div className="min-w-0">
                    <p className="truncate font-mono text-sm text-content">{s.selected_models.join(', ')}</p>
                    <p className="mt-1 text-xs text-content-subtle">{titleCase(s.selected_tier ?? s.session_type)}</p>
                    <p className="mt-0.5 text-xs text-content-faint">{relativeTime(s.completed_at ?? s.created_at)}</p>
                  </div>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
