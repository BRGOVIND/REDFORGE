import { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  BarChart3,
  Boxes,
  Clock,
  Command,
  Database,
  Dumbbell,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  ScrollText,
  Search,
  Server,
  Settings,
  Shield,
  Sparkles,
  Trophy,
  Zap,
} from 'lucide-react';
import { cn } from '../lib/cn';
import { useModels, useProviders, useSessions } from '../hooks/queries';
import { CommandPalette, openCommandPalette } from './CommandPalette';
import { Assistant } from './Assistant';

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
  end?: boolean;
  match?: string; // extra pathname prefix that should also mark this item active
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

// Grouped like Linear / VS Code — every module maps to an existing route.
const NAV: NavGroup[] = [
  {
    title: 'Workspace',
    items: [
      { to: '/', label: 'Dashboard', icon: <LayoutDashboard size={16} />, end: true },
      { to: '/studio', label: 'Projects', icon: <Boxes size={16} /> },
    ],
  },
  {
    title: 'Build',
    items: [
      { to: '/models', label: 'Models', icon: <Server size={16} /> },
      { to: '/datasets', label: 'Datasets', icon: <Database size={16} /> },
      { to: '/training', label: 'Training', icon: <Dumbbell size={16} /> },
      { to: '/benchmarks', label: 'Benchmarks', icon: <BarChart3 size={16} />, match: '/benchmarks' },
      { to: '/playground', label: 'Playground', icon: <Sparkles size={16} /> },
    ],
  },
  {
    title: 'Security',
    items: [
      { to: '/new', label: 'Evaluate', icon: <Shield size={16} /> },
      { to: '/live', label: 'Live', icon: <Zap size={16} />, match: '/live' },
      { to: '/reports', label: 'Reports', icon: <ScrollText size={16} />, match: '/reports' },
      { to: '/leaderboard', label: 'Leaderboard', icon: <Trophy size={16} /> },
      { to: '/history', label: 'History', icon: <Clock size={16} /> },
    ],
  },
  {
    title: 'System',
    items: [
      { to: '/runtime', label: 'Runtime', icon: <Server size={16} /> },
      { to: '/setup', label: 'Settings', icon: <Settings size={16} /> },
    ],
  },
];

const ALL_ITEMS = NAV.flatMap((g) => g.items);
const COLLAPSE_KEY = 'redforge_nav_collapsed';

function sectionTitle(pathname: string): string {
  const hit = ALL_ITEMS.find(
    (i) => (i.end ? pathname === i.to : pathname.startsWith(i.match ?? i.to) || pathname === i.to)
  );
  return hit?.label ?? 'RedForge';
}

// --- Left navigation -------------------------------------------------------

