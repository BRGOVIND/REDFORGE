import { useMemo, useRef, useState, type ReactNode } from 'react';
import { cn } from '../lib/cn';

export interface Column<T> {
  key: string;
  header: ReactNode;
  /** Cell renderer. */
  cell: (row: T, index: number) => ReactNode;
  /** Optional fixed/min width (Tailwind class or style handled by caller). */
  className?: string;
  /** Optional value accessor for client-side sorting. */
  sortValue?: (row: T) => string | number;
}

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T, index: number) => string;
  /** Fixed row height in px (required for windowing). */
  rowHeight?: number;
  /** Viewport height in px. */
  height?: number;
  overscan?: number;
  onRowClick?: (row: T, index: number) => void;
  empty?: ReactNode;
}

/**
 * One shared, dependency-free virtualized table. Renders only the visible window
 * of rows (fixed row height + a spacer), so a list of hundreds of thousands of
 * rows stays smooth and low-memory. Supports sticky header, client-side sort by
 * clicking a sortable column, and keyboard navigation (↑/↓, Home/End, Enter).
 *
 * Reused across the app (Dataset preview, and future: attacks, models, runs,
 * reports) — one component to maintain, one behavior everywhere.
 */
export function VirtualTable<T>({
  rows,
  columns,
  rowKey,
  rowHeight = 36,
  height = 420,
  overscan = 8,
  onRowClick,
  empty,
}: Props<T>) {
  const [scrollTop, setScrollTop] = useState(0);
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const [active, setActive] = useState(0);
  const scrollerRef = useRef<HTMLDivElement>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    // Copy before sort so we never mutate the caller's array.
    return [...rows].sort((a, b) => {
      const va = col.sortValue!(a);
      const vb = col.sortValue!(b);
      return va < vb ? -sort.dir : va > vb ? sort.dir : 0;
    });
  }, [rows, sort, columns]);

  const total = sorted.length;
  const start = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
  const visibleCount = Math.ceil(height / rowHeight) + overscan * 2;
  const end = Math.min(total, start + visibleCount);
  const slice = sorted.slice(start, end);

  const toggleSort = (key: string) =>
    setSort((s) => (s?.key === key ? { key, dir: (s.dir === 1 ? -1 : 1) as 1 | -1 } : { key, dir: 1 }));

  const moveActive = (next: number) => {
    const clamped = Math.max(0, Math.min(total - 1, next));
    setActive(clamped);
    // Keep the active row in view.
    const el = scrollerRef.current;
    if (el) {
      const top = clamped * rowHeight;
      if (top < el.scrollTop) el.scrollTop = top;
      else if (top + rowHeight > el.scrollTop + height) el.scrollTop = top + rowHeight - height;
    }
  };

  if (total === 0 && empty) return <>{empty}</>;

  return (
    <div className="overflow-hidden rounded-lg border border-border" role="grid" aria-rowcount={total}>
      {/* Sticky header */}
      <div className="flex border-b border-border bg-overlay text-[11px] font-medium text-content-subtle" role="row">
        {columns.map((c) => (
          <button
            key={c.key}
            onClick={c.sortValue ? () => toggleSort(c.key) : undefined}
            className={cn(
              'flex items-center gap-1 px-3 py-2 text-left',
              c.className ?? 'flex-1',
              c.sortValue ? 'cursor-pointer hover:text-content rf-focus' : 'cursor-default'
            )}
            role="columnheader"
            aria-sort={sort?.key === c.key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}
          >
            {c.header}
            {sort?.key === c.key && <span aria-hidden>{sort.dir === 1 ? '▲' : '▼'}</span>}
          </button>
        ))}
      </div>

      {/* Windowed body */}
      <div
        ref={scrollerRef}
        onScroll={(e) => setScrollTop((e.target as HTMLDivElement).scrollTop)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); moveActive(active + 1); }
          else if (e.key === 'ArrowUp') { e.preventDefault(); moveActive(active - 1); }
          else if (e.key === 'Home') { e.preventDefault(); moveActive(0); }
          else if (e.key === 'End') { e.preventDefault(); moveActive(total - 1); }
          else if (e.key === 'Enter' && onRowClick) { onRowClick(sorted[active], active); }
        }}
        tabIndex={0}
        className="relative overflow-y-auto rf-focus"
        style={{ height }}
      >
        <div style={{ height: total * rowHeight }}>
          <div style={{ transform: `translateY(${start * rowHeight}px)` }}>
            {slice.map((row, i) => {
              const idx = start + i;
              return (
                <div
                  key={rowKey(row, idx)}
                  role="row"
                  aria-rowindex={idx + 1}
                  onClick={() => {
                    setActive(idx);
                    onRowClick?.(row, idx);
                  }}
                  className={cn(
                    'flex items-center border-b border-border/60 text-xs',
                    idx === active ? 'bg-overlay' : 'hover:bg-overlay/50',
                    onRowClick && 'cursor-pointer'
                  )}
                  style={{ height: rowHeight }}
                >
                  {columns.map((c) => (
                    <div key={c.key} role="gridcell" className={cn('truncate px-3', c.className ?? 'flex-1')}>
                      {c.cell(row, idx)}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
