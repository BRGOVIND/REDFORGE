import { Package, Database, Dumbbell, Gauge, ShieldCheck, FileText } from 'lucide-react';
import { usePinStage } from '../motion';
import { cn } from '../lib/cn';
import { ForgeMesh } from './ForgeMesh';

// One connected engineering workflow, not isolated tools. Everything below runs
// locally and flows into the next stage, with full lineage.
const STAGES = [
  { k: 'Discover', icon: Package, d: 'Browse the Model Hub and one-click download models from Hugging Face or Ollama, into a local project. No terminal.' },
  { k: 'Datasets', icon: Database, d: 'Import, preprocess, and version datasets for training and evaluation. Everything stays on disk, under your control.' },
  { k: 'Train', icon: Dumbbell, d: 'Fine-tune with LoRA / QLoRA. The workflow mirrors real execution today and is actively evolving, marked Experimental.' },
  { k: 'Benchmark', icon: Gauge, d: 'Score and compare models across suites, tracked over time, so you know what actually improved.' },
  { k: 'Secure & Evaluate', icon: ShieldCheck, d: 'Red-team and evaluate any local model with deterministic verdicts, security as one capability among many.' },
  { k: 'Report & Export', icon: FileText, d: 'Turn runs into structured reports and export results (adapters, GGUF, or an Ollama model) ready to ship.' },
];

export function Pipeline() {
  const [ref, active] = usePinStage<HTMLDivElement>(STAGES.length);

  return (
    <section id="how" ref={ref} className="relative" style={{ height: '280vh' }}>
      <div className="pipeline-pin sticky top-0 flex h-dvh items-center overflow-hidden">
        <ForgeMesh active host=".pipeline-pin" />
        <div className="blueprint-grid-fine pointer-events-none absolute inset-0 opacity-40" />
        <div className="relative mx-auto grid w-full max-w-editorial grid-cols-1 items-center gap-10 px-6 sm:px-10 lg:grid-cols-2 lg:gap-16">
          {/* Left, the active stage, cross-fading */}
          <div>
            <div className="pipeline-stage relative h-[220px] sm:h-[280px]" data-mesh-quiet>
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

          {/* Right, the drawing pipeline */}
          <div className="relative mx-auto w-full max-w-sm">
            <div className="pipeline-timeline flex flex-col">
              {STAGES.map((s, i) => {
                const lit = i <= active;
                const Icon = s.icon;
                return (
                  <div key={s.k} className={cn('pipeline-step relative flex items-center gap-5', i < active && 'is-complete')}>
                    <span
                      className={cn(
                        'relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border transition-all duration-500 ease-forge',
                        lit
                          ? 'border-forge bg-[#f8f6f2] text-forge'
                          : 'border-steel-700 bg-char text-steel-500'
                      )}
                      style={lit ? { boxShadow: '0 3px 12px rgba(122,0,0,0.1)' } : undefined}
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
