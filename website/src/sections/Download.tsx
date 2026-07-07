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
import { SectionLabel } from '../components/marks';
import {
  CHECKSUMS_URL,
  DOWNLOAD_BASE_URL,
  OTHER_DOWNLOADS,
  REPO,
  RELEASE_NOTES_URL,
  VERSION,
  primaryFor,
  type OS,
} from '../config/downloads';

function detectOS(): OS {
  if (typeof navigator === 'undefined') return 'other';
  const s = `${navigator.userAgent} ${navigator.platform}`.toLowerCase();
  if (s.includes('win')) return 'windows';
  if (s.includes('mac')) return 'mac';
  if (s.includes('linux') || s.includes('android') || s.includes('x11')) return 'linux';
  return 'other';
}

/** Best-effort check that an optional artifact is hosted; hide the UI if not. */
async function exists(url: string): Promise<boolean> {
  try {
    const res = await fetch(url, { method: 'HEAD' });
    return res.ok;
  } catch {
    return false;
  }
}

const REQUIREMENTS = ['Python 3.11+', 'Ollama', 'Windows / Linux / macOS', 'Local AI models'];

export function Download() {
  const [os, setOs] = useState<OS>('other');
  const [showOther, setShowOther] = useState(false);
  const [hasChecksums, setHasChecksums] = useState(false);
  const [hasNotes, setHasNotes] = useState(false);

  useEffect(() => {
    setOs(detectOS());
    void exists(CHECKSUMS_URL).then(setHasChecksums);
    void exists(RELEASE_NOTES_URL).then(setHasNotes);
  }, []);

  const primary = primaryFor(os);

  return (
    <section id="download" className="relative border-t border-steel-800 py-32 sm:py-44">
      <div className="mx-auto max-w-editorial px-6 sm:px-10">
        <div className="grid grid-cols-1 gap-16 lg:grid-cols-12">
          {/* Primary download */}
          <div className="lg:col-span-6">
            <Reveal>
              <SectionLabel index="10">Download</SectionLabel>
            </Reveal>
            <Reveal delay={120}>
              <h2 className="display mt-8 text-6xl text-bone sm:text-7xl">
                Forge it<br />yourself.
              </h2>
            </Reveal>
            <Reveal delay={200}>
              <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-steel-700 px-3 py-1">
                <span className="h-1.5 w-1.5 rounded-full bg-forge" />
                <span className="label text-steel-300">RedForge V{VERSION}</span>
              </div>
            </Reveal>

            {/* OS-detected primary button */}
            <Reveal delay={280}>
              {primary ? (
                <a
                  href={primary.asset.url}
                  download={primary.asset.filename}
                  className="focus-ring group mt-8 flex items-center gap-4 rounded-xl border border-forge/40 bg-forge/10 px-5 py-4 transition-colors hover:bg-forge/20"
                  aria-label={`${primary.label} — ${primary.asset.filename}`}
                >
                  <DownloadIcon size={22} className="shrink-0 text-forge" />
                  <div className="flex-1">
                    <div className="display text-lg text-bone">{primary.label}</div>
                    <div className="text-xs text-steel-300">{primary.sub}</div>
                  </div>
                  <ArrowUpRight size={18} className="text-forge transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                </a>
              ) : (
                <button
                  onClick={() => setShowOther(true)}
                  className="focus-ring group mt-8 flex w-full items-center gap-4 rounded-xl border border-forge/40 bg-forge/10 px-5 py-4 text-left transition-colors hover:bg-forge/20"
                >
                  <DownloadIcon size={22} className="shrink-0 text-forge" />
                  <div className="flex-1">
                    <div className="display text-lg text-bone">Download RedForge</div>
                    <div className="text-xs text-steel-300">Choose your platform · v{VERSION}</div>
                  </div>
                  <ChevronDown size={18} className="text-forge" />
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
                  {OTHER_DOWNLOADS.map((a) => (
                    <li key={a.id}>
                      <a
                        href={a.url}
                        download={a.filename}
                        className="focus-ring group flex items-center justify-between gap-3 rounded py-1.5 text-[13px] text-steel-300 hover:text-bone"
                      >
                        <span>{a.label}</span>
                        <span className="font-mono text-[11px] text-steel-500 group-hover:text-steel-300">{a.filename}</span>
                      </a>
                    </li>
                  ))}
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

            {/* Install snippet */}
            <Reveal delay={400}>
              <div className="mt-8 max-w-sm rounded-lg border border-steel-700 bg-char/60 p-4 font-mono text-[13px] leading-relaxed text-steel-300">
                <span className="text-steel-500"># install once, then:</span>
                <br />
                <span className="text-steel-500">$ </span>redforge start
                <br />
                <span className="text-forge">→ </span>browser opens · no Node.js needed
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
                <ul className="grid grid-cols-2 gap-x-6 gap-y-3">
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
              {hasChecksums && (
                <Reveal>
                  <a href={CHECKSUMS_URL} className="focus-ring group flex items-center gap-4 border-t border-steel-800 py-6 transition-all duration-500 ease-forge hover:pl-3">
                    <FileCheck2 size={20} className="shrink-0 text-steel-400 group-hover:text-forge" />
                    <div className="flex-1">
                      <h3 className="display text-lg text-bone">Verify Download</h3>
                      <p className="text-[13px] text-steel-400">SHA-256 checksums</p>
                    </div>
                    <ArrowUpRight size={18} className="text-steel-500 transition-all duration-500 ease-forge group-hover:-translate-y-1 group-hover:translate-x-1 group-hover:text-forge" />
                  </a>
                </Reveal>
              )}
              {hasNotes && (
                <Reveal>
                  <a href={RELEASE_NOTES_URL} className="focus-ring group flex items-center gap-4 border-t border-steel-800 py-6 transition-all duration-500 ease-forge hover:pl-3">
                    <ScrollText size={20} className="shrink-0 text-steel-400 group-hover:text-forge" />
                    <div className="flex-1">
                      <h3 className="display text-lg text-bone">View Release Notes</h3>
                      <p className="text-[13px] text-steel-400">What's new in v{VERSION}</p>
                    </div>
                    <ArrowUpRight size={18} className="text-steel-500 transition-all duration-500 ease-forge group-hover:-translate-y-1 group-hover:translate-x-1 group-hover:text-forge" />
                  </a>
                </Reveal>
              )}
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
                Files served from <span className="font-mono">{DOWNLOAD_BASE_URL}</span>.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
