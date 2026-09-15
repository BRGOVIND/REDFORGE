import { useEffect, useRef } from 'react';
import { createForgeMesh } from '../motion/forgeMesh';

export function ForgeMesh({ active }: { active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const hero = canvas?.closest('section');
    if (!active || !canvas || !hero) return;
    return createForgeMesh(canvas, hero);
  }, [active]);

  return <canvas ref={canvasRef} className="forge-mesh" aria-hidden="true" />;
}
