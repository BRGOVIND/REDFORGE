/**
 * Minimal Sonner-style toast system.
 *
 * The spec calls for `sonner`, but with no network to install it this provides
 * the same `toast.success(...) / toast.error(...)` API and a bottom-right
 * stacked, auto-dismissing toaster, styled to match the design system.
 */
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { CheckCircle2, Info, X, XCircle } from 'lucide-react';
import { cn } from './cn';

type ToastKind = 'success' | 'error' | 'info';

interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
  description?: string;
}

type Emit = (t: Omit<ToastItem, 'id'>) => void;

let emit: Emit | null = null;
let counter = 0;

export const toast = {
  success: (message: string, description?: string) =>
    emit?.({ kind: 'success', message, description }),
  error: (message: string, description?: string) =>
    emit?.({ kind: 'error', message, description }),
  info: (message: string, description?: string) =>
    emit?.({ kind: 'info', message, description }),
};

const ICONS = {
  success: <CheckCircle2 size={16} className="text-pass" />,
  error: <XCircle size={16} className="text-fail" />,
  info: <Info size={16} className="text-info" />,
};

const ToastCtx = createContext<null>(null);

export function ToasterProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  useEffect(() => {
    emit = (t) => {
      const id = ++counter;
      setToasts((prev) => [...prev, { ...t, id }]);
      window.setTimeout(() => remove(id), 4500);
    };
    return () => {
      emit = null;
    };
  }, [remove]);

  return (
    <ToastCtx.Provider value={null}>
      {children}
      <div
        className="fixed bottom-4 right-4 z-[100] flex w-[360px] max-w-[calc(100vw-2rem)] flex-col gap-2"
        aria-live="polite"
        role="status"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              'rf-card flex items-start gap-3 p-3.5 shadow-lg shadow-black/30 animate-slide-in',
              'border-border-strong'
            )}
          >
            <div className="mt-0.5">{ICONS[t.kind]}</div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-content">{t.message}</p>
              {t.description && (
                <p className="mt-0.5 text-xs text-content-muted">{t.description}</p>
              )}
            </div>
            <button
              onClick={() => remove(t.id)}
              className="rf-focus rounded p-0.5 text-content-subtle hover:text-content"
              aria-label="Dismiss notification"
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToastContext() {
  return useContext(ToastCtx);
}
