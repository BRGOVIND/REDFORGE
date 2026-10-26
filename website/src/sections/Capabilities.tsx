import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Plus, Minus } from 'lucide-react';
import { Reveal } from '../motion';
import { ProductScreen, type ScreenName } from '../components/ProductScreen';
import { ScreenshotViewer } from '../components/ScreenshotViewer';

const TOOLS: { title: string; description: string; detail: string; screen: ScreenName; label: string }[] = [
  { title: 'Bring your models.', description: 'One workspace for the models and runtimes you already use.', detail: 'Inspect installed models, connect a local runtime, and organize models, datasets and runs into projects. Training with LoRA and QLoRA remains experimental.', screen: 'models', label: 'Model Manager / Local runtimes' },
  { title: 'Make a fair comparison.', description: 'Put prompts and model runs beside each other. Keep the context.', detail: 'Use the Prompt Workbench to test responses, and Benchmark Center to compare recorded metrics. Review which suites are implemented before interpreting a score.', screen: 'benchmarks', label: 'Workbench / Benchmark Center' },
  { title: 'Watch the details.', description: 'From the first test to the final verdict, see what is happening.', detail: 'Follow evaluation progress and timestamped events. Inspect model responses, review failures and control a running session without leaving the workspace.', screen: 'live', label: 'Live evaluations / Task manager' },
  { title: 'Keep the evidence.', description: 'Find the weak points. Take the findings with you.', detail: 'Inspect security findings by category, read recommendations and export reports as JSON, Markdown or PDF. Scores describe a test run, not a guarantee of safety.', screen: 'report', label: 'Security reports / Exports' },
];

export function Capabilities() {
  const [active, setActive] = useState(0);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [following, setFollowing] = useState(false);
  const areaRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef<HTMLButtonElement>(null);
  const [viewer, setViewer] = useState<ScreenName | null>(null);
  const activeRef = useRef(0);
  const place = (index: number) => {
    const area = areaRef.current, preview = previewRef.current;
    const row = area?.querySelectorAll<HTMLElement>('.workspace-row')[index];
    if (!area || !preview || !row) return;
    activeRef.current = index;
    setActive(index); setFollowing(true);
    const rect = area.getBoundingClientRect();
    const rowRect = (row.querySelector('.workspace-row-button') ?? row).getBoundingClientRect();
    // A stable target lets the pointer move from the row onto its screenshot.
    const y = Math.max(0, Math.min(rect.height - preview.offsetHeight, rowRect.top - rect.top + (rowRect.height - preview.offsetHeight) / 2));
    preview.style.transform = `translate3d(${rect.width * .38}px, ${y}px, 0)`;
  };
  useEffect(() => {
    if (viewer) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      const area = areaRef.current;
      if (!area) return;
      const rect = area.getBoundingClientRect();
      if (rect.bottom < 140 || rect.top > innerHeight - 80) { setFollowing(false); return; }
      if (previewRef.current?.matches(':hover, :focus-visible')) { place(activeRef.current); return; }
      const hovered = Array.from(area.querySelectorAll<HTMLElement>('.workspace-row')).findIndex(row => row.matches(':hover'));
      if (hovered >= 0) { place(hovered); return; }
      let closest = 0, distance = Infinity;
      Array.from(area.querySelectorAll<HTMLElement>('.workspace-row')).forEach((row, index) => {
        const bounds = row.getBoundingClientRect();
        const next = Math.abs(bounds.top + bounds.height / 2 - innerHeight * .52);
        if (next < distance) { distance = next; closest = index; }
      });
      place(closest);
    };
    const schedule = () => { if (!raf) raf = requestAnimationFrame(update); };
    const observer = new ResizeObserver(schedule);
    if (areaRef.current) observer.observe(areaRef.current);
    if (previewRef.current) observer.observe(previewRef.current);
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    schedule();
    return () => { cancelAnimationFrame(raf); observer.disconnect(); window.removeEventListener('scroll', schedule); window.removeEventListener('resize', schedule); };
  }, [viewer]);

  return (
    <section id="capabilities" className="workspace-index">
      <div className="workspace-inner">
        <Reveal><div className="workspace-heading"><h2>One place.<br /><span>The whole job.</span></h2><p>A model is the start.<br />Here is what you do next.</p></div></Reveal>
        <div className="workspace-rows" ref={areaRef}>
          {TOOLS.map((tool, index) => <Reveal key={tool.title} y={16} duration={650} delay={index * 65}><div className="workspace-row" data-active={active === index} onPointerEnter={() => place(index)}>
            <button type="button" className="workspace-row-button focus-ring" aria-expanded={expanded === index} aria-controls={`tool-detail-${index}`} onFocus={() => place(index)} onClick={() => setExpanded(expanded === index ? null : index)}>
              <span className="workspace-number">0{index + 1}</span><h3>{tool.title}</h3><span className="workspace-row-copy">{tool.description}</span>
              {expanded === index ? <Minus size={18} aria-hidden="true" /> : <Plus size={18} aria-hidden="true" />}
            </button>
            <button type="button" className="workspace-inline-preview focus-ring" aria-label={`Enlarge ${tool.label}`} aria-haspopup="dialog" onClick={() => setViewer(tool.screen)}><ProductScreen name={tool.screen} animate={false} /><span>{tool.label} · Enlarge ↗</span></button>
            <div id={`tool-detail-${index}`} className="workspace-row-detail" hidden={expanded !== index}><p>{tool.detail}</p><button type="button" className="workspace-open-screen focus-ring" onClick={() => setViewer(tool.screen)}>Open screenshot <ArrowUpRight size={14} aria-hidden="true" /></button></div>
          </div></Reveal>)}
          <button type="button" ref={previewRef} className={`workspace-follow focus-ring ${following ? 'is-following' : ''}`} aria-label={`Open ${TOOLS[active].label} screenshot`} aria-haspopup="dialog" onClick={() => setViewer(TOOLS[active].screen)}>
            <ProductScreen key={TOOLS[active].screen} name={TOOLS[active].screen} />
            <span>{TOOLS[active].label}<b>Click to explore ↗</b></span>
          </button>
        </div>
        <p className="workspace-footnote">Scroll or hover to preview. Click a screenshot to explore. Open a row for details.</p>
      </div>
      {viewer && <ScreenshotViewer initial={viewer} onClose={() => setViewer(null)} />}
    </section>
  );
}
