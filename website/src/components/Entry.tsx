import { useLayoutEffect, useRef, type RefObject } from 'react';

const DURATION = 2420;
const EASE = 'cubic-bezier(0.65, 0, 0.2, 1)';

interface EntryProps {
  logoRef: RefObject<HTMLDivElement>;
  onDone: () => void;
}

/** The navbar owns the only logo. This overlay choreographs it in place. */
export function Entry({ logoRef, onDone }: EntryProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const logo = logoRef.current;
    const overlay = overlayRef.current;
    if (!logo || !overlay) { onDone(); return; }

    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    if (reduced.matches || document.hidden || window.scrollY > 4 || location.hash) {
      onDone();
      return;
    }

    const animations: Animation[] = [];
    let finished = false;
    let docking: Animation;
    const started = performance.now();
    const finish = () => {
      if (finished) return;
      finished = true;
      if (overlay.contains(document.activeElement)) {
        logo.closest<HTMLAnchorElement>('a')?.focus({ preventScroll: true });
      }
      onDone();
    };
    const animate = (element: Element | null, frames: Keyframe[], duration: number, delay = 0) => {
      if (!element) return;
      const animation = element.animate(frames, { duration, delay, easing: EASE, fill: 'both' });
      animations.push(animation);
    };

    const target = logo.getBoundingClientRect();
    const scale = innerWidth < 640 ? 2 : 2.6;
    const markSize = logo.querySelector('svg')?.getBoundingClientRect().width ?? 22;
    const centerY = innerHeight * 0.44;
    const translate = (x: number, y: number, s: number) => `translate3d(${x}px, ${y}px, 0) scale(${s})`;
    const markCentered = translate(innerWidth / 2 - target.left - markSize * scale / 2,
      centerY - target.top - target.height * scale / 2, scale);
    const wordCentered = translate(innerWidth / 2 - target.left - target.width * scale / 2,
      centerY - target.top - target.height * scale / 2, scale);

    docking = logo.animate([
      { transform: markCentered, offset: 0 },
      { transform: markCentered, offset: 0.43, easing: EASE },
      { transform: wordCentered, offset: 0.64 },
      { transform: wordCentered, offset: 0.69, easing: EASE },
      { transform: 'none', offset: 1 },
    ], { duration: DURATION, fill: 'both', easing: 'linear' });
    animations.push(docking);
    docking.onfinish = finish;

    // Flatten the actual chevrons onto the ember axis, contract, then unfold.
    for (const selector of ['.forge-angle-top', '.forge-angle-bottom']) {
      animate(logo.querySelector(selector), [
        { transform: 'scale(0.01, 0.015)', stroke: '#D12A2A', opacity: 0, offset: 0 },
        { transform: 'scale(9, 0.015)', stroke: '#A11212', opacity: 0.7, offset: 0.28 },
        { transform: 'scale(1, 0.015)', stroke: '#D12A2A', opacity: 1, offset: 0.66 },
        { transform: 'none', stroke: '#55555F', opacity: 1, offset: 1 },
      ], 1320);
    }
    animate(logo.querySelector('.forge-flame'), [
      { transform: 'scale(0.2, 0.12)', opacity: 0, offset: 0 },
      { transform: 'scale(0.8, 0.28)', opacity: 1, offset: 0.22, fill: '#D12A2A' },
      { transform: 'scale(0.8, 0.28)', opacity: 1, offset: 0.55, fill: '#D12A2A' },
      { transform: 'none', opacity: 1, fill: '#A11212', offset: 1 },
    ], 1320);
    animate(logo.querySelector('.forge-word'), [
      { opacity: 0, transform: 'translateX(-8px)', clipPath: 'inset(0 100% 0 0)' },
      { opacity: 1, transform: 'none', clipPath: 'inset(0 0% 0 0)' },
    ], 440, 1040);
    animate(overlay, [{ opacity: 1 }, { opacity: 0 }], 660, 1760);
    animate(overlay.querySelector('p'), [
      { opacity: 0, offset: 0 }, { opacity: 0.7, offset: 0.35 },
      { opacity: 0.7, offset: 0.65 }, { opacity: 0, offset: 1 },
    ], 1550, 300);

    const resize = () => {
      if (finished) return;
      // Rebase from the current visual position to the newly measured navbar slot.
      const current = logo.getBoundingClientRect();
      docking.cancel();
      const destination = logo.getBoundingClientRect();
      docking = logo.animate([
        { transform: translate(current.left - destination.left, current.top - destination.top,
          current.width / destination.width) },
        { transform: 'none' },
      ], { duration: Math.max(120, DURATION - (performance.now() - started)), easing: EASE, fill: 'both' });
      animations.push(docking);
      docking.onfinish = finish;
    };
    const key = (event: KeyboardEvent) => { if (event.key === 'Escape' || event.key === 'Tab') finish(); };
    const visibility = () => { if (document.hidden) finish(); };
    const interact = (event: Event) => {
      if (event.target instanceof Element && event.target.closest('a, button')) finish();
    };
    const fallback = window.setTimeout(finish, DURATION + 160);
    let logoWidth = logo.offsetWidth;
    const logoObserver = new ResizeObserver(() => {
      if (logo.offsetWidth !== logoWidth) {
        logoWidth = logo.offsetWidth;
        resize();
      }
    });
    logoObserver.observe(logo);
    window.addEventListener('resize', resize);
    window.addEventListener('keydown', key);
    window.addEventListener('wheel', finish, { passive: true });
    window.addEventListener('touchmove', finish, { passive: true });
    document.addEventListener('pointerdown', interact);
    document.addEventListener('focusin', interact);
    document.addEventListener('visibilitychange', visibility);
    reduced.addEventListener('change', finish);
    return () => {
      finished = true;
      clearTimeout(fallback);
      logoObserver.disconnect();
      animations.forEach(animation => animation.cancel());
      window.removeEventListener('resize', resize);
      window.removeEventListener('keydown', key);
      window.removeEventListener('wheel', finish);
      window.removeEventListener('touchmove', finish);
      document.removeEventListener('pointerdown', interact);
      document.removeEventListener('focusin', interact);
      document.removeEventListener('visibilitychange', visibility);
      reduced.removeEventListener('change', finish);
    };
  }, [logoRef, onDone]);

  return (
    <div ref={overlayRef} className="forge-entry">
      <p className="label forge-entry-caption" aria-hidden="true">Local AI Security Laboratory</p>
      <button onClick={onDone} className="focus-ring forge-entry-skip label hover:text-steel-200">Skip</button>
    </div>
  );
}
