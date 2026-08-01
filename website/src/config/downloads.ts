/**
 * Download configuration — the single source of truth for the distribution portal.
 *
 * Two layers, so the buttons are never wrong and never need a site rebuild:
 *
 *   1. **Static fallback** — filenames derived from the VERSION baked in at build
 *      time. Always renders instantly, works with JS disabled, and matches the
 *      artifactName patterns in `desktop/package.json` exactly.
 *   2. **Live resolution** — on mount we ask the GitHub Releases API for the
 *      *latest* release and swap in its real assets. Publishing a new release is
 *      therefore enough; the site follows automatically.
 *
 * If the API is unreachable or rate-limited, layer 1 stands and the "all releases"
 * link still gets the user there.
 */
import { useEffect, useState } from 'react';

// Injected from the repo-root VERSION file at build time (see vite.config.ts).
declare const __APP_VERSION__: string;
export const VERSION: string =
  typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : '2.0.0';

export const REPO = 'https://github.com/BRGOVIND/REDFORGE';
const OWNER_REPO = 'BRGOVIND/REDFORGE';
const API_LATEST = `https://api.github.com/repos/${OWNER_REPO}/releases/latest`;

/** Always-valid, zero-maintenance links (GitHub resolves "latest" server-side). */
export const LATEST_RELEASE_URL = `${REPO}/releases/latest`;
export const ALL_RELEASES_URL = `${REPO}/releases`;

export type OS = 'windows' | 'linux' | 'mac' | 'other';

export interface Asset {
  id: string;
  label: string;
  /** Short platform note shown under the primary button. */
  note: string;
  filename: string;
  url: string;
  size?: number;
}

/**
 * How to recognise each artifact in a release, in priority order.
 * These mirror `desktop/package.json` → build.*.artifactName.
 */
const PATTERNS: { id: string; label: string; note: string; os: OS; test: RegExp }[] = [
  { id: 'win-setup',     label: 'Download for Windows', note: 'Installer (.exe)',      os: 'windows', test: /-Setup\.exe$/i },
  { id: 'win-portable',  label: 'Windows Portable',     note: 'No install (.zip)',     os: 'windows', test: /-Portable\.zip$/i },
  { id: 'mac-arm64',     label: 'Download for macOS',   note: 'Apple Silicon (.dmg)',  os: 'mac',     test: /-arm64\.dmg$/i },
  { id: 'mac-x64',       label: 'macOS (Intel)',        note: 'Intel (.dmg)',          os: 'mac',     test: /-x64\.dmg$/i },
  { id: 'linux-appimage',label: 'Download for Linux',   note: 'AppImage',              os: 'linux',   test: /\.AppImage$/i },
  { id: 'linux-deb',     label: 'Linux (.deb)',         note: 'Debian / Ubuntu',       os: 'linux',   test: /\.deb$/i },
];

function staticUrl(version: string, filename: string): string {
  return `${REPO}/releases/download/v${version}/${filename}`;
}

/** Filenames the release pipeline is guaranteed to publish for a given version. */
function staticFilename(id: string, version: string): string {
  switch (id) {
    case 'win-setup':      return `RedForge-v${version}-Setup.exe`;
    case 'win-portable':   return `RedForge-v${version}-Portable.zip`;
    case 'mac-arm64':      return `RedForge-v${version}-arm64.dmg`;
    case 'mac-x64':        return `RedForge-v${version}-x64.dmg`;
    // AppImage uses x86_64, deb uses amd64 (electron-builder's per-target
    // arch convention). These must match scripts/artifact_names.py.
    case 'linux-appimage': return `RedForge-v${version}-x86_64.AppImage`;
    case 'linux-deb':      return `RedForge-v${version}-amd64.deb`;
    default:               return '';
  }
}

export interface Release {
  version: string;
  assets: Asset[];
  notesUrl: string;
  checksumsUrl: string;
  /** Where the data came from — 'static' means the live lookup hasn't landed. */
  source: 'static' | 'github';
}

