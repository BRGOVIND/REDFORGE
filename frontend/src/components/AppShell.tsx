import { NavLink, useLocation } from 'react-router-dom';
import {
  Boxes,
  Clock,
  FlaskConical,
  LayoutDashboard,
  Plus,
  ScrollText,
  Server,
  Trophy,
  Zap,
} from 'lucide-react';
import { cn } from '../lib/cn';
import { useModels, useProviders } from '../hooks/queries';

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
  end?: boolean;
}

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: <LayoutDashboard size={17} />, end: true },
  { to: '/new', label: 'New Evaluation', icon: <Plus size={17} /> },
  { to: '/live', label: 'Live', icon: <Zap size={17} /> },
  { to: '/reports', label: 'Reports', icon: <ScrollText size={17} /> },
  { to: '/leaderboard', label: 'Leaderboard', icon: <Trophy size={17} /> },
  { to: '/history', label: 'History', icon: <Clock size={17} /> },
  { to: '/runtime', label: 'Runtime', icon: <Server size={17} /> },
  { to: '/models', label: 'Models', icon: <Boxes size={17} /> },
];

function SystemStatus() {
  const { data, isError } = useModels();
  const providers = useProviders();
  const online = !isError && !data?.error;
  // Show the active runtime provider (from the Runtime Manager), not a hardcode.
  const providerLabel =
    providers.data?.providers.find((p) => p.is_default)?.label ??
    providers.data?.default ??
    'Runtime';
  return (
    <NavLink
      to="/setup"
      className="flex items-center gap-2 rounded-md px-3 py-2 text-xs text-content-subtle transition-colors hover:bg-overlay hover:text-content rf-focus"
      title="System check & setup"
    >
      <span
        className={cn(
          'h-2 w-2 rounded-full',
          online ? 'bg-pass' : 'bg-uncertain',
          online && 'animate-pulse-dot'
        )}
      />
      {online ? `${providerLabel} · ${data?.models?.length ?? 0} models` : 'Setup required'}
    </NavLink>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-60 min-w-60 flex-col border-r border-border bg-surface">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <img src="/logo-mark.png" alt="RedForge" width={32} height={32} className="h-8 w-8 rounded-lg" />
          <div className="leading-tight">
            <p className="text-sm font-semibold text-content">RedForge</p>
            <p className="font-mono text-[10px] text-content-faint">v{__APP_VERSION__} · evaluation</p>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 px-3 py-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  'group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-colors rf-focus',
                  isActive || (item.to === '/live' && location.pathname.startsWith('/live'))
                    ? 'bg-red-soft text-red-400'
                    : 'text-content-muted hover:bg-overlay hover:text-content'
                )
              }
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-border py-2">
          <SystemStatus />
          <div className="flex items-center gap-1.5 px-3 py-1 text-[11px] text-content-faint">
            <FlaskConical size={12} />
            AI Security Evaluation
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto bg-base">
        <div className="mx-auto max-w-[1200px] px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
