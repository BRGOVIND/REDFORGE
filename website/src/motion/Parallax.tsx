import React from 'react';
import { useScrollProgress } from './useScrollProgress';
import { lerp } from '../lib/cn';

interface ParallaxProps {
  children: React.ReactNode;
  className?: string;
  /** total vertical travel in px across the element's viewport pass */
  distance?: number;
}

/** Subtle depth: the element drifts as it passes through the viewport. */
export function Parallax({ children, className, distance = 80 }: ParallaxProps) {
  const [ref, progress] = useScrollProgress<HTMLDivElement>();
  const y = lerp(distance / 2, -distance / 2, progress);
  return (
    <div ref={ref} className={className} style={{ transform: `translate3d(0, ${y}px, 0)` }}>
      {children}
    </div>
  );
}
