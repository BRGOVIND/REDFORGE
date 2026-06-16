import React from 'react';
import { NavLink } from 'react-router-dom';
import { Shield, Cpu, Zap, Play, Brain, FileText, BarChart2 } from 'lucide-react';
import ThreatPulse from './ThreatPulse';

interface NavItem {
  to: string;
  icon: React.ReactNode;
  label: string;
}

const navItems: NavItem[] = [
  { to: '/', icon: <Shield size={18} />, label: 'Dashboard' },
  { to: '/models', icon: <Cpu size={18} />, label: 'Models' },
  { to: '/attacks', icon: <Zap size={18} />, label: 'Attacks' },
  { to: '/run', icon: <Play size={18} />, label: 'Run Tests' },
  { to: '/hallucination', icon: <Brain size={18} />, label: 'Hallucination' },
  { to: '/reports', icon: <FileText size={18} />, label: 'Reports' },
  { to: '/compare', icon: <BarChart2 size={18} />, label: 'Compare Models' },
];

const Navbar: React.FC = () => {
  return (
    <nav
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        padding: '0',
      }}
    >
      {/* Logo */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '24px 20px 20px 20px',
          borderBottom: '1px solid #374151',
        }}
      >
        <span
          style={{
            fontFamily: "'JetBrains Mono', 'Courier New', monospace",
            fontWeight: 700,
            fontSize: '20px',
            color: '#EF4444',
            letterSpacing: '-0.5px',
            lineHeight: 1,
          }}
        >
          RF
        </span>
        <span
          style={{
            fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
            fontWeight: 600,
            fontSize: '16px',
            color: '#FFFFFF',
            letterSpacing: '0.01em',
          }}
        >
          RedForge
        </span>
      </div>

      {/* ThreatPulse */}
      <div style={{ padding: '16px 12px 8px 12px' }}>
        <ThreatPulse />
      </div>

      {/* Nav Links */}
      <ul
        style={{
          listStyle: 'none',
          margin: '8px 0 0 0',
          padding: '0 8px',
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          gap: '2px',
        }}
      >
        {navItems.map(({ to, icon, label }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={to === '/'}
              style={({ isActive }: { isActive: boolean }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '9px 12px',
                borderRadius: '6px',
                textDecoration: 'none',
                fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                fontSize: '14px',
                fontWeight: isActive ? 500 : 400,
                color: isActive ? '#EF4444' : '#9CA3AF',
                background: isActive ? 'rgba(239, 68, 68, 0.10)' : 'transparent',
                borderLeft: isActive ? '2px solid #EF4444' : '2px solid transparent',
                transition: 'color 0.15s ease, background 0.15s ease',
                cursor: 'pointer',
              })}
              onMouseEnter={(e: React.MouseEvent<HTMLAnchorElement>) => {
                const el = e.currentTarget;
                if (!el.classList.contains('active')) {
                  el.style.color = '#FFFFFF';
                }
              }}
              onMouseLeave={(e: React.MouseEvent<HTMLAnchorElement>) => {
                const el = e.currentTarget;
                if (!el.classList.contains('active')) {
                  el.style.color = '#9CA3AF';
                }
              }}
            >
              {icon}
              {label}
            </NavLink>
          </li>
        ))}
      </ul>

      {/* Version Badge */}
      <div
        style={{
          padding: '16px 20px',
          borderTop: '1px solid #374151',
        }}
      >
        <span
          style={{
            fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
            fontSize: '12px',
            color: '#6B7280',
            letterSpacing: '0.02em',
          }}
        >
          v1.0.0
        </span>
      </div>
    </nav>
  );
};

export default Navbar;
