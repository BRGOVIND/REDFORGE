import { Cpu, Brain, Crosshair, Scale, Activity, FileText } from 'lucide-react';
import { usePinProgress } from '../motion';
import { cn, clamp } from '../lib/cn';

const STAGES = [
  { k: 'Model', icon: Cpu, d: 'Point RedForge at any model served by your local runtime — Ollama, LM Studio, llama.cpp, or vLLM. Nothing is sent away.' },
  { k: 'Planner', icon: Brain, d: 'It profiles the model and drafts a deterministic attack plan — categories, ordering, and escalation, tuned to the target.' },
  { k: 'Attack Engine', icon: Crosshair, d: 'Adversarial prompts are fired in waves. When one is resisted, it mutates and escalates — automatically.' },
  { k: 'Judge', icon: Scale, d: 'Each response is scored — by heuristics or an LLM-as-judge — into PASS, FAIL, or UNCERTAIN, with a reason.' },
  { k: 'Analysis', icon: Activity, d: 'Verdicts become a security score, category breakdowns, ranked vulnerabilities, and failure patterns.' },
  { k: 'Report', icon: FileText, d: 'A structured report lands with an executive summary, findings, evidence, and concrete recommendations.' },
];

export function Pipeline() {
  const [ref, progress] = usePinProgress<HTMLDivElement>();
  const active = clamp(Math.floor(progress * STAGES.length), 0, STAGES.length - 1);
  const drawn = clamp(progress * 1.02, 0, 1);

  return (
    <section id="how" ref={ref} className="relative" style={{ height: '360vh' }}>
      <div className="sticky top-0 flex h-screen items-center overflow-hidden border-t border-steel-800">
        <div className="blueprint-grid-fine pointer-events-none absolute inset-0 opacity-40" />
        <div className="relative mx-auto grid w-full max-w-editorial grid-cols-1 items-center gap-10 px-6 sm:px-10 lg:grid-cols-2 lg:gap-16">
          {/* Left — the active stage, cross-fading */}
          <div>
            <div className="relative h-[220px] sm:h-[280px]">
              {STAGES.map((s, i) => (
                <div
                  key={s.k}
                  className="absolute inset-0"
                  style={{
                    opacity: i === active ? 1 : 0,
                    transform: i === active ? 'translateY(0)' : 'translateY(18px)',
                    filter: i === active ? 'blur(0)' : 'blur(6px)',
                    transition: 'opacity 600ms ease, transform 600ms cubic-bezier(0.16,1,0.3,1), filter 600ms ease',
                    pointerEvents: i === active ? 'auto' : 'none',
                  }}
                >
                  <h2 className="display text-5xl text-bone sm:text-6xl lg:text-7xl">{s.k}</h2>
                  <p className="mt-6 max-w-md text-[15px] leading-relaxed text-steel-300 sm:text-[16px]">{s.d}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Right — the drawing pipeline */}
          <div className="relative mx-auto w-full max-w-sm">
            <div className="absolute bottom-3 left-[19px] top-3 w-px bg-steel-700" />
            <div
              className="absolute left-[19px] top-3 w-px origin-top"
              style={{
                height: `calc((100% - 24px) * ${drawn})`,
                background: 'linear-gradient(180deg, #D12A2A, #A11212, #5A0000)',
                boxShadow: '0 0 12px rgba(122,0,0,0.5)',
              }}
            />
            <div className="flex flex-col gap-6 sm:gap-9">
              {STAGES.map((s, i) => {
                const lit = i <= active;
                const Icon = s.icon;
                return (
                  <div key={s.k} className="flex items-center gap-5">
                    <span
                      className={cn(
                        'relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border transition-all duration-500 ease-forge',
                        lit
                          ? 'border-forge bg-forge/10 text-forge'
                          : 'border-steel-700 bg-char text-steel-500'
                      )}
                      style={lit ? { boxShadow: '0 0 22px -4px rgba(122,0,0,0.6)' } : undefined}
                    >
                      <Icon size={16} />
                    </span>
                    <div className="flex-1">
                      <span
                        className={cn(
                          'display text-lg transition-colors duration-500',
                          lit ? 'text-bone' : 'text-steel-500'
                        )}
                      >
                        {s.k}
                      </span>
                    </div>
                    <span
                      className={cn(
                        'label transition-opacity duration-500',
                        i === active ? 'text-forge opacity-100' : 'opacity-0'
                      )}
                    >
                      active
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
