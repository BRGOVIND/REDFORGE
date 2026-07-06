/**
 * Live terminal stream.
 *
 * Polls `GET /sessions/{id}/terminal?after_id=cursor`, appending only new
 * human-readable lines (the backend owns all formatting). Uses the same cursor
 * pattern as the event feed, so history is never re-fetched. Stops once the
 * session is terminal. WebSocket-ready: swap the poll for a socket and the
 * consumer (the Terminal panel) is unchanged.
 */
import { useEffect, useRef, useState } from 'react';
import * as api from '../api/endpoints';
import type { TerminalLine } from '../api/types';

const TERMINAL_STATES = ['completed', 'failed', 'cancelled'];
const POLL_MS = 1000;

export function useTerminalStream(sessionId: string | null): {
  lines: TerminalLine[];
  done: boolean;
} {
  const [lines, setLines] = useState<TerminalLine[]>([]);
  const [done, setDone] = useState(false);
  const cursor = useRef(0);

  useEffect(() => {
    if (!sessionId) return;
    setLines([]);
    setDone(false);
    cursor.current = 0;

    let active = true;
    let timer: number;

    const tick = async () => {
      try {
        const res = await api.getSessionTerminal(sessionId, cursor.current);
        if (!active) return;
        if (res.cursor > cursor.current) cursor.current = res.cursor;
        if (res.lines.length) setLines((prev) => [...prev, ...res.lines]);
        if (TERMINAL_STATES.includes(res.status)) {
          setDone(true);
          return;
        }
      } catch {
        /* keep polling; a transient error shouldn't kill the stream */
      }
      if (active) timer = window.setTimeout(tick, POLL_MS);
    };

    void tick();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [sessionId]);

  return { lines, done };
}
