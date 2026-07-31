import { Cpu, Download, Package, Play, Server, Sparkles } from 'lucide-react';
import { Reveal } from '../motion';

const STEPS = [
  { icon: Download, k: 'Download', v: 'One installer for your platform. Nothing to configure.', cmd: 'Setup.exe · .dmg · .AppImage' },
  { icon: Package, k: 'Install', v: 'A normal desktop install — shortcuts, Start menu, uninstaller.', cmd: 'double-click' },
  { icon: Server, k: 'Launch', v: 'RedForge starts its own backend. No Python, no terminal.', cmd: 'automatic' },
  { icon: Cpu, k: 'Hardware detected', v: 'GPU, VRAM and installed runtimes are found for you.', cmd: 'first-run wizard' },
  { icon: Sparkles, k: 'Get a model', v: 'Pick one from the built-in Model Hub and download it in a click.', cmd: 'Model Hub' },
  { icon: Play, k: 'Start working', v: 'Chat, benchmark, evaluate, or fine-tune. Done.', cmd: '→ first result' },
];

export function InstallSteps() {
  return (
    <section id="install" className="relative overflow-hidden border-t border-steel-800 py-24 sm:py-32 lg:py-40">
      <div className="blueprint-grid-fine pointer-events-none absolute inset-0 opacity-30" />
      <div className="relative mx-auto max-w-editorial px-6 sm:px-10">
        <Reveal delay={120}>
          <h2 className="display max-w-2xl text-5xl text-bone sm:text-6xl">
            From download to first report<span className="text-forge">.</span>
          </h2>
        </Reveal>

        {/* Vertical drawn timeline */}
        <div className="relative mt-16 border-l border-steel-700 pl-8 sm:pl-10">
          <div
            className="absolute left-0 top-0 h-full w-px"
            style={{ background: 'linear-gradient(180deg, #D12A2A, #A11212 50%, transparent)' }}
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
            The backend is <span className="text-bone">bundled</span> — no Python, no Node.js, no
            terminal. A local runtime (<span className="text-bone">Ollama</span>, LM Studio,
            llama.cpp, or vLLM) is only needed to run models, and RedForge helps you install one.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
