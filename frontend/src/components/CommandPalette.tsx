import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Boxes,
  Clock,
  Command,
  Database,
  Dumbbell,
  LayoutDashboard,
  Plus,
  Rocket,
  ScrollText,
  Search,
  Server,
  Settings,
  Shield,
  Sparkles,
  Trophy,
  Zap,
} from 'lucide-react';

const OPEN_EVENT = 'redforge:open-palette';

/** Open the command palette from anywhere (top bar, status bar, shortcuts). */
export function openCommandPalette() {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT));
}

interface Cmd {
  id: string;
  label: string;
  group: 'Actions' | 'Navigation';
  hint?: string;
  icon: React.ReactNode;
  run: () => void;
}

/** Global ⌘/Ctrl-K command palette — the fastest way to navigate + act. */
export function CommandPalette() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
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

  const commands: Cmd[] = useMemo(() => {
    const go = (path: string) => () => {
      navigate(path);
      setOpen(false);
    };
    return [
      // Actions route to existing creation flows — no new features.
      { id: 'a-eval', group: 'Actions', label: 'Start security evaluation', icon: <Shield size={15} />, run: go('/new') },
      { id: 'a-train', group: 'Actions', label: 'Launch training run', icon: <Rocket size={15} />, run: go('/training') },
      { id: 'a-project', group: 'Actions', label: 'New project', icon: <Plus size={15} />, run: go('/studio') },
      { id: 'a-dataset', group: 'Actions', label: 'Import dataset', icon: <Database size={15} />, run: go('/datasets') },
      { id: 'a-chat', group: 'Actions', label: 'Open Playground', icon: <Sparkles size={15} />, run: go('/playground') },

      { id: 'n-dash', group: 'Navigation', label: 'Dashboard', icon: <LayoutDashboard size={15} />, run: go('/') },
      { id: 'n-projects', group: 'Navigation', label: 'Projects', icon: <Boxes size={15} />, run: go('/studio') },
      { id: 'n-models', group: 'Navigation', label: 'Models', icon: <Server size={15} />, run: go('/models') },
      { id: 'n-datasets', group: 'Navigation', label: 'Datasets', icon: <Database size={15} />, run: go('/datasets') },
      { id: 'n-training', group: 'Navigation', label: 'Training', icon: <Dumbbell size={15} />, run: go('/training') },
      { id: 'n-playground', group: 'Navigation', label: 'Playground', icon: <Sparkles size={15} />, run: go('/playground') },
      { id: 'n-live', group: 'Navigation', label: 'Live evaluations', icon: <Zap size={15} />, run: go('/live') },
      { id: 'n-reports', group: 'Navigation', label: 'Reports', icon: <ScrollText size={15} />, run: go('/reports') },
      { id: 'n-leaderboard', group: 'Navigation', label: 'Leaderboard', icon: <Trophy size={15} />, run: go('/leaderboard') },
      { id: 'n-history', group: 'Navigation', label: 'History', icon: <Clock size={15} />, run: go('/history') },
      { id: 'n-runtime', group: 'Navigation', label: 'Runtime', icon: <Server size={15} />, run: go('/runtime') },
      { id: 'n-settings', group: 'Navigation', label: 'Settings', icon: <Settings size={15} />, run: go('/setup') },
    ];
  }, [navigate]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return commands;
    return commands.filter((c) => c.label.toLowerCase().includes(s) || c.group.toLowerCase().includes(s));
  }, [q, commands]);

  // Flat list drives keyboard selection; render is grouped.
  const groups = useMemo(() => {
    const out: { title: string; items: Cmd[] }[] = [];
    for (const g of ['Actions', 'Navigation'] as const) {
      const items = filtered.filter((c) => c.group === g);
      if (items.length) out.push({ title: g, items });
    }
    return out;
  }, [filtered]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[120] flex items-start justify-center bg-black/50 px-4 pt-[14vh]"
      onClick={() => setOpen(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface shadow-xl"
      >
        <div className="flex items-center gap-2.5 border-b border-border px-4 py-3">
          <Search size={16} className="text-content-subtle" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActive((a) => Math.min(a + 1, filtered.length - 1));
              } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActive((a) => Math.max(a - 1, 0));
              } else if (e.key === 'Enter') {
                e.preventDefault();
                filtered[active]?.run();
              }
            }}
            placeholder="Search commands and pages…"
            className="flex-1 bg-transparent text-sm text-content placeholder:text-content-faint focus:outline-none"
          />
          <kbd className="flex items-center gap-0.5 rounded border border-border px-1.5 py-0.5 text-[10px] text-content-faint">
            <Command size={10} /> K
          </kbd>
        </div>
        <div className="max-h-[22rem] overflow-y-auto py-1.5">
          {filtered.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-content-subtle">No matching commands.</p>
          ) : (
            groups.map((group) => (
              <div key={group.title} className="mb-1">
                <p className="px-4 py-1 text-[10px] font-semibold uppercase tracking-wider text-content-faint">
                  {group.title}
                </p>
                {group.items.map((c) => {
                  const idx = filtered.indexOf(c);
                  return (
                    <button
                      key={c.id}
                      onMouseEnter={() => setActive(idx)}
                      onClick={c.run}
                      className={`flex w-full items-center gap-3 px-4 py-2 text-left text-sm rf-focus ${
                        idx === active ? 'bg-overlay text-content' : 'text-content-muted'
                      }`}
                    >
                      <span className="text-content-subtle">{c.icon}</span>
                      <span className="flex-1">{c.label}</span>
                      {c.hint && <span className="text-[11px] text-content-faint">{c.hint}</span>}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
