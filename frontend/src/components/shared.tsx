import { Badge } from './ui';
import { cn } from '../lib/cn';

const RISK_TONE: Record<string, 'red' | 'amber' | 'green' | 'grey'> = {
  critical: 'red',
  high: 'red',
  medium: 'amber',
  low: 'grey',
  none: 'green',
};

export function RiskBadge({ risk }: { risk: string }) {
  return <Badge tone={RISK_TONE[risk?.toLowerCase()] ?? 'neutral'}>{risk}</Badge>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <Badge tone={RISK_TONE[severity?.toLowerCase()] ?? 'neutral'}>{severity}</Badge>;
}

export function VerdictBadge({ verdict }: { verdict: string | null | undefined }) {
  const v = (verdict || '').toUpperCase();
  const tone = v === 'PASS' ? 'green' : v === 'FAIL' ? 'red' : v === 'ERROR' ? 'grey' : 'amber';
  return <Badge tone={tone}>{v || 'UNKNOWN'}</Badge>;
}

/** Circular security-score gauge (0–100). */
export function ScoreDonut({
  score,
  size = 120,
  label = 'Security Score',
}: {
  score: number;
  size?: number;
  label?: string;
}) {
  const stroke = 9;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score));
  const offset = c - (pct / 100) * c;
  const color = pct >= 90 ? '#3FB950' : pct >= 75 ? '#E8E8EC' : pct >= 50 ? '#D29922' : '#E5484D';

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#26262B" strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.6s ease-out' }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-2xl font-semibold tabular-nums" style={{ color }}>
          {Math.round(pct)}
        </span>
        <span className="text-[10px] uppercase tracking-wide text-content-subtle">{label}</span>
      </div>
    </div>
  );
}

export function KeyValue({ label, value, className }: { label: string; value: React.ReactNode; className?: string }) {
  return (
    <div className={cn('flex items-center justify-between gap-4 py-1.5 text-sm', className)}>
      <span className="text-content-subtle">{label}</span>
      <span className="font-medium text-content">{value}</span>
    </div>
  );
}
