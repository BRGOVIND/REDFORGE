import { Reveal } from '../motion';

const PRINCIPLES = [
  {
    k: 'Local by default',
    v: 'Use Ollama, LM Studio, llama.cpp, or vLLM to keep inference on your machine. Hosted providers are available when you choose to connect them.',
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
    <section id="about" className="relative border-t border-steel-800 py-12 sm:py-14 lg:py-16">
      <div className="mx-auto grid max-w-editorial grid-cols-1 gap-12 px-6 sm:px-10 lg:grid-cols-12 lg:gap-16">
        <div className="lg:col-span-5">
          <Reveal delay={120}>
            <h2 className="display text-5xl leading-[1.02] text-bone sm:text-6xl">
              Your workspace.
              <br />
              <span className="text-steel-400">Your machine.</span>
            </h2>
          </Reveal>
          <Reveal delay={240}>
            <p className="mt-8 max-w-md text-[15px] leading-relaxed text-steel-300">
              RedForge began as a local model security lab. It now brings models, prompts, datasets,
              benchmarks, and evaluation into one desktop workspace. Fine-tuning remains experimental.
            </p>
          </Reveal>
          <Reveal delay={320}>
            <p className="mt-5 max-w-md text-[15px] leading-relaxed text-steel-400">
              With a local runtime, prompts and evaluation results stay on your hardware. Hosted
              providers are optional. Security remains one capability within the wider workflow.
            </p>
          </Reveal>
        </div>

          <div className="lg:col-span-7 lg:pt-8">
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
