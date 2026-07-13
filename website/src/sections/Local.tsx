import { usePinProgress } from '../motion';
import { cn, clamp } from '../lib/cn';

const LINES = ['YOUR MODEL.', 'YOUR MACHINE.', 'YOUR DATA.'];

export function Local() {
  const [ref, progress] = usePinProgress<HTMLDivElement>();
  const active = clamp(Math.floor(progress * LINES.length + 0.15), 0, LINES.length - 1);

  return (
    <section id="local" ref={ref} className="relative" style={{ height: '260vh' }}>
      <div className="sticky top-0 flex h-screen flex-col items-center justify-center overflow-hidden border-t border-steel-800">
        <div
          className="pointer-events-none absolute left-1/2 top-1/2 h-[600px] w-[600px] -translate-x-1/2 -translate-y-1/2 rounded-full blur-[160px]"
          style={{ background: 'radial-gradient(circle, rgba(90,0,0,0.16), transparent 60%)' }}
        />
        <div className="relative text-center">
          {LINES.map((line, i) => (
            <h2
              key={line}
              className={cn(
                'display text-[13vw] leading-[1.02] transition-all duration-700 ease-forge lg:text-[8.5vw]'
              )}
              style={{
                color: i <= active ? '#EDECE8' : '#2A2A31',
                opacity: i <= active ? 1 : 0.5,
                transform: i === active ? 'scale(1)' : 'scale(0.985)',
              }}
            >
              {line}
            </h2>
          ))}
        </div>

        <div
          className="relative mt-12 flex flex-wrap items-center justify-center gap-x-8 gap-y-2"
          style={{
            opacity: progress > 0.6 ? 1 : 0,
            transform: progress > 0.6 ? 'none' : 'translateY(16px)',
            transition: 'opacity 700ms ease, transform 700ms cubic-bezier(0.16,1,0.3,1)',
          }}
        >
          {['No API keys', 'No cloud', 'No vendor lock-in'].map((t) => (
            <span key={t} className="label flex items-center gap-2 text-steel-300">
              <span className="h-1 w-1 rounded-full bg-forge" />
              {t}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
