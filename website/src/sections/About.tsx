import { Reveal } from '../motion';
import { SectionLabel } from '../components/marks';

const PRINCIPLES = [
  {
    k: 'Local by default',
    v: 'Every model runs through Ollama on your machine. Prompts, responses, and findings never leave it — there is no server to trust and no API key to leak.',
  },
  {
    k: 'You own the data',
    v: 'Results live in a local SQLite database you control. The most sensitive testing you do stays entirely under your roof.',
  },
  {
    k: 'Deterministic & auditable',
    v: 'Planning and analysis are reproducible. The engine is open source — read it, fork it, extend the attacks and evaluators.',
  },
];

export function About() {
  return (
    <section id="about" className="relative border-t border-steel-800 py-24 sm:py-32 lg:py-40">
      <div className="mx-auto grid max-w-editorial grid-cols-1 gap-12 px-6 sm:px-10 lg:grid-cols-12 lg:gap-16">
        <div className="lg:col-span-5">
          <Reveal>
            <SectionLabel>About RedForge</SectionLabel>
          </Reveal>
          <Reveal delay={120}>
            <h2 className="display mt-8 text-5xl leading-[1.02] text-bone sm:text-6xl">
              A security lab
              <br />
              that never leaves
              <br />
              <span className="text-steel-400">your machine.</span>
            </h2>
          </Reveal>
          <Reveal delay={240}>
            <p className="mt-8 max-w-md text-[15px] leading-relaxed text-steel-300">
              RedForge is a local red-teaming laboratory for large language models. It ships a
              library of adversarial attacks and a benchmark, runs them against any model you have
              pulled in Ollama, scores the responses, and reports where the model breaks.
            </p>
          </Reveal>
          <Reveal delay={320}>
            <p className="mt-5 max-w-md text-[15px] leading-relaxed text-steel-400">
              Language models fail in ways traditional software never did — adversarial, subtle, and
              invisible until someone goes looking. Testing them is exactly the kind of work that
              shouldn't require handing your prompts to a third party. RedForge exists so it doesn't.
            </p>
          </Reveal>
        </div>

        <div className="lg:col-span-7 lg:pt-16">
          <div className="border-l border-steel-700 pl-8">
            {PRINCIPLES.map((p, i) => (
              <Reveal key={p.k} delay={i * 140} className="relative pb-12 last:pb-0">
                <span className="absolute -left-[41px] top-1.5 h-2.5 w-2.5 rounded-full bg-forge glow-forge" />
                <h3 className="display text-2xl text-bone">{p.k}</h3>
                <p className="mt-2 max-w-lg text-[14px] leading-relaxed text-steel-400">{p.v}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
