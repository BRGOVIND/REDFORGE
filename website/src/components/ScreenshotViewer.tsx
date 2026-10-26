import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, ZoomIn, ZoomOut, ArrowLeft, ArrowRight } from 'lucide-react';
import { SCREENS, type ScreenName } from './ProductScreen';

const NAMES = Object.keys(SCREENS) as ScreenName[];

/** Native modal supplies focus trapping, Escape and an inert background. */
export function ScreenshotViewer({ initial, onClose }: { initial: ScreenName; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const [name, setName] = useState(initial);
  const [zoomed, setZoomed] = useState(false);
  const screen = SCREENS[name];
  useEffect(() => {
    const dialog = dialogRef.current;
    const trigger = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    dialog?.showModal();
    dialog?.querySelector<HTMLButtonElement>('[aria-label="Close screenshot"]')?.focus();
    document.body.style.overflow = 'hidden';
    return () => {
      dialog?.close();
      document.body.style.overflow = previousOverflow;
      trigger?.focus({ preventScroll: true });
    };
  }, []);
  const select = (direction: number) => {
    setName(NAMES[(NAMES.indexOf(name) + direction + NAMES.length) % NAMES.length]);
    setZoomed(false);
    viewportRef.current?.scrollTo(0, 0);
  };
  return createPortal(
    <dialog ref={dialogRef} className="screenshot-viewer" aria-labelledby="screenshot-title" aria-describedby="screenshot-note"
      onClose={() => { if (!dialogRef.current?.open) onClose(); }} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="screenshot-panel">
        <header className="screenshot-toolbar">
          <h2 id="screenshot-title">Inside RedForge</h2>
          <div>
            <button type="button" className="focus-ring" aria-label="Previous screenshot" onClick={() => select(-1)}><ArrowLeft size={18} /></button>
            <button type="button" className="focus-ring" aria-label="Next screenshot" onClick={() => select(1)}><ArrowRight size={18} /></button>
            <button type="button" className="focus-ring" aria-label={zoomed ? 'Fit screenshot' : 'Zoom screenshot'} aria-pressed={zoomed} onClick={() => setZoomed(!zoomed)}>{zoomed ? <ZoomOut size={18} /> : <ZoomIn size={18} />}</button>
            <button type="button" className="focus-ring" aria-label="Close screenshot" onClick={onClose}><X size={20} /></button>
          </div>
        </header>
        <div className={`screenshot-viewport ${zoomed ? 'is-zoomed' : ''}`} ref={viewportRef}>
          <img src={screen.src} alt={screen.alt} width={screen.size[0]} height={screen.size[1]} draggable={false} />
        </div>
        <footer className="screenshot-footer"><p aria-live="polite">{screen.alt}</p><p id="screenshot-note">Actual 2.0.3 screenshot. Preview only; app controls are not live. Zoom to inspect, then scroll to pan.</p></footer>
      </div>
    </dialog>, document.body,
  );
}
