import { useEffect, type RefObject } from 'react';

/** Scroll writes CSS variables, without rendering the React tree every frame. */
export function useScrollScene(ref: RefObject<HTMLElement>, mode: 'travel' | 'pin' = 'travel') {
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    let visible = true;
    const clamp = (value: number) => Math.max(0, Math.min(1, value));
    const update = () => {
      frame = 0;
      const rect = element.getBoundingClientRect();
      const viewport = window.innerHeight;
      const entry = reduced.matches ? 1 : clamp((viewport - rect.top) / Math.min(rect.height, viewport * 0.85));
      const exit = reduced.matches ? 0 : clamp(-rect.top / Math.max(rect.height, 1));
      const progress = reduced.matches ? 1 : mode === 'pin'
        ? clamp(-rect.top / Math.max(1, rect.height - viewport))
        : clamp((viewport - rect.top) / (viewport + rect.height));
      element.style.setProperty('--scene-entry', entry.toFixed(4));
      element.style.setProperty('--scene-exit', exit.toFixed(4));
      element.style.setProperty('--scene-progress', progress.toFixed(4));
    };
    const schedule = () => {
      if (!frame && visible && !document.hidden) frame = requestAnimationFrame(update);
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      // Set final values at both boundaries, including jumps via anchors.
      update();
    });
    const resize = new ResizeObserver(schedule);
    observer.observe(element);
    resize.observe(element);
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    document.addEventListener('visibilitychange', schedule);
    reduced.addEventListener('change', update);
    update();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      resize.disconnect();
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      document.removeEventListener('visibilitychange', schedule);
      reduced.removeEventListener('change', update);
    };
  }, [ref, mode]);
}
