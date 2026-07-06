import { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, Trophy } from 'lucide-react';
import { Card, EmptyState, PageHeader, Spinner } from '../components/ui';
import { useLeaderboard } from '../hooks/queries';
import { scoreColor } from '../lib/format';
import { cn } from '../lib/cn';
import type { LeaderboardEntry } from '../api/types';

type SortKey = keyof Pick<
  LeaderboardEntry,
  'avg_overall_score' | 'avg_latency_ms' | 'avg_injection_rate' | 'avg_hallucination_rate'
>;

const COLUMNS: { key: SortKey; label: string; fmt: (v: number) => string; higherBetter: boolean }[] = [
  { key: 'avg_overall_score', label: 'Security Score', fmt: (v) => Math.round(v).toString(), higherBetter: true },
  { key: 'avg_latency_ms', label: 'Avg Latency', fmt: (v) => `${Math.round(v)} ms`, higherBetter: false },
  { key: 'avg_injection_rate', label: 'Injection Fail', fmt: (v) => `${Math.round(v * 100)}%`, higherBetter: false },
  { key: 'avg_hallucination_rate', label: 'Hallucination', fmt: (v) => `${Math.round(v * 100)}%`, higherBetter: false },
];

export default function LeaderboardPage() {
  const lb = useLeaderboard();
  const [sortKey, setSortKey] = useState<SortKey>('avg_overall_score');
  const [asc, setAsc] = useState(false);

  const rows = useMemo(() => {
    const data = [...(lb.data ?? [])];
    data.sort((a, b) => (asc ? a[sortKey] - b[sortKey] : b[sortKey] - a[sortKey]));
    return data;
  }, [lb.data, sortKey, asc]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setAsc((v) => !v);
    else {
      setSortKey(key);
      setAsc(false);
    }
  };

  return (
    <div>
      <PageHeader title="Leaderboard" description="Models ranked by overall security score." />

      {lb.isLoading ? (
        <Spinner />
      ) : (lb.data?.length ?? 0) === 0 ? (
        <EmptyState
          icon={<Trophy size={26} />}
          title="No ranked models yet"
          description="Run benchmark evaluations to populate the leaderboard."
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-content-subtle">
                  <th className="px-4 py-3 font-medium">#</th>
                  <th className="px-4 py-3 font-medium">Model</th>
                  {COLUMNS.map((c) => (
                    <th key={c.key} className="px-4 py-3 font-medium">
                      <button
                        onClick={() => toggleSort(c.key)}
                        className="inline-flex items-center gap-1 hover:text-content rf-focus"
                      >
                        {c.label}
                        {sortKey === c.key &&
                          (asc ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                      </button>
                    </th>
                  ))}
                  <th className="px-4 py-3 font-medium">Runs</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((e, i) => (
                  <tr
                    key={e.model_name}
                    className="border-b border-border/60 last:border-0 hover:bg-overlay"
                  >
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          'inline-flex h-6 w-6 items-center justify-center rounded-md text-xs font-semibold',
                          i === 0 ? 'bg-red-soft text-red-400' : 'bg-elevated text-content-subtle'
                        )}
                      >
                        {i + 1}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-[13px] text-content">{e.model_name}</td>
                    {COLUMNS.map((c) => (
                      <td
                        key={c.key}
                        className={cn(
                          'px-4 py-3 tabular-nums',
                          c.key === 'avg_overall_score' ? scoreColor(e.avg_overall_score) + ' font-semibold' : 'text-content-muted'
                        )}
                      >
                        {c.fmt(e[c.key])}
                      </td>
                    ))}
                    <td className="px-4 py-3 text-content-subtle">{e.benchmark_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
