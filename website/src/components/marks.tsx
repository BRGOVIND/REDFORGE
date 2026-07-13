import { cn } from '../lib/cn';

/** Minimal geometric forge mark — an ember caught between two steel angles. */
export function ForgeMark({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-hidden>
      <path d="M6 9 L16 4 L26 9" stroke="#55555F" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M6 23 L16 28 L26 23" stroke="#55555F" strokeWidth="1.5" strokeLinecap="round" />
      <path
        d="M16 10 C13 13 13 16 16 18 C19 16 19 13 16 10 Z M16 18 C14.5 19.5 14.5 21.5 16 23 C17.5 21.5 17.5 19.5 16 18 Z"
        fill="#A11212"
      />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <div className={cn('flex items-center gap-2.5', className)}>
      <ForgeMark size={22} />
      <span className="display text-[15px] tracking-tight text-bone">
        Red<span className="text-forge">Forge</span>
      </span>
    </div>
  );
}

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="h-px w-8 bg-steel-600" />
      <span className="label">{children}</span>
    </div>
  );
}

export function Hairline({ className }: { className?: string }) {
  return <div className={cn('h-px w-full', className)} style={{ background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.12), transparent)' }} />;
}
