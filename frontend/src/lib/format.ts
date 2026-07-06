/** Small presentation helpers shared across pages. */

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—';
  if (seconds < 1) return '<1s';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return s ? `${m}m ${s}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

export function formatMB(mb: number | null | undefined): string {
  if (mb == null) return '—';
  if (mb < 1024) return `${Math.round(mb)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null) return '—';
  return n.toLocaleString();
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const diff = Date.now() - then;
  const min = Math.floor(diff / 60000);
  if (min < 1) return 'just now';
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

/** Tailwind text color for a 0–100 security score. */
export function scoreColor(score: number): string {
  if (score >= 90) return 'text-pass';
  if (score >= 75) return 'text-content';
  if (score >= 50) return 'text-uncertain';
  return 'text-fail';
}

export function verdictColor(verdict: string | null | undefined): string {
  switch ((verdict || '').toUpperCase()) {
    case 'PASS':
      return 'text-pass';
    case 'FAIL':
      return 'text-fail';
    case 'ERROR':
      return 'text-content-subtle';
    default:
      return 'text-uncertain';
  }
}

export function riskColor(risk: string | null | undefined): string {
  switch ((risk || '').toLowerCase()) {
    case 'critical':
    case 'high':
      return 'text-fail';
    case 'medium':
      return 'text-uncertain';
    case 'low':
      return 'text-content-muted';
    default:
      return 'text-pass';
  }
}

export function titleCase(s: string): string {
  return s
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
