import React from 'react';
import type { Verdict } from '../types';

interface VerdictBadgeProps {
  verdict: Verdict;
}

const verdictStyles: Record<Verdict, { bg: string; text: string; border: string }> = {
  PASS: {
    bg: 'rgba(16, 185, 129, 0.2)',
    text: '#10B981',
    border: 'rgba(16, 185, 129, 0.3)',
  },
  FAIL: {
    bg: 'rgba(239, 68, 68, 0.2)',
    text: '#EF4444',
    border: 'rgba(239, 68, 68, 0.3)',
  },
  UNCERTAIN: {
    bg: 'rgba(245, 158, 11, 0.2)',
    text: '#F59E0B',
    border: 'rgba(245, 158, 11, 0.3)',
  },
};

const VerdictBadge: React.FC<VerdictBadgeProps> = ({ verdict }) => {
  const style = verdictStyles[verdict];

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        backgroundColor: style.bg,
        color: style.text,
        border: `1px solid ${style.border}`,
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        textTransform: 'uppercase',
        fontSize: '11px',
        fontWeight: 600,
        padding: '2px 8px',
        borderRadius: '2px',
        letterSpacing: '0.05em',
      }}
    >
      {verdict}
    </span>
  );
};

export default VerdictBadge;
