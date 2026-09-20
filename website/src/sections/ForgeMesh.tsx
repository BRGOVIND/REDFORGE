import { useEffect, useRef } from 'react';
import { createForgeMesh } from '../motion/forgeMesh';

export function ForgeMesh({ active, host = '.forge-hero-content' }: { active: boolean; host?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const hero = canvas?.closest<HTMLElement>(host);
    if (!active || !canvas || !hero) return;
    return createForgeMesh(canvas, hero);
  }, [active, host]);

  return <canvas ref={canvasRef} className="forge-mesh" aria-hidden="true" />;
}
