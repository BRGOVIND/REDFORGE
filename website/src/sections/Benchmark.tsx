import { useEffect, useState } from 'react';
import { Reveal, useInView } from '../motion';
import { SectionLabel } from '../components/marks';

function CountUp({ to, duration = 1600 }: { to: number; duration?: number }) {
  const [ref, inView] = useInView<HTMLSpanElement>({ once: true });
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!inView) return;
    let raf = 0;
    const start = performance.now();
    const tick = (t: number) => {
      const p = Math.min((t - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setN(Math.round(to * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, to, duration]);
  return <span ref={ref}>{n.toLocaleString()}</span>;
}

const CAPABILITIES = [
  { k: 'Adaptive attacks', v: 'Prompts that mutate and escalate in response to a model that resists — the harder it holds, the harder it pushes.' },
  { k: 'Autonomous evaluation', v: 'An agent that runs the whole loop unattended, bounded by round, token, and time budgets.' },
  { k: 'Research mode', v: 'Deterministic, reproducible runs with a versioned dataset — built for results you can cite.' },
];

export function Benchmark() {
  return (
    <section id="benchmark" className="relative overflow-hidden border-t border-steel-800 py-32 sm:py-44">
      <div className="mx-auto grid max-w-editorial grid-cols-1 gap-16 px-6 sm:px-10 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <Reveal>
            <SectionLabel index="07">Benchmark Engine</SectionLabel>
          </Reveal>
          <Reveal delay={120}>
            <div className="mt-10 display leading-none text-bone">
              <span className="block text-[24vw] text-ember-gradient sm:text-[13vw] lg:text-[11vw]">
                <CountUp to={800} />
              </span>
            </div>
          </Reveal>
          <Reveal delay={220}>
            <p className="mt-4 max-w-xs text-[15px] leading-relaxed text-steel-300">
              validated cases in RedForge-Bench-V1, hand-authored and expanded across five
              attack categories.
            </p>
          </Reveal>
        </div>

        <div className="lg:col-span-7 lg:pt-16">
          <div className="flex flex-col">
            {CAPABILITIES.map((c, i) => (
              <Reveal key={c.k} delay={i * 120}>
                <div className="border-t border-steel-800 py-8 last:border-b">
                  <div className="flex items-baseline gap-6">
                    <span className="label text-steel-500">{String(i + 1).padStart(2, '0')}</span>
                    <div>
                      <h3 className="display text-2xl text-bone sm:text-3xl">{c.k}</h3>
                      <p className="mt-3 max-w-lg text-[14px] leading-relaxed text-steel-400">{c.v}</p>
                    </div>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
