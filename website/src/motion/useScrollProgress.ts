import { useEffect, useRef, useState } from 'react';
import { clamp } from '../lib/cn';

/**
 * Progress (0→1) of an element travelling through the viewport:
 * 0 as its top reaches the bottom of the screen, 1 as its bottom leaves the top.
 * rAF-throttled, passive, the basis for parallax and scroll-linked motion.
 */
export function useScrollProgress<T extends HTMLElement = HTMLDivElement>(): [
  React.RefObject<T>,
  number
] {
  const ref = useRef<T>(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let raf = 0;
    const compute = () => {
      raf = 0;
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const vh = window.innerHeight;
      const total = rect.height + vh;
      const passed = vh - rect.top;
      setProgress(clamp(passed / total, 0, 1));
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(compute);
    };
    compute();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      cancelAnimationFrame(raf);
    };
  }, []);

  return [ref, progress];
}

/**
 * Progress (0→1) across a PINNED (sticky) section: 0 when the section top hits
 * the viewport top, 1 when the section has fully scrolled through. Give the
 * outer wrapper a tall height and stick an inner 100vh panel to it.
 */
export function usePinProgress<T extends HTMLElement = HTMLDivElement>(): [
  React.RefObject<T>,
  number
] {
  const ref = useRef<T>(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let raf = 0;
    const compute = () => {
      raf = 0;
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const scrollable = rect.height - window.innerHeight;
      if (scrollable <= 0) {
        setProgress(0);
        return;
      }
      setProgress(clamp(-rect.top / scrollable, 0, 1));
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(compute);
    };
    compute();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      cancelAnimationFrame(raf);
    };
  }, []);

  return [ref, progress];
}

/** Only rerender when a pinned section changes stage, not on every scroll frame. */
export function usePinStage<T extends HTMLElement = HTMLDivElement>(stages: number): [
  React.RefObject<T>,
  number
] {
  const ref = useRef<T>(null);
  const [stage, setStage] = useState(0);

  useEffect(() => {
    let raf = 0;
    let current = 0;
    const compute = () => {
      raf = 0;
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const scrollable = rect.height - window.innerHeight;
      const progress = scrollable > 0 ? clamp(-rect.top / scrollable, 0, 1) : 0;
      const next = clamp(Math.floor(progress * stages), 0, stages - 1);
      if (next !== current) {
        current = next;
        setStage(next);
      }
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(compute); };
    compute();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      cancelAnimationFrame(raf);
    };
  }, [stages]);

  return [ref, stage];
}
