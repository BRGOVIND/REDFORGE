/**
 * Download configuration — the single source of truth for the website's
 * distribution portal. Nothing here points at GitHub Releases; files are served
 * from a configurable base URL so the site is host-agnostic and version-aware.
 *
 * To point at a new host: set VITE_DOWNLOAD_BASE_URL at build time.
 * To ship a new version: bump the repo-root VERSION file — filenames follow.
 */

// Injected from the repo-root VERSION file at build time (see vite.config.ts).
declare const __APP_VERSION__: string;
export const VERSION: string =
  typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : '1.0.0';

// Where release artifacts are hosted. Defaults to a same-origin /downloads path;
// override with VITE_DOWNLOAD_BASE_URL (e.g. a CDN) without touching components.
const envBase = (import.meta.env as Record<string, string | undefined>)
  .VITE_DOWNLOAD_BASE_URL;
export const DOWNLOAD_BASE_URL: string = (envBase || '/downloads').replace(/\/$/, '');

// GitHub is secondary — "View Source", never the primary download destination.
export const REPO = 'https://github.com/BRGOVIND/REDFORGE';

export type OS = 'windows' | 'linux' | 'mac' | 'other';

export function assetUrl(filename: string): string {
  return `${DOWNLOAD_BASE_URL}/${filename}`;
}

export interface Asset {
  id: string;
  label: string;
  filename: string;
  url: string;
}

function asset(id: string, label: string, filename: string): Asset {
  return { id, label, filename, url: assetUrl(filename) };
}

/** Version-aware artifact names (match scripts/build_release.py + installers). */
export const ASSETS = {
  windowsInstaller: asset('win-exe', 'Windows Installer (.exe)', `RedForge-Setup-${VERSION}.exe`),
  windowsZip: asset('win-zip', 'Windows ZIP', `redforge-${VERSION}.zip`),
  linuxAppImage: asset('linux-appimage', 'Linux AppImage', `RedForge-${VERSION}-x86_64.AppImage`),
  linuxTarGz: asset('linux-tar', 'Linux / macOS (.tar.gz)', `redforge-${VERSION}.tar.gz`),
} as const;

/** The primary, OS-detected download. Returns null for unknown OS. */
export function primaryFor(os: OS): { asset: Asset; label: string; sub: string } | null {
  switch (os) {
    case 'windows':
      return { asset: ASSETS.windowsInstaller, label: 'Download for Windows', sub: `Installer · v${VERSION}` };
    case 'linux':
      return { asset: ASSETS.linuxAppImage, label: 'Download for Linux', sub: `AppImage · v${VERSION}` };
    case 'mac':
      return { asset: ASSETS.linuxTarGz, label: 'Download for macOS', sub: `Archive (.tar.gz) · v${VERSION}` };
    default:
      return null;
  }
}

/** Everything under "Other Downloads", including Source Code. */
export const OTHER_DOWNLOADS: Asset[] = [
  ASSETS.windowsInstaller,
  ASSETS.windowsZip,
  ASSETS.linuxAppImage,
  ASSETS.linuxTarGz,
];

// Optional artifacts detected at runtime (shown only if present on the host).
export const CHECKSUMS_URL = assetUrl('checksums.txt');
export const RELEASE_NOTES_URL = assetUrl('RELEASE_NOTES.md');
