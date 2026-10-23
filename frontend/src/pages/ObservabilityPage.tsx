import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Activity, ArrowRight, Bell, CheckCircle2, FlaskConical, Plus, RefreshCw } from 'lucide-react';
import { http, errorMessage } from '../api/client';
import { Card, EmptyState, PageHeader, Spinner } from '../components/ui';
import {
  approveFeedback, createFeedback, createRule, dryRunRule, editFeedback, getFeedback,
  listAlerts, listFeedback, listRules, replayFeedback, setAlertState, setFeedbackState,
  type AnomalyAlert, type AnomalyRule, type FeedbackCase,
} from '../api/phase4';

interface Project { id: string; name: string }
interface PromptSet { id: string; title: string }
const metrics = [
  ['latency_p95', 'P95 latency, ms'], ['error_rate', 'Error rate, %'],
  ['timeout_rate', 'Timeout rate, %'], ['tokens_per_call', 'Tokens per call'],
  ['cost_per_call_usd', 'Cost per call, USD'], ['project_spend_usd', 'Project spend, USD'],
  ['eval_pass_rate', 'Evaluation pass rate, %'],
  ['provider_availability', 'Provider availability, %'],
];
const categories = ['incorrect_output', 'hallucination', 'tool_failure', 'policy_violation', 'latency_regression', 'security_concern'];
const input = 'rounded-md border border-border bg-surface px-3 py-2 text-sm text-content rf-focus';
const secondary = 'rounded-md border border-border px-3 py-2 text-xs text-content transition-colors hover:bg-overlay rf-focus';
const primary = 'rounded-md bg-red-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-red-700 rf-focus';

