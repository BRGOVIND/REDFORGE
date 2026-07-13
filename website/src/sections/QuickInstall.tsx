import { useState } from 'react';
import { Check, Copy, Terminal } from 'lucide-react';
import { Reveal } from '../motion';

const COMMANDS: { cmd: string; note: string }[] = [
  { cmd: 'pip install redforge', note: 'Get the CLI (Python 3.11+).' },
  { cmd: 'redforge install', note: 'Sets up the runtime and dependencies.' },
  { cmd: 'redforge start', note: 'Launches RedForge and opens your browser.' },
];

const COMPAT: { k: string; v: string }[] = [
  { k: 'Operating system', v: 'Windows · macOS · Linux' },
  { k: 'Python', v: '3.11 or newer' },
  { k: 'Runtime', v: 'Ollama, LM Studio, llama.cpp, vLLM' },
  { k: 'Node.js', v: 'Not required to run' },
];

const CLI: { cmd: string; v: string }[] = [
  { cmd: 'redforge doctor', v: 'Check your system' },
  { cmd: 'redforge models', v: 'List installed models' },
  { cmd: 'redforge evaluate <model>', v: 'Run an evaluation' },
  { cmd: 'redforge diagnose', v: 'Write a support bundle' },
  { cmd: 'redforge update', v: 'Update to the latest release' },
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard unavailable — non-fatal */
    }
  };
  return (
    <button
      type="button"
      onClick={onCopy}
      aria-label={copied ? 'Copied' : `Copy command: ${text}`}
      className="shrink-0 rounded-md border border-steel-800 bg-char/60 p-2 text-steel-400 transition-colors hover:border-forge/40 hover:text-forge focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forge"
    >
      {copied ? <Check size={15} aria-hidden /> : <Copy size={15} aria-hidden />}
    </button>
  );
}

export function QuickInstall() {
  return (
    <section
      id="quickstart"
      aria-labelledby="quickstart-heading"
      className="relative overflow-hidden border-t border-steel-800 py-24 sm:py-32 lg:py-40"
    >
      <div className="blueprint-grid-fine pointer-events-none absolute inset-0 opacity-30" />
      <div className="relative mx-auto max-w-editorial px-6 sm:px-10">
        <Reveal delay={120}>
          <h2 id="quickstart-heading" className="display max-w-2xl text-5xl text-bone sm:text-6xl">
            Install in 60 seconds<span className="text-forge">.</span>
          </h2>
        </Reveal>
        <Reveal delay={160}>
          <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-steel-300">
            Three commands. Everything runs on your machine — no cloud, no API keys.
          </p>
        </Reveal>

        {/* The three commands */}
        <ol className="mt-12 space-y-3">
          {COMMANDS.map((c, i) => (
            <Reveal key={c.cmd} delay={i * 90}>
              <li className="flex items-center gap-4 rounded-lg border border-steel-800 bg-char/40 px-4 py-3.5 sm:px-5">
                <span
                  aria-hidden
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-forge/40 font-mono text-[13px] text-forge"
                >
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <code className="block break-all font-mono text-[15px] text-bone sm:text-base">
                    <span className="select-none text-steel-500">$ </span>
                    {c.cmd}
                  </code>
                  <p className="mt-1 text-[13px] text-steel-400">{c.note}</p>
                </div>
                <CopyButton text={c.cmd} />
              </li>
            </Reveal>
          ))}
        </ol>

        {/* Compatibility + CLI reference */}
        <div className="mt-14 grid gap-6 sm:grid-cols-2">
          <Reveal>
            <div className="h-full rounded-lg border border-steel-800 bg-char/30 p-6">
              <h3 className="label text-steel-400">Compatibility</h3>
              <dl className="mt-4 space-y-2.5">
                {COMPAT.map((r) => (
                  <div key={r.k} className="flex items-baseline justify-between gap-4">
                    <dt className="text-[13px] text-steel-400">{r.k}</dt>
                    <dd className="text-right text-[13px] text-bone">{r.v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </Reveal>
          <Reveal delay={90}>
            <div className="h-full rounded-lg border border-steel-800 bg-char/30 p-6">
              <h3 className="label flex items-center gap-2 text-steel-400">
                <Terminal size={13} aria-hidden /> CLI reference
              </h3>
              <dl className="mt-4 space-y-2.5">
                {CLI.map((r) => (
                  <div key={r.cmd} className="flex items-baseline justify-between gap-4">
                    <dt className="font-mono text-[12.5px] text-bone">{r.cmd}</dt>
                    <dd className="text-right text-[12.5px] text-steel-400">{r.v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
