import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Copy,
  ExternalLink,
  Minus,
  RefreshCw,
} from 'lucide-react';
import { Badge, Button, Card } from './ui';
import { errorMessage } from '../api/client';
import { toast } from '../lib/toast';
import * as api from '../api/endpoints';
import type { Dependency, DependencyReport } from '../api/types';

/**
 * "What's installed on this machine, and how do I get the rest?"
 *
 * Shared by the first-run wizard and Settings → Diagnostics so both always tell
 * the same story. Deliberately non-alarming: nothing here is required for
 * RedForge to run (the app bundles its own backend), so missing tools are shown
 * as capability unlocks with a concrete next step — never as errors.
 */

function SeverityBadge({ severity }: { severity: Dependency['severity'] }) {
  if (severity === 'required') return <Badge tone="red" title="RedForge cannot run without this">required</Badge>;
  if (severity === 'recommended') return <Badge tone="amber" title="A headline capability needs this">recommended</Badge>;
  return <Badge tone="grey" title="Only a specific workflow needs this">optional</Badge>;
}

function StatusIcon({ dep }: { dep: Dependency }) {
  if (dep.found) return <Check size={15} className="shrink-0 text-pass" aria-label="detected" />;
  if (dep.severity === 'required') return <AlertTriangle size={15} className="shrink-0 text-fail" aria-label="missing" />;
  return <Minus size={15} className="shrink-0 text-content-faint" aria-label="not detected" />;
}

function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(command);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          toast.error('Could not copy', 'Clipboard access was denied by the browser.');
        }
      }}
      title={`Copy: ${command}`}
      className="inline-flex items-center gap-1.5 rounded border border-border bg-base px-2 py-1 font-mono text-[11px] text-content-subtle transition-colors hover:border-border-strong hover:text-content rf-focus"
    >
      {copied ? <Check size={11} className="text-pass" /> : <Copy size={11} />}
      <span className="max-w-[220px] truncate">{command}</span>
    </button>
  );
}

function DependencyRow({ dep }: { dep: Dependency }) {
  return (
    <li className="flex items-start justify-between gap-4 px-5 py-3.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <StatusIcon dep={dep} />
          <span className="text-[13px] font-medium text-content">{dep.label}</span>
          {dep.version && <span className="font-mono text-[11px] text-content-faint">{dep.version}</span>}
          {!dep.found && <SeverityBadge severity={dep.severity} />}
        </div>
        <p className="mt-1 pl-[23px] text-[11px] leading-relaxed text-content-subtle">{dep.purpose}</p>
        {dep.found && dep.path && (
          <p className="mt-0.5 truncate pl-[23px] font-mono text-[10px] text-content-faint" title={dep.path}>
            {dep.path}
          </p>
        )}
      </div>

      {/* Missing → give the user the shortest path to fixing it. */}
      {!dep.found && (
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          {dep.remedy.command && <CopyCommand command={dep.remedy.command} />}
          {dep.remedy.url && (
            <a
              href={dep.remedy.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[11px] text-content-muted hover:text-content rf-focus"
            >
              Download <ExternalLink size={10} />
            </a>
          )}
        </div>
      )}
    </li>
  );
}

export function DependencyPanel({ compact = false }: { compact?: boolean }) {
  const [report, setReport] = useState<DependencyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (refresh = false) => {
    refresh ? setRefreshing(true) : setLoading(true);
    try {
      setReport(await api.getDependencies(refresh));
    } catch (e) {
      toast.error('Could not detect installed tools', errorMessage(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (loading) {
    return (
      <Card className="mt-4 p-5">
        <p className="text-[12px] text-content-subtle">Detecting installed tools…</p>
      </Card>
    );
  }
  if (!report) return null;

  // Missing-but-useful first: that is the only part the user may want to act on.
  const ordered = [...report.dependencies].sort((a, b) => {
    if (a.found !== b.found) return a.found ? 1 : -1;
    const rank = { required: 0, recommended: 1, optional: 2 } as const;
    return rank[a.severity] - rank[b.severity];
  });

  return (
    <Card className="mt-4 overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
        <div>
          <h3 className="text-[13px] font-semibold text-content">Installed tools</h3>
          <p className="mt-0.5 text-[11px] text-content-subtle">
            {report.summary} detected on {report.platform}
            {report.ready && ' · nothing required is missing'}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => load(true)} loading={refreshing}>
          <RefreshCw size={13} /> Re-scan
        </Button>
      </div>

      <ul className="divide-y divide-border">
        {(compact ? ordered.filter((d) => !d.found || d.severity !== 'optional') : ordered).map((d) => (
          <DependencyRow key={d.key} dep={d} />
        ))}
      </ul>

      <p className="border-t border-border px-5 py-3 text-[11px] text-content-subtle">
        RedForge bundles its own backend — none of these are needed just to run the app.
        Install one to unlock the capability it describes, then re-scan.
      </p>
    </Card>
  );
}
