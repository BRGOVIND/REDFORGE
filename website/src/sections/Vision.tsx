import { Reveal } from '../motion';

const PRINCIPLES = [
  { k: 'Local by default', v: 'Use a local runtime to keep model inference, prompts, and results on your machine.' },
  { k: 'No account for local use', v: 'Get started locally without an account or API keys. Hosted providers are optional.' },
  { k: 'Open source', v: 'Run, inspect, and contribute to RedForge without a subscription.' },
];

export function Vision() {
  return (
    <section className="relative overflow-hidden border-t border-steel-800 py-12 sm:py-14 lg:py-16">
      <div
        className="pointer-events-none absolute right-[-10%] top-0 h-[500px] w-[500px] rounded-full blur-[140px]"
        style={{ background: 'radial-gradient(circle, rgba(90,0,0,0.14), transparent 65%)' }}
      />
      <div className="mx-auto grid max-w-editorial grid-cols-1 gap-12 px-6 sm:px-10 lg:grid-cols-2 lg:gap-16">
        <div>
          <Reveal delay={120}>
            <h2 className="display text-5xl leading-[1.02] text-bone sm:text-6xl">
              Serious security testing
              <br />
              shouldn't require
              <br />
              <span className="text-steel-400">handing over your model.</span>
            </h2>
          </Reveal>
          <Reveal delay={260}>
            <p className="mt-8 max-w-md text-[15px] leading-relaxed text-steel-300">
              Choose a local runtime for sensitive evaluations so prompts and responses stay on
              your machine. Hosted providers remain available when you choose to connect them.
            </p>
          </Reveal>
        </div>

        <div className="lg:pl-10">
          <ul className="principle-list">
            {PRINCIPLES.map((p, i) => (
              <li key={p.k} className="principle-item">
                <span aria-hidden="true" className="principle-node" />
                <Reveal delay={i * 140}>
                  <h3 className="display text-2xl text-bone">{p.k}</h3>
                  <p className="mt-3 max-w-sm text-[14px] leading-relaxed text-steel-400">{p.v}</p>
                </Reveal>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