function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const location = useLocation();
  return (
    <aside
      className={cn(
        'sticky top-0 flex h-screen shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-150',
        collapsed ? 'w-14' : 'w-56'
      )}
    >
      {/* Brand */}
      <div className={cn('flex h-11 items-center border-b border-border', collapsed ? 'justify-center px-0' : 'px-4')}>
        <img src="/logo-mark.png" alt="RedForge" width={22} height={22} className="h-[22px] w-[22px] rounded-md" />
        {!collapsed && <span className="ml-2.5 text-[13px] font-semibold tracking-tight text-content">RedForge</span>}
      </div>

      {/* Groups */}
      <nav className="flex-1 overflow-y-auto py-2" aria-label="Primary">
        {NAV.map((group) => (
          <div key={group.title} className="mb-1 px-2">
            {!collapsed && (
              <p className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-content-faint">
                {group.title}
              </p>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const active = item.end
                  ? location.pathname === item.to
                  : location.pathname === item.to || location.pathname.startsWith(item.match ?? item.to);
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    title={collapsed ? item.label : undefined}
                    className={cn(
                      'group relative flex items-center rounded-md text-[13px] transition-colors rf-focus',
                      collapsed ? 'justify-center px-0 py-2' : 'gap-2.5 px-2.5 py-1.5',
                      active
                        ? 'bg-overlay text-content'
                        : 'text-content-muted hover:bg-overlay/60 hover:text-content'
                    )}
                  >
                    {/* Active accent bar — calm, not a glow */}
                    {active && (
                      <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-r bg-red-500" />
                    )}
                    <span className={active ? 'text-red-400' : ''}>{item.icon}</span>
                    {!collapsed && item.label}
                  </NavLink>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Collapse toggle */}
      <div className="border-t border-border p-2">
        <button
          onClick={onToggle}
          className={cn(
            'flex w-full items-center rounded-md py-1.5 text-[12px] text-content-subtle transition-colors hover:bg-overlay hover:text-content rf-focus',
            collapsed ? 'justify-center' : 'gap-2 px-2.5'
          )}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          {!collapsed && 'Collapse'}
        </button>
      </div>
    </aside>
  );
}

// --- Top bar ---------------------------------------------------------------

function TopBar() {
  const location = useLocation();
  const title = sectionTitle(location.pathname);
  const providers = useProviders();
  const active = providers.data?.providers.find((p) => p.is_default);
  const online = active?.health?.online ?? false;

  return (
    <header className="flex h-11 shrink-0 items-center gap-4 border-b border-border bg-surface px-4">
      {/* Breadcrumb / section */}
      <div className="flex items-center gap-2 text-[13px]">
        <span className="text-content-faint">RedForge</span>
        <span className="text-content-faint">/</span>
        <span className="font-medium text-content">{title}</span>
      </div>

      {/* Global search → command palette */}
      <button
        onClick={openCommandPalette}
        className="ml-4 hidden h-7 max-w-sm flex-1 items-center gap-2 rounded-md border border-border bg-base px-2.5 text-[12px] text-content-subtle transition-colors hover:border-border-strong sm:flex rf-focus"
      >
        <Search size={13} />
        <span className="flex-1 text-left">Search or run a command…</span>
        <kbd className="flex items-center gap-0.5 rounded border border-border px-1 py-0.5 text-[10px] text-content-faint">
          <Command size={9} />K
        </kbd>
      </button>

      <div className="ml-auto flex items-center gap-3">
        {/* Provider status pill */}
        <div
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-[12px] text-content-muted"
          title={online ? 'Runtime provider is reachable' : 'Runtime provider offline'}
        >
          <span className={cn('h-1.5 w-1.5 rounded-full', online ? 'bg-pass' : 'bg-uncertain')} />
          {active?.label ?? providers.data?.default ?? 'Runtime'}
        </div>
      </div>
    </header>
  );
}

// --- Bottom status bar (VS Code style) -------------------------------------

function StatusBar() {
  const models = useModels();
  const providers = useProviders();
  const sessions = useSessions();
  const active = providers.data?.providers.find((p) => p.is_default);
  const online = active?.health?.online ?? false;
  const running = (sessions.data ?? []).filter((s) => s.status === 'running').length;

  return (
    <footer className="flex h-6 shrink-0 items-center gap-4 border-t border-border bg-surface px-3 text-[11px] text-content-subtle">
      <span className="flex items-center gap-1.5">
        <span className={cn('h-1.5 w-1.5 rounded-full', online ? 'bg-pass' : 'bg-uncertain')} />
        {active?.label ?? 'Runtime'} {online ? 'online' : 'offline'}
      </span>
      <span>{models.data?.models?.length ?? 0} models</span>
      {running > 0 && (
        <span className="flex items-center gap-1.5 text-content">
          <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-red-500" />
          {running} running
        </span>
      )}
      <button
        onClick={openCommandPalette}
        className="ml-auto flex items-center gap-1 hover:text-content rf-focus"
        title="Command palette"
      >
        <Command size={10} /> K
      </button>
      <span className="font-mono text-content-faint">v{__APP_VERSION__}</span>
    </footer>
  );
}

// --- Shell -----------------------------------------------------------------

export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState<boolean>(
    () => localStorage.getItem(COLLAPSE_KEY) === '1'
  );

  useEffect(() => {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-y-auto bg-base">
          {/* Responsive workspace width: comfortable on 13", wider on ultrawide. */}
          <div className="mx-auto w-full max-w-[1400px] px-6 py-6 lg:px-8">{children}</div>
        </main>
        <StatusBar />
      </div>

      {/* App-wide: command palette + floating assistant (not on landing/onboarding). */}
      <CommandPalette />
      <Assistant />
    </div>
  );
}
