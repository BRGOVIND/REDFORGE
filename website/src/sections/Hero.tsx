import { ArrowDown } from 'lucide-react';
import { Parallax } from '../motion';

/** Section 2 — Hero. Typography is the hero; whitespace does the rest. */
export function Hero({ started }: { started: boolean }) {
  const words = ['BREAK', 'YOUR', 'MODEL.'];
  const words2 = ['BEFORE', 'ATTACKERS', 'DO.'];

  const wordStyle = (i: number): React.CSSProperties => ({
    opacity: started ? 1 : 0,
    transform: started ? 'none' : 'translateY(28px)',
    filter: started ? 'blur(0)' : 'blur(8px)',
    transition: `opacity 1s cubic-bezier(0.16,1,0.3,1) ${300 + i * 90}ms, transform 1s cubic-bezier(0.16,1,0.3,1) ${300 + i * 90}ms, filter 1s ease ${300 + i * 90}ms`,
  });

  return (
    <section id="top" className="relative flex min-h-screen items-center overflow-hidden">
      <Parallax distance={120} className="pointer-events-none absolute inset-0">
        <div className="blueprint-grid absolute inset-0 opacity-60" />
        <div
          className="absolute inset-0"
          style={{ background: 'radial-gradient(120% 80% at 50% 0%, transparent 40%, #050506 100%)' }}
        />
      </Parallax>

      {/* faint ember bloom */}
      <div
        className="pointer-events-none absolute left-[8%] top-1/3 h-[420px] w-[420px] rounded-full blur-[120px]"
        style={{ background: 'radial-gradient(circle, rgba(229,72,77,0.16), transparent 65%)' }}
      />

      <div className="relative mx-auto w-full max-w-editorial px-6 sm:px-10">
        <div
          className="label mb-8 flex items-center gap-3"
          style={{ opacity: started ? 0.8 : 0, transition: 'opacity 1s ease 200ms' }}
        >
          <span className="h-1.5 w-1.5 animate-ember-flicker rounded-full bg-forge" />
          Adversarial evaluation for local LLMs
        </div>

        <h1 className="display text-bone text-[15vw] leading-[0.9] sm:text-[12vw] lg:text-[9.5vw]">
          <span className="block">
            {words.map((w, i) => (
              <span key={w} className="inline-block" style={wordStyle(i)}>
                {w}&nbsp;
              </span>
            ))}
          </span>
          <span className="mt-2 block">
            {words2.map((w, i) => (
              <span
                key={w}
                className={cnWord(w)}
                style={wordStyle(i + 3)}
              >
                {w}&nbsp;
              </span>
            ))}
          </span>
        </h1>

        <div
          className="mt-12 flex max-w-xl items-start gap-4"
          style={{ opacity: started ? 1 : 0, transition: 'opacity 1.2s ease 900ms' }}
        >
          <span className="mt-1 h-10 w-px bg-forge" />
          <p className="text-[15px] leading-relaxed text-steel-200">
            A red-teaming laboratory that lives on your machine. Throw thousands of adversarial
            prompts at any Ollama model and watch exactly where it breaks — before someone else finds out.
          </p>
        </div>
      </div>

      <a
        href="#problem"
        className="focus-ring absolute bottom-8 left-1/2 flex -translate-x-1/2 flex-col items-center gap-2 text-steel-300"
        style={{ opacity: started ? 1 : 0, transition: 'opacity 1s ease 1400ms' }}
        aria-label="Scroll to begin"
      >
        <span className="label">Scroll</span>
        <ArrowDown size={16} className="animate-bounce" style={{ animationDuration: '2.4s' }} />
      </a>
    </section>
  );
}

function cnWord(w: string): string {
  return w === 'ATTACKERS' ? 'inline-block text-ember-gradient' : 'inline-block';
}
