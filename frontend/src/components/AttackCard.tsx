import React, { useState } from 'react';
import type { Attack } from '../types';

interface AttackCardProps {
  attack: Attack;
  onRun?: (attack: Attack) => void;
}

const severityBadgeStyle: Record<string, { bg: string; text: string; border: string }> = {
  low: { bg: 'rgba(59, 130, 246, 0.15)', text: '#60A5FA', border: 'rgba(59, 130, 246, 0.3)' },
  medium: { bg: 'rgba(245, 158, 11, 0.15)', text: '#F59E0B', border: 'rgba(245, 158, 11, 0.3)' },
  high: { bg: 'rgba(249, 115, 22, 0.15)', text: '#F97316', border: 'rgba(249, 115, 22, 0.3)' },
  critical: { bg: 'rgba(239, 68, 68, 0.15)', text: '#EF4444', border: 'rgba(239, 68, 68, 0.3)' },
};

const AttackCard: React.FC<AttackCardProps> = ({ attack, onRun }) => {
  const [hoverBtn, setHoverBtn] = useState(false);
  const sev = severityBadgeStyle[attack.severity] ?? severityBadgeStyle.medium;

  return (
    <div
      style={{
        backgroundColor: '#1E2433',
        border: '1px solid #374151',
        borderRadius: '4px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
        <span style={{ color: '#FFFFFF', fontWeight: 600, fontSize: '14px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {attack.name}
        </span>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            backgroundColor: sev.bg,
            color: sev.text,
            border: `1px solid ${sev.border}`,
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '10px',
            fontWeight: 600,
            padding: '2px 7px',
            borderRadius: '2px',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            flexShrink: 0,
          }}
        >
          {attack.severity}
        </span>
      </div>

      <p
        style={{
          color: '#9CA3AF',
          fontSize: '13px',
          lineHeight: '1.5',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
          margin: 0,
        }}
      >
        {attack.description}
      </p>

      <div style={{ backgroundColor: '#0A0E1A', padding: '8px', borderRadius: '4px' }}>
        <p
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            color: '#9CA3AF',
            fontSize: '11px',
            lineHeight: '1.55',
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            margin: 0,
            wordBreak: 'break-word',
          }}
        >
          {attack.prompt}
        </p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
        <span
          style={{
            backgroundColor: 'rgba(55, 65, 81, 0.5)',
            color: '#9CA3AF',
            fontSize: '10px',
            fontWeight: 500,
            padding: '3px 8px',
            borderRadius: '3px',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            fontFamily: "'JetBrains Mono', monospace",
            border: '1px solid #374151',
          }}
        >
          {attack.category.replace(/_/g, ' ')}
        </span>

        {onRun && (
          <button
            onClick={() => onRun(attack)}
            onMouseEnter={() => setHoverBtn(true)}
            onMouseLeave={() => setHoverBtn(false)}
            style={{
              backgroundColor: hoverBtn ? 'rgba(239, 68, 68, 0.15)' : 'transparent',
              color: '#EF4444',
              border: '1px solid #EF4444',
              borderRadius: '3px',
              fontSize: '11px',
              fontWeight: 600,
              padding: '4px 12px',
              cursor: 'pointer',
              fontFamily: "'JetBrains Mono', monospace",
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              transition: 'background-color 0.15s ease',
            }}
          >
            Run Attack
          </button>
        )}
      </div>
    </div>
  );
};

export default AttackCard;
