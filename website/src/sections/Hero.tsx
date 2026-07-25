import { ArrowDown } from 'lucide-react';
import { Parallax } from '../motion';
import { HeroSilhouette } from './HeroSilhouette';

/** Section 2 — Hero. Typography is the hero; whitespace does the rest. */
export function Hero({ started }: { started: boolean }) {
  const words = ['BUILD.', 'EVALUATE.', 'MANAGE.'];
  const words2 = ['LOCAL', 'AI.'];

  const wordStyle = (i: number): React.CSSProperties => ({
    opacity: started ? 1 : 0,
    transform: started ? 'translate3d(0,0,0)' : 'translate3d(0,28px,0)',
    filter: started ? 'blur(0)' : 'blur(8px)',
    transition: `opacity 1s cubic-bezier(0.16,1,0.3,1) ${300 + i * 90}ms, transform 1s cubic-bezier(0.16,1,0.3,1) ${300 + i * 90}ms, filter 1s ease ${300 + i * 90}ms`,
    // GPU-composite the entrance so the blur/translate doesn't flicker.
    willChange: 'transform, opacity, filter',
    backfaceVisibility: 'hidden',
  });

  return (
    // pt clears the fixed navbar so the centered title never underlaps it on the
    // first paint (no layout shift); 100svh avoids the mobile URL-bar resize jump.
    <section
      id="top"
      className="relative flex min-h-screen min-h-[100svh] items-center overflow-hidden pt-16"
    >
      <Parallax distance={120} className="pointer-events-none absolute inset-0">
        <div className="blueprint-grid absolute inset-0 opacity-50" />
        <div
          className="absolute inset-0"
          style={{ background: 'radial-gradient(120% 80% at 50% 0%, transparent 40%, #050506 100%)' }}
        />
      </Parallax>

      {/* faint ember bloom */}
      <div
        className="pointer-events-none absolute left-[8%] top-1/3 h-[420px] w-[420px] rounded-full blur-[120px]"
        style={{ background: 'radial-gradient(circle, rgba(90,0,0,0.20), transparent 65%)' }}
      />

      {/* barely-visible shadow-fortress skyline — depth behind the text */}
      <HeroSilhouette />

      <div className="relative mx-auto w-full max-w-editorial px-6 sm:px-10">
        <h1 className="display text-bone text-[14vw] leading-[0.92] sm:text-[12vw] lg:text-[9.5vw]">
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
          className="mt-10 flex max-w-2xl items-start gap-4 sm:mt-14"
          style={{ opacity: started ? 1 : 0, transition: 'opacity 1.2s ease 900ms' }}
        >
          <span className="mt-1 h-10 w-px shrink-0 bg-forge" />
          <p className="text-[15px] leading-relaxed text-steel-200 sm:text-base">
            The complete Local AI Engineering Platform. Discover models, manage runtimes,
            engineer prompts, benchmark, evaluate, secure, and fine-tune — everything you need to
            build with local AI, running entirely on your machine.
          </p>
        </div>

        {/* Primary + secondary CTAs */}
        <div
          className="mt-9 flex flex-wrap items-center gap-3 sm:mt-11"
          style={{ opacity: started ? 1 : 0, transition: 'opacity 1.2s ease 1100ms' }}
        >
          <a
            href="#download"
            className="focus-ring group inline-flex items-center gap-2 rounded-full bg-forge px-6 py-3 text-[14px] font-medium text-bone transition-all duration-300 hover:bg-forge/90 hover:shadow-[0_0_28px_-6px_rgba(122,0,0,0.7)]"
          >
            Download RedForge
          </a>
          <a
            href="#capabilities"
            className="focus-ring inline-flex items-center gap-2 rounded-full border border-steel-600 px-6 py-3 text-[14px] text-bone transition-colors duration-300 hover:border-steel-400"
          >
            View Documentation
          </a>
          <span className="ml-1 hidden items-center gap-4 text-[12px] text-steel-400 sm:flex">
            <span>⭐ 100% Local</span>
            <span>🔒 Privacy First</span>
            <span>⚡ Multi-Runtime</span>
            <span>🧪 Training (Experimental)</span>
          </span>
        </div>
      </div>

      <a
        href="#capabilities"
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
  return w === 'LOCAL' ? 'inline-block text-ember-gradient' : 'inline-block';
}
