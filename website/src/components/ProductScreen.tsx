import { useEffect, useRef, useState, type CSSProperties } from 'react';

export const SCREENS = {
  benchmarks: { src: '/screens/benchmarks.png', alt: 'RedForge Benchmark Center with a model comparison chart and results table', size: [1641, 962], crop: [0, 0, 1, 0.95952] },
  live: { src: '/screens/live.png', alt: 'A local evaluation with progress, model details and a timestamped event feed', size: [1637, 1040], crop: [0.015, 0.058, 0.97, 0.85883] },
  report: { src: '/screens/report.png', alt: 'A RedForge security report with category scores and an executive summary', size: [1917, 1047], crop: [0.16, 0.06, 0.825, 0.84965] },
  models: { src: '/screens/models.png', alt: 'Three installed local models with their sizes, quantization and runtime details', size: [1917, 1042], crop: [0.16, 0.06, 0.825, 0.50] },
  evaluation: { src: '/screens/evaluation.png', alt: 'Evaluation setup with model and profile selection, resource estimates and memory warnings', size: [1632, 1046], crop: [0.015, 0.065, 0.97, 0.88] },
  findings: { src: '/screens/findings.png', alt: 'Security findings with failed test names, severity and recommendations', size: [1917, 1045], crop: [0.16, 0.055, 0.825, 0.87] },
} as const;
export type ScreenName = keyof typeof SCREENS;

/** Real screenshot below, temporary low-resolution canvas above. Original assets stay intact. */
export function ProductScreen({ name, animate = true, clear }: { name: ScreenName; animate?: boolean; clear?: boolean }) {
  const frameRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const resolutionRef = useRef(22);
  const [failed, setFailed] = useState(false);
  const screen = SCREENS[name];
  const [x, y, w, h] = screen.crop;

  useEffect(() => {
    const frame = frameRef.current;
    const canvas = canvasRef.current;
    const image = imageRef.current;
    if (!frame || !canvas || !image || !animate || clear !== undefined) return;
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    const context = canvas.getContext('2d');
    if (!context) return;
    let raf = 0;
    let visible = false;
    let played = false;
    let disposed = false;
    let start = 0;
    let lastStep = -1;
    // Ten small redraws, stretched with nearest-neighbour sampling. No persistent render loop.
    const steps = [22, 32, 48, 72, 110, 170, 260, 400, 640, 1000];
    const stop = () => { cancelAnimationFrame(raf); canvas.style.opacity = '0'; };
    const tick = (time: number) => {
      if (disposed || document.hidden || reduced.matches) { stop(); return; }
      if (!start) start = time;
      const progress = Math.min((time - start) / 760, 1);
      const step = Math.min(steps.length - 1, Math.floor(progress * steps.length));
      if (step !== lastStep) {
        lastStep = step;
        const width = Math.min(steps[step], Math.ceil(frame.clientWidth));
        canvas.width = width;
        canvas.height = Math.max(1, Math.round(width * frame.clientHeight / Math.max(1, frame.clientWidth)));
        context.imageSmoothingEnabled = true;
        context.drawImage(image, x * image.naturalWidth, y * image.naturalHeight,
          w * image.naturalWidth, h * image.naturalHeight, 0, 0, canvas.width, canvas.height);
        canvas.style.opacity = '1';
      }
      if (progress < 1) raf = requestAnimationFrame(tick);
      else stop();
    };
    const play = () => {
      if (!visible || played || disposed || !image.complete || !image.naturalWidth) return;
      played = true;
      if (!reduced.matches && !document.hidden) raf = requestAnimationFrame(tick);
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible) play();
      else if (played) stop();
    }, { threshold: 0.18 });
    observer.observe(frame);
    image.addEventListener('load', play);
    reduced.addEventListener('change', stop);
    document.addEventListener('visibilitychange', stop);
    return () => {
      disposed = true;
      stop();
      observer.disconnect();
      image.removeEventListener('load', play);
      reduced.removeEventListener('change', stop);
      document.removeEventListener('visibilitychange', stop);
    };
  }, [name, animate, clear, x, y, w, h]);

  // The gallery resolves its centered screen and coarsens the outgoing screen.
  // Draw only while visible, and only when a quantized resolution changes.
  useEffect(() => {
    const frame = frameRef.current, canvas = canvasRef.current, image = imageRef.current;
    if (clear === undefined || !frame || !canvas || !image) return;
    const context = canvas.getContext('2d');
    if (!context) return;
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    let raf = 0, visible = false, start = 0, lastWidth = 0;
    let from = resolutionRef.current;
    const target = clear ? 1000 : 22;
    const draw = (resolution: number) => {
      resolutionRef.current = resolution;
      if (resolution >= 1000 || reduced.matches) { canvas.style.opacity = '0'; return; }
      const width = Math.max(1, Math.round(resolution));
      if (width === lastWidth) return;
      lastWidth = width;
      canvas.width = width;
      canvas.height = Math.max(1, Math.round(width * screen.size[1] * h / (screen.size[0] * w)));
      context.drawImage(image, x * image.naturalWidth, y * image.naturalHeight, w * image.naturalWidth, h * image.naturalHeight, 0, 0, canvas.width, canvas.height);
      canvas.style.opacity = '1';
    };
    const tick = (time: number) => {
      if (!start) start = time;
      const t = Math.min(1, (time - start) / 560);
      const step = Math.floor(t * 12) / 12;
      draw(Math.exp(Math.log(from) + (Math.log(target) - Math.log(from)) * step));
      if (t < 1) raf = requestAnimationFrame(tick);
      else draw(target);
    };
    const play = () => {
      cancelAnimationFrame(raf);
      if (!image.complete || !image.naturalWidth) return;
      if (reduced.matches) { canvas.style.opacity = '0'; return; }
      if (!visible || document.hidden) return;
      from = resolutionRef.current;
      start = 0;
      draw(from);
      if (from !== target) raf = requestAnimationFrame(tick);
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible) play(); else cancelAnimationFrame(raf);
    });
    observer.observe(frame);
    image.addEventListener('load', play);
    reduced.addEventListener('change', play);
    document.addEventListener('visibilitychange', play);
    return () => {
      cancelAnimationFrame(raf); observer.disconnect();
      image.removeEventListener('load', play);
      reduced.removeEventListener('change', play);
      document.removeEventListener('visibilitychange', play);
    };
  }, [clear, name, x, y, w, h, screen]);

  return (
    <div className="product-screen" ref={frameRef} style={{
      '--screen-width': `${100 / w}%`, '--screen-height': `${100 / h}%`,
      '--screen-left': `${-x / w * 100}%`, '--screen-top': `${-y / h * 100}%`,
      '--screen-aspect': (screen.size[0] * w) / (screen.size[1] * h),
      '--screen-ratio': `${screen.size[0] * w} / ${screen.size[1] * h}`,
    } as CSSProperties}>
      <img ref={imageRef} src={screen.src} alt={screen.alt} width="1600" height="900"
        loading="lazy" decoding="async" draggable={false} onError={() => setFailed(true)} />
      <canvas ref={canvasRef} aria-hidden="true" />
      {failed && <span className="screen-fallback">Preview unavailable. Explore the workflow descriptions below.</span>}
    </div>
  );
}
