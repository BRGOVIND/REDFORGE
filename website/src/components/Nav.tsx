import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { Wordmark } from './marks';
import { cn } from '../lib/cn';

const LINKS = [
  { href: '#how', label: 'How it works' },
  { href: '#benchmark', label: 'Benchmark' },
  { href: '#local', label: 'Local' },
  { href: '#quickstart', label: 'Quickstart' },
];

export function Nav({ visible }: { visible: boolean }) {
  const [progress, setProgress] = useState(0);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    let raf = 0;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const max = document.documentElement.scrollHeight - window.innerHeight;
        setProgress(max > 0 ? window.scrollY / max : 0);
        setScrolled(window.scrollY > 40);
      });
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <header
      className={cn(
        'fixed inset-x-0 top-0 z-50 transition-all duration-700',
        visible ? 'translate-y-0 opacity-100' : '-translate-y-full opacity-0'
      )}
    >
      <div
        className={cn(
          'border-b transition-colors duration-500',
          scrolled ? 'border-steel-700/80 bg-ink/70 backdrop-blur-xl' : 'border-transparent'
        )}
      >
        <nav className="mx-auto flex max-w-editorial items-center justify-between px-6 py-4 sm:px-10">
          <a href="#top" className="focus-ring rounded" aria-label="RedForge home">
            <Wordmark />
          </a>
          <div className="hidden items-center gap-8 md:flex">
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
            className="focus-ring group flex items-center gap-2 rounded-full border border-steel-600 px-4 py-2.5 text-[13px] text-bone transition-colors duration-300 hover:border-forge hover:bg-forge/10 sm:py-2"
          >
            <Download size={14} className="text-steel-300 transition-colors group-hover:text-forge" />
            Download
          </a>
        </nav>
      </div>
      {/* Forge progress line */}
      <div
        className="h-px origin-left"
        style={{
          background: 'linear-gradient(90deg, #5A0000, #A11212, #D12A2A)',
          transform: `scaleX(${progress})`,
          transition: 'transform 120ms linear',
        }}
      />
    </header>
  );
}
