import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Cpu,
  Download,
  HardDrive,
  Minus,
  RefreshCw,
  Trash2,
  Zap,
} from 'lucide-react';
import { Badge, Button, Card } from './ui';
import { useTaskManager } from './TaskManager';
import { errorMessage } from '../api/client';
import { toast } from '../lib/toast';
import * as api from '../api/endpoints';
import type { TrainingRuntimeReport } from '../api/types';

/**
 * The Training Runtime experience.
 *
 * RedForge ships without the 2–4 GB training engine to keep installers small.
 * That is a deliberate trade-off, so the UI states it plainly and offers a
 * one-click install — it never silently substitutes simulated training, which is
 * the behaviour this panel exists to replace.
 */

function gb(mb?: number | null): string {
  if (!mb && mb !== 0) return '—';
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;
}

function StatusBadge({ report }: { report: TrainingRuntimeReport }) {
  switch (report.status) {
    case 'ready':
      return <Badge tone="green" title={report.message}>Training ready</Badge>;
    case 'partial':
      return <Badge tone="amber" title={report.message}>Installation incomplete</Badge>;
    case 'broken':
      return <Badge tone="red" title={report.message}>Needs repair</Badge>;
    case 'installing':
      return <Badge tone="amber">Installing…</Badge>;
    default:
      return <Badge tone="grey">Not installed</Badge>;
  }
}

function PackageRow({ label, installed, version, required }:
  { label: string; installed: boolean; version: string | null; required: boolean }) {
  return (
    <li className="flex items-center justify-between gap-3 py-1.5">
      <span className="flex items-center gap-2 text-[12px] text-content">
        {installed
          ? <Check size={13} className="shrink-0 text-pass" />
          : <Minus size={13} className="shrink-0 text-content-faint" />}
        {label}
        {!required && <span className="text-[10px] text-content-faint">optional</span>}
      </span>
      <span className="font-mono text-[11px] text-content-faint">{version ?? (installed ? '—' : '')}</span>
    </li>
  );
}

/** Hardware facts, gathered before anything is installed. */
function HardwareStrip({ report }: { report: TrainingRuntimeReport }) {
  const tiles = [
    { icon: <Zap size={13} />, label: 'GPU', value: report.gpu.name ?? 'none detected' },
    { icon: <Cpu size={13} />, label: 'VRAM', value: gb(report.gpu.vram_mb) },
    { icon: <Cpu size={13} />, label: 'CUDA', value: report.gpu.cuda_version ?? '—' },
    { icon: <HardDrive size={13} />, label: 'Disk free', value: gb(report.disk_free_mb) },
  ];
  return (
    <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-lg border border-border bg-base px-3 py-2">
          <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-content-subtle">
            {t.icon}{t.label}
          </span>
          <p className="mt-0.5 truncate text-[12px] font-medium text-content" title={t.value}>{t.value}</p>
        </div>
      ))}
    </div>
  );
}

