import { useEffect, useRef, useState } from 'react';

interface Options {
  once?: boolean;
  threshold?: number;
  margin?: string;
}

/** IntersectionObserver hook — the backbone of every scroll reveal. */
export function useInView<T extends HTMLElement = HTMLDivElement>({
  once = true,
  threshold = 0.15,
  margin = '0px 0px -10% 0px',
}: Options = {}): [React.RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          if (once) observer.disconnect();
        } else if (!once) {
          setInView(false);
        }
      },
      { threshold, rootMargin: margin }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [once, threshold, margin]);

  return [ref, inView];
}
