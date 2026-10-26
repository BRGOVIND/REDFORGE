import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, ArrowDownRight, Expand } from 'lucide-react';
import { ProductScreen, type ScreenName } from '../components/ProductScreen';
import { ScreenshotViewer } from '../components/ScreenshotViewer';

const VIEWS: { name: string; screen: ScreenName; title: string; description: string }[] = [
  { name: 'Evaluate', screen: 'evaluation', title: 'Choose the test before you run it.', description: 'Pick a model and evaluation profile. Review estimated time, calls and memory requirements, including warnings when a run may exceed your hardware.' },
  { name: 'Observe', screen: 'live', title: 'Follow every step of the run.', description: 'Watch evaluation progress and timestamped events. Inspect the current finding, or pause and cancel without leaving the workspace.' },
  { name: 'Compare', screen: 'benchmarks', title: 'Put results next to each other.', description: 'Compare recorded model runs, latency and throughput. Some suites shown here are architectural previews; the screen is an example, not a universal ranking.' },
  { name: 'Report', screen: 'report', title: 'Take the evidence with you.', description: 'Read the summary and category scores, then export JSON, Markdown or PDF. A security score describes this test run, not a guarantee of safety.' },
  { name: 'Inspect', screen: 'findings', title: 'Understand what needs attention.', description: 'Go beyond the score. Review failed tests, severity and recommendations so the next change starts with a specific finding.' },
];

export function WorkbenchPreview() {
  const [active, setActive] = useState(0);
  const [viewer, setViewer] = useState<ScreenName | null>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<HTMLDivElement>(null);
  const stickyRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(false);
  const move = (index: number) => {
    const track = trackRef.current;
    const scene = sceneRef.current;
    const card = track?.children[Math.max(0, Math.min(VIEWS.length - 1, index))] as HTMLElement | undefined;
    if (!track || !card || !scene) return;
    const left = card.offsetLeft - (track.clientWidth - card.clientWidth) / 2;
    const behavior = matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth';
    if (pinned && stickyRef.current) {
      const distance = scene.offsetHeight - stickyRef.current.offsetHeight;
      const top = parseFloat(getComputedStyle(stickyRef.current).top);
      window.scrollTo({ top: window.scrollY + scene.getBoundingClientRect().top - top + distance * left / Math.max(1, track.scrollWidth - track.clientWidth), behavior });
    } else track.scrollTo({ left, behavior });
  };

  useEffect(() => {
    const track = trackRef.current, scene = sceneRef.current, sticky = stickyRef.current;
    if (!track || !scene || !sticky) return;
    let raf = 0;
    const media = matchMedia('(prefers-reduced-motion: no-preference) and (min-height: 520px) and (min-width: 640px), (prefers-reduced-motion: no-preference) and (min-height: 700px) and (max-width: 639px)');
    const mode = () => { setPinned(media.matches); schedule(); };
    const measure = () => {
      raf = 0;
      if (media.matches) {
        const top = parseFloat(getComputedStyle(sticky).top);
        const progress = Math.max(0, Math.min(1, (top - scene.getBoundingClientRect().top) / Math.max(1, scene.offsetHeight - sticky.offsetHeight)));
        track.scrollLeft = progress * (track.scrollWidth - track.clientWidth);
      }
      const center = track.scrollLeft + track.clientWidth / 2;
      let nearest = 0, distance = Infinity;
      Array.from(track.children).forEach((child, index) => {
        const card = child as HTMLElement;
        const delta = Math.abs(card.offsetLeft + card.clientWidth / 2 - center);
        if (delta < distance) { nearest = index; distance = delta; }
      });
      setActive(nearest);
    };
    const schedule = () => { if (!raf) raf = requestAnimationFrame(measure); };
    window.addEventListener('scroll', schedule, { passive: true });
    track.addEventListener('scroll', schedule, { passive: true });
    media.addEventListener('change', mode);
    const resize = new ResizeObserver(schedule);
    resize.observe(track); resize.observe(scene); resize.observe(sticky);
    mode();
    return () => { cancelAnimationFrame(raf); resize.disconnect(); media.removeEventListener('change', mode); window.removeEventListener('scroll', schedule); track.removeEventListener('scroll', schedule); };
  }, []);

  return (
    <div id="product-tour" className="product-tour" ref={sceneRef}>
      <div className="tour-sticky" ref={stickyRef}>
      <div className="tour-heading">
        <div><p className="edition-label">Inside RedForge</p><h2>The work. In plain sight.</h2></div>
        <a href="#capabilities" className="focus-ring">Explore the tools <ArrowDownRight size={17} /></a>
      </div>
      <div className="tour-gallery" role="region" aria-label="RedForge product screenshots" aria-roledescription="carousel">
        <div className="tour-gallery-track focus-ring" ref={trackRef} role="group" tabIndex={0} aria-label={pinned ? "Scroll down to explore screenshots, or use left and right arrow keys" : "Scroll screenshots sideways, or use left and right arrow keys"} onKeyDown={event => {
          if (event.target !== event.currentTarget) return;
          if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); move(active + (event.key === 'ArrowRight' ? 1 : -1)); }
          if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); move(event.key === 'Home' ? 0 : VIEWS.length - 1); }
        }}>
          {VIEWS.map((view, index) => <figure key={view.screen} className="tour-gallery-card" data-centered={active === index} aria-label={`${index + 1} of ${VIEWS.length}: ${view.name}`}>
            <button type="button" className="tour-gallery-image focus-ring" tabIndex={active === index ? 0 : -1} onClick={() => setViewer(view.screen)} aria-label={`Enlarge ${view.name.toLowerCase()} screenshot`} aria-haspopup="dialog">
              <ProductScreen name={view.screen} clear={active === index} />
              <span className="tour-enlarge"><Expand size={15} /> Explore screenshot</span>
            </button>
            <figcaption><span className="tour-gallery-verb">{view.name}</span><div><h3>{view.title}</h3><p>{view.description}</p></div></figcaption>
          </figure>)}
        </div>
        <div className="tour-gallery-navigation">
          <p>{pinned ? "Keep scrolling down. Follow the workflow." : "Explore the workflow with the arrows or swipe."}</p>
          <span aria-live="polite" aria-atomic="true">{String(active + 1).padStart(2, '0')} / 05</span>
          <button type="button" className="focus-ring" aria-label="Previous product screen" disabled={active === 0} onClick={() => move(active - 1)}><ArrowLeft size={18} /></button>
          <button type="button" className="focus-ring" aria-label="Next product screen" disabled={active === VIEWS.length - 1} onClick={() => move(active + 1)}><ArrowRight size={18} /></button>
        </div>
      </div>
      <p className="tour-disclosure">Actual RedForge 2.0.3 screens. Example runs, not universal model ratings. Screenshots open as previews, not live app controls.</p>
      </div>
      {viewer && <ScreenshotViewer initial={viewer} onClose={() => setViewer(null)} />}
    </div>
  );
}