export function TrainingRuntimePanel({ onChanged }: { onChanged?: () => void }) {
  const [report, setReport] = useState<TrainingRuntimeReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const taskMgr = useTaskManager();

  const load = useCallback(async (refresh = false) => {
    try {
      setReport(await api.getTrainingRuntime(refresh));
    } catch (e) {
      toast.error('Could not read the training runtime status', errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // While an install runs it is a Task; poll so the panel flips to "ready"
  // the moment it finishes, without a page reload.
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => { void load(true); }, 5000);
    return () => clearInterval(timer);
  }, [busy, load]);

  const install = async (force = false) => {
    setBusy(true);
    try {
      await api.installTrainingRuntime(force);
      toast.success(
        'Installing the training runtime',
        'Track progress in the task panel. You can keep using RedForge meanwhile.',
      );
      taskMgr.refetch();
      taskMgr.setOpen(true);
      void load(true);
    } catch (e) {
      const detail = (e as { details?: { error?: string; message?: string; fix?: string } })?.details;
      if (detail?.error === 'install_in_progress') {
        toast.error('Already installing', detail.fix ?? '');
        taskMgr.setOpen(true);
      } else {
        toast.error('Could not start the installation', errorMessage(e));
      }
      setBusy(false);
    }
  };

  const verify = async () => {
    setBusy(true);
    try {
      const next = await api.verifyTrainingRuntime();
      setReport(next);
      toast[next.ready ? 'success' : 'error'](
        next.ready ? 'Training runtime verified' : 'Runtime not usable', next.message);
      onChanged?.();
    } catch (e) {
      toast.error('Verification failed', errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      const res = await api.removeTrainingRuntime();
      setReport(res.runtime);
      toast.success('Training runtime removed', 'Your models, datasets and runs were not touched.');
      onChanged?.();
    } catch (e) {
      toast.error('Could not remove the runtime', errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <Card className="p-5"><p className="text-[12px] text-content-subtle">Checking the training runtime…</p></Card>;
  }
  if (!report) return null;

  const plan = report.plan;

  // --- installed and working ------------------------------------------------
  if (report.ready) {
    return (
      <Card className="overflow-hidden">
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div>
            <h3 className="flex items-center gap-2 text-[13px] font-semibold text-content">
              Training Runtime <StatusBadge report={report} />
            </h3>
            <p className="mt-0.5 text-[11px] text-content-subtle">
              Real LoRA and QLoRA are available. {report.gpu.name ?? ''}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={verify} loading={busy}>
              <RefreshCw size={13} /> Verify
            </Button>
            <Button variant="ghost" size="sm" onClick={remove} loading={busy}>
              <Trash2 size={13} /> Remove
            </Button>
          </div>
        </div>
        <div className="px-5 py-4">
          <HardwareStrip report={report} />
          <ul className="mt-4 grid grid-cols-1 gap-x-8 sm:grid-cols-2">
            {report.packages.map((p) => (
              <PackageRow key={p.name} label={p.label} installed={p.installed}
                          version={p.version} required={p.required} />
            ))}
          </ul>
          <p className="mt-3 truncate font-mono text-[10px] text-content-faint" title={report.root}>
            {report.root}
          </p>
        </div>
      </Card>
    );
  }

  // --- not installed / incomplete / broken ---------------------------------
  const isRepair = report.status === 'broken' || report.status === 'partial';
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-border px-5 py-4">
        <h3 className="flex items-center gap-2 text-[13px] font-semibold text-content">
          Training Runtime Required <StatusBadge report={report} />
        </h3>
        <p className="mt-1 max-w-xl text-[12px] leading-relaxed text-content-muted">
          {isRepair
            ? report.message
            : 'Real training is not installed. RedForge ships without the training engine to keep downloads small.'}
        </p>
      </div>

      <div className="px-5 py-4">
        <HardwareStrip report={report} />

        {plan && (
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-border bg-base p-4">
              <p className="text-[10px] uppercase tracking-wide text-content-subtle">Install size</p>
              <p className="mt-1 text-lg font-semibold text-content">
                ~{(plan.download_mb_estimate / 1024).toFixed(1)}–4 GB
              </p>
              <p className="mt-0.5 text-[11px] text-content-subtle">
                Estimated time: {plan.minutes_estimate}
              </p>
              <p className="mt-2 text-[11px] text-content-subtle">{plan.reason}</p>
            </div>
            <div className="rounded-lg border border-border bg-base p-4">
              <p className="text-[10px] uppercase tracking-wide text-content-subtle">Includes</p>
              <ul className="mt-1.5 grid grid-cols-2 gap-x-4">
                {report.packages.map((p) => (
                  <li key={p.name} className="flex items-center gap-1.5 py-0.5 text-[11px] text-content">
                    {p.installed
                      ? <Check size={11} className="shrink-0 text-pass" />
                      : <Check size={11} className="shrink-0 text-content-faint" />}
                    {p.label}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {plan?.warnings.map((w) => (
          <p key={w} className="mt-3 flex items-start gap-2 rounded-lg border border-uncertain/30 bg-uncertain/10 px-3 py-2 text-[11px] text-content">
            <AlertTriangle size={13} className="mt-px shrink-0 text-uncertain" />
            {w}
          </p>
        ))}

        {report.resumable && !isRepair && (
          <p className="mt-3 text-[11px] text-content-subtle">
            A previous installation was interrupted — installing again resumes where it stopped.
          </p>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button onClick={() => install(isRepair)} loading={busy}>
            <Download size={14} />
            {isRepair ? 'Repair Training Runtime' : 'Install Training Runtime'}
          </Button>
          <Button variant="ghost" size="sm" onClick={verify} loading={busy}>
            <RefreshCw size={13} /> Re-check
          </Button>
        </div>

        <p className="mt-3 text-[11px] text-content-subtle">
          Installs into an isolated environment at{' '}
          <span className="font-mono text-content-faint">{report.root}</span>. Your system
          Python is never modified. Until then, Training runs in clearly-labelled
          Simulation mode.
        </p>
      </div>
    </Card>
  );
}
