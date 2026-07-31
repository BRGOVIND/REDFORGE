import { useEffect, useState } from 'react';
import {
  ArrowUpRight,
  Check,
  ChevronDown,
  Cpu,
  Download as DownloadIcon,
  FileCheck2,
  Github,
  ScrollText,
} from 'lucide-react';
import { Reveal } from '../motion';
import {
  ALL_RELEASES_URL,
  REPO,
  detectOS,
  formatSize,
  otherDownloads,
  primaryFor,
  useLatestRelease,
  type OS,
} from '../config/downloads';

// The desktop app bundles its own backend — Python is NOT a requirement any more.
const REQUIREMENTS = [
  'Windows 10+, macOS 12+, or Linux',
  '8 GB RAM (16 GB recommended)',
  '~2 GB disk for the app',
  'NVIDIA GPU optional — for training',
];

export function Download() {
  const [os, setOs] = useState<OS>('other');
  const [showOther, setShowOther] = useState(false);
  const { release } = useLatestRelease();

  useEffect(() => {
    setOs(detectOS());
  }, []);

  const primary = primaryFor(os, release);
  const others = otherDownloads(release, primary);

  return (
    <section id="download" className="relative border-t border-steel-800 py-24 sm:py-32 lg:py-40">
      <div className="mx-auto max-w-editorial px-6 sm:px-10">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:gap-16">
          {/* Primary download */}
          <div className="lg:col-span-6">
            <Reveal delay={120}>
              <h2 className="display text-5xl text-bone sm:text-6xl lg:text-7xl">
                Forge it<br />yourself.
              </h2>
            </Reveal>
            <Reveal delay={200}>
              <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-steel-700 px-3 py-1">
                <span className="h-1.5 w-1.5 rounded-full bg-forge" />
                <span className="label text-steel-300">RedForge V{release.version}</span>
              </div>
            </Reveal>

            {/* OS-detected primary button */}
            <Reveal delay={280}>
              {primary ? (
                <a
                  href={primary.url}
                  download={primary.filename}
                  className="focus-ring group mt-8 flex w-full items-center gap-4 rounded-xl border border-forge/50 bg-forge/10 px-5 py-4 transition-all duration-300 ease-forge hover:border-forge/70 hover:bg-forge/20 sm:px-6 sm:py-5"
                  aria-label={`${primary.label} — ${primary.filename}`}
                >
                  <DownloadIcon size={22} className="shrink-0 text-forge" />
                  <div className="flex-1">
                    <div className="display text-lg text-bone sm:text-xl">{primary.label}</div>
                    <div className="mt-0.5 text-xs text-steel-300">
                      {primary.note} · v{release.version}
                      {primary.size ? ` · ${formatSize(primary.size)}` : ''}
                    </div>
                  </div>
                  <ArrowUpRight size={18} className="shrink-0 text-forge transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                </a>
              ) : (
                <button
                  onClick={() => setShowOther(true)}
                  className="focus-ring group mt-8 flex w-full items-center gap-4 rounded-xl border border-forge/50 bg-forge/10 px-5 py-4 text-left transition-all duration-300 ease-forge hover:border-forge/70 hover:bg-forge/20 sm:px-6 sm:py-5"
                >
                  <DownloadIcon size={22} className="shrink-0 text-forge" />
                  <div className="flex-1">
                    <div className="display text-lg text-bone sm:text-xl">Download RedForge</div>
                    <div className="mt-0.5 text-xs text-steel-300">Choose your platform · v{release.version}</div>
                  </div>
                  <ChevronDown size={18} className="shrink-0 text-forge" />
                </button>
              )}
            </Reveal>

            {/* Other Downloads (expandable) */}
            <Reveal delay={340}>
              <button
                onClick={() => setShowOther((v) => !v)}
                aria-expanded={showOther}
                aria-controls="other-downloads"
                className="focus-ring mt-4 flex items-center gap-1.5 rounded text-[13px] text-steel-400 hover:text-bone"
              >
                Other downloads
                <ChevronDown size={14} className={`transition-transform ${showOther ? 'rotate-180' : ''}`} />
              </button>
              {showOther && (
                <ul id="other-downloads" className="mt-3 space-y-1 border-l border-steel-800 pl-4">
                  {others.map((a) => (
                    <li key={a.id}>
                      <a
                        href={a.url}
                        download={a.filename}
                        className="focus-ring group flex items-center justify-between gap-3 rounded py-1.5 text-[13px] text-steel-300 hover:text-bone"
                      >
                        <span>{a.label} <span className="text-steel-500">· {a.note}</span></span>
                        <span className="font-mono text-[11px] text-steel-500 group-hover:text-steel-300">
                          {formatSize(a.size) || a.filename}
                        </span>
                      </a>
                    </li>
                  ))}
                  <li>
                    <a
                      href={ALL_RELEASES_URL}
                      target="_blank"
                      rel="noreferrer"
                      className="focus-ring group flex items-center justify-between gap-3 rounded py-1.5 text-[13px] text-steel-300 hover:text-bone"
                    >
                      <span>All releases &amp; changelog</span>
                      <ArrowUpRight size={13} className="text-steel-500 group-hover:text-steel-300" />
                    </a>
                  </li>
                  <li>
                    <a
                      href={REPO}
                      target="_blank"
                      rel="noreferrer"
                      className="focus-ring group flex items-center justify-between gap-3 rounded py-1.5 text-[13px] text-steel-300 hover:text-bone"
                    >
                      <span className="flex items-center gap-1.5"><Github size={13} /> Source Code (GitHub)</span>
                      <ArrowUpRight size={13} className="text-steel-500 group-hover:text-steel-300" />
                    </a>
                  </li>
                </ul>
              )}
            </Reveal>

            {/* Install flow — no terminal required */}
            <Reveal delay={400}>
              <div className="mt-8 max-w-sm rounded-lg border border-steel-700 bg-char/60 p-4 text-[13px] leading-relaxed text-steel-300">
                <span className="label text-steel-500">Three steps</span>
                <ol className="mt-2 space-y-1">
                  <li><span className="text-forge">1 </span>Download the installer</li>
                  <li><span className="text-forge">2 </span>Install &amp; launch RedForge</li>
                  <li><span className="text-forge">3 </span>The backend starts itself</li>
                </ol>
                <p className="mt-3 text-[12px] text-steel-500">
                  No Python. No Node.js. No terminal.
                </p>
              </div>
            </Reveal>
          </div>

          {/* Requirements + secondary actions */}
          <div className="lg:col-span-6 lg:pt-16">
            <Reveal delay={160}>
              <div className="rounded-xl border border-steel-800 bg-char/40 p-6">
                <p className="label mb-4 flex items-center gap-2 text-steel-400">
                  <Cpu size={13} /> Requirements
                </p>
                <ul className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
                  {REQUIREMENTS.map((r) => (
                    <li key={r} className="flex items-center gap-2 text-[14px] text-steel-200">
                      <Check size={15} className="shrink-0 text-forge" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            </Reveal>

            {/* Secondary actions */}
            <div className="mt-8">
              <Reveal>
                <a href={release.checksumsUrl} className="focus-ring group flex items-center gap-4 border-t border-steel-800 py-6 transition-all duration-500 ease-forge hover:pl-3">
                  <FileCheck2 size={20} className="shrink-0 text-steel-400 group-hover:text-forge" />
                  <div className="flex-1">
                    <h3 className="display text-lg text-bone">Verify Download</h3>
                    <p className="text-[13px] text-steel-400">SHA-256 checksums</p>
                  </div>
                  <ArrowUpRight size={18} className="text-steel-500 transition-all duration-500 ease-forge group-hover:-translate-y-1 group-hover:translate-x-1 group-hover:text-forge" />
                </a>
              </Reveal>
              <Reveal>
                <a href={release.notesUrl} target="_blank" rel="noreferrer" className="focus-ring group flex items-center gap-4 border-t border-steel-800 py-6 transition-all duration-500 ease-forge hover:pl-3">
                  <ScrollText size={20} className="shrink-0 text-steel-400 group-hover:text-forge" />
                  <div className="flex-1">
                    <h3 className="display text-lg text-bone">View Release Notes</h3>
                    <p className="text-[13px] text-steel-400">What's new in v{release.version}</p>
                  </div>
                  <ArrowUpRight size={18} className="text-steel-500 transition-all duration-500 ease-forge group-hover:-translate-y-1 group-hover:translate-x-1 group-hover:text-forge" />
                </a>
              </Reveal>
              <Reveal>
                <a href={REPO} target="_blank" rel="noreferrer" className="focus-ring group flex items-center gap-4 border-t border-b border-steel-800 py-6 transition-all duration-500 ease-forge hover:pl-3">
                  <Github size={20} className="shrink-0 text-steel-400 group-hover:text-forge" />
                  <div className="flex-1">
                    <h3 className="display text-lg text-bone">View Source</h3>
                    <p className="text-[13px] text-steel-400">Star, fork, and contribute on GitHub</p>
                  </div>
                  <ArrowUpRight size={18} className="text-steel-500 transition-all duration-500 ease-forge group-hover:-translate-y-1 group-hover:translate-x-1 group-hover:text-forge" />
                </a>
              </Reveal>
              <p className="mt-4 text-[11px] text-steel-600">
                Files served from <span className="font-mono">GitHub Releases</span>.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
