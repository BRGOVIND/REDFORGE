import { useEffect, useState } from 'react';
import { Wordmark } from './marks';

/**
 * Cinematic entry: black → a forged red line draws itself → an ember catches →
 * the wordmark rises → the curtain lifts to reveal the hero. Elegant, slow,
 * silent. Honors reduced-motion by resolving almost instantly.
 */
export function Entry({ onDone }: { onDone: () => void }) {
  const [phase, setPhase] = useState(0); // 0 black · 1 line · 2 mark · 3 lift
  const [gone, setGone] = useState(false);

  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const seq = reduced ? [50, 120, 200, 320] : [350, 1500, 2900, 3700];
    const timers = [
      window.setTimeout(() => setPhase(1), seq[0]),
      window.setTimeout(() => setPhase(2), seq[1]),
      window.setTimeout(() => setPhase(3), seq[2]),
      window.setTimeout(() => {
        setGone(true);
        onDone();
      }, seq[3]),
    ];
    document.body.style.overflow = 'hidden';
    window.scrollTo(0, 0);
    return () => {
      timers.forEach(clearTimeout);
      document.body.style.overflow = '';
    };
  }, [onDone]);

  useEffect(() => {
    if (phase === 3) document.body.style.overflow = '';
  }, [phase]);

  if (gone) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-ink"
      style={{
        transform: phase === 3 ? 'translateY(-100%)' : 'none',
        opacity: phase === 3 ? 0 : 1,
        transition: 'transform 1000ms cubic-bezier(0.7,0,0.2,1), opacity 900ms ease',
      }}
      aria-hidden={phase === 3}
    >
      {/* Wordmark rises */}
      <div
        className="mb-8"
        style={{
          opacity: phase >= 2 ? 1 : 0,
          transform: phase >= 2 ? 'translateY(0)' : 'translateY(14px)',
          filter: phase >= 2 ? 'blur(0)' : 'blur(6px)',
          transition: 'opacity 900ms ease, transform 900ms cubic-bezier(0.16,1,0.3,1), filter 900ms ease',
        }}
      >
        <Wordmark className="scale-[1.6]" />
      </div>

      {/* Forged line + ember */}
      <div className="relative flex h-6 w-[min(60vw,520px)] items-center justify-center">
        <div
          className="absolute h-px w-full origin-center"
          style={{
            background: 'linear-gradient(90deg, transparent, #A11212 20%, #D12A2A 50%, #A11212 80%, transparent)',
            transform: `scaleX(${phase >= 1 ? 1 : 0})`,
            opacity: phase >= 1 ? 1 : 0,
            boxShadow: '0 0 24px 1px rgba(122,0,0,0.5)',
            transition: 'transform 1100ms cubic-bezier(0.16,1,0.3,1), opacity 700ms ease',
          }}
        />
        <div
          className="absolute h-2.5 w-2.5 rounded-full"
          style={{
            background: 'radial-gradient(circle, #D12A2A, #A11212 45%, #5A0000 75%)',
            boxShadow: '0 0 24px 6px rgba(122,0,0,0.6)',
            opacity: phase >= 1 ? 1 : 0,
            transform: phase >= 1 ? 'scale(1)' : 'scale(0.3)',
            transition: 'opacity 600ms ease 200ms, transform 900ms cubic-bezier(0.16,1,0.3,1) 200ms',
          }}
        />
      </div>

      <p
        className="label mt-10"
        style={{ opacity: phase === 2 ? 0.7 : 0, transition: 'opacity 800ms ease 300ms' }}
      >
        Local AI Security Laboratory
      </p>

      <button
        onClick={() => {
          setGone(true);
          document.body.style.overflow = '';
          onDone();
        }}
        className="focus-ring absolute bottom-8 right-8 label hover:text-steel-200"
      >
        Skip
      </button>
    </div>
  );
}
