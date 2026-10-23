import { lazy, Suspense, useEffect, useState } from 'react';
import { Activity, Copy, KeyRound } from 'lucide-react';
import { http, errorMessage } from '../api/client';
import { Card, EmptyState, PageHeader, Spinner } from '../components/ui';
import { getTracePrivacy, putTracePrivacy, type TracePrivacySettings } from '../api/endpoints';

const TraceDetail = lazy(() => import('./TraceDetail'));

export interface TraceItem {
  event_id: string;
  cursor: number;
  received_at: string;
  started_at: string | null;
  duration_ms: number | null;
  provider: string | null;
  model: string | null;
  operation: string | null;
  route: string | null;
  status: string;
  input_tokens: number | null;
  output_tokens: number | null;
  cached_input_tokens: number | null;
  reasoning_tokens: number | null;
  usage_source: string | null;
  cost_usd: number | null;
  cost_source: string | null;
  pricing_record_id: string | null;
  cost_calculated_at: string | null;
  service: string | null;
  environment: string | null;
  trace_id: string | null;
  parent_span_id: string | null;
  span_id: string | null;
  conversation_id: string | null;
  tenant_id: string | null;
}

interface Project { id: string; name: string }
interface Page { items: TraceItem[]; next_cursor: number | null }
interface TokenInfo { id: string; name: string; prefix: string; tenant_id: string | null; revoked_at: string | null }
const fields = ['provider', 'model', 'status', 'service', 'environment', 'route', 'tenant_id', 'trace_id', 'conversation_id'] as const;

