import { useEffect, useState } from 'react';
import { Copy, Download, ExternalLink, FolderOpen, RefreshCw } from 'lucide-react';
import { Badge, Button } from './ui';
import { DependencyPanel } from './DependencyPanel';
import { errorMessage } from '../api/client';
import { toast } from '../lib/toast';
import * as api from '../api/endpoints';
import {
  desktop,
  isDesktop,
  type DesktopAppInfo,
  type UpdateChannel,
  type UpdateStatus,
} from '../lib/desktop';

const REPO = 'https://github.com/BRGOVIND/REDFORGE';

const CHANNELS: { key: UpdateChannel; label: string; blurb: string }[] = [
  { key: 'stable', label: 'Stable', blurb: 'Tested releases only. Recommended.' },
  { key: 'beta', label: 'Beta', blurb: 'Release candidates, ahead of stable.' },
  { key: 'nightly', label: 'Nightly', blurb: 'Every build. Expect rough edges.' },
];

function Row({ label, value, action }: { label: string; value: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border py-2.5 last:border-0">
      <span className="text-[12px] text-content-muted">{label}</span>
      <div className="flex min-w-0 items-center gap-2">
        <span className="truncate font-mono text-[11px] text-content" title={value}>{value}</span>
        {action}
      </div>
    </div>
  );
}

/**
 * Settings → About. The version lives in three places by design (window title,
 * native About dialog, and here); this is the one a user can actually copy from
 * when filing a bug, so it doubles as the diagnostics entry point.
 *
 * Update controls only render inside the desktop shell — in a browser there is
 * nothing to update, and showing dead switches would be worse than hiding them.
 */
