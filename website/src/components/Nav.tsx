import { useEffect, useRef, useState, type RefObject } from 'react';
import { Download } from 'lucide-react';
import { Wordmark } from './marks';
import { cn } from '../lib/cn';

const LINKS = [
  { href: '#capabilities', label: 'Platform' },
  { href: '#how', label: 'Workflow' },
  { href: '#security', label: 'Security' },
  { href: '#local', label: 'Local' },
];

export function Nav({ visible, logoRef }: { visible: boolean; logoRef: RefObject<HTMLDivElement> }) {
  const [scrolled, setScrolled] = useState(false);
  const progressRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let raf = 0;
    let wasScrolled = false;
    const compute = () => {
        raf = 0;
        const max = document.documentElement.scrollHeight - window.innerHeight;
        progressRef.current?.style.setProperty('transform', `scaleX(${max > 0 ? window.scrollY / max : 0})`);
        const next = window.scrollY > 40;
        if (next !== wasScrolled) {
          wasScrolled = next;
          setScrolled(next);
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
  }, []);

  return (
    <header
      className={cn(
        'forge-nav fixed inset-x-0 top-0',
        visible ? 'is-ready' : 'is-forging',
        visible && 'is-on-light'
      )}
    >
      <div
        className={cn(
          'border-b transition-colors duration-500',
          scrolled && visible
            ? 'border-stone-300/80 bg-[#f2efe8]/90 backdrop-blur-xl'
            : 'border-transparent'
        )}
      >
        <nav className="mx-auto flex max-w-editorial items-center justify-between px-6 py-4 sm:px-10">
          <a href="#top" className="focus-ring rounded" aria-label="RedForge home" data-forge-home>
            <div ref={logoRef} className="forge-nav-logo"><Wordmark /></div>
          </a>
          <div className="forge-nav-reveal hidden items-center gap-8 md:flex">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="focus-ring rounded text-[13px] text-steel-200 transition-colors hover:text-bone"
              >
                {l.label}
              </a>
            ))}
          </div>
          <a
            href="#download"
            className="forge-nav-reveal focus-ring group flex items-center gap-2 rounded-full border border-steel-600 px-4 py-2.5 text-[13px] text-bone transition-colors duration-300 hover:border-forge hover:bg-forge/10 sm:py-2"
          >
            <Download size={14} className="text-steel-300 transition-colors group-hover:text-forge" />
            Download
          </a>
        </nav>
      </div>
      {/* Forge progress line */}
      <div
        ref={progressRef}
        className="forge-nav-reveal h-px origin-left"
        style={{
          background: 'linear-gradient(90deg, #5A0000, #A11212, #D12A2A)',
          transform: 'scaleX(0)',
          transition: 'transform 120ms linear',
        }}
      />
    </header>
  );
}
