import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDownToLine, Copy, Eraser, Pause, Play, TerminalSquare } from 'lucide-react';
import { cn } from '../lib/cn';
import { toast } from '../lib/toast';
import type { TerminalLevel, TerminalLine } from '../api/types';

const LEVEL_COLOR: Record<TerminalLevel, string> = {
  info: 'text-zinc-400',
  success: 'text-pass',
  warning: 'text-uncertain',
  failure: 'text-fail',
  system: 'text-sky-400',
};

function hms(ts: string | null): string {
  if (!ts) return '--:--:--';
  const d = new Date(ts);
  return Number.isNaN(d.getTime())
    ? '--:--:--'
    : d.toLocaleTimeString([], { hour12: false });
}

function IconButton({
  label,
  onClick,
  active,
  children,
}: {
  label: string;
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      className={cn(
        'rf-focus flex h-7 w-7 items-center justify-center rounded-md transition-colors',
        active ? 'bg-red-soft text-red-400' : 'text-content-subtle hover:bg-white/5 hover:text-content'
      )}
    >
      {children}
    </button>
  );
}

/** Real-terminal panel: black background, monospace, auto-scrolling, colorized. */
export function Terminal({ lines, live }: { lines: TerminalLine[]; live: boolean }) {
  const [autoscroll, setAutoscroll] = useState(true);
  const [clearedCount, setClearedCount] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Only render the tail — long runs never blow up the DOM.
  const visible = useMemo(
    () => lines.slice(Math.max(clearedCount, lines.length - 500)),
    [lines, clearedCount]
  );

  useEffect(() => {
    if (autoscroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [visible.length, autoscroll]);

  const asText = () => visible.map((l) => `[${hms(l.ts)}] ${l.text}`).join('\n');

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(asText());
      toast.success('Logs copied to clipboard');
    } catch {
      toast.error('Could not copy logs');
    }
  };

  const download = () => {
    const blob = new Blob([asText()], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `redforge-terminal-${Date.now()}.log`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-black">
      <div className="flex items-center justify-between border-b border-border/80 bg-[#0c0c0e] px-4 py-2.5">
        <div className="flex items-center gap-2 text-content-muted">
          <TerminalSquare size={14} />
          <span className="text-xs font-medium">Terminal</span>
          {live && (
            <span className="ml-1 flex items-center gap-1.5 text-[11px] text-red-400">
              <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse-dot" />
              live
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <IconButton
            label={autoscroll ? 'Pause auto-scroll' : 'Resume auto-scroll'}
            onClick={() => setAutoscroll((v) => !v)}
            active={!autoscroll}
          >
            {autoscroll ? <Pause size={13} /> : <Play size={13} />}
          </IconButton>
          <IconButton label="Copy logs" onClick={copy}>
            <Copy size={13} />
          </IconButton>
          <IconButton label="Download logs" onClick={download}>
            <ArrowDownToLine size={13} />
          </IconButton>
          <IconButton label="Clear view" onClick={() => setClearedCount(lines.length)}>
            <Eraser size={13} />
          </IconButton>
        </div>
      </div>

      <div
        ref={scrollRef}
        className="h-[360px] overflow-y-auto px-4 py-3 font-mono text-[12.5px] leading-relaxed"
      >
        {visible.length === 0 ? (
          <p className="text-content-faint">Waiting for output…</p>
        ) : (
          visible.map((l) => (
            <div key={l.id} className="flex gap-2 animate-fade-in">
              <span className="shrink-0 select-none text-zinc-600">[{hms(l.ts)}]</span>
              <span className={cn('whitespace-pre-wrap break-words', LEVEL_COLOR[l.level])}>
                {l.text}
              </span>
            </div>
          ))
        )}
        {live && !autoscroll && (
          <button
            onClick={() => setAutoscroll(true)}
            className="rf-focus mt-2 text-[11px] text-red-400 hover:underline"
          >
            ↓ Jump to latest
          </button>
        )}
      </div>
    </div>
  );
}
