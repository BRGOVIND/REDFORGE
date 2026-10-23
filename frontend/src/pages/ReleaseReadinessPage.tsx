import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, CheckCircle2, LockKeyhole, RefreshCw, ShieldCheck } from 'lucide-react';
import { http, errorMessage } from '../api/client';
import { Card, EmptyState, PageHeader, Spinner } from '../components/ui';
import {
  approveSecurityCandidate, classifySecurityRun, createGatePolicy, createSecurityCandidate,
  createSecurityRegression,
  editSecurityCandidate, evaluateGate, listGateDecisions, listGatePolicies,
  listSecurityCandidates, listSecurityRuns, readSecurityCandidate,
  reviewSecurityCandidate, runSecurityCandidate,
  type GateDecision, type GatePolicy, type SecurityCandidate,
} from '../api/phase5';

interface Project { id: string; name: string }
const input = 'rounded-md border border-border bg-surface px-3 py-2 text-sm text-content rf-focus';
const secondary = 'rounded-md border border-border px-3 py-2 text-xs text-content transition-colors hover:bg-overlay rf-focus';
const primary = 'rounded-md bg-red-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-red-700 rf-focus';
const categories = ['PROMPT_INJECTION', 'JAILBREAK', 'CONTEXT_MANIPULATION', 'DATA_LEAKAGE'];

