import { useState } from 'react';
import { cn } from '../lib/cn';

const AUDIENCES = [
  { k: 'AI Engineers', v: 'A single local workspace to discover models, engineer prompts, benchmark, evaluate, and ship — without stitching five tools together.' },
  { k: 'ML Engineers', v: 'Manage datasets, fine-tune (experimental), track experiments, and compare results with real metrics and full lineage — on your own hardware.' },
  { k: 'Researchers', v: 'Reproducible, citable runs with a versioned benchmark and deterministic evaluation — no prompt ever leaves your machine.' },
  { k: 'Students', v: 'A hands-on way to learn the entire local-AI workflow, end to end, for free on a laptop.' },
  { k: 'Security Engineers', v: 'Red-team any local model in minutes and export findings your team can act on — one capability inside a full platform.' },
  { k: 'Developers & Hobbyists', v: 'Run models locally with zero API cost, unlimited experimentation, and a native desktop app that just works.' },
];

export function BuiltFor() {
  const [active, setActive] = useState(0);

  return (
    <section className="relative border-t border-steel-800 py-24 sm:py-32 lg:py-40">
      <div className="mx-auto max-w-editorial px-6 sm:px-10">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:gap-16">
          <div className="lg:col-span-7">
            <ul className="flex flex-col">
              {AUDIENCES.map((a, i) => (
                <li key={a.k}>
                  <button
                    onMouseEnter={() => setActive(i)}
                    onFocus={() => setActive(i)}
                    className={cn(
                      'focus-ring group flex w-full items-center gap-5 border-b border-steel-800 py-5 text-left transition-all duration-500 ease-forge sm:py-6',
                      active === i ? 'pl-4' : 'pl-0'
                    )}
                  >
                    <span
                      className={cn(
                        'display text-[26px] leading-tight transition-colors duration-500 sm:text-5xl',
                        active === i ? 'text-bone' : 'text-steel-500'
                      )}
                    >
                      {a.k}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="lg:col-span-5 lg:pt-6">
            <div className="sticky top-32 border-l border-steel-700 pl-8">
              <p className="label mb-6">In practice</p>
              <div className="relative min-h-[140px]">
                {AUDIENCES.map((a, i) => (
                  <p
                    key={a.k}
                    className="absolute inset-0 text-[18px] leading-relaxed text-steel-200"
                    style={{
                      opacity: active === i ? 1 : 0,
                      transform: active === i ? 'none' : 'translateY(10px)',
                      transition: 'opacity 500ms ease, transform 500ms cubic-bezier(0.16,1,0.3,1)',
                      pointerEvents: active === i ? 'auto' : 'none',
                    }}
                  >
                    {a.v}
                  </p>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
