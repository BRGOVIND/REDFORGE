import { useCallback, useEffect, useState } from 'react';
import { Activity, ArrowRight, GitCompareArrows, RefreshCw, Route, Wallet } from 'lucide-react';
import { http, errorMessage } from '../api/client';
import { Card, EmptyState, PageHeader } from '../components/ui';
import {
  activateRouting, cancelComparison, comparisonResults, createComparison, createPrice,
  createRouting, disableRouting, getBudget, getUsage, listComparisons, listPrices,
  listRouting, setBudget, startComparison,
  type Budget, type ComparisonPlan, type ComparisonResult, type RoutingPolicy, type UsageRow,
} from '../api/phase3';

interface Project { id: string; name: string }
interface PromptSet { id: string; title: string }
const field = 'rounded-md border border-border bg-surface px-3 py-2 text-sm text-content rf-focus';
const button = 'rounded-md border border-border px-3 py-2 text-xs text-content hover:bg-overlay rf-focus disabled:opacity-50';
const action = 'rounded-md bg-red-600 px-3 py-2 text-xs font-semibold text-white hover:bg-red-700 rf-focus disabled:opacity-50';
const candidates = (text: string) => text.split('\n').map(line => line.trim()).filter(Boolean).map(line => {
  const colon = line.indexOf(':');
  return { provider: colon < 0 ? '' : line.slice(0, colon).trim(), model: colon < 0 ? '' : line.slice(colon + 1).trim() };
});

