import React from 'react';
import { cn, EASE_FORGE } from '../lib/cn';
import { useInView } from './useInView';

interface RevealProps {
  children: React.ReactNode;
  className?: string;
  /** ms delay before this element animates in */
  delay?: number;
  /** initial vertical offset in px */
  y?: number;
  /** initial horizontal offset in px */
  x?: number;
  blur?: boolean;
  duration?: number;
  once?: boolean;
  as?: 'div' | 'span' | 'li' | 'section' | 'h2' | 'p';
}

/**
 * Slow, confident reveal — the site's primary entrance motion. Fades + eases a
 * slight translate/blur as the element enters view. (A drop-in for the
 * Framer-Motion `whileInView` the brief mentions; the API is intentionally
 * similar.)
 */
export function Reveal({
  children,
  className,
  delay = 0,
  y = 30,
  x = 0,
  blur = false,
  duration = 1000,
  once = true,
  as: Tag = 'div',
}: RevealProps) {
  const [ref, inView] = useInView<HTMLDivElement>({ once });

  const style: React.CSSProperties = {
    opacity: inView ? 1 : 0,
    transform: inView ? 'none' : `translate3d(${x}px, ${y}px, 0)`,
    filter: inView || !blur ? 'none' : 'blur(10px)',
    transition: `opacity ${duration}ms ${EASE_FORGE} ${delay}ms, transform ${duration}ms ${EASE_FORGE} ${delay}ms, filter ${duration}ms ${EASE_FORGE} ${delay}ms`,
    willChange: 'opacity, transform',
  };

  return (
    // @ts-expect-error — ref typing across the polymorphic tag union is safe here
    <Tag ref={ref} style={style} className={cn(className)}>
      {children}
    </Tag>
  );
}
