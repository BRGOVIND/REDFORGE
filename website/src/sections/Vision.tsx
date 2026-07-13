import { Reveal } from '../motion';

const PRINCIPLES = [
  { k: 'No cloud', v: 'Inference never leaves the machine. There is no server to trust.' },
  { k: 'No API keys', v: 'Nothing to sign up for, nothing to rotate, nothing to leak.' },
  { k: 'No subscriptions', v: 'Open source. Yours to run, fork, and audit — forever.' },
];

export function Vision() {
  return (
    <section className="relative overflow-hidden border-t border-steel-800 py-24 sm:py-32 lg:py-40">
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
              Hosted evaluation platforms want your prompts, your responses, and a subscription.
              RedForge was built on the opposite belief — that the most sensitive testing you do
              should happen entirely on your own machine.
            </p>
          </Reveal>
        </div>

        <div className="lg:pl-10">
          <div className="relative border-l border-steel-700 pl-8">
            {PRINCIPLES.map((p, i) => (
              <Reveal key={p.k} delay={i * 140} className="relative pb-12 last:pb-0">
                <span className="absolute -left-[41px] top-1.5 h-2.5 w-2.5 rounded-full bg-forge glow-forge" />
                <h3 className="display text-2xl text-bone">{p.k}</h3>
                <p className="mt-2 max-w-sm text-[14px] leading-relaxed text-steel-400">{p.v}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
