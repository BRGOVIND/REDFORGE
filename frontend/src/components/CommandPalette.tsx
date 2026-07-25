import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity, Boxes, Brain, ClipboardList, Clock, Command as CommandIcon, Cpu, Database,
  Download, Dumbbell, FlaskConical, Gauge, LayoutDashboard, Layers, Microscope, Package,
  Play, Plus, RefreshCw, Rocket, ScrollText, Search, Server, Settings, Shield, Sparkles,
  Trash2, Trophy, Wrench, Zap,
} from 'lucide-react';
import { queryClient } from '../lib/query';
import { toast } from '../lib/toast';
import * as api from '../api/endpoints';
import { useTaskManager } from './TaskManager';

const OPEN_EVENT = 'redforge:open-palette';
const RECENTS_KEY = 'redforge_cmd_recents';

/** Open the command palette from anywhere (top bar, status bar, shortcuts). */
export function openCommandPalette() {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT));
}

interface Cmd {
  id: string;
  title: string;
  section: string;
  keywords?: string;        // extra terms for smart search (space-separated)
  hint?: string;
  icon: React.ReactNode;
  run: () => void;
}

// --- fuzzy matching --------------------------------------------------------
/** Score a command against a query. Higher is better; -1 = no match.
 *  Ranks: exact-substring > word-start > subsequence, across title + keywords. */
function scoreText(text: string, q: string): number {
  const t = text.toLowerCase();
  const i = t.indexOf(q);
  if (i === 0) return 1000;
  if (i > 0) return (/\b/.test(t[i - 1] ?? ' ') ? 800 : 600) - i;
  // subsequence (all query chars in order)
  let ti = 0;
  for (let qi = 0; qi < q.length; qi++) {
    ti = t.indexOf(q[qi], ti);
    if (ti === -1) return -1;
    ti++;
  }
  return 200 - (ti - q.length);
}

function scoreCmd(c: Cmd, q: string): number {
  const hay = [c.title, c.keywords ?? '', c.section];
  let best = -1;
  for (const h of hay) best = Math.max(best, scoreText(h, q));
  return best;
}

