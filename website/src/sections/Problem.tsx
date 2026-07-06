import { useState } from 'react';
import { Reveal } from '../motion';
import { SectionLabel } from '../components/marks';
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
    <section id="problem" className="relative border-t border-steel-800 py-32 sm:py-44">
      <div className="mx-auto grid max-w-editorial grid-cols-1 gap-16 px-6 sm:px-10 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <Reveal>
            <SectionLabel index="03">The Problem</SectionLabel>
          </Reveal>
          <Reveal delay={120}>
            <h2 className="display mt-8 text-5xl text-bone sm:text-6xl">
              Every model has a<br />
              <span className="text-ember-gradient">breaking point.</span>
            </h2>
          </Reveal>
          <Reveal delay={240}>
            <p className="mt-6 max-w-sm text-[15px] leading-relaxed text-steel-300">
              Language models fail in ways traditional software never did. The failures are
              subtle, adversarial, and invisible until someone goes looking.
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
                    'focus-ring group relative w-full border-t border-steel-800 py-8 text-left transition-all duration-500 ease-forge',
                    active === i ? 'pl-6' : 'pl-0',
                    i === FAILURES.length - 1 && 'border-b'
                  )}
                >
                  <span
                    className="absolute left-0 top-1/2 h-0 w-[3px] -translate-y-1/2 bg-forge transition-all duration-500 ease-forge"
                    style={{ height: active === i ? '58%' : '0%' }}
                  />
                  <div className="flex items-baseline justify-between gap-6">
                    <div className="flex items-baseline gap-6">
                      <span className="label text-steel-500">{f.n}</span>
                      <span
                        className={cn(
                          'display text-3xl transition-colors duration-500 sm:text-5xl',
                          active === i ? 'text-bone' : 'text-steel-300'
                        )}
                      >
                        {f.title}
                      </span>
                    </div>
                  </div>
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
