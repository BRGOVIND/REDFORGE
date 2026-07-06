/** Shared design-system primitives. Dark-first, neutral grey + red accent. */
import React from 'react';
import { AlertTriangle, Inbox, Loader2 } from 'lucide-react';
import { cn } from '../../lib/cn';

// --- Card ------------------------------------------------------------------

export function Card({
  className,
  hover,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { hover?: boolean }) {
  return <div className={cn('rf-card', hover && 'rf-card-hover', className)} {...props} />;
}

export function CardHeader({
  title,
  subtitle,
  icon,
  action,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  icon?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
      <div className="flex items-center gap-2.5 min-w-0">
        {icon && <span className="text-content-muted">{icon}</span>}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-content truncate">{title}</h3>
          {subtitle && <p className="text-xs text-content-subtle mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}

// --- Button ----------------------------------------------------------------

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md';

const BTN_BASE =
  'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors rf-focus disabled:opacity-50 disabled:pointer-events-none';
const BTN_VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-red-600 text-white hover:bg-red-500',
  secondary: 'bg-overlay text-content border border-border hover:border-border-strong',
  ghost: 'text-content-muted hover:text-content hover:bg-overlay',
  danger: 'bg-transparent text-fail border border-red-700/40 hover:bg-red-soft',
};
const BTN_SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
};

export function Button({
  variant = 'primary',
  size = 'md',
  className,
  loading,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}) {
  return (
    <button
      className={cn(BTN_BASE, BTN_VARIANTS[variant], BTN_SIZES[size], className)}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading && <Loader2 size={14} className="animate-spin" />}
      {children}
    </button>
  );
}

// --- Badge -----------------------------------------------------------------

type BadgeTone = 'neutral' | 'red' | 'green' | 'amber' | 'grey';
const BADGE_TONES: Record<BadgeTone, string> = {
  neutral: 'bg-overlay text-content-muted border-border',
  red: 'bg-red-soft text-red-400 border-red-700/30',
  green: 'bg-pass/10 text-pass border-pass/20',
  amber: 'bg-uncertain/10 text-uncertain border-uncertain/20',
  grey: 'bg-overlay text-content-subtle border-border',
};

export function Badge({
  tone = 'neutral',
  className,
  children,
}: {
  tone?: BadgeTone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium',
        BADGE_TONES[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

const STATUS_TONE: Record<string, BadgeTone> = {
  completed: 'green',
  running: 'red',
  pending: 'grey',
  paused: 'amber',
  failed: 'red',
  cancelled: 'grey',
};

export function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? 'neutral';
  return (
    <Badge tone={tone}>
      {status === 'running' && (
        <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse-dot" />
      )}
      {status}
    </Badge>
  );
}

// --- Progress --------------------------------------------------------------

export function Progress({ value, className }: { value: number; className?: string }) {
  const pct = Math.max(0, Math.min(100, value * 100));
  return (
    <div className={cn('h-2 w-full overflow-hidden rounded-full bg-overlay', className)}>
      <div
        className="h-full rounded-full bg-gradient-to-r from-red-600 to-red-400 transition-[width] duration-500 ease-out"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

// --- Stat ------------------------------------------------------------------

export function Stat({
  label,
  value,
  hint,
  icon,
  valueClass,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: React.ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5 text-xs text-content-subtle">
        {icon}
        <span>{label}</span>
      </div>
      <span className={cn('text-2xl font-semibold tracking-tight text-content', valueClass)}>
        {value}
      </span>
      {hint && <span className="text-xs text-content-subtle">{hint}</span>}
    </div>
  );
}

// --- Skeleton --------------------------------------------------------------

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-md bg-overlay',
        'after:absolute after:inset-0 after:-translate-x-full after:animate-[shimmer_1.5s_infinite]',
        'after:bg-gradient-to-r after:from-transparent after:via-white/5 after:to-transparent',
        className
      )}
    />
  );
}

// --- States ----------------------------------------------------------------

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-content-muted">
      <Loader2 size={16} className="animate-spin" />
      {label ?? 'Loading…'}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border px-6 py-14 text-center">
      <div className="text-content-faint">{icon ?? <Inbox size={28} />}</div>
      <div>
        <p className="text-sm font-medium text-content">{title}</p>
        {description && <p className="mt-1 text-xs text-content-subtle max-w-sm">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-red-700/30 bg-red-soft px-6 py-10 text-center">
      <AlertTriangle size={24} className="text-fail" />
      <p className="text-sm text-content">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

// --- Page header -----------------------------------------------------------

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-content">{title}</h1>
        {description && <p className="mt-1 text-sm text-content-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
