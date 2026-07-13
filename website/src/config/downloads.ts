/**
 * Download configuration — the single source of truth for the website's
 * distribution portal. Assets are served directly from the **official GitHub
 * Release** for this version's tag (`v<VERSION>`) — never proxied through Vercel.
 * The release workflow uploads exactly the filenames below, so the buttons match
 * the published assets 1:1.
 *
 * To mirror on a CDN: set VITE_DOWNLOAD_BASE_URL at build time.
 * To ship a new version: bump the repo-root VERSION file — tag + filenames follow.
 */

// Injected from the repo-root VERSION file at build time (see vite.config.ts).
declare const __APP_VERSION__: string;
export const VERSION: string =
  typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : '1.0.0';

// Repository + release host.
export const REPO = 'https://github.com/BRGOVIND/REDFORGE';

// Assets are downloaded straight from the GitHub Release for tag v<VERSION>.
// Override with VITE_DOWNLOAD_BASE_URL (e.g. a CDN mirror) without touching components.
const envBase = (import.meta.env as Record<string, string | undefined>)
  .VITE_DOWNLOAD_BASE_URL;
export const DOWNLOAD_BASE_URL: string = (
  envBase || `${REPO}/releases/download/v${VERSION}`
).replace(/\/$/, '');

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

/**
 * The asset offered as the primary Windows download.
 *
 * A signed `RedForge-Setup-<VERSION>.exe` installer has not been built yet, so we
 * ship the verified ZIP as the primary download. The installer remains fully
 * defined (see ASSETS.windowsInstaller / OTHER_DOWNLOADS) — once the real
 * installer exists, switch this one line back to `ASSETS.windowsInstaller`.
 */
export const WINDOWS_PRIMARY: Asset = ASSETS.windowsZip;

/** The primary, OS-detected download. Returns null for unknown OS. */
export function primaryFor(os: OS): { asset: Asset; label: string; sub: string } | null {
  switch (os) {
    case 'windows': {
      const isInstaller = WINDOWS_PRIMARY === ASSETS.windowsInstaller;
      return {
        asset: WINDOWS_PRIMARY,
        label: 'Download for Windows',
        sub: `${isInstaller ? 'Installer' : 'ZIP'} · v${VERSION}`,
      };
    }
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

// SHA-256 checksums are a release asset; release notes are the Release page body.
export const CHECKSUMS_URL = assetUrl('SHA256SUMS.txt');
export const RELEASE_NOTES_URL = `${REPO}/releases/tag/v${VERSION}`;
