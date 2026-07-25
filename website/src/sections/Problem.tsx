import { useState } from 'react';
import { Reveal } from '../motion';
import { cn } from '../lib/cn';

const FAILURES = [
  {
    n: '01',
    title: 'Prompt Injection',
    line: 'A single crafted instruction overrides everything you told it to be.',
  },
  {
    n: '02',
    title: 'Jailbreaks',
    line: 'Personas, fiction, and pressure walk the model straight past its guardrails.',
  },
  {
    n: '03',
    title: 'Hallucination',
    line: 'Confident, fluent, and completely fabricated — presented as fact.',
  },
  {
    n: '04',
    title: 'Data Leakage',
    line: 'System prompts, hidden context, and training data coaxed into the open.',
  },
];

export function Problem() {
  const [active, setActive] = useState<number | null>(null);

  return (
    <section id="security" className="relative border-t border-steel-800 py-24 sm:py-32 lg:py-40">
      <div className="mx-auto grid max-w-editorial grid-cols-1 gap-12 px-6 sm:px-10 lg:grid-cols-12 lg:gap-16">
        <div className="lg:col-span-4">
          <Reveal delay={80}>
            <p className="label mb-4">Security testing · one capability</p>
          </Reveal>
          <Reveal delay={120}>
            <h2 className="display text-5xl text-bone sm:text-6xl">
              Every model has a<br />
              <span className="text-ember-gradient">breaking point.</span>
            </h2>
          </Reveal>
          <Reveal delay={240}>
            <p className="mt-6 max-w-sm text-[15px] leading-relaxed text-steel-300">
              RedForge keeps a full red-teaming engine built in — now one capability inside a
              complete platform. Throw thousands of adversarial prompts at any local model and see
              exactly where it breaks, with deterministic, exportable results.
            </p>
          </Reveal>
        </div>

        <div className="lg:col-span-8">
          <div className="flex flex-col">
            {FAILURES.map((f, i) => (
              <Reveal key={f.n} delay={i * 110}>
                <button
                  onMouseEnter={() => setActive(i)}
                  onMouseLeave={() => setActive(null)}
                  onFocus={() => setActive(i)}
                  onBlur={() => setActive(null)}
                  className={cn(
                    'focus-ring group relative w-full border-t border-steel-800 py-7 text-left transition-all duration-500 ease-forge sm:py-8',
                    active === i ? 'pl-6' : 'pl-0',
                    i === FAILURES.length - 1 && 'border-b'
                  )}
                >
                  <span
                    className="absolute left-0 top-1/2 h-0 w-[3px] -translate-y-1/2 bg-forge transition-all duration-500 ease-forge"
                    style={{ height: active === i ? '58%' : '0%' }}
                  />
                  <span
                    className={cn(
                      'display text-3xl transition-colors duration-500 sm:text-5xl',
                      active === i ? 'text-bone' : 'text-steel-300'
                    )}
                  >
                    {f.title}
                  </span>
                  <p
                    className="mt-4 max-w-lg text-[14px] leading-relaxed text-steel-400 transition-all duration-500 ease-forge"
                    style={{
                      opacity: active === i ? 1 : 0.35,
                    }}
                  >
                    {f.line}
                  </p>
                </button>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
