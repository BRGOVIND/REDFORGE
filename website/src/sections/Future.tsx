import { Reveal } from '../motion';

const HORIZON = [
  { k: 'Real fine-tuning', v: 'Graduate Training from Experimental to production — full local LoRA / QLoRA with real GPU execution.' },
  { k: 'Distributed training', v: 'Scale runs across multiple GPUs and machines, orchestrated from one workspace.' },
  { k: 'Plugin marketplace', v: 'Install community runtimes, attacks, evaluators, and workflows in one click.' },
  { k: 'Agent workflows', v: 'Compose multi-step agentic pipelines over your local models and tools.' },
  { k: 'Cloud sync & collaboration', v: 'Optional sync and team workspaces — for those who want to share, without giving up local-first.' },
];

export function Future() {
  return (
    <section id="future" className="relative border-t border-steel-800 py-24 sm:py-32 lg:py-40">
      <div className="mx-auto max-w-editorial px-6 sm:px-10">
        <Reveal delay={120}>
          <h2 className="display max-w-2xl text-5xl text-bone sm:text-6xl">
            What&apos;s forging next.
          </h2>
        </Reveal>

        <div className="relative mt-20">
          <div className="absolute left-0 right-0 top-[7px] hidden h-px bg-steel-700 lg:block" />
          <div className="grid grid-cols-1 gap-12 sm:grid-cols-2 lg:grid-cols-4 lg:gap-8">
            {HORIZON.map((h, i) => (
              <Reveal key={h.k} delay={i * 140}>
                <div className="relative lg:pr-6">
                  <span className="mb-5 block h-3.5 w-3.5 rounded-full border border-forge bg-ink lg:-mt-[1px]">
                    <span className="mx-auto mt-[3px] block h-1.5 w-1.5 rounded-full bg-forge" />
                  </span>
                  <h3 className="display text-xl text-bone">{h.k}</h3>
                  <p className="mt-3 text-[14px] leading-relaxed text-steel-400">{h.v}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
