/**
 * Typed access to the RedForge desktop shell.
 *
 * The Electron preload exposes `window.redforge`. In a plain browser it is simply
 * absent, so every helper here degrades to null/no-op and callers can render
 * desktop-only affordances behind `isDesktop()` without branching on `any`.
 */

export type UpdateChannel = 'stable' | 'beta' | 'nightly';

export interface DesktopLocations {
  home: string;
  cache: string;
  downloads: string;
  models: string;
  datasets: string;
  logs: string;
}

export interface DesktopAppInfo {
  version: string;
  electron: string;
  node: string;
  chrome: string;
  platform: string;
  arch: string;
  portable: boolean;
  locations: DesktopLocations;
  channel: UpdateChannel;
}

export interface UpdateStatus {
  state: 'idle' | 'checking' | 'available' | 'downloading' | 'ready' | 'none' | 'error';
  channel: UpdateChannel;
  autoCheck: boolean;
  currentVersion: string;
  info: { version?: string; releaseDate?: string } | null;
  error: string | null;
  supported: boolean;
}

export interface UpdateEvent {
  event: 'checking' | 'none' | 'available' | 'progress' | 'downloaded' | 'error';
  channel: UpdateChannel;
  version?: string;
  percent?: number;
  message?: string;
}

interface DesktopBridge {
  isDesktop: true;
  appInfo(): Promise<DesktopAppInfo>;
  diagnostics(): Promise<string>;
  copyDiagnostics(): Promise<boolean>;
  openPath(target: string): Promise<string>;
  chooseDirectory(opts?: { title?: string; defaultPath?: string }): Promise<string | null>;
  backend: {
    status(): Promise<{ status: string; url: string }>;
    restart(): Promise<void>;
    onStatus(cb: (d: unknown) => void): () => void;
    onHealth(cb: (d: { online: boolean }) => void): () => void;
  };
  update: {
    status(): Promise<UpdateStatus | null>;
    check(): Promise<unknown>;
    install(): Promise<void>;
    setChannel(channel: UpdateChannel): Promise<UpdateChannel>;
    setAutoCheck(on: boolean): Promise<boolean>;
    onEvent(cb: (e: UpdateEvent) => void): () => void;
  };
  onOpenFile(cb: (d: { path: string }) => void): () => void;
  onSplashStatus(cb: (d: unknown) => void): () => void;
}

declare global {
  interface Window {
    redforge?: DesktopBridge;
  }
}

export function desktop(): DesktopBridge | null {
  return typeof window !== 'undefined' && window.redforge ? window.redforge : null;
}

export function isDesktop(): boolean {
  return desktop() !== null;
}