export default function ReleaseReadinessPage() {
  const [params] = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState(params.get('project') || '');
  const [tab, setTab] = useState<'security' | 'gates'>(params.get('tab') === 'gates' ? 'gates' : 'security');
  const [candidates, setCandidates] = useState<SecurityCandidate[]>([]);
  const [policies, setPolicies] = useState<GatePolicy[]>([]);
  const [decisions, setDecisions] = useState<GateDecision[]>([]);
  const [selected, setSelected] = useState<SecurityCandidate | null>(null);
  const [runs, setRuns] = useState<{ id: string; model: string; status: string; outcome: string | null;
    classification: string; severity: string | null }[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState({ event_id: params.get('event') || '', category: 'PROMPT_INJECTION', title: '' });
  const [draft, setDraft] = useState({ title: '', prompt_text: '' });
  const [model, setModel] = useState('');
  const [findingSeverity, setFindingSeverity] = useState('high');
  const [findingReason, setFindingReason] = useState('');
  const [policy, setPolicy] = useState({ name: '', environment: 'staging', max_evidence_age_hours: '24',
    min_quality_score: '80' });
  const [gate, setGate] = useState({ policy_id: '', artifact_type: 'model', artifact_id: '',
    artifact_version: '', model: '', provider: 'ollama', evaluation_session_ids: '' });

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
      const [candidatePage, policyList, decisionList] = await Promise.all([
        listSecurityCandidates(project), listGatePolicies(project), listGateDecisions(project),
      ]);
      setCandidates(candidatePage.items); setPolicies(policyList); setDecisions(decisionList);
      setGate(previous => ({ ...previous, policy_id: policyList.some(x => x.id === previous.policy_id)
        ? previous.policy_id : policyList[0]?.id || '' }));
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
  async function openCandidate(id: string) {
    try {
      const [candidate, history] = await Promise.all([
        readSecurityCandidate(project, id), listSecurityRuns(project, id),
      ]);
      setSelected(candidate); setRuns(history);
      setDraft({ title: candidate.title, prompt_text: candidate.prompt_text || '' });
      setModel(candidate.model || '');
      setError('');
    } catch (e) { setError(errorMessage(e)); }
  }

  return <div className="space-y-5">
    <PageHeader title="Security & release" description="Promote real failures into reviewed local tests. Gate releases against linked evidence, not guesses." />
    <div className="flex flex-wrap items-center gap-3">
      <label htmlFor="release-project" className="text-xs text-content-subtle">Project</label>
      <select id="release-project" value={project} onChange={e => { setProject(e.target.value); setSelected(null); }} className={input}>
        {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <button type="button" onClick={() => void refresh()} disabled={!project || busy} className={`${secondary} ml-auto inline-flex items-center gap-1`}><RefreshCw size={13} /> Refresh</button>
    </div>
    <div className="flex gap-1 border-b border-border" role="tablist" aria-label="Release readiness sections">
      {(['security', 'gates'] as const).map(value => <button key={value} type="button" role="tab"
        aria-selected={tab === value} onClick={() => setTab(value)}
        className={`border-b-2 px-4 py-2 text-sm transition-colors rf-focus ${tab === value
          ? 'border-red-600 text-content' : 'border-transparent text-content-subtle hover:text-content'}`}>
        {value === 'security' ? 'Trace-driven tests' : 'Release gates'}
      </button>)}
    </div>
    {error && <p role="alert" className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-400">{error}</p>}
    {notice && <p role="status" className="rounded-md border border-border bg-surface p-3 text-sm text-content">{notice}</p>}
    {!project ? <EmptyState icon={<ShieldCheck size={25} />} title="No project" description="Create a project to review security evidence." /> : tab === 'security' ? <>
      <Card><form className="space-y-3 p-4" onSubmit={e => { e.preventDefault(); void act(async () => {
        await createSecurityCandidate(project, source);
        setSource({ event_id: '', category: 'PROMPT_INJECTION', title: '' });
      }, 'Draft created. Add a sanitized test prompt, review, then approve.'); }}>
        <div className="flex items-center gap-2"><LockKeyhole size={16} className="text-red-500" /><h2 className="text-sm font-semibold text-content">Trace to security case</h2></div>
        <p className="text-xs text-content-subtle">Source body stays private by default. No production operation or external tool is replayed.</p>
        <div className="flex flex-wrap gap-2">
          <input required aria-label="Source trace event ID" placeholder="Trace event ID" value={source.event_id}
            onChange={e => setSource({ ...source, event_id: e.target.value })} className={`${input} min-w-48 flex-1`} />
          <select aria-label="Security category" value={source.category} onChange={e => setSource({ ...source, category: e.target.value })} className={input}>
            {categories.map(c => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
          </select>
          <input required aria-label="Case title" placeholder="What happened?" value={source.title}
            onChange={e => setSource({ ...source, title: e.target.value })} className={`${input} min-w-48 flex-1`} />
          <button type="submit" disabled={busy} className={primary}>Create draft</button>
        </div>
      </form></Card>
      <section><h2 className="mb-2 text-sm font-semibold text-content">Review queue</h2>
        {candidates.length === 0 ? <EmptyState icon={<ShieldCheck size={25} />} title="No security cases" description="Start with a trace from the local explorer." />
          : <div className="space-y-2">{candidates.map(candidate => <Card key={candidate.id}><div className="flex items-center gap-3 p-4">
            <span className={`h-8 w-1 rounded-full ${candidate.state === 'approved' ? 'bg-emerald-500' : 'bg-red-600'}`} aria-hidden="true" />
            <div className="min-w-0 flex-1"><p className="text-sm font-semibold text-content">{candidate.title}</p>
              <p className="truncate text-xs text-content-subtle">{candidate.category.replace(/_/g, ' ')} · trace {candidate.source_event_id || 'retained provenance'} · {candidate.state}</p></div>
            <button type="button" onClick={() => void openCandidate(candidate.id)} className={`${secondary} inline-flex items-center gap-1`}>Open <ArrowRight size={13} /></button>
          </div></Card>)}</div>}</section>
      {selected && <Card><div className="space-y-3 p-4"><div className="flex items-center justify-between"><h2 className="text-sm font-semibold text-content">{selected.title}</h2>
        <button type="button" className={secondary} onClick={() => setSelected(null)}>Close</button></div>
        {selected.state === 'draft' || selected.state === 'in_review' ? <>
          <input aria-label="Security case title" value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} className={`${input} w-full`} />
          <textarea aria-label="Sanitized security prompt" rows={4} value={draft.prompt_text} onChange={e => setDraft({ ...draft, prompt_text: e.target.value })} className={`${input} w-full`} placeholder="Sanitized test prompt. Never paste secrets." />
          <div className="flex flex-wrap gap-2"><button type="button" className={primary} onClick={() => void act(async () => {
            await editSecurityCandidate(project, selected.id, draft.title, draft.prompt_text); await openCandidate(selected.id);
          }, 'Draft saved.')}>Save</button>
            {selected.state === 'draft' && <button type="button" className={secondary} onClick={() => void act(async () => {
              await reviewSecurityCandidate(project, selected.id); await openCandidate(selected.id);
            }, 'Marked for review.')}>Mark for review</button>}
            {selected.state === 'in_review' && <button type="button" className={secondary} onClick={() => void act(async () => {
              await approveSecurityCandidate(project, selected.id); await openCandidate(selected.id);
            }, 'Approved immutable security case.')}>Approve</button>}</div>
        </> : selected.state === 'approved' ? <>
          <p className="text-xs text-content-subtle">Approved snapshot immutable. Heuristic detections need human confirmation before called exploitable.</p>
          <div className="flex flex-wrap gap-2"><input aria-label="Local evaluation model" value={model} onChange={e => setModel(e.target.value)} className={input} placeholder="Local model" />
            <button type="button" disabled={!model || busy} className={primary} onClick={() => void act(async () => {
              const queued = await runSecurityCandidate(project, selected.id, model);
              setNotice(`Local security job ${queued.job.id} queued.`);
            }, '')}>Run locally</button><Link to="/jobs" className={secondary}>View jobs</Link></div>
          {runs.length > 0 && <div className="space-y-2 border-t border-border pt-3">{runs.map(run => <div key={run.id} className="rounded border border-border p-2 text-xs text-content-subtle">
            <p>{run.model} · {run.status} · {run.outcome || 'pending'} · {run.classification}{run.severity ? ` (${run.severity})` : ''}</p>
            {run.status === 'completed' && run.outcome === 'detected' && <div className="mt-2 flex flex-wrap items-center gap-2">
              {run.classification === 'observed' && <><select aria-label="Reviewed finding severity" className={input} value={findingSeverity} onChange={e => setFindingSeverity(e.target.value)}>
                {['low', 'medium', 'high', 'critical'].map(level => <option key={level} value={level}>{level}</option>)}
              </select><input aria-label="Finding justification" placeholder="Why is this exploitable?" className={`${input} min-w-56 flex-1`} value={findingReason} onChange={e => setFindingReason(e.target.value)} />
                <button type="button" disabled={findingReason.trim().length < 3} className={secondary} onClick={() => void act(async () => {
                  await classifySecurityRun(project, selected.id, run.id, findingSeverity, findingReason); await openCandidate(selected.id);
                }, 'Finding classification audited.')}>Confirm finding</button></>}
              <button type="button" className={secondary} onClick={() => void act(async () => {
                const result = await createSecurityRegression(project, selected.id, run.id);
                setNotice(`Feedback draft ${result.case_id} created. Review expected outcome before approval.`);
              }, '')}>Make regression draft</button>
            </div>}
          </div>)}</div>}
        </> : <p className="text-xs text-content-subtle">Archived. History retained.</p>}</div></Card>}
    </> : <>
      <Card><form className="space-y-3 p-4" onSubmit={e => { e.preventDefault(); void act(async () => {
        await createGatePolicy(project, { name: policy.name, environment: policy.environment,
          rules: { max_evidence_age_hours: Number(policy.max_evidence_age_hours), missing_evidence: 'fail',
            require_evaluation: true, min_quality_score: Number(policy.min_quality_score) } });
      }, 'Immutable policy version published.'); }}>
        <h2 className="text-sm font-semibold text-content">New quality gate</h2>
        <p className="text-xs text-content-subtle">Thresholds chosen by you. Missing, stale, or mismatched evaluation evidence fails.</p>
        <div className="flex flex-wrap gap-2"><input required aria-label="Policy name" placeholder="Policy name" value={policy.name} onChange={e => setPolicy({ ...policy, name: e.target.value })} className={`${input} min-w-40 flex-1`} />
          <input required aria-label="Target environment" value={policy.environment} onChange={e => setPolicy({ ...policy, environment: e.target.value })} className={`${input} w-32`} />
          <input required type="number" min="1" max="8760" aria-label="Evidence age hours" value={policy.max_evidence_age_hours} onChange={e => setPolicy({ ...policy, max_evidence_age_hours: e.target.value })} className={`${input} w-28`} />
          <input required type="number" min="0" max="100" aria-label="Minimum quality score" value={policy.min_quality_score} onChange={e => setPolicy({ ...policy, min_quality_score: e.target.value })} className={`${input} w-28`} />
          <button type="submit" disabled={busy} className={primary}>Publish policy</button></div>
      </form></Card>
      <Card><form className="space-y-3 p-4" onSubmit={e => { e.preventDefault(); void act(async () => {
        const decision = await evaluateGate(project, gate.policy_id, { dry_run: true,
          candidate: { artifact_type: gate.artifact_type, artifact_id: gate.artifact_id,
            artifact_version: gate.artifact_version, model: gate.model, provider: gate.provider },
          evidence: { evaluation_session_ids: gate.evaluation_session_ids.split(',').map(x => x.trim()).filter(Boolean) } });
        setNotice(`Dry run: ${decision.outcome}. Inspect checks below.`);
      }, ''); }}>
        <h2 className="text-sm font-semibold text-content">Check candidate</h2>
        <p className="text-xs text-content-subtle">Use completed Workbench session IDs tagged with matching release candidate identity. This screen never deploys.</p>
        <div className="grid gap-2 sm:grid-cols-2"><select aria-label="Release policy" value={gate.policy_id} onChange={e => setGate({ ...gate, policy_id: e.target.value })} className={input}>
          {policies.map(p => <option key={p.id} value={p.id}>{p.name} · {p.environment} · v{p.version}</option>)}
        </select><select aria-label="Artifact type" value={gate.artifact_type} onChange={e => setGate({ ...gate, artifact_type: e.target.value })} className={input}>
          {['model', 'prompt', 'configuration', 'application'].map(type => <option key={type} value={type}>{type}</option>)}
        </select><input required aria-label="Artifact ID" placeholder="Artifact ID" value={gate.artifact_id} onChange={e => setGate({ ...gate, artifact_id: e.target.value })} className={input} />
          <input required aria-label="Artifact version" placeholder="Artifact version" value={gate.artifact_version} onChange={e => setGate({ ...gate, artifact_version: e.target.value })} className={input} />
          <input required aria-label="Candidate model" placeholder="Exact model" value={gate.model} onChange={e => setGate({ ...gate, model: e.target.value })} className={input} />
          <input required aria-label="Candidate provider" placeholder="Provider" value={gate.provider} onChange={e => setGate({ ...gate, provider: e.target.value })} className={input} /></div>
        <input aria-label="Evaluation session IDs" placeholder="Evaluation session IDs, comma separated" value={gate.evaluation_session_ids} onChange={e => setGate({ ...gate, evaluation_session_ids: e.target.value })} className={`${input} w-full`} />
        <button type="submit" disabled={!gate.policy_id || busy} className={primary}>Dry run gate</button>
      </form></Card>
      <section><h2 className="mb-2 text-sm font-semibold text-content">Decision history</h2>{decisions.length === 0 ? <EmptyState icon={<CheckCircle2 size={25} />} title="No decisions" description="Run a candidate against a versioned policy." />
        : <div className="space-y-2">{decisions.map(decision => <Card key={decision.id}><div className="flex gap-3 p-4">
          <span className={`h-8 w-1 shrink-0 rounded-full ${decision.outcome === 'pass' ? 'bg-emerald-500' : decision.outcome === 'fail' ? 'bg-red-600' : 'bg-amber-500'}`} aria-hidden="true" />
          <div><p className="text-sm font-semibold text-content">{decision.outcome.toUpperCase()} · {String(decision.candidate.artifact_id || 'candidate')} {String(decision.candidate.artifact_version || '')}</p>
            <p className="text-xs text-content-subtle">{decision.dry_run ? 'Dry run' : 'Enforced'} · {new Date(decision.created_at).toLocaleString()}</p>
            <div className="mt-2 space-y-1">{decision.checks.map(check => <p key={check.name} className="text-xs text-content-subtle">{check.name}: {check.status} · {check.reason}</p>)}</div>
          </div></div></Card>)}</div>}</section>
    </>}
    {busy && <div className="sr-only"><Spinner label="Working…" /></div>}
  </div>;
}
