import { Download, Globe, Package, Play, Server, TerminalSquare } from 'lucide-react';
import { Reveal } from '../motion';
import { SectionLabel } from '../components/marks';

const STEPS = [
  { icon: Download, k: 'Download', v: 'Grab the release for your OS.', cmd: 'RedForge-Setup.exe / AppImage' },
  { icon: Package, k: 'Install', v: 'One command installs the Python side.', cmd: 'install.cmd  ·  ./install.sh' },
  { icon: Server, k: 'Start Ollama', v: 'Your models run locally through Ollama.', cmd: 'ollama serve' },
  { icon: TerminalSquare, k: 'Run RedForge', v: 'A single process — no Node.js.', cmd: 'redforge start' },
  { icon: Globe, k: 'Browser opens', v: 'Onboarding begins automatically.', cmd: 'localhost:8000' },
  { icon: Play, k: 'Run evaluation', v: 'Pick a model and a profile. Done.', cmd: '→ security report' },
];

export function InstallSteps() {
  return (
    <section id="install" className="relative overflow-hidden border-t border-steel-800 py-24 sm:py-32 lg:py-40">
      <div className="blueprint-grid-fine pointer-events-none absolute inset-0 opacity-30" />
      <div className="relative mx-auto max-w-editorial px-6 sm:px-10">
        <Reveal>
          <SectionLabel>Installation</SectionLabel>
        </Reveal>
        <Reveal delay={120}>
          <h2 className="display mt-8 max-w-2xl text-5xl text-bone sm:text-6xl">
            From download to first report<span className="text-forge">.</span>
          </h2>
        </Reveal>

        {/* Vertical drawn timeline */}
        <div className="relative mt-16 border-l border-steel-700 pl-8 sm:pl-10">
          <div
            className="absolute left-0 top-0 h-full w-px"
            style={{ background: 'linear-gradient(180deg, #FF7A45, #E5484D 50%, transparent)' }}
          />
          {STEPS.map((s, i) => {
            const Icon = s.icon;
            return (
              <Reveal key={s.k} delay={i * 90} className="relative pb-12 last:pb-0">
                <span className="absolute -left-[46px] flex h-8 w-8 items-center justify-center rounded-full border border-forge/40 bg-ink text-forge sm:-left-[54px]">
                  <Icon size={15} />
                </span>
                <h3 className="display text-2xl text-bone sm:text-3xl">{s.k}</h3>
                <p className="mt-2 max-w-md text-[15px] leading-relaxed text-steel-300">{s.v}</p>
                <code className="mt-2 inline-block rounded border border-steel-800 bg-char/60 px-2 py-1 font-mono text-[12px] text-steel-400">
                  {s.cmd}
                </code>
              </Reveal>
            );
          })}
        </div>

        <Reveal delay={120}>
          <p className="mt-14 text-center text-sm text-steel-400">
            Requires only <span className="text-bone">Python 3.11+</span> and{' '}
            <span className="text-bone">Ollama</span>. Node.js is never needed to run.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