export function AboutPanel() {
  const [version, setVersion] = useState<string>('');
  const [python, setPython] = useState<string>('');
  const [platform, setPlatform] = useState<string>('');
  const [info, setInfo] = useState<DesktopAppInfo | null>(null);
  const [update, setUpdate] = useState<UpdateStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const bridge = desktop();

  useEffect(() => {
    api.getSystemVersion()
      .then((v) => { setVersion(v.version); setPython(v.python); setPlatform(v.platform); })
      .catch((e) => toast.error('Could not read the version', errorMessage(e)));

    if (bridge) {
      bridge.appInfo().then(setInfo).catch(() => {});
      bridge.update.status().then(setUpdate).catch(() => {});
      return bridge.update.onEvent((e) => {
        if (e.event === 'downloaded') toast.success('Update ready', `Version ${e.version} will install on restart.`);
        if (e.event === 'error') toast.error('Update failed', e.message ?? 'Unknown error');
        bridge.update.status().then(setUpdate).catch(() => {});
      });
    }
  }, [bridge]);

  const checkNow = async () => {
    if (!bridge) return;
    setChecking(true);
    try {
      await bridge.update.check();
      setUpdate(await bridge.update.status());
    } catch (e) {
      toast.error('Could not check for updates', errorMessage(e));
    } finally {
      setChecking(false);
    }
  };

  const setChannel = async (channel: UpdateChannel) => {
    if (!bridge) return;
    try {
      await bridge.update.setChannel(channel);
      setUpdate(await bridge.update.status());
      toast.success(`Switched to the ${channel} channel`);
    } catch (e) {
      toast.error('Could not change channel', errorMessage(e));
    }
  };

  const copyDiagnostics = async () => {
    try {
      if (bridge) {
        await bridge.copyDiagnostics();
      } else {
        await navigator.clipboard.writeText(
          `RedForge ${version}\nPlatform: ${platform}\nPython: ${python}\nUser agent: ${navigator.userAgent}`
        );
      }
      toast.success('Diagnostics copied', 'Paste it into a bug report.');
    } catch (e) {
      toast.error('Could not copy diagnostics', errorMessage(e));
    }
  };

  return (
    <div>
      {/* --- version ------------------------------------------------------ */}
      <section className="rf-card p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-content">About RedForge</h2>
            <p className="mt-0.5 text-[11px] text-content-subtle">
              The local AI engineering platform.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone="neutral">v{version || '—'}</Badge>
            {info?.portable && <Badge tone="amber" title="All data is stored beside the executable">portable</Badge>}
            {!isDesktop() && <Badge tone="grey" title="Running in a browser, not the desktop app">browser</Badge>}
          </div>
        </div>

        <div className="mt-4">
          <Row label="Version" value={version || '—'} />
          <Row label="Platform" value={info ? `${info.platform} ${info.arch}` : platform || '—'} />
          {python && <Row label="Python" value={python} />}
          {info && <Row label="Electron" value={`${info.electron} · Chromium ${info.chrome}`} />}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="ghost" size="sm" onClick={copyDiagnostics}>
            <Copy size={13} /> Copy diagnostics
          </Button>
          <a href={`${REPO}/releases`} target="_blank" rel="noreferrer">
            <Button variant="ghost" size="sm">
              <ExternalLink size={13} /> Release notes
            </Button>
          </a>
          <a href={`${REPO}/issues/new/choose`} target="_blank" rel="noreferrer">
            <Button variant="ghost" size="sm">
              <ExternalLink size={13} /> Report an issue
            </Button>
          </a>
        </div>
      </section>

      {/* --- updates (desktop only) --------------------------------------- */}
      {bridge && (
        <section className="rf-card mt-4 p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-content">Updates</h2>
              <p className="mt-0.5 text-[11px] text-content-subtle">
                {update?.supported
                  ? 'RedForge checks for updates automatically and installs them on restart.'
                  : 'This build does not support automatic updates.'}
              </p>
            </div>
            <Button size="sm" variant="ghost" onClick={checkNow} loading={checking}>
              <RefreshCw size={13} /> Check now
            </Button>
          </div>

          {update?.state === 'available' && update.info?.version && (
            <p className="mt-3 rounded-lg border border-border bg-base px-3 py-2 text-[12px] text-content">
              <Download size={12} className="mr-1.5 inline text-red-400" />
              Version {update.info.version} is downloading…
            </p>
          )}
          {update?.state === 'ready' && (
            <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-border bg-base px-3 py-2">
              <span className="text-[12px] text-content">
                Version {update.info?.version} is ready to install.
              </span>
              <Button size="sm" onClick={() => bridge.update.install()}>Restart &amp; update</Button>
            </div>
          )}
          {update?.state === 'none' && (
            <p className="mt-3 text-[12px] text-content-subtle">You are on the latest {update.channel} release.</p>
          )}
          {update?.error && <p className="mt-3 text-[12px] text-fail">{update.error}</p>}

          <p className="mt-5 text-[11px] font-medium uppercase tracking-wide text-content-faint">Channel</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {CHANNELS.map((c) => {
              const active = (update?.channel ?? info?.channel ?? 'stable') === c.key;
              return (
                <button
                  key={c.key}
                  onClick={() => setChannel(c.key)}
                  className={`rounded-lg border p-3 text-left transition-colors rf-focus ${
                    active ? 'border-red-500/50 bg-red-soft' : 'border-border bg-base hover:border-border-strong'
                  }`}
                >
                  <span className="text-[12px] font-medium text-content">{c.label}</span>
                  <p className="mt-0.5 text-[10px] leading-relaxed text-content-subtle">{c.blurb}</p>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {/* --- locations (desktop only) ------------------------------------- */}
      {bridge && info && (
        <section className="rf-card mt-4 p-5">
          <h2 className="text-sm font-semibold text-content">Locations</h2>
          <p className="mt-0.5 text-[11px] text-content-subtle">
            {info.portable
              ? 'Portable mode — everything is stored beside the executable.'
              : 'Where RedForge keeps your workspace and downloads.'}
          </p>
          <div className="mt-3">
            {(Object.entries(info.locations) as [string, string][]).map(([key, path]) => (
              <Row
                key={key}
                label={key[0].toUpperCase() + key.slice(1)}
                value={path}
                action={
                  <button
                    onClick={() => bridge.openPath(path)}
                    title={`Open ${path}`}
                    className="shrink-0 rounded p-1 text-content-faint transition-colors hover:text-content rf-focus"
                  >
                    <FolderOpen size={13} />
                  </button>
                }
              />
            ))}
          </div>
        </section>
      )}

      {/* --- host tools --------------------------------------------------- */}
      <DependencyPanel />
    </div>
  );
}
