import React from 'react';

type RiskLevel = 'low' | 'medium' | 'high' | 'safe';

interface MetricCardProps {
  title: string;
  value: string | number;
  unit?: string;
  riskLevel?: RiskLevel;
}

const riskColor: Record<string, string> = {
  safe: '#10B981',
  low: '#10B981',
  medium: '#F59E0B',
  high: '#EF4444',
};

const MetricCard: React.FC<MetricCardProps> = ({ title, value, unit, riskLevel }) => {
  const accentColor = riskLevel ? (riskColor[riskLevel] ?? '#FFFFFF') : '#FFFFFF';
  const valueColor = riskLevel ? (riskColor[riskLevel] ?? '#FFFFFF') : '#FFFFFF';

  return (
    <div
      style={{
        backgroundColor: '#1E2433',
        border: '1px solid #374151',
        borderRadius: '4px',
        padding: '20px',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <p
        style={{
          color: '#9CA3AF',
          fontSize: '11px',
          fontWeight: 500,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          marginBottom: '10px',
          margin: '0 0 10px 0',
        }}
      >
        {title}
      </p>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
        <span
          style={{
            fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
            fontSize: '28px',
            fontWeight: 700,
            color: valueColor,
            lineHeight: 1,
          }}
        >
          {value}
        </span>
        {unit && (
          <span
            style={{
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              fontSize: '13px',
              color: '#9CA3AF',
              fontWeight: 400,
            }}
          >
            {unit}
          </span>
        )}
      </div>

      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: '2px',
          backgroundColor: accentColor,
          opacity: 0.6,
        }}
      />
    </div>
  );
};

export default MetricCard;
