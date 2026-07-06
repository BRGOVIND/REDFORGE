import { Link, useParams } from 'react-router-dom';
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ArrowLeft, Download, FileJson, FileText, Printer } from 'lucide-react';
import { Badge, Button, Card, CardHeader, ErrorState, PageHeader, Spinner } from '../components/ui';
import { RiskBadge, ScoreDonut, SeverityBadge } from '../components/shared';
import { useReport } from '../hooks/queries';
import { errorMessage } from '../api/client';
import { downloadBlob, reportToMarkdown } from '../lib/export';
import { titleCase } from '../lib/format';

const BAR_COLOR = (score: number) =>
  score >= 90 ? '#3FB950' : score >= 75 ? '#8B8B93' : score >= 50 ? '#D29922' : '#E5484D';

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const report = useReport(id ?? null);

  if (report.isLoading) return <Spinner label="Loading report…" />;
  if (report.isError || !report.data)
    return (
      <ErrorState
        message={report.isError ? errorMessage(report.error) : 'Report not available yet.'}
        onRetry={report.refetch}
      />
    );

  const r = report.data.report;
  const model = (r.model_overview?.model_name as string) || (r.evaluation_summary?.profile as string) || 'model';
  const chartData = r.security_score.categories.map((c) => ({
    name: titleCase(c.category).replace(' ', '\n'),
    score: Math.round(c.score),
  }));

  const exportJson = () =>
    downloadBlob(`redforge-report-${id}.json`, JSON.stringify(r, null, 2), 'application/json');
  const exportMd = () =>
    downloadBlob(`redforge-report-${id}.md`, reportToMarkdown(r, model), 'text/markdown');

  return (
    <div>
      <PageHeader
        title="Security Report"
        description={String(r.evaluation_summary?.profile ?? '')}
        actions={
          <div className="flex items-center gap-2">
            <Link to="/reports">
              <Button variant="ghost" size="sm">
                <ArrowLeft size={14} /> Back
              </Button>
            </Link>
            <Button variant="secondary" size="sm" onClick={exportJson}>
              <FileJson size={14} /> JSON
            </Button>
            <Button variant="secondary" size="sm" onClick={exportMd}>
              <FileText size={14} /> Markdown
            </Button>
            <Button variant="secondary" size="sm" onClick={() => window.print()}>
              <Printer size={14} /> PDF
            </Button>
          </div>
        }
      />

      {/* Summary band */}
      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="flex flex-col items-center justify-center p-6">
          <ScoreDonut score={r.security_score.overall} size={140} />
          <div className="mt-3">
            <RiskBadge risk={r.security_score.risk_band} />
          </div>
        </Card>
        <Card className="lg:col-span-2 p-6">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-content">
            <Download size={14} className="text-content-muted" /> Executive Summary
          </h3>
          <p className="text-sm leading-relaxed text-content-muted">{r.executive_summary}</p>
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <Badge tone="grey">{String(r.evaluation_summary?.total_tests ?? 0)} tests</Badge>
            <Badge tone="red">{String(r.evaluation_summary?.failed_tests ?? 0)} compromised</Badge>
            <Badge tone="neutral">v{r.report_version}</Badge>
          </div>
        </Card>
      </div>

      {/* Category scores chart */}
      <Card className="mb-6">
        <CardHeader title="Category Scores" />
        <div className="p-4" style={{ height: 240 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: -16 }}>
              <XAxis dataKey="name" tick={{ fill: '#A1A1AA', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 100]} tick={{ fill: '#71717A', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: 'rgba(255,255,255,0.03)' }}
                contentStyle={{ background: '#1A1A1E', border: '1px solid #33333A', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: '#E8E8EC' }}
              />
              <Bar dataKey="score" radius={[4, 4, 0, 0]} maxBarSize={64}>
                {chartData.map((d, i) => (
                  <Cell key={i} fill={BAR_COLOR(d.score)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Findings */}
        <Card>
          <CardHeader title="Findings" subtitle={`${r.findings.length} identified`} />
          <div className="divide-y divide-border">
            {r.findings.length === 0 ? (
              <p className="p-6 text-center text-sm text-content-subtle">No vulnerabilities found.</p>
            ) : (
              r.findings.map((f) => (
                <div key={f.id} className="p-4">
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-content">{f.title}</span>
                    <SeverityBadge severity={f.severity} />
                  </div>
                  <p className="text-xs text-content-muted">{f.reason}</p>
                  {f.evidence.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {f.evidence.map((e, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-content-subtle">
                          <span className="font-mono">{e.attack_name}</span>
                          <span className="text-fail">{e.verdict}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <p className="mt-2 rounded-lg border border-border bg-elevated p-2.5 text-xs text-content-muted">
                    <span className="font-medium text-content">Recommendation:</span> {f.recommendation}
                  </p>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* Top vulnerabilities + recommendations */}
        <div className="space-y-6">
          <Card>
            <CardHeader title="Recommendations" />
            <div className="p-4">
              {r.recommendations.length === 0 ? (
                <p className="text-center text-sm text-content-subtle">No action needed.</p>
              ) : (
                <ul className="space-y-2">
                  {r.recommendations.map((rec, i) => (
                    <li key={i} className="flex gap-2 text-sm text-content-muted">
                      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-red-500" />
                      {rec}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Category Detail" />
            <div className="divide-y divide-border">
              {r.security_score.categories.map((c) => (
                <div key={c.category} className="flex items-center justify-between px-4 py-2.5 text-sm">
                  <span className="text-content">{titleCase(c.category)}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-content-subtle">{c.failed}/{c.total} failed</span>
                    <RiskBadge risk={c.risk_level} />
                    <span className="w-8 text-right font-medium tabular-nums text-content">{Math.round(c.score)}</span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