export default function TraceExplorerPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState('');
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [cursor, setCursor] = useState<number | null>(null);
  const [page, setPage] = useState<Page>({ items: [], next_cursor: null });
  const [selected, setSelected] = useState<string | null>(null);
  const [token, setToken] = useState('');
  const [tokens, setTokens] = useState<TokenInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [privacy, setPrivacy] = useState<TracePrivacySettings | null>(null);
  const [savingPrivacy, setSavingPrivacy] = useState(false);

  useEffect(() => {
    http.get<Project[]>('/projects', { params: { limit: 200 } }).then(({ data }) => {
      setProjects(data);
      setProject((previous) => previous || data[0]?.id || '');
    }).catch((e) => setError(errorMessage(e)));
  }, []);

  useEffect(() => {
    if (!project) return;
    const controller = new AbortController();
    setBusy(true);
    setError('');
    http.get<Page>(`/projects/${project}/traces`, {
      params: { ...filters, [filters.trace_id || filters.conversation_id ? 'after_id' : 'before_id']: cursor || undefined, limit: 50 }, signal: controller.signal,
    }).then(({ data }) => setPage(data)).catch((e) => {
      if (!controller.signal.aborted) setError(errorMessage(e));
    }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [project, filters, cursor]);

  useEffect(() => {
    if (!project) return;
    http.get<TokenInfo[]>(`/projects/${project}/trace-tokens`).then(({ data }) => setTokens(data)).catch(() => setTokens([]));
  }, [project]);

  useEffect(() => {
    if (!project) return;
    setPrivacy(null);
    getTracePrivacy(project).then(setPrivacy).catch((e) => setError(errorMessage(e)));
  }, [project]);

  async function savePrivacy() {
    if (!privacy || !project) return;
    setSavingPrivacy(true);
    try { setPrivacy(await putTracePrivacy(project, privacy)); setError(''); }
    catch (e) { setError(errorMessage(e)); }
    finally { setSavingPrivacy(false); }
  }

  function apply(next: Record<string, string>) {
    const query = { ...next };
    for (const key of ['after', 'before']) {
      if (query[key]) query[key] = new Date(query[key]).toISOString();
    }
    setFilters(query);
    setCursor(null);
    setSelected(null);
  }

  async function createToken() {
    if (!project) return;
    try {
      setError('');
      const { data } = await http.post<{ token: string }>(`/projects/${project}/trace-tokens?name=SDK`);
      setToken(data.token);
      const listed = await http.get<TokenInfo[]>(`/projects/${project}/trace-tokens`);
      setTokens(listed.data);
    } catch (e) { setError(errorMessage(e)); }
  }

  async function revokeToken(tokenId: string) {
    try {
      await http.delete(`/projects/${project}/trace-tokens/${tokenId}`);
      setTokens(tokens.map((item) => item.id === tokenId ? { ...item, revoked_at: new Date().toISOString() } : item));
      setToken('');
    } catch (e) { setError(errorMessage(e)); }
  }

  return <div>
    <PageHeader title="Trace Explorer" description="Observed model calls, grouped by the IDs your application sends." />
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <label htmlFor="trace-project" className="text-xs text-content-subtle">Project</label>
      <select id="trace-project" value={project} onChange={(e) => { setProject(e.target.value); setCursor(null); setSelected(null); setToken(''); setTokens([]); }} className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-content rf-focus">
        {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <button type="button" onClick={createToken} disabled={!project} className="ml-auto flex items-center gap-1 rounded-md border border-border px-3 py-2 text-xs text-content hover:bg-overlay rf-focus"><KeyRound size={14} /> Create SDK token</button>
    </div>
    {token && <Card><div className="mb-4 flex flex-wrap items-center gap-2 p-3 text-xs text-content">
      <span>Copy now. Token shown once:</span><code className="break-all rounded bg-base px-2 py-1">{token}</code>
      <button type="button" aria-label="Copy token" onClick={() => navigator.clipboard.writeText(token)} className="rf-focus"><Copy size={15} /></button>
      <button type="button" onClick={() => setToken('')} className="ml-auto underline rf-focus">Dismiss</button>
    </div></Card>}
    {tokens.length > 0 && <details className="mb-4 text-xs text-content-subtle"><summary className="cursor-pointer rf-focus">Manage SDK tokens ({tokens.filter((item) => !item.revoked_at).length} active)</summary>
      <ul className="mt-2 space-y-1">{tokens.map((item) => <li key={item.id} className="flex items-center gap-3 rounded border border-border px-3 py-2"><span>{item.name} · {item.prefix}…{item.tenant_id ? ` · ${item.tenant_id}` : ''}</span><span>{item.revoked_at ? 'Revoked' : 'Active'}</span>{!item.revoked_at && <button type="button" onClick={() => revokeToken(item.id)} className="ml-auto text-red-400 underline rf-focus">Revoke</button>}</li>)}</ul>
    </details>}
    {privacy && <details className="mb-4 rounded-lg border border-border bg-surface/70 p-4 text-xs text-content">
      <summary className="cursor-pointer font-semibold rf-focus">Capture policy <span className="ml-2 font-normal text-content-subtle">{privacy.telemetry_enabled ? (privacy.capture_input || privacy.capture_output ? 'Bodies allowed' : privacy.capture_metadata ? 'Metadata only' : 'Bodies off') : 'Off'}</span></summary>
      <p className="mt-3 max-w-2xl leading-relaxed text-content-subtle">Prompt and response capture is off by default. Enable only when this project may store sensitive content. Redaction runs again on the server before storage.</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {([['telemetry_enabled', 'Trace collection'], ['capture_input', 'Input bodies'], ['capture_output', 'Output bodies'], ['capture_metadata', 'Allowlisted metadata'], ['capture_errors', 'Error details']] as const).map(([key, label]) =>
          <label key={key} className="flex items-center gap-2 rounded border border-border px-3 py-2 hover:bg-overlay"><input type="checkbox" checked={privacy[key]} onChange={(e) => setPrivacy({ ...privacy, [key]: e.target.checked })} className="accent-red-600" />{label}</label>)}
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <label>Metadata allowlist <input value={privacy.metadata_allowlist.join(', ')} onChange={(e) => setPrivacy({ ...privacy, metadata_allowlist: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} placeholder="team, experiment" className="mt-1 w-full rounded border border-border bg-base px-2 py-1.5 rf-focus" /></label>
        <label>Retention (days) <input type="number" min="1" max="365" value={privacy.retention_days} onChange={(e) => setPrivacy({ ...privacy, retention_days: Number(e.target.value) })} className="mt-1 w-full rounded border border-border bg-base px-2 py-1.5 rf-focus" /></label>
        <label>Sample rate <input type="number" min="0" max="1" step="0.05" value={privacy.sample_rate} onChange={(e) => setPrivacy({ ...privacy, sample_rate: Number(e.target.value) })} className="mt-1 w-full rounded border border-border bg-base px-2 py-1.5 rf-focus" /></label>
      </div>
      <button type="button" onClick={savePrivacy} disabled={savingPrivacy} className="mt-3 rounded bg-red-600 px-3 py-2 font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-50 rf-focus">{savingPrivacy ? 'Saving…' : 'Save capture policy'}</button>
    </details>}
    <form onSubmit={(e) => { e.preventDefault(); apply(draft); }} className="mb-4 flex flex-wrap gap-2" aria-label="Trace filters">
      {fields.map((field) => <input key={field} aria-label={field.replace(/_/g, ' ')} placeholder={field.replace(/_/g, ' ')} value={draft[field] || ''} onChange={(e) => setDraft({ ...draft, [field]: e.target.value })} className="min-w-28 flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-content placeholder:text-content-faint rf-focus" />)}
      <input type="datetime-local" aria-label="After" value={draft.after || ''} onChange={(e) => setDraft({ ...draft, after: e.target.value })} className="rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-content rf-focus" />
      <input type="datetime-local" aria-label="Before" value={draft.before || ''} onChange={(e) => setDraft({ ...draft, before: e.target.value })} className="rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-content rf-focus" />
      <button type="submit" className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white rf-focus">Filter</button>
      <button type="button" onClick={() => { setDraft({}); apply({}); }} className="rounded-md border border-border px-3 py-1.5 text-xs rf-focus">Clear</button>
    </form>
    {error && <p role="alert" className="mb-3 text-sm text-red-400">{error}</p>}
    {!project ? <EmptyState icon={<Activity size={26} />} title="No project yet" description="Create a project before collecting traces." />
      : busy ? <Spinner label="Loading traces…" />
      : page.items.length === 0 ? <EmptyState icon={<Activity size={26} />} title="No matching traces" description="Instrument a model call or change filters." />
      : <Card><div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-xs"><thead className="border-b border-border text-content-subtle"><tr>{['Time', 'Provider / model', 'Status', 'Duration', 'Tokens', 'Cost', 'Service', 'Trace'].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead><tbody>
        {page.items.map((item) => <tr key={item.event_id} className="border-b border-border/50 hover:bg-overlay">
          <td className="whitespace-nowrap px-3 py-2"><button type="button" onClick={() => setSelected(item.event_id)} className="text-left text-content underline-offset-2 hover:underline rf-focus">{new Date(item.received_at).toLocaleString()}</button></td>
          <td className="px-3 py-2 text-content">{item.provider || 'Unknown'} / {item.model || 'Unknown'}</td>
          <td className="px-3 py-2">{item.status}</td><td className="px-3 py-2">{item.duration_ms == null ? 'Unknown' : `${Math.round(item.duration_ms)} ms`}</td>
          <td className="px-3 py-2">{item.input_tokens == null && item.output_tokens == null ? 'Unknown' : `${item.input_tokens ?? '?'} / ${item.output_tokens ?? '?'}`} {item.usage_source === 'estimated' ? '(est.)' : ''}</td>
          <td className="px-3 py-2">{item.cost_usd == null ? 'Unknown' : `$${item.cost_usd.toFixed(4)}${item.cost_source === 'estimated' ? ' est.' : ''}`}</td>
          <td className="px-3 py-2">{item.service || 'Unknown'}</td>
          <td className="max-w-32 truncate px-3 py-2">{item.trace_id ? <><button type="button" onClick={() => { const next = { ...draft, trace_id: item.trace_id! }; setDraft(next); apply(next); }} className="underline rf-focus" title="Show trace">{item.trace_id}</button>{item.parent_span_id && <span className="block text-content-subtle" title={`Child of ${item.parent_span_id}`}>Child span</span>}</> : 'None'}</td>
        </tr>)}</tbody></table></div></Card>}
    {page.next_cursor && !busy && <button type="button" onClick={() => setCursor(page.next_cursor)} className="mt-3 rounded-md border border-border px-3 py-2 text-xs rf-focus">{filters.trace_id || filters.conversation_id ? 'More in group' : 'Older events'}</button>}
    {selected && <Suspense fallback={<Spinner label="Loading detail…" />}><TraceDetail project={project} eventId={selected} onClose={() => setSelected(null)} onGroup={(key, value) => { const next = { ...draft, [key]: value }; setDraft(next); apply(next); }} /></Suspense>}
  </div>;
}
