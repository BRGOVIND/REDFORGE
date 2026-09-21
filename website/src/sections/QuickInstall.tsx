import { Terminal } from 'lucide-react';
import { Reveal } from '../motion';

/**
 * "Prefer the terminal?", the CLI is NOT publicly available yet, so this
 * section shows a preview of it rather than installation instructions.
 *
 * Nothing here is runnable and nothing is copyable: advertising
 * `pip install redforge` while the package is unpublished sends people to a
 * dead end. When the CLI ships, replace <CliPreview /> below with the real
 * install steps, the surrounding heading, copy and compatibility table are
 * already written for that future and need no changes.
 */

/** Commands the CLI will expose. Presentation only, see the note above. */
const PREVIEW_COMMANDS: { cmd: string; desc: string }[] = [
  { cmd: 'evaluate', desc: 'Run model evaluations' },
  { cmd: 'benchmark', desc: 'Benchmark a model' },
  { cmd: 'attack', desc: 'Run security tests' },
  { cmd: 'report', desc: 'Generate reports' },
];

const COMPAT: { k: string; v: string }[] = [
  { k: 'Operating system', v: 'Windows · macOS · Linux' },
  { k: 'Python', v: '3.11+ (CLI only)' },
  { k: 'Runtime', v: 'Ollama, LM Studio, llama.cpp, vLLM' },
  { k: 'Node.js', v: 'Not required to run' },
];

/**
 * A silhouette of the CLI, deliberately low-contrast so it reads as something
 * on the way rather than something you can use. Exposed to assistive tech as a
 * single labelled image so a screen reader never dictates it as instructions.
 */
function CliPreview() {
  return (
    <figure
      role="img"
      aria-label="Preview of the RedForge command-line interface. The CLI is not available yet."
      className="glow-forge overflow-hidden rounded-xl border border-steel-800 bg-char/70"
    >
      {/* Title bar */}
      <div className="flex items-center gap-3 border-b border-steel-800 bg-ink/60 px-4 py-3 sm:px-5">
        <span aria-hidden className="flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-steel-600" />
          <span className="h-2.5 w-2.5 rounded-full bg-steel-600" />
          <span className="h-2.5 w-2.5 rounded-full bg-steel-600" />
        </span>
        <span className="label ml-auto flex items-center gap-2 text-steel-500">
          <span aria-hidden className="h-1.5 w-1.5 animate-ember-flicker rounded-full bg-forge" />
          RedForge CLI
        </span>
      </div>

      {/* Body */}
      <div className="relative px-4 py-6 font-mono sm:px-7 sm:py-8">
        <div className="blueprint-grid-fine pointer-events-none absolute inset-0 opacity-40" />
        <div className="relative space-y-5 text-[12px] leading-relaxed sm:text-[13.5px]">
          <p className="text-bone/70">
            <span className="select-none text-steel-500">$ </span>
            redforge
            <span
              aria-hidden
              className="ml-1.5 inline-block h-[1em] w-[0.5em] translate-y-[0.12em] animate-ember-flicker bg-forge/70"
            />
          </p>

          <p className="text-steel-400">Local AI engineering from your terminal.</p>

          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 sm:gap-x-6">
            {PREVIEW_COMMANDS.map((c) => (
              <div key={c.cmd} className="contents">
                <dt className="text-steel-200">
                  <span aria-hidden className="select-none text-forge/70">
                    &gt;{' '}
                  </span>
                  {c.cmd}
                </dt>
                <dd className="min-w-0 text-steel-500">{c.desc}</dd>
              </div>
            ))}
          </dl>

          <p className="label pt-1 text-steel-600">CLI preview</p>
        </div>
      </div>
    </figure>
  );
}

export function QuickInstall() {
  return (
    <section
      id="quickstart"
      aria-labelledby="quickstart-heading"
      className="relative overflow-hidden border-t border-steel-800 py-16 sm:py-20 lg:py-24"
    >
      <div className="blueprint-grid-fine pointer-events-none absolute inset-0 opacity-30" />
      <div className="relative mx-auto max-w-editorial px-6 sm:px-10">
        <Reveal delay={120}>
          <h2 id="quickstart-heading" className="display max-w-2xl text-5xl text-bone sm:text-6xl">
            Prefer the terminal<span className="text-forge">?</span>
          </h2>
        </Reveal>

        <Reveal delay={160}>
          <div className="mt-6 flex items-center gap-3">
            <Terminal size={13} className="text-forge" aria-hidden />
            <span className="label text-forge">CLI: Coming soon</span>
          </div>
        </Reveal>

        <Reveal delay={200}>
          <div className="mt-5 max-w-xl space-y-3 text-[15px] leading-relaxed">
            <p className="text-bone">RedForge CLI is coming soon.</p>
            <p className="text-steel-300">
              Run evaluations, benchmarks, and workflows from the terminal, without opening the
              desktop app.
            </p>
            <p className="text-steel-400">
              Until then,{' '}
              <a
                href="#download"
                className="text-bone underline decoration-forge/40 underline-offset-4 hover:decoration-forge"
              >
                download the app
              </a>
              . Local workflows run on your machine.
            </p>
          </div>
        </Reveal>

        <Reveal delay={240} y={40}>
          <div className="mt-8 sm:mt-10">
            <CliPreview />
          </div>
        </Reveal>

        <Reveal delay={120}>
          <div className="mt-10 rounded-lg border border-steel-800 bg-char/30 p-6">
            <h3 className="text-sm font-medium text-bone">CLI compatibility</h3>
            <dl className="mt-4 grid gap-2.5 sm:grid-cols-2 sm:gap-x-10">
              {COMPAT.map((r) => (
                <div key={r.k} className="flex items-baseline justify-between gap-4">
                  <dt className="text-[13px] text-steel-400">{r.k}</dt>
                  <dd className="text-right text-[13px] text-bone">{r.v}</dd>
                </div>
              ))}
            </dl>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
