import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export const EASE_FORGE = 'cubic-bezier(0.16, 1, 0.3, 1)';

export function clamp(n: number, min = 0, max = 1): number {
  return Math.min(max, Math.max(min, n));
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}
