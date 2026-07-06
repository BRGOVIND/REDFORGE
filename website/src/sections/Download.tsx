import { useEffect, useState } from 'react';
import { ArrowUpRight, BookOpen, Download as DownloadIcon, Github, Map, Terminal } from 'lucide-react';
import { Reveal } from '../motion';
import { SectionLabel } from '../components/marks';

const RELEASES = 'https://github.com/BRGOVIND/REDFORGE/releases/latest';
const REPO = 'https://github.com/BRGOVIND/REDFORGE';

type OS = 'windows' | 'linux' | 'mac' | 'other';

function detectOS(): OS {
  if (typeof navigator === 'undefined') return 'other';
  const s = `${navigator.userAgent} ${navigator.platform}`.toLowerCase();
  if (s.includes('win')) return 'windows';
  if (s.includes('mac')) return 'mac';
  if (s.includes('linux') || s.includes('x11')) return 'linux';
  return 'other';
}

const PRIMARY: Record<OS, { label: string; sub: string }> = {
  windows: { label: 'Download for Windows', sub: 'Installer (.exe) · Python 3.11+ & Ollama' },
  linux: { label: 'Download for Linux', sub: 'AppImage · Python 3.11+ & Ollama' },
  mac: { label: 'Download for macOS', sub: 'Archive (.tar.gz) · Python 3.11+ & Ollama' },
  other: { label: 'Download RedForge', sub: 'Choose your platform on the releases page' },
};

const LINKS = [
  { icon: Github, k: 'GitHub', v: 'Clone the source, star the repo, open a pull request.', href: REPO },
  { icon: BookOpen, k: 'Documentation', v: 'Installation, quick start, troubleshooting.', href: `${REPO}#readme` },
  { icon: Map, k: 'Roadmap', v: 'Where RedForge is going — and how to shape it.', href: REPO },
];

export function Download() {
  const [os, setOs] = useState<OS>('other');
  useEffect(() => setOs(detectOS()), []);
  const primary = PRIMARY[os];

  return (
    <section id="download" className="relative border-t border-steel-800 py-32 sm:py-44">
      <div className="mx-auto max-w-editorial px-6 sm:px-10">
        <div className="grid grid-cols-1 gap-16 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <Reveal>
              <SectionLabel index="10">Download</SectionLabel>
            </Reveal>
            <Reveal delay={120}>
              <h2 className="display mt-8 text-6xl text-bone sm:text-7xl">
                Forge it<br />yourself.
              </h2>
            </Reveal>

            {/* OS-detected primary download */}
            <Reveal delay={220}>
              <a
                href={RELEASES}
                target="_blank"
                rel="noreferrer"
                className="focus-ring group mt-8 flex items-center gap-4 rounded-xl border border-forge/40 bg-forge/10 px-5 py-4 transition-colors hover:bg-forge/20"
              >
                <DownloadIcon size={22} className="shrink-0 text-forge" />
                <div className="flex-1">
                  <div className="display text-lg text-bone">{primary.label}</div>
                  <div className="text-xs text-steel-300">{primary.sub}</div>
                </div>
                <ArrowUpRight size={18} className="text-forge transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
              </a>
            </Reveal>

            <Reveal delay={300}>
              <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-steel-400">
                <a href={RELEASES} target="_blank" rel="noreferrer" className="hover:text-bone focus-ring">Windows</a>
                <a href={RELEASES} target="_blank" rel="noreferrer" className="hover:text-bone focus-ring">Linux AppImage</a>
                <a href={RELEASES} target="_blank" rel="noreferrer" className="hover:text-bone focus-ring">macOS</a>
                <a href={REPO} target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-bone focus-ring">
                  <Terminal size={12} /> Developer (git clone)
                </a>
              </div>
            </Reveal>

            <Reveal delay={360}>
              <div className="mt-8 max-w-sm rounded-lg border border-steel-700 bg-char/60 p-4 font-mono text-[13px] leading-relaxed text-steel-300">
                <span className="text-steel-500"># install once, then:</span>
                <br />
                <span className="text-steel-500">$ </span>redforge start
                <br />
                <span className="text-forge">→ </span>browser opens · no Node.js needed
              </div>
            </Reveal>
          </div>

          <div className="lg:col-span-7">
            {LINKS.map((l, i) => {
              const Icon = l.icon;
              return (
                <Reveal key={l.k} delay={i * 110}>
                  <a
                    href={l.href}
                    target="_blank"
                    rel="noreferrer"
                    className="focus-ring group flex items-center gap-6 border-t border-steel-800 py-8 transition-all duration-500 ease-forge last:border-b hover:pl-4"
                  >
                    <Icon size={22} className="shrink-0 text-steel-400 transition-colors group-hover:text-forge" />
                    <div className="flex-1">
                      <h3 className="display text-2xl text-bone sm:text-3xl">{l.k}</h3>
                      <p className="mt-1 text-[14px] text-steel-400">{l.v}</p>
                    </div>
                    <ArrowUpRight
                      size={22}
                      className="shrink-0 text-steel-500 transition-all duration-500 ease-forge group-hover:-translate-y-1 group-hover:translate-x-1 group-hover:text-forge"
                    />
                  </a>
                </Reveal>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