// --- palette ---------------------------------------------------------------
export function CommandPalette() {
  const navigate = useNavigate();
  const taskMgr = useTaskManager();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const [recents, setRecents] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(RECENTS_KEY) || '[]'); } catch { return []; }
  });
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      // Ctrl/⌘+K  OR  Ctrl/⌘+Shift+P — the two professional palette shortcuts.
      if (((e.ctrlKey || e.metaKey) && k === 'k') || ((e.ctrlKey || e.metaKey) && e.shiftKey && k === 'p')) {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === 'Escape') {
        setOpen(false);
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener('keydown', onKey);
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener(OPEN_EVENT, onOpen);
    };
  }, []);

  useEffect(() => {
    if (open) {
      setQ('');
      setActive(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const pushRecent = (id: string) => {
    const next = [id, ...recents.filter((r) => r !== id)].slice(0, 6);
    setRecents(next);
    try { localStorage.setItem(RECENTS_KEY, JSON.stringify(next)); } catch { /* ignore */ }
  };

  const commands: Cmd[] = useMemo(() => {
    const go = (path: string) => () => { navigate(path); setOpen(false); };
    const act = (fn: () => void) => () => { fn(); setOpen(false); };
    const openTasks = () => taskMgr.setOpen(true);
    const scanRuntimes = async () => {
      try {
        await api.submitJob({ type: 'runtime_discovery' });
        toast.info('Runtime scan started', 'Track it in the task panel');
        taskMgr.setOpen(true);
      } catch { toast.error('Could not start runtime scan'); }
    };
    return [
      // Projects
      { id: 'proj-open', section: 'Projects', title: 'Open Projects', keywords: 'project workspace studio', icon: <Boxes size={15} />, run: go('/studio') },
      { id: 'proj-new', section: 'Projects', title: 'Create Project', keywords: 'new project add', icon: <Plus size={15} />, run: go('/studio') },
      // Datasets
      { id: 'ds-import', section: 'Datasets', title: 'Import Dataset', keywords: 'dataset upload data', icon: <Database size={15} />, run: go('/datasets') },
      { id: 'ds-new', section: 'Datasets', title: 'Create Dataset', keywords: 'dataset new', icon: <Database size={15} />, run: go('/datasets') },
      { id: 'ds-prep', section: 'Datasets', title: 'Preprocess Dataset', keywords: 'dataset clean tokenize pipeline', icon: <Layers size={15} />, run: go('/pipeline/datasets') },
      // Models
      { id: 'm-hub', section: 'Models', title: 'Model Hub', keywords: 'browse discover download model catalog', icon: <Package size={15} />, run: go('/model-hub') },
      { id: 'm-download', section: 'Models', title: 'Download Model', keywords: 'model pull huggingface ollama gguf get', icon: <Download size={15} />, run: go('/model-hub') },
      { id: 'm-import', section: 'Models', title: 'Import Model', keywords: 'model local add', icon: <Server size={15} />, run: go('/models') },
      { id: 'm-registry', section: 'Models', title: 'Model Registry', keywords: 'model manage list delete', icon: <Server size={15} />, run: go('/models') },
      { id: 'm-foundation', section: 'Models', title: 'Foundation Models', keywords: 'model foundation base hf repo', icon: <Package size={15} />, run: go('/foundation-models') },
      { id: 'm-refresh', section: 'Models', title: 'Refresh Models', keywords: 'model reload rescan sync', icon: <RefreshCw size={15} />, run: act(() => { queryClient.invalidate(['models']); toast.success('Models refreshed'); }) },
      // Runtimes
      { id: 'rt-scan', section: 'Runtimes', title: 'Scan Runtimes', keywords: 'runtime discover detect ollama scan health', icon: <RefreshCw size={15} />, run: act(scanRuntimes) },
      { id: 'rt-open', section: 'Runtimes', title: 'Runtime Manager', keywords: 'runtime restart connect health logs status', icon: <Server size={15} />, run: go('/runtime') },
      { id: 'rt-connect', section: 'Runtimes', title: 'Connect Runtime', keywords: 'runtime provider connect ollama openai', icon: <Cpu size={15} />, run: go('/runtime') },
      // Benchmarks
      { id: 'bm-run', section: 'Benchmarks', title: 'Run Benchmark', keywords: 'benchmark evaluate score suite', icon: <Gauge size={15} />, run: go('/benchmarks') },
      { id: 'bm-compare', section: 'Benchmarks', title: 'Compare Models', keywords: 'benchmark compare leaderboard versus', icon: <Trophy size={15} />, run: go('/benchmarks') },
      { id: 'bm-history', section: 'Benchmarks', title: 'Benchmark History', keywords: 'benchmark past results history', icon: <Clock size={15} />, run: go('/benchmarks') },
      // Reports
      { id: 'rp-gen', section: 'Reports', title: 'Generate Report', keywords: 'report create summary', icon: <ScrollText size={15} />, run: go('/reports') },
      { id: 'rp-export', section: 'Reports', title: 'Export PDF', keywords: 'report export pdf download', icon: <Download size={15} />, run: go('/reports') },
      // Training
      { id: 'tr-launch', section: 'Training', title: 'Launch Training', keywords: 'train fine-tune lora qlora experimental', icon: <Rocket size={15} />, run: go('/training') },
      { id: 'tr-finetune', section: 'Training', title: 'Fine-Tune (Pipeline)', keywords: 'train fine-tune pipeline adapter', icon: <Dumbbell size={15} />, run: go('/pipeline/train') },
      { id: 'tr-jobs', section: 'Training', title: 'View Training Jobs', keywords: 'train jobs runs tasks', icon: <Activity size={15} />, run: go('/jobs') },
      // Prompt Workbench
      { id: 'wb-new', section: 'Prompt Workbench', title: 'New Prompt', keywords: 'prompt workbench test evaluate', icon: <FlaskConical size={15} />, run: go('/workbench') },
      { id: 'wb-reg', section: 'Prompt Workbench', title: 'Regression Test', keywords: 'prompt regression compare workbench', icon: <ClipboardList size={15} />, run: go('/workbench') },
      { id: 'wb-play', section: 'Prompt Workbench', title: 'Open Playground', keywords: 'prompt chat playground', icon: <Sparkles size={15} />, run: go('/playground') },
      // Security
      { id: 'sec-scan', section: 'Security', title: 'Run Security Scan', keywords: 'security scan evaluate red team attack', icon: <Shield size={15} />, run: go('/new') },
      { id: 'sec-attack', section: 'Security', title: 'Attack Model', keywords: 'security attack red team jailbreak', icon: <Zap size={15} />, run: go('/new') },
      { id: 'sec-live', section: 'Security', title: 'Live Evaluations', keywords: 'security live monitor', icon: <Activity size={15} />, run: go('/live') },
      // Workspace
      { id: 'ws-tasks', section: 'Workspace', title: 'Open Task Manager', keywords: 'tasks jobs running progress downloads', icon: <Activity size={15} />, run: act(openTasks) },
      { id: 'ws-logs', section: 'Workspace', title: 'Open Logs', keywords: 'logs jobs output developer', icon: <ScrollText size={15} />, run: go('/jobs') },
      { id: 'ws-settings', section: 'Workspace', title: 'Open Settings', keywords: 'settings preferences config', icon: <Settings size={15} />, run: go('/setup') },
      { id: 'ws-theme', section: 'Workspace', title: 'Theme & Appearance', keywords: 'theme dark light appearance', icon: <Sparkles size={15} />, run: go('/setup') },
      { id: 'ws-cache', section: 'Workspace', title: 'Clear Cache', keywords: 'clear cache refresh reload developer', icon: <Trash2 size={15} />, run: act(() => { queryClient.invalidate(); toast.success('Cache cleared', 'Fresh data will load'); }) },
      { id: 'ws-artifacts', section: 'Workspace', title: 'Artifacts', keywords: 'artifacts lineage outputs', icon: <Layers size={15} />, run: go('/artifacts') },
      { id: 'ws-experiments', section: 'Workspace', title: 'Experiments', keywords: 'experiments compare', icon: <Microscope size={15} />, run: go('/experiments') },
      { id: 'ws-hw', section: 'Workspace', title: 'Hardware & GPU', keywords: 'hardware gpu vram compatibility developer', icon: <Wrench size={15} />, run: go('/setup') },
      // Navigation basics
      { id: 'nav-dash', section: 'Go to', title: 'Dashboard', keywords: 'home overview', icon: <LayoutDashboard size={15} />, run: go('/') },
      { id: 'nav-brain', section: 'Go to', title: 'Foundation Models', keywords: 'models base', icon: <Brain size={15} />, run: go('/foundation-models') },
    ];
  }, [navigate, taskMgr]);

  const byId = useMemo(() => new Map(commands.map((c) => [c.id, c])), [commands]);

  const results: Cmd[] = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) {
      const rec = recents.map((id) => byId.get(id)).filter(Boolean) as Cmd[];
      const recIds = new Set(rec.map((c) => c.id));
      return [...rec, ...commands.filter((c) => !recIds.has(c.id))];
    }
    return commands
      .map((c) => ({ c, score: scoreCmd(c, s) }))
      .filter((x) => x.score >= 0)
      .sort((a, b) => b.score - a.score)
      .map((x) => x.c);
  }, [q, commands, recents, byId]);

  // Group for display (recents first when idle), keep a flat index for keyboard nav.
  const groups = useMemo(() => {
    const s = q.trim();
    const out: { title: string; items: Cmd[] }[] = [];
    if (!s && recents.length) {
      const rec = recents.map((id) => byId.get(id)).filter(Boolean) as Cmd[];
      if (rec.length) out.push({ title: 'Recently used', items: rec });
    }
    const seen = new Set(out.flatMap((g) => g.items.map((i) => i.id)));
    const order: string[] = [];
    for (const c of results) if (!seen.has(c.id) && !order.includes(c.section)) order.push(c.section);
    for (const section of order) {
      const items = results.filter((c) => c.section === section && !seen.has(c.id));
      if (items.length) out.push({ title: section, items });
    }
    return out;
  }, [results, recents, byId, q]);

  const flat = useMemo(() => groups.flatMap((g) => g.items), [groups]);

  useEffect(() => { setActive(0); }, [q]);
  useEffect(() => {
    listRef.current?.querySelector(`[data-idx="${active}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [active]);

  const runCmd = (c: Cmd) => { pushRecent(c.id); c.run(); };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[120] flex items-start justify-center bg-black/50 px-4 pt-[12vh]"
      onClick={() => setOpen(false)}
      role="dialog" aria-modal="true" aria-label="Command palette"
    >
      <div onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-surface shadow-2xl shadow-black/40">
        <div className="flex items-center gap-2.5 border-b border-border px-4 py-3">
          <Search size={16} className="text-content-subtle" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, flat.length - 1)); }
              else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
              else if (e.key === 'Enter') { e.preventDefault(); const c = flat[active]; if (c) runCmd(c); }
            }}
            placeholder="Search commands, models, actions…"
            className="flex-1 bg-transparent text-sm text-content placeholder:text-content-faint focus:outline-none"
          />
          <kbd className="hidden items-center gap-0.5 rounded border border-border px-1.5 py-0.5 text-[10px] text-content-faint sm:flex">
            <CommandIcon size={10} /> K
          </kbd>
        </div>

        <div ref={listRef} className="max-h-[24rem] overflow-y-auto py-1.5">
          {flat.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-content-subtle">No matching commands.</p>
          ) : (
            groups.map((group) => (
              <div key={group.title} className="mb-1">
                <p className="px-4 py-1 text-[10px] font-semibold uppercase tracking-wider text-content-faint">
                  {group.title}
                </p>
                {group.items.map((c) => {
                  const idx = flat.indexOf(c);
                  return (
                    <button
                      key={c.id}
                      data-idx={idx}
                      onMouseMove={() => setActive(idx)}
                      onClick={() => runCmd(c)}
                      className={`flex w-full items-center gap-3 px-4 py-2 text-left text-sm rf-focus ${
                        idx === active ? 'bg-overlay text-content' : 'text-content-muted'
                      }`}
                    >
                      <span className={idx === active ? 'text-red-400' : 'text-content-subtle'}>{c.icon}</span>
                      <span className="flex-1 truncate">{c.title}</span>
                      <span className="text-[10px] text-content-faint">{c.section}</span>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        <div className="flex items-center gap-3 border-t border-border px-4 py-2 text-[10px] text-content-faint">
          <span className="flex items-center gap-1"><Play size={9} /> Enter to run</span>
          <span>↑↓ to navigate</span>
          <span className="ml-auto flex items-center gap-1">
            <kbd className="rounded border border-border px-1">Ctrl</kbd>
            <kbd className="rounded border border-border px-1">Shift</kbd>
            <kbd className="rounded border border-border px-1">P</kbd>
          </span>
        </div>
      </div>
    </div>
  );
}
