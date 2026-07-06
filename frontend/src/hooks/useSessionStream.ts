/**
 * Live session stream.
 *
 * The backend event store exposes an incremental cursor
 * (`GET /sessions/{id}/events?after_id=N`) that was designed for a future
 * WebSocket feed. WebSockets are not yet available server-side, so this hook
 * polls that cursor on a short interval — the same data, delivered live — and is
 * structured so a `WebSocket` transport can be dropped in without changing any
 * consumer. It accumulates events and derives the live metrics the UI shows.
 */
import { useEffect, useRef, useState } from 'react';
import * as api from '../api/endpoints';
import type { EvaluationEvent, SessionResponse } from '../api/types';

const TERMINAL: string[] = ['completed', 'failed', 'cancelled'];
const POLL_MS = 1200;

export interface LiveMetrics {
  completed: number;
  total: number;
  remaining: number;
  progress: number; // 0..1
  currentModel: string | null;
  currentCategory: string | null;
  currentAttack: string | null;
  avgLatencyMs: number | null;
  liveScore: number | null; // running % of resisted attacks
  etaSeconds: number | null;
  stage: string;
}

export interface SessionStream {
  session: SessionResponse | null;
  events: EvaluationEvent[];
  metrics: LiveMetrics;
  isLive: boolean;
  isDone: boolean;
  error: unknown;
}

const EMPTY_METRICS: LiveMetrics = {
  completed: 0,
  total: 0,
  remaining: 0,
  progress: 0,
  currentModel: null,
  currentCategory: null,
  currentAttack: null,
  avgLatencyMs: null,
  liveScore: null,
  etaSeconds: null,
  stage: 'created',
};

function deriveMetrics(session: SessionResponse | null, events: EvaluationEvent[]): LiveMetrics {
  if (!session) return EMPTY_METRICS;
  const total = session.total_tasks || 0;
  const completed = session.completed_tasks || 0;

  const verdicts = events.filter((e) => e.event_type === 'verdict_generated');
  const latencies = verdicts.map((e) => e.latency_ms).filter((n): n is number => n != null && n > 0);
  const avgLatencyMs = latencies.length
    ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length)
    : null;

  // Live score: proportion of decisive attacks the model resisted (not FAIL).
  const decisive = verdicts.filter((e) => e.verdict && e.verdict !== 'ERROR');
  const resisted = decisive.filter((e) => e.verdict !== 'FAIL').length;
  const liveScore = decisive.length ? Math.round((resisted / decisive.length) * 100) : null;

  const last = [...events].reverse();
  const lastAttack = last.find((e) => e.attack_name);

  const remaining = Math.max(total - completed, 0);
  const etaSeconds =
    avgLatencyMs && remaining > 0 ? Math.round((avgLatencyMs / 1000) * remaining) : null;

  const stage = (session.metadata?.stage as string) || session.status;

  return {
    completed,
    total,
    remaining,
    progress: total ? completed / total : 0,
    currentModel: lastAttack?.model_name ?? session.selected_models[0] ?? null,
    currentCategory: lastAttack?.category ?? null,
    currentAttack: lastAttack?.attack_name ?? null,
    avgLatencyMs,
    liveScore,
    etaSeconds,
    stage,
  };
}

export function useSessionStream(sessionId: string | null): SessionStream {
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [events, setEvents] = useState<EvaluationEvent[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [isDone, setDone] = useState(false);
  const cursorRef = useRef(0);

  useEffect(() => {
    if (!sessionId) return;
    setSession(null);
    setEvents([]);
    setDone(false);
    setError(null);
    cursorRef.current = 0;

    let active = true;
    let timer: number;

    const tick = async () => {
      try {
        const [s, newEvents] = await Promise.all([
          api.getSession(sessionId),
          api.getSessionEvents(sessionId, cursorRef.current),
        ]);
        if (!active) return;
        setSession(s);
        if (newEvents.length) {
          cursorRef.current = newEvents[newEvents.length - 1].id;
          setEvents((prev) => [...prev, ...newEvents]);
        }
        if (TERMINAL.includes(s.status)) {
          setDone(true);
          return; // stop polling once terminal
        }
      } catch (err) {
        if (active) setError(err);
      }
      if (active) timer = window.setTimeout(tick, POLL_MS);
    };

    void tick();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [sessionId]);

  return {
    session,
    events,
    metrics: deriveMetrics(session, events),
    isLive: !!session && !isDone,
    isDone,
    error,
  };
}
