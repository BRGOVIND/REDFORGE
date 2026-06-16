import React, { useEffect } from 'react';

const STYLE_ID = 'threat-pulse-keyframes';

const keyframesCSS = `
@keyframes threatPulseRing {
  0% { transform: scale(1); opacity: 0.8; }
  70% { transform: scale(2.4); opacity: 0; }
  100% { transform: scale(2.4); opacity: 0; }
}
@keyframes threatPulseDot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
`;

const ThreatPulse: React.FC = () => {
  useEffect(() => {
    if (!document.getElementById(STYLE_ID)) {
      const style = document.createElement('style');
      style.id = STYLE_ID;
      style.textContent = keyframesCSS;
      document.head.appendChild(style);
    }
  }, []);

  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
      <div style={{ position: 'relative', width: '10px', height: '10px', flexShrink: 0 }}>
        <span
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            backgroundColor: '#EF4444',
            animation: 'threatPulseRing 1.8s ease-out infinite',
          }}
        />
        <span
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            backgroundColor: '#EF4444',
            animation: 'threatPulseDot 1.8s ease-in-out infinite',
          }}
        />
      </div>
      <span
        style={{
          fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          fontSize: '11px',
          color: '#F87171',
          letterSpacing: '0.08em',
          fontWeight: 600,
          textTransform: 'uppercase',
        }}
      >
        ACTIVE SCAN
      </span>
    </div>
  );
};

export default ThreatPulse;
