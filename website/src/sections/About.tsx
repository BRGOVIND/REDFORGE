import { Reveal } from '../motion';

const PRINCIPLES = [
  {
    k: 'Local by default',
    v: 'Every model runs through a local runtime on your machine, Ollama, LM Studio, llama.cpp, or vLLM. Prompts, data, and results never leave it: no server to trust, no API key to leak.',
  },
  {
    k: 'Simulation-first architecture',
    v: 'Where infrastructure is still evolving, workflows accurately mirror real execution while preserving the final production experience, an intentional engineering decision, not a limitation. Training is currently Experimental.',
  },
  {
    k: 'Open & extensible',
    v: 'Results live in a local database you own; the platform is open source. Read it, fork it, and add runtimes, attacks, evaluators, and workflows.',
  },
];

export function About() {
  return (
    <section id="about" className="relative border-t border-steel-800 py-24 sm:py-32 lg:py-40">
      <div className="mx-auto grid max-w-editorial grid-cols-1 gap-12 px-6 sm:px-10 lg:grid-cols-12 lg:gap-16">
        <div className="lg:col-span-5">
          <Reveal delay={120}>
            <h2 className="display text-5xl leading-[1.02] text-bone sm:text-6xl">
              A platform
              <br />
              that never leaves
              <br />
              <span className="text-steel-400">your machine.</span>
            </h2>
          </Reveal>
          <Reveal delay={240}>
            <p className="mt-8 max-w-md text-[15px] leading-relaxed text-steel-300">
              RedForge began as a local AI security &amp; evaluation lab. It has grown into a complete
              Local AI Engineering Platform. Discover and manage models, engineer prompts, work with
              datasets, benchmark, evaluate, fine-tune, and secure, all from one native desktop app.
            </p>
          </Reveal>
          <Reveal delay={320}>
            <p className="mt-5 max-w-md text-[15px] leading-relaxed text-steel-400">
              Everything runs through a local runtime you control, no prompt, dataset, or result
              leaves your hardware. Security is still here, sharper than ever, but now it's one
              capability among many in a cohesive engineering workflow.
            </p>
          </Reveal>
        </div>

        <div className="lg:col-span-7 lg:pt-16">
          <ul className="principle-list">
            {PRINCIPLES.map((p, i) => (
              <li key={p.k} className="principle-item">
                <span aria-hidden="true" className="principle-node" />
                <Reveal delay={i * 140}>
                  <h3 className="display text-2xl text-bone">{p.k}</h3>
                  <p className="mt-3 max-w-lg text-[14px] leading-relaxed text-steel-400">{p.v}</p>
                </Reveal>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
