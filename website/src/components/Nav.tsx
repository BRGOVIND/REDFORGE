import { useEffect, useRef, useState, type RefObject } from 'react';
import { Download, Menu, X, Compass } from 'lucide-react';
import { Wordmark } from './marks';
import { cn } from '../lib/cn';

const LINKS = [
  { href: '#product-tour', label: 'Inside' },
  { href: '#capabilities', label: 'Platform' },
  { href: '#how', label: 'Workflow' },
  { href: '#security', label: 'Security' },
  { href: '#local', label: 'Local' },
];

export function Nav({ visible, logoRef, onReplay }: { visible: boolean; logoRef: RefObject<HTMLDivElement>; onReplay: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const open = visible && (expanded || hovered || focused);
  const [scrolled, setScrolled] = useState(false);
  const [active, setActive] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const returnToCompass = useRef(false);
  const compassRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open && returnToCompass.current) {
      returnToCompass.current = false;
      compassRef.current?.focus({ preventScroll: true });
    }
  }, [open]);

  useEffect(() => {
    if (!expanded) return;
    const frame = requestAnimationFrame(() => document.querySelector<HTMLAnchorElement>('#forge-desktop-links a')?.focus({ preventScroll: true }));
    return () => cancelAnimationFrame(frame);
  }, [expanded]);

  useEffect(() => {
    let raf = 0;
    let wasScrolled = false;
    let previousActive = '';
    const compute = () => {
        raf = 0;
        const max = document.documentElement.scrollHeight - window.innerHeight;
        progressRef.current?.style.setProperty('transform', `scaleX(${max > 0 ? window.scrollY / max : 0})`);
        const next = window.scrollY > 40;
        if (next !== wasScrolled) {
          wasScrolled = next;
          setScrolled(next);
        }
        const section = [...LINKS, { href: '#download', label: 'Download' }].reduce((current, link) => {
          const element = document.querySelector(link.href);
          return element && element.getBoundingClientRect().top <= 160 ? link.href : current;
        }, '');
        if (section !== previousActive) { previousActive = section; setActive(section); }
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

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setMenuOpen(false); menuRef.current?.focus(); }
    };
    const desktop = matchMedia('(min-width: 900px)');
    const resize = () => { if (desktop.matches) setMenuOpen(false); };
    document.addEventListener('keydown', close);
    desktop.addEventListener('change', resize);
    return () => { document.removeEventListener('keydown', close); desktop.removeEventListener('change', resize); };
  }, [menuOpen]);

  return (
    <header
      className={cn(
        'forge-nav fixed inset-x-0 top-0',
        visible ? 'is-ready' : 'is-forging',
        visible && 'is-on-light'
      )}
    >
      <div className={cn('forge-glass-shell', scrolled && 'is-scrolled', open && 'is-expanded')} onPointerEnter={event => { if (event.pointerType !== 'touch') setHovered(true); }} onPointerLeave={() => setHovered(false)} onFocusCapture={event => { if (!(event.target as HTMLElement).closest('.forge-compass-trigger')) setFocused(true); }} onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) { setFocused(false); setExpanded(false); } }} onKeyDown={event => { if (event.key === 'Escape' && matchMedia('(min-width: 900px)').matches) { event.preventDefault(); returnToCompass.current = true; setExpanded(false); setHovered(false); setFocused(false); } }}>
        <button ref={compassRef} type="button" className="forge-compass-trigger focus-ring" aria-label="Expand navigation" aria-expanded={open} aria-controls="forge-desktop-links" onClick={() => setExpanded(true)}>
          <span>Explore</span><Compass size={19} aria-hidden="true" />
        </button>
        <div className="forge-nav-ruler forge-nav-reveal" aria-hidden="true">
          <span className="forge-nav-ticks" />
          <span ref={progressRef} className="forge-nav-progress" />
        </div>
        <nav className="forge-glass-nav" aria-label="Main navigation">
          <a href="#top" className="focus-ring rounded" aria-label="RedForge home" data-forge-home onClick={event => { event.preventDefault(); setMenuOpen(false); setExpanded(false); setHovered(false); setFocused(false); event.currentTarget.blur(); onReplay(); }}>
            <div ref={logoRef} className="forge-nav-logo"><Wordmark /></div>
          </a>
          <div id="forge-desktop-links" className="forge-nav-reveal forge-desktop-links">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="forge-dock-link focus-ring"
                aria-current={active === l.href ? 'location' : undefined}
              >
                {l.label}
              </a>
            ))}
          </div>
          <div className="forge-nav-actions forge-nav-reveal"><a
            href="#download"
            className="forge-dock-download focus-ring"
            onClick={() => setMenuOpen(false)}
          >
            <Download size={14} aria-hidden="true" />
            Download
          </a><button ref={menuRef} type="button" className="forge-menu-toggle focus-ring" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} aria-controls="forge-mobile-menu" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={19} /> : <Menu size={19} />}</button></div>
        </nav>
        <nav id="forge-mobile-menu" aria-label="Mobile navigation" className="forge-mobile-menu" hidden={!menuOpen}>
          {LINKS.map(link => <a key={link.href} href={link.href} className="focus-ring" aria-current={active === link.href ? 'location' : undefined} onClick={() => setMenuOpen(false)}>{link.label}<span aria-hidden="true">↗</span></a>)}
        </nav>
      </div>
    </header>
  );
}
