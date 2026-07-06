import { Reveal } from '../motion';
import { SectionLabel, Wordmark } from '../components/marks';

const HORIZON = [
  { k: 'Enterprise', v: 'Team workspaces, SSO, and audit trails for organizations running RedForge at scale.' },
  { k: 'Fine-tuning workspace', v: 'Close the loop — turn findings into training signal and re-harden the model in place.' },
  { k: 'API connectors', v: 'Optional bridges to hosted models, for teams that need to test beyond local.' },
  { k: 'Research platform', v: 'Shared benchmarks, leaderboards, and reproducible studies for the community.' },
];

export function Future() {
  return (
    <section className="relative border-t border-steel-800 py-32 sm:py-40">
      <div className="mx-auto max-w-editorial px-6 sm:px-10">
        <Reveal>
          <SectionLabel index="11">The Horizon</SectionLabel>
        </Reveal>
        <Reveal delay={120}>
          <h2 className="display mt-8 max-w-2xl text-5xl text-bone sm:text-6xl">
            What&apos;s forging next.
          </h2>
        </Reveal>

        <div className="relative mt-20">
          <div className="absolute left-0 right-0 top-[7px] hidden h-px bg-steel-700 lg:block" />
          <div className="grid grid-cols-1 gap-12 sm:grid-cols-2 lg:grid-cols-4 lg:gap-8">
            {HORIZON.map((h, i) => (
              <Reveal key={h.k} delay={i * 140}>
                <div className="relative lg:pr-6">
                  <span className="mb-6 block h-3.5 w-3.5 rounded-full border border-forge bg-ink lg:-mt-[1px]">
                    <span className="mx-auto mt-[3px] block h-1.5 w-1.5 rounded-full bg-forge" />
                  </span>
                  <p className="label mb-3 text-steel-500">0{i + 1}</p>
                  <h3 className="display text-xl text-bone">{h.k}</h3>
                  <p className="mt-3 text-[14px] leading-relaxed text-steel-400">{h.v}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="mx-auto mt-40 max-w-editorial px-6 sm:px-10">
        <div className="flex flex-col items-start justify-between gap-8 border-t border-steel-800 pt-10 sm:flex-row sm:items-center">
          <div>
            <Wordmark />
            <p className="mt-3 max-w-xs text-[13px] text-steel-500">
              Break your model before attackers do. Local AI security, forged in the open.
            </p>
          </div>
          <div className="flex items-center gap-8">
            <a href="#top" className="focus-ring text-[13px] text-steel-300 hover:text-bone">Back to top</a>
            <a href="https://github.com/BRGOVIND/REDFORGE" target="_blank" rel="noreferrer" className="focus-ring text-[13px] text-steel-300 hover:text-bone">GitHub</a>
            <span className="label text-steel-600">MIT · {new Date().getFullYear()}</span>
          </div>
        </div>
      </footer>
    </section>
  );
}