/** The build-time fallback release. Rendered immediately, before any network. */
export function staticRelease(version = VERSION): Release {
  const assets = PATTERNS.map(({ id, label, note }) => {
    const filename = staticFilename(id, version);
    return { id, label, note, filename, url: staticUrl(version, filename) };
  });
  return {
    version,
    assets,
    notesUrl: `${REPO}/releases/tag/v${version}`,
    checksumsUrl: staticUrl(version, 'SHA256SUMS.txt'),
    source: 'static',
  };
}

interface GitHubAsset { name: string; browser_download_url: string; size: number }
interface GitHubRelease { tag_name: string; html_url: string; assets: GitHubAsset[] }

/** Ask GitHub for the newest published release and map its assets to our slots. */
export async function fetchLatestRelease(signal?: AbortSignal): Promise<Release | null> {
  try {
    const res = await fetch(API_LATEST, {
      signal,
      headers: { Accept: 'application/vnd.github+json' },
    });
    if (!res.ok) return null;
    const data: GitHubRelease = await res.json();
    const version = (data.tag_name || '').replace(/^v/, '');
    if (!version) return null;

    const assets: Asset[] = [];
    for (const { id, label, note, test } of PATTERNS) {
      const hit = data.assets.find((a) => test.test(a.name));
      if (hit) {
        assets.push({ id, label, note, filename: hit.name, url: hit.browser_download_url, size: hit.size });
      }
    }
    // A release with no recognisable installers is not useful — keep the fallback.
    if (assets.length === 0) return null;

    const sums = data.assets.find((a) => /^SHA256SUMS/i.test(a.name));
    return {
      version,
      assets,
      notesUrl: data.html_url,
      checksumsUrl: sums ? sums.browser_download_url : staticUrl(version, 'SHA256SUMS.txt'),
      source: 'github',
    };
  } catch {
    return null; // offline, rate-limited, or blocked — the fallback stands
  }
}

const CACHE_KEY = 'redforge_latest_release';

/**
 * The release to render. Starts with the static fallback so there is never a
 * loading state on the download button, then upgrades to live data.
 */
export function useLatestRelease(): { release: Release; live: boolean } {
  const [release, setRelease] = useState<Release>(() => {
    // A cached lookup from earlier in the session avoids a second API call.
    try {
      const raw = sessionStorage.getItem(CACHE_KEY);
      if (raw) return JSON.parse(raw) as Release;
    } catch { /* ignore */ }
    return staticRelease();
  });

  useEffect(() => {
    const controller = new AbortController();
    fetchLatestRelease(controller.signal).then((latest) => {
      if (!latest) return;
      setRelease(latest);
      try {
        sessionStorage.setItem(CACHE_KEY, JSON.stringify(latest));
      } catch { /* storage disabled — not fatal */ }
    });
    return () => controller.abort();
  }, []);

  return { release, live: release.source === 'github' };
}

export function detectOS(): OS {
  if (typeof navigator === 'undefined') return 'other';
  const s = `${navigator.userAgent} ${navigator.platform}`.toLowerCase();
  if (s.includes('win')) return 'windows';
  if (s.includes('mac')) return 'mac';
  if (s.includes('linux') || s.includes('android') || s.includes('x11')) return 'linux';
  return 'other';
}

/** The one asset to feature for a platform (Apple Silicon is the mac default). */
export function primaryFor(os: OS, release: Release): Asset | null {
  const pick = (id: string) => release.assets.find((a) => a.id === id) ?? null;
  switch (os) {
    case 'windows': return pick('win-setup') ?? pick('win-portable');
    case 'mac':     return pick('mac-arm64') ?? pick('mac-x64');
    case 'linux':   return pick('linux-appimage') ?? pick('linux-deb');
    default:        return null;
  }
}

/** Everything else, for the "Other downloads" list. */
export function otherDownloads(release: Release, primary: Asset | null): Asset[] {
  return release.assets.filter((a) => a.id !== primary?.id);
}

export function formatSize(bytes?: number): string {
  if (!bytes) return '';
  return `${(bytes / 1024 / 1024).toFixed(0)} MB`;
}
