import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { http, errorMessage } from '../api/client';
import { Card, Spinner } from '../components/ui';
import type { TraceItem } from './TraceExplorerPage';

interface Detail extends TraceItem {
  error_detail: string | null;
  input_text: string | null;
  output_text: string | null;
  attributes: Record<string, unknown>;
  application_version: string | null;
  git_revision: string | null;
  user_id: string | null;
  prompt_template_id: string | null;
  prompt_version_id: string | null;
}

export default function TraceDetail({ project, eventId, onClose, onGroup }: {
  project: string; eventId: string; onClose: () => void; onGroup: (key: string, value: string) => void;
}) {
  const [item, setItem] = useState<Detail | null>(null);
  const [error, setError] = useState('');
  const [revealed, setRevealed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setItem(null);
    setRevealed(false);
    http.get<Detail>(`/projects/${project}/traces/${encodeURIComponent(eventId)}`, { signal: controller.signal })
      .then(({ data }) => setItem(data)).catch((e) => { if (!controller.signal.aborted) setError(errorMessage(e)); });
    return () => controller.abort();
  }, [project, eventId]);
  async function revealBodies() {
    try {
      const { data } = await http.get<Detail>(`/projects/${project}/traces/${encodeURIComponent(eventId)}`, {
        params: { include_bodies: true }, headers: { 'X-RedForge-Sensitive-Access': 'allow' },
      });
      setItem(data);
      setRevealed(true);
    } catch (e) { setError(errorMessage(e)); }
  }
  return <section aria-label="Trace detail" className="mt-4">
    <div className="mb-2 flex items-center justify-between"><h2 className="text-lg font-semibold text-content">Call detail</h2><button type="button" onClick={onClose} className="text-sm underline rf-focus">Close</button></div>
    {error ? <p role="alert" className="text-red-400">{error}</p> : !item ? <Spinner label="Loading detail…" /> : <Card><div className="space-y-4 p-4 text-sm text-content">
      <div className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
        {(['event_id', 'provider', 'model', 'operation', 'route', 'status', 'started_at', 'duration_ms', 'service', 'environment', 'application_version', 'git_revision', 'input_tokens', 'output_tokens', 'usage_source', 'cost_usd', 'cost_source', 'error_detail', 'span_id', 'parent_span_id', 'tenant_id', 'user_id', 'prompt_template_id', 'prompt_version_id'] as const).map((key) => <div key={key} className="break-all"><span className="text-content-subtle">{key.replace(/_/g, ' ')}: </span>{item[key] == null ? 'Unknown' : String(item[key])}</div>)}
      </div>
      {(['trace_id', 'conversation_id'] as const).map((key) => item[key] && <button key={key} type="button" onClick={() => onGroup(key, item[key]!)} className="mr-3 text-xs underline rf-focus">Show {key.replace('_', ' ')}: {item[key]}</button>)}
      {!revealed && <button type="button" onClick={revealBodies} className="w-fit rounded border border-red-500/40 px-3 py-2 text-xs text-content transition-colors hover:bg-red-500/10 rf-focus">Reveal captured bodies · audited</button>}
      <Link to={`/signals?tab=feedback&project=${encodeURIComponent(project)}&event=${encodeURIComponent(eventId)}`} className="ml-2 w-fit rounded border border-border px-3 py-2 text-xs text-content transition-colors hover:bg-overlay rf-focus">Create regression case</Link>
      <div><h3 className="mb-1 font-medium">Input</h3><pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-base p-3 text-xs">{item.input_text ?? 'Not captured'}</pre></div>
      <div><h3 className="mb-1 font-medium">Output</h3><pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-base p-3 text-xs">{item.output_text ?? 'Not captured'}</pre></div>
      <div><h3 className="mb-1 font-medium">Metadata</h3><pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-base p-3 text-xs">{JSON.stringify(item.attributes || {}, null, 2)}</pre></div>
      <p className="text-xs text-content-subtle">Time received by RedForge. Usage and cost show their source; unknown means no metric was reported.</p>
    </div></Card>}
  </section>;
}