export default function OptimizationPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState('');
  const [tab, setTab] = useState<'compare' | 'routing' | 'costs'>('compare');
  const [sets, setSets] = useState<PromptSet[]>([]);
  const [plans, setPlans] = useState<ComparisonPlan[]>([]);
  const [selected, setSelected] = useState('');
  const [results, setResults] = useState<ComparisonResult[]>([]);
  const [policies, setPolicies] = useState<RoutingPolicy[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [budget, setBudgetState] = useState<Budget>({ configured: false });
  const [prices, setPrices] = useState<{ id: string; provider: string; model: string;
    version: number; source: string; rates: Record<string, number> }[]>([]);
  const [usage, setUsage] = useState<UsageRow[]>([]);
  const [groupBy, setGroupBy] = useState('provider');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [comparison, setComparison] = useState({ name: '', setId: '', targets: 'ollama:model-a\nollama:model-b',
    maxTokens: '512', timeout: '30', concurrency: '2', remote: false, maxCost: '1' });
  const [routeForm, setRouteForm] = useState({ name: '', mode: 'fixed', targets: 'ollama:model-a',
    maxAttempts: '1', remote: false, maxCost: '1', maxLatency: '', maxObservedCost: '', minSamples: '5' });
  const [routePrompt, setRoutePrompt] = useState('');
  const [routeRemote, setRouteRemote] = useState(false);
  const [routeResult, setRouteResult] = useState('');
  const [priceForm, setPriceForm] = useState({ provider: 'openai', model: '', source: '', input: '', output: '' });
  const [budgetForm, setBudgetForm] = useState({ period: 'monthly', soft: '10', hard: '' });

  useEffect(() => {
    http.get<Project[]>('/projects', { params: { limit: 200 } }).then(({ data }) => {
      setProjects(data); setProject(p => p || data[0]?.id || '');
    }).catch(e => setError(errorMessage(e)));
  }, []);

  const refresh = useCallback(async () => {
    if (!project) return;
    try {
      const [promptSets, comparisons, routing, priceList, currentBudget, totals] = await Promise.all([
        http.get<PromptSet[]>('/evaluation-workbench/prompt-sets', { params: { project_id: project } }).then(r => r.data),
        listComparisons(project), listRouting(project), listPrices(project), getBudget(project), getUsage(project, groupBy),
      ]);
      setSets(promptSets); setPlans(comparisons); setPolicies(routing.items); setActive(routing.active_policy_id);
      setPrices(priceList); setBudgetState(currentBudget); setUsage(totals.rows);
      setComparison(c => ({ ...c, setId: promptSets.some(s => s.id === c.setId) ? c.setId : promptSets[0]?.id || '' }));
      setSelected(id => comparisons.some(p => p.id === id) ? id : comparisons[0]?.id || '');
      setError('');
    } catch (e) { setError(errorMessage(e)); }
  }, [project, groupBy]);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!project || !plans.some(p => p.status === 'pending' || p.status === 'running')) return;
    const timer = window.setInterval(() => { void refresh(); }, 2500);
    return () => window.clearInterval(timer);
  }, [project, plans, refresh]);
  useEffect(() => {
    if (!project || !selected) { setResults([]); return; }
    void comparisonResults(project, selected).then(data => setResults(data.results)).catch(e => setError(errorMessage(e)));
  }, [project, selected, plans]);

  async function act(work: () => Promise<unknown>, message: string) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); setNotice(message); await refresh(); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  const current = plans.find(p => p.id === selected);

  return <div className="space-y-5">
    <PageHeader title="Model decisions" description="Compare measured runs, choose an explicit route, and see which usage has a real price." />
    <div className="flex flex-wrap items-center gap-3">
      <label htmlFor="optimization-project" className="text-xs text-content-subtle">Project</label>
      <select id="optimization-project" value={project} onChange={e => setProject(e.target.value)} className={field}>
        {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <button type="button" className={`${button} ml-auto inline-flex items-center gap-1`} onClick={() => void refresh()} disabled={!project || busy}><RefreshCw size={13} /> Refresh</button>
    </div>
    <div className="flex gap-1 border-b border-border" role="tablist" aria-label="Model decisions">
      {(['compare', 'routing', 'costs'] as const).map(key => <button key={key} type="button" role="tab"
        aria-selected={tab === key} onClick={() => setTab(key)} className={`border-b-2 px-4 py-2 text-sm rf-focus ${tab === key
          ? 'border-red-600 text-content' : 'border-transparent text-content-subtle hover:text-content'}`}>
        {key === 'compare' ? 'Compare' : key === 'routing' ? 'Routing' : 'Costs'}
      </button>)}
    </div>
    {error && <p role="alert" className="rounded-md border border-red-500/30 p-3 text-sm text-red-400">{error}</p>}
    {notice && <p role="status" className="rounded-md border border-border p-3 text-sm text-content">{notice}</p>}
    {!project ? <EmptyState icon={<Activity size={24} />} title="No project" description="Create a project first." /> : tab === 'compare' ? <>
      <Card><form className="space-y-3 p-4" onSubmit={e => { e.preventDefault(); void act(async () => {
        const plan = await createComparison(project, { name: comparison.name, prompt_set_id: comparison.setId,
          candidates: candidates(comparison.targets), max_output_tokens: Number(comparison.maxTokens),
          timeout_seconds: Number(comparison.timeout), concurrency_limit: Number(comparison.concurrency),
          approve_remote: comparison.remote,
          max_estimated_cost_usd: comparison.remote ? Number(comparison.maxCost) : null });
        setSelected(plan.id);
      }, 'Plan frozen. Review it before starting.'); }}>
        <div className="flex items-center gap-2"><GitCompareArrows size={16} className="text-red-400" /><h2 className="text-sm font-semibold text-content">New comparison</h2></div>
        <p className="text-xs text-content-subtle">Uses published Workbench prompts. Same frozen dataset and scorer for every candidate. No run starts until you press Start.</p>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-xs text-content-subtle">Name<input required value={comparison.name} onChange={e => setComparison({ ...comparison, name: e.target.value })} className={`${field} mt-1 w-full`} /></label>
          <label className="text-xs text-content-subtle">Prompt set<select required value={comparison.setId} onChange={e => setComparison({ ...comparison, setId: e.target.value })} className={`${field} mt-1 w-full`}>
            {sets.map(s => <option key={s.id} value={s.id}>{s.title}</option>)}
          </select></label>
        </div>
        <label className="block text-xs text-content-subtle">Candidates, one provider:model per line<textarea rows={3} required value={comparison.targets} onChange={e => setComparison({ ...comparison, targets: e.target.value })} className={`${field} mt-1 w-full font-mono`} /></label>
        <div className="flex flex-wrap gap-3">
          <label className="text-xs text-content-subtle">Max output tokens<input type="number" min="1" max="2048" value={comparison.maxTokens} onChange={e => setComparison({ ...comparison, maxTokens: e.target.value })} className={`${field} mt-1 w-32`} /></label>
          <label className="text-xs text-content-subtle">Timeout, seconds<input type="number" min="1" max="60" value={comparison.timeout} onChange={e => setComparison({ ...comparison, timeout: e.target.value })} className={`${field} mt-1 w-28`} /></label>
          <label className="text-xs text-content-subtle">Concurrency<input type="number" min="1" max="4" value={comparison.concurrency} onChange={e => setComparison({ ...comparison, concurrency: e.target.value })} className={`${field} mt-1 w-24`} /></label>
        </div>
        <label className="flex items-center gap-2 text-xs text-content-subtle"><input type="checkbox" checked={comparison.remote} onChange={e => setComparison({ ...comparison, remote: e.target.checked })} />Approve billable remote candidates</label>
        {comparison.remote && <label className="text-xs text-content-subtle">Estimated run limit, USD<input type="number" min="0.01" step="0.01" value={comparison.maxCost} onChange={e => setComparison({ ...comparison, maxCost: e.target.value })} className={`${field} ml-2 w-28`} /></label>}
        <button type="submit" disabled={busy || !sets.length} className={action}>Freeze plan</button>
      </form></Card>
      <div className="grid gap-4 lg:grid-cols-[minmax(220px,1fr)_minmax(0,2fr)]">
        <Card><div className="p-4"><h2 className="mb-3 text-sm font-semibold text-content">Plans</h2>
          {plans.length ? <div className="space-y-2">{plans.map(p => <button type="button" key={p.id} onClick={() => setSelected(p.id)}
            className={`flex w-full items-center justify-between rounded-md border p-3 text-left text-xs rf-focus ${selected === p.id ? 'border-red-500/50 bg-red-500/5' : 'border-border hover:bg-overlay'}`}>
            <span><strong className="block text-content">{p.snapshot.name}</strong><span className="text-content-subtle">{p.status} · {p.progress ? `${p.progress.completed}/${p.progress.total}` : 'not started'}</span></span><ArrowRight size={14} />
          </button>)}</div> : <p className="text-xs text-content-subtle">No comparison plans yet.</p>}</div></Card>
        <Card><div className="space-y-3 p-4"><h2 className="text-sm font-semibold text-content">{current?.snapshot.name || 'Select a plan'}</h2>
          {current && <><p className="text-xs text-content-subtle">{current.snapshot.candidates.map(c => `${c.provider}/${c.model}`).join(' vs ')} · {Object.keys(current.snapshot.dataset.prompts).length} frozen prompts</p>
            <p className="text-xs text-content-subtle">Remote estimate: {current.snapshot.remote_estimate_usd == null ? 'not applicable' : `$${current.snapshot.remote_estimate_usd} (not a hard cap)`}</p>
            <div className="flex gap-2">{current.status === 'created' && <button type="button" className={action} disabled={busy} onClick={() => void act(() => startComparison(project, current.id, Boolean(current.snapshot.remote_estimate_usd != null)), 'Run queued.')}>Start run</button>}
              {(current.status === 'pending' || current.status === 'running') && <button type="button" className={button} onClick={() => void act(() => cancelComparison(project, current.id), 'Cancellation requested.')}>Cancel</button>}
              {current.session_id && <a className={button} href={`/api/projects/${encodeURIComponent(project)}/comparisons/${current.id}/results?format=csv`}>Export CSV</a>}</div>
            {results.length > 0 && <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr className="border-b border-border text-content-subtle"><th className="py-2">Candidate</th><th>Prompt</th><th>Verdict</th><th>Quality</th><th>Latency</th><th>Cost</th></tr></thead><tbody>{results.map((r, i) => <tr key={i} className="border-b border-border/50"><td className="py-2 text-content">{r.provider}/{r.target_model}</td><td>{r.prompt_title}</td><td>{r.error || r.verdict}</td><td>{r.similarity_score ?? '—'}</td><td>{r.metrics.latency_ms == null ? '—' : `${Math.round(r.metrics.latency_ms)} ms`}</td><td>{r.metrics.cost_usd == null ? '—' : `$${r.metrics.cost_usd}`}</td></tr>)}</tbody></table></div>}
          </>}</div></Card>
      </div>
    </> : tab === 'routing' ? <>
      <Card><div className="space-y-3 p-4"><div className="flex items-center gap-2"><Route size={16} className="text-red-400" /><h2 className="text-sm font-semibold text-content">Active policy</h2></div>
        <p className="text-xs text-content-subtle">Routing affects only explicit calls to this endpoint. It never changes the global runtime or silently sends prompts off-device.</p>
        <p className="text-sm text-content">{active ? policies.find(p => p.id === active)?.name || 'Unknown policy' : 'Disabled'}</p>
        {active && <button type="button" className={button} onClick={() => void act(() => disableRouting(project), 'Routing disabled.')}>Disable routing</button>}</div></Card>
      <Card><form className="space-y-3 p-4" onSubmit={e => { e.preventDefault(); void act(async () => {
        await createRouting(project, { name: routeForm.name, mode: routeForm.mode,
          candidates: candidates(routeForm.targets), max_attempts: Number(routeForm.maxAttempts),
          max_output_tokens: 512, total_timeout_seconds: 30, remote_enabled: routeForm.remote,
          max_estimated_cost_usd: routeForm.remote ? Number(routeForm.maxCost) : null,
          max_observed_latency_ms: routeForm.mode === 'threshold' && routeForm.maxLatency ? Number(routeForm.maxLatency) : null,
          max_observed_cost_usd: routeForm.mode === 'threshold' && routeForm.maxObservedCost ? Number(routeForm.maxObservedCost) : null,
          min_samples: Number(routeForm.minSamples) });
      }, 'Versioned policy created. Activate it explicitly.'); }}>
        <h2 className="text-sm font-semibold text-content">New policy version</h2>
        <div className="flex flex-wrap gap-3"><input required aria-label="Policy name" placeholder="Policy name" value={routeForm.name} onChange={e => setRouteForm({ ...routeForm, name: e.target.value })} className={`${field} flex-1`} />
          <select aria-label="Routing mode" value={routeForm.mode} onChange={e => setRouteForm({ ...routeForm, mode: e.target.value })} className={field}><option value="fixed">Fixed</option><option value="fallback">Ordered fallback</option><option value="threshold">Measured threshold</option></select>
          <input aria-label="Maximum attempts" type="number" min="1" max="3" value={routeForm.maxAttempts} onChange={e => setRouteForm({ ...routeForm, maxAttempts: e.target.value })} className={`${field} w-28`} /></div>
        <textarea rows={2} aria-label="Route candidates" value={routeForm.targets} onChange={e => setRouteForm({ ...routeForm, targets: e.target.value })} className={`${field} w-full font-mono`} />
        {routeForm.mode === 'threshold' && <div className="space-y-2">
          <p className="text-xs text-content-subtle">Only candidates with enough successful calls in the last 24 hours and measured averages within these limits can be selected. No evidence means no route.</p>
          <div className="flex flex-wrap gap-2">
            <input aria-label="Maximum observed latency milliseconds" placeholder="Max latency, ms" type="number" min="1" max="120000" value={routeForm.maxLatency} onChange={e => setRouteForm({ ...routeForm, maxLatency: e.target.value })} className={`${field} w-40`} />
            <input aria-label="Maximum observed cost USD" placeholder="Max cost, USD" type="number" min="0" max="100" step="0.0001" value={routeForm.maxObservedCost} onChange={e => setRouteForm({ ...routeForm, maxObservedCost: e.target.value })} className={`${field} w-40`} />
            <input aria-label="Minimum samples" type="number" min="5" max="1000" value={routeForm.minSamples} onChange={e => setRouteForm({ ...routeForm, minSamples: e.target.value })} className={`${field} w-28`} />
          </div>
        </div>}
        <label className="flex items-center gap-2 text-xs text-content-subtle"><input type="checkbox" checked={routeForm.remote} onChange={e => setRouteForm({ ...routeForm, remote: e.target.checked })} />Allow remote candidate in this policy</label>
        {routeForm.remote && <label className="text-xs text-content-subtle">Estimated per-call limit, USD<input type="number" step="0.01" min="0.01" value={routeForm.maxCost} onChange={e => setRouteForm({ ...routeForm, maxCost: e.target.value })} className={`${field} ml-2 w-28`} /></label>}
        <button type="submit" disabled={busy} className={action}>Save policy</button>
      </form></Card>
      <div className="space-y-2">{policies.map(p => <Card key={p.id}><div className="flex items-center gap-3 p-3 text-xs"><div className="min-w-0 flex-1"><p className="font-semibold text-content">{p.name} · v{p.version} {active === p.id ? '· active' : ''}</p><p className="text-content-subtle">{p.definition.mode} · {p.definition.candidates.map(c => `${c.provider}/${c.model}`).join(' → ')}</p></div>
        {active !== p.id && <button type="button" className={button} onClick={() => void act(() => activateRouting(project, p.id), 'Policy activated.')}>Activate</button>}</div></Card>)}</div>
      {active && <Card><div className="space-y-3 p-4"><h2 className="text-sm font-semibold text-content">Try active route</h2>
        <textarea rows={3} aria-label="Test prompt" placeholder="Type a non-sensitive test prompt" value={routePrompt} onChange={e => setRoutePrompt(e.target.value)} className={`${field} w-full`} />
        <label className="flex items-center gap-2 text-xs text-content-subtle"><input type="checkbox" checked={routeRemote} onChange={e => setRouteRemote(e.target.checked)} />I explicitly approve sending this prompt to a configured remote provider if routing selects it</label>
        <button type="button" disabled={busy || !routePrompt.trim()} className={action} onClick={() => void act(async () => {
          const { data } = await http.post<{ output: string | null; attempts: { provider: string; status: string }[] }>(`/projects/${encodeURIComponent(project)}/routing/execute`, {
            prompt: routePrompt, allow_remote: routeRemote, confirm_sensitive_remote: routeRemote,
          }); setRouteResult(`${data.attempts.map(a => `${a.provider}: ${a.status}`).join(' → ')}\n\n${data.output || 'No output'}`);
        }, 'Route complete.')}>Run explicit test</button>
        {routeResult && <pre className="whitespace-pre-wrap rounded-md border border-border bg-base p-3 text-xs text-content">{routeResult}</pre>}
      </div></Card>}
    </> : <>
      <div className="grid gap-4 md:grid-cols-2"><Card><div className="space-y-2 p-4"><div className="flex items-center gap-2"><Wallet size={16} className="text-red-400" /><h2 className="text-sm font-semibold text-content">Observed spend</h2></div>
        <p className="text-2xl font-semibold text-content">{budget.observed_usd == null ? '—' : `$${budget.observed_usd.toFixed(4)}`}</p>
        <p className="text-xs text-content-subtle">{budget.configured ? `${budget.period} period · soft limit $${budget.soft_limit_usd}` : 'No budget configured'} · unpriced calls excluded</p>
        {budget.soft_exceeded && <p className="text-xs text-red-400">Soft limit exceeded. Review usage before more remote calls.</p>}
        <p className="text-xs text-content-subtle">Hard limits block new billable RedForge route/comparison calls. SDK or external calls cannot be preempted.</p>
      </div></Card><Card><form className="space-y-2 p-4" onSubmit={e => { e.preventDefault(); void act(() => setBudget(project, {
        period: budgetForm.period, soft_limit_usd: Number(budgetForm.soft),
        hard_limit_usd: budgetForm.hard ? Number(budgetForm.hard) : null,
      }), 'Budget saved.'); }}><h2 className="text-sm font-semibold text-content">Budget limits</h2>
        <div className="flex flex-wrap gap-2"><select aria-label="Budget period" className={field} value={budgetForm.period} onChange={e => setBudgetForm({ ...budgetForm, period: e.target.value })}><option value="monthly">Monthly</option><option value="daily">Daily</option></select>
          <input aria-label="Soft limit USD" type="number" step="0.01" min="0.01" value={budgetForm.soft} onChange={e => setBudgetForm({ ...budgetForm, soft: e.target.value })} className={`${field} w-28`} />
          <input aria-label="Hard limit USD optional" placeholder="Hard, optional" type="number" step="0.01" min="0.01" value={budgetForm.hard} onChange={e => setBudgetForm({ ...budgetForm, hard: e.target.value })} className={`${field} w-36`} /></div><button type="submit" className={action}>Save budget</button>
      </form></Card></div>
      <Card><form className="space-y-3 p-4" onSubmit={e => { e.preventDefault(); void act(() => createPrice(project, {
        provider: priceForm.provider, model: priceForm.model, source: priceForm.source,
        effective_at: new Date().toISOString(), input_usd_per_million: Number(priceForm.input),
        output_usd_per_million: Number(priceForm.output),
      }), 'Versioned price saved. Historical prices remain unchanged.'); }}>
        <h2 className="text-sm font-semibold text-content">Add operator-verified price</h2><p className="text-xs text-content-subtle">USD per million tokens. Enter a source and exact model. No automatic pricing download.</p>
        <div className="flex flex-wrap gap-2"><input required aria-label="Price provider" placeholder="provider" value={priceForm.provider} onChange={e => setPriceForm({ ...priceForm, provider: e.target.value })} className={`${field} w-28`} />
          <input required aria-label="Price model" placeholder="Exact model ID" value={priceForm.model} onChange={e => setPriceForm({ ...priceForm, model: e.target.value })} className={`${field} flex-1`} />
          <input required aria-label="Pricing source" placeholder="Pricing source or note" value={priceForm.source} onChange={e => setPriceForm({ ...priceForm, source: e.target.value })} className={`${field} flex-1`} />
          <input required aria-label="Input rate" placeholder="Input $/M" type="number" min="0" step="0.0001" value={priceForm.input} onChange={e => setPriceForm({ ...priceForm, input: e.target.value })} className={`${field} w-28`} />
          <input required aria-label="Output rate" placeholder="Output $/M" type="number" min="0" step="0.0001" value={priceForm.output} onChange={e => setPriceForm({ ...priceForm, output: e.target.value })} className={`${field} w-28`} /></div>
        <button type="submit" disabled={busy} className={action}>Save price</button>
      </form></Card>
      <Card><div className="space-y-3 p-4"><div className="flex items-center justify-between"><h2 className="text-sm font-semibold text-content">Usage, last 30 days</h2><select aria-label="Group usage by" value={groupBy} onChange={e => setGroupBy(e.target.value)} className={field}>{['provider', 'model', 'service', 'route', 'environment', 'tenant', 'day'].map(x => <option key={x} value={x}>{x}</option>)}</select></div>
        {usage.length ? <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr className="border-b border-border text-content-subtle"><th className="py-2">{groupBy}</th><th>Calls</th><th>USD</th><th>Input</th><th>Output</th><th>Unpriced</th></tr></thead><tbody>{usage.map(row => <tr key={row.dimension} className="border-b border-border/50"><td className="py-2 text-content">{row.dimension}</td><td>{row.calls}</td><td>{row.cost_usd == null ? '—' : `$${row.cost_usd}`}</td><td>{row.input_tokens ?? '—'}</td><td>{row.output_tokens ?? '—'}</td><td>{row.unpriced_calls}</td></tr>)}</tbody></table></div> : <p className="text-xs text-content-subtle">No captured successful calls in this window.</p>}
        <a className={button} href={`/api/projects/${encodeURIComponent(project)}/costs/usage?group_by=${encodeURIComponent(groupBy)}&format=csv`}>Export CSV</a>
      </div></Card>
      <div className="space-y-2">{prices.slice(0, 10).map(price => <Card key={price.id}><div className="flex items-center justify-between p-3 text-xs"><span className="text-content">{price.provider}/{price.model} · v{price.version}</span><span className="text-content-subtle">{price.source} · ${price.rates.input}/M in · ${price.rates.output}/M out</span></div></Card>)}</div>
    </>}
  </div>;
}
