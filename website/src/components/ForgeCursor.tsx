import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

/** Decorative pointer only; native selection, copying and control behavior stay intact. */
export function ForgeCursor() {
  const cursorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const cursor = cursorRef.current;
    if (!cursor || typeof cursor.showPopover !== 'function') return;
    cursor.setAttribute('popover', 'manual');
    const media = matchMedia('(hover: hover) and (pointer: fine) and (forced-colors: none)');
    let frame = 0, x = 0, y = 0, tracking = false;
    let layerDialog: Element | null = null;
    const hide = () => {
      document.documentElement.classList.remove('forge-cursor-active');
      cursor.dataset.visible = 'false';
      if (cursor.matches(':popover-open')) cursor.hidePopover();
    };
    const draw = () => {
      frame = 0;
      const target = document.elementFromPoint(x, y);
      if (!tracking || !media.matches || document.hidden || !target) {
        hide(); return;
      }
      const action = target.closest('a, button, [role="button"], summary');
      const dialog = document.querySelector('dialog[open]');
      // A manual popover renders above modal backdrops without intercepting input.
      if (dialog !== layerDialog) {
        if (cursor.matches(':popover-open')) cursor.hidePopover();
        layerDialog = dialog;
      }
      if (!cursor.matches(':popover-open')) cursor.showPopover();
      cursor.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      cursor.dataset.mode = target.closest('.tour-gallery-image, .workspace-follow, .workspace-inline-preview') ? 'view' : action ? 'action' : 'default';
      cursor.dataset.visible = 'true';
      document.documentElement.classList.add('forge-cursor-active');
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(draw); };
    const move = (event: PointerEvent) => {
      tracking = event.pointerType === 'mouse';
      x = event.clientX; y = event.clientY;
      schedule();
    };
    const leave = () => { tracking = false; cursor.dataset.pressed = 'false'; hide(); };
    const out = (event: PointerEvent) => { if (!event.relatedTarget) leave(); };
    const press = () => { cursor.dataset.pressed = 'true'; };
    const release = () => { cursor.dataset.pressed = 'false'; };
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['open'] });
    document.addEventListener('pointermove', move, { passive: true });
    document.addEventListener('pointerout', out, { passive: true });
    document.addEventListener('pointerdown', press, { passive: true });
    document.addEventListener('pointerup', release, { passive: true });
    document.addEventListener('pointercancel', leave);
    document.addEventListener('visibilitychange', leave);
    window.addEventListener('blur', leave);
    window.addEventListener('scroll', schedule, { passive: true });
    media.addEventListener('change', schedule);
    return () => {
      cancelAnimationFrame(frame); observer.disconnect(); hide();
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerout', out);
      document.removeEventListener('pointerdown', press);
      document.removeEventListener('pointerup', release);
      document.removeEventListener('pointercancel', leave);
      document.removeEventListener('visibilitychange', leave);
      window.removeEventListener('blur', leave);
      window.removeEventListener('scroll', schedule);
      media.removeEventListener('change', schedule);
    };
  }, []);

  return createPortal(<div ref={cursorRef} className="forge-cursor" aria-hidden="true" data-visible="false">
    <span className="forge-cursor-ring"><span>View</span></span>
    <span className="forge-cursor-dot" />
  </div>, document.body);
}