export default function ObservabilityPage() {
  const [params] = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState(params.get('project') || '');
  const [tab, setTab] = useState<'alerts' | 'feedback'>(params.get('tab') === 'feedback' ? 'feedback' : 'alerts');
  const [rules, setRules] = useState<AnomalyRule[]>([]);
  const [alerts, setAlerts] = useState<AnomalyAlert[]>([]);
  const [cases, setCases] = useState<FeedbackCase[]>([]);
  const [promptSets, setPromptSets] = useState<PromptSet[]>([]);
  const [selected, setSelected] = useState<FeedbackCase | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [newRule, setNewRule] = useState({ name: '', metric: 'error_rate', threshold: '10', min_samples: '20' });
  const [newCase, setNewCase] = useState({ event_id: params.get('event') || '', category: 'incorrect_output', title: '' });
  const [draft, setDraft] = useState({ title: '', notes: '', labels: '', prompt_text: '', expected_output: '', min_similarity: '60' });
  const [setId, setSetId] = useState('');
  const [model, setModel] = useState('');

  useEffect(() => {
    http.get<Project[]>('/projects', { params: { limit: 200 } }).then(({ data }) => {
      setProjects(data);
      setProject(previous => previous || data[0]?.id || '');
    }).catch(e => setError(errorMessage(e)));
  }, []);

  const refresh = useCallback(async () => {
    if (!project) return;
    setBusy(true);
    try {
      const [r, a, c, sets] = await Promise.all([
        listRules(project), listAlerts(project), listFeedback(project),
        http.get<PromptSet[]>('/evaluation-workbench/prompt-sets', { params: { project_id: project } }).then(x => x.data),
      ]);
      setRules(r.items); setAlerts(a.items); setCases(c.items); setPromptSets(sets);
      setSetId(previous => sets.some(s => s.id === previous) ? previous : sets[0]?.id || '');
      setError('');
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }, [project]);
  useEffect(() => { void refresh(); }, [refresh]);

  async function act(work: () => Promise<unknown>, message: string) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); if (message) setNotice(message); await refresh(); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  async function openCase(id: string) {
    setError('');
    try {
      const data = await getFeedback(project, id);
      setSelected(data);
      setDraft({ title: data.title, notes: data.notes || '', labels: (data.labels || []).join(', '),
        prompt_text: data.prompt_text || '', expected_output: data.expected_output || '',
        min_similarity: '60' });
    } catch (e) { setError(errorMessage(e)); }
  }

  return <div className="space-y-5">
    <PageHeader title="Signals & feedback" description="Local alerts from observed calls. Reviewed failures become versioned evaluation cases." />
    <div className="flex flex-wrap items-center gap-3">
      <label htmlFor="signal-project" className="text-xs text-content-subtle">Project</label>
      <select id="signal-project" value={project} onChange={e => { setProject(e.target.value); setSelected(null); }} className={input}>
        {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <button type="button" onClick={() => void refresh()} disabled={!project || busy} className={`${secondary} ml-auto inline-flex items-center gap-1`}><RefreshCw size={13} /> Refresh</button>
    </div>
    <div className="flex gap-1 border-b border-border" role="tablist" aria-label="Observability sections">
      {(['alerts', 'feedback'] as const).map(value => <button key={value} type="button" role="tab" aria-selected={tab === value}
        onClick={() => setTab(value)} className={`border-b-2 px-4 py-2 text-sm capitalize transition-colors rf-focus ${tab === value ? 'border-red-600 text-content' : 'border-transparent text-content-subtle hover:text-content'}`}>{value === 'alerts' ? `Alerts ${alerts.filter(a => a.state === 'open').length || ''}` : `Feedback ${cases.length || ''}`}</button>)}
    </div>
    {error && <p role="alert" className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-400">{error}</p>}
    {notice && <p role="status" className="rounded-md border border-border bg-surface p-3 text-sm text-content">{notice}</p>}
    {!project ? <EmptyState icon={<Activity size={26} />} title="No project" description="Create a project to monitor calls." /> : tab === 'alerts' ? <>
      <Card><div className="border-l-2 border-red-600 p-4">
        <div className="mb-3 flex items-center gap-2"><Bell size={16} className="text-red-500" /><h2 className="text-sm font-semibold text-content">New alert rule</h2></div>
        <p className="mb-4 text-xs text-content-subtle">Thresholds use local data only. Sparse windows stay quiet. Alerts describe observed anomalies, not confirmed incidents.</p>
        <form onSubmit={e => { e.preventDefault(); void act(() => createRule(project, {
          name: newRule.name, metric: newRule.metric, threshold: Number(newRule.threshold), min_samples: Number(newRule.min_samples),
        }), 'Rule created. It will be evaluated on the next monitoring interval.'); }} className="flex flex-wrap gap-2">
          <input aria-label="Rule name" required placeholder="Rule name" value={newRule.name} onChange={e => setNewRule({ ...newRule, name: e.target.value })} className={`${input} min-w-44 flex-1`} />
          <select aria-label="Metric" value={newRule.metric} onChange={e => setNewRule({ ...newRule, metric: e.target.value, min_samples: e.target.value === 'provider_availability' ? '1' : newRule.min_samples })} className={input}>{metrics.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
          <input type="number" aria-label="Threshold" min="0" required value={newRule.threshold} onChange={e => setNewRule({ ...newRule, threshold: e.target.value })} className={`${input} w-28`} />
          <input type="number" aria-label="Minimum samples" min="1" max="5000" required value={newRule.min_samples} onChange={e => setNewRule({ ...newRule, min_samples: e.target.value })} className={`${input} w-28`} />
          <button type="submit" disabled={busy} className={`${primary} inline-flex items-center gap-1`}><Plus size={14} /> Add rule</button>
        </form>
      </div></Card>
      <section><h2 className="mb-2 text-sm font-semibold text-content">Rules</h2>{rules.length === 0 ? <p className="text-sm text-content-subtle">No rules yet.</p> : <div className="grid gap-2 md:grid-cols-2">{rules.map(rule => <Card key={rule.id}><div className="flex items-start justify-between gap-3 p-4"><div><p className="font-medium text-content">{rule.name}</p><p className="mt-1 text-xs text-content-subtle">{rule.metric.replace(/_/g, ' ')} · threshold {rule.threshold} · min {rule.min_samples} samples</p></div><button type="button" onClick={() => void act(async () => { const result = await dryRunRule(project, rule.id); setNotice(result.status === 'insufficient_data' ? `No alert: ${result.reason}` : `${result.status}: ${result.observed} from ${result.samples} samples`); }, '')} className={secondary}>Dry run</button></div></Card>)}</div>}</section>
      <section><h2 className="mb-2 text-sm font-semibold text-content">Alert history</h2>{alerts.length === 0 ? <EmptyState icon={<CheckCircle2 size={24} />} title="Quiet so far" description="No rule has crossed a threshold with enough evidence." /> : <div className="space-y-2">{alerts.map(alert => <Card key={alert.id}><div className="flex flex-wrap items-center gap-3 p-4"><span className={`h-8 w-1 rounded-full ${alert.severity === 'critical' ? 'bg-red-600' : 'bg-amber-500'}`} aria-hidden="true" /><div className="min-w-52 flex-1"><p className="text-sm font-semibold text-content">{alert.metric.replace(/_/g, ' ')}: {alert.observed.toFixed(2)}</p><p className="text-xs text-content-subtle">{alert.sample_count} samples · baseline {alert.baseline == null ? 'not used' : alert.baseline.toFixed(2)} · {new Date(alert.created_at).toLocaleString()} · {alert.occurrences} occurrence{alert.occurrences === 1 ? '' : 's'}</p></div><span className="rounded-full border border-border px-2 py-1 text-xs text-content-subtle">{alert.classification} · {alert.state}</span>{alert.state !== 'resolved' && <><button type="button" onClick={() => void act(() => setAlertState(project, alert.id, 'acknowledged'), 'Alert acknowledged.')} className={secondary}>Acknowledge</button><button type="button" onClick={() => void act(() => setAlertState(project, alert.id, 'resolved'), 'Alert resolved.')} className={secondary}>Resolve</button></>}</div></Card>)}</div>}</section>
    </> : <>
      <Card><form onSubmit={e => { e.preventDefault(); void act(async () => { await createFeedback(project, newCase); setNewCase({ event_id: '', category: 'incorrect_output', title: '' }); }, 'Draft created. Add a sanitized prompt and review it before approval.'); }} className="p-4"><div className="mb-3 flex items-center gap-2"><FlaskConical size={16} className="text-red-500" /><h2 className="text-sm font-semibold text-content">Trace to test case</h2></div><p className="mb-4 text-xs text-content-subtle">Default: provenance only. Captured input is not copied. Add only the sanitized text needed for a regression test.</p><div className="flex flex-wrap gap-2"><input required aria-label="Trace event ID" placeholder="Trace event ID" value={newCase.event_id} onChange={e => setNewCase({ ...newCase, event_id: e.target.value })} className={`${input} min-w-48 flex-1`} /><select aria-label="Problem category" value={newCase.category} onChange={e => setNewCase({ ...newCase, category: e.target.value })} className={input}>{categories.map(c => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}</select><input required aria-label="Case title" placeholder="What went wrong?" value={newCase.title} onChange={e => setNewCase({ ...newCase, title: e.target.value })} className={`${input} min-w-48 flex-1`} /><button type="submit" disabled={busy} className={primary}>Create draft</button></div></form></Card>
      <section><h2 className="mb-2 text-sm font-semibold text-content">Review queue</h2>{cases.length === 0 ? <EmptyState icon={<FlaskConical size={24} />} title="No feedback cases" description="Select a production trace to start a safe regression case." /> : <div className="space-y-2">{cases.map(c => <Card key={c.id}><div className="flex flex-wrap items-center gap-3 p-4"><span className={`h-8 w-1 rounded-full ${c.state === 'approved' ? 'bg-emerald-500' : 'bg-red-600'}`} /><div className="flex-1"><p className="text-sm font-semibold text-content">{c.title}</p><p className="text-xs text-content-subtle">{c.category.replace(/_/g, ' ')} · trace {c.trace_id || c.source_event_id || c.trace_event_id} · {c.state}{c.dataset_version ? ` · dataset v${c.dataset_version}` : ''}</p></div><button type="button" onClick={() => void openCase(c.id)} className={`${secondary} inline-flex items-center gap-1`}>Open <ArrowRight size={13} /></button></div></Card>)}</div>}</section>
      {selected && <Card><div className="space-y-3 p-4"><div className="flex items-center justify-between"><h2 className="text-sm font-semibold text-content">{selected.title}</h2><button type="button" onClick={() => setSelected(null)} className={secondary}>Close</button></div>{selected.state === 'draft' || selected.state === 'in_review' ? <><div className="grid gap-2 sm:grid-cols-2"><input aria-label="Case title" value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} className={input} /><input aria-label="Labels" placeholder="Labels, comma separated" value={draft.labels} onChange={e => setDraft({ ...draft, labels: e.target.value })} className={input} /></div><textarea aria-label="Sanitized test prompt" placeholder="Sanitized test prompt" rows={3} value={draft.prompt_text} onChange={e => setDraft({ ...draft, prompt_text: e.target.value })} className={`${input} w-full`} /><textarea aria-label="Expected output" placeholder="Expected output, optional. Leave blank if no ground truth." rows={2} value={draft.expected_output} onChange={e => setDraft({ ...draft, expected_output: e.target.value })} className={`${input} w-full`} /><textarea aria-label="Review notes" placeholder="Review notes" rows={2} value={draft.notes} onChange={e => setDraft({ ...draft, notes: e.target.value })} className={`${input} w-full`} /><div className="flex flex-wrap gap-2"><button type="button" onClick={() => void act(async () => { await editFeedback(project, selected.id, { title: draft.title, notes: draft.notes, labels: draft.labels.split(',').map(x => x.trim()).filter(Boolean), prompt_text: draft.prompt_text || null, expected_output: draft.expected_output || null, acceptance_criteria: { min_similarity: Number(draft.min_similarity) } }); await openCase(selected.id); }, 'Draft saved.')} className={primary}>Save draft</button>{selected.state === 'draft' && <button type="button" onClick={() => void act(async () => { await setFeedbackState(project, selected.id, 'in_review'); await openCase(selected.id); }, 'Ready for review.')} className={secondary}>Mark for review</button>}{selected.state === 'in_review' && <><select aria-label="Evaluation prompt set" value={setId} onChange={e => setSetId(e.target.value)} className={input}>{promptSets.map(s => <option key={s.id} value={s.id}>{s.title}</option>)}</select><button type="button" disabled={!setId} onClick={() => void act(async () => { await approveFeedback(project, selected.id, setId); await openCase(selected.id); }, 'Approved into the versioned evaluation dataset.')} className={primary}>Approve into Workbench</button></>}<button type="button" onClick={() => void act(async () => { await setFeedbackState(project, selected.id, 'archived'); setSelected(null); }, 'Case archived.')} className={secondary}>Archive</button></div></> : selected.state === 'approved' ? <div className="flex flex-wrap items-center gap-2"><p className="mr-auto text-xs text-content-subtle">Published prompt and dataset version are immutable. Replay uses only a selected local evaluation environment.</p><input aria-label="Local candidate model" placeholder="Local model name" value={model} onChange={e => setModel(e.target.value)} className={input} /><button type="button" disabled={!model} onClick={() => void act(async () => { const job = await replayFeedback(project, selected.id, model); setNotice(`Local replay queued as job ${job.id}.`); }, '')} className={primary}>Replay locally</button><Link to="/jobs" className={secondary}>View jobs</Link></div> : <p className="text-xs text-content-subtle">Case retained for audit. No replay.</p>}</div></Card>}
    </>}
    {busy && <div className="sr-only"><Spinner label="Working…" /></div>}
  </div>;
}
