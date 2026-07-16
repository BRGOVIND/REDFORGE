import { useEffect, useRef, useState } from 'react';
import { MessageCircleQuestion, SendHorizonal, Sparkles, X } from 'lucide-react';
import { useAssistant } from '../hooks/queries';
import { assistantSuggestions } from '../api/endpoints';
import { Markdown } from './Markdown';

interface Turn {
  q: string;
  a: string;
}

/**
 * Floating RedForge Assistant — a lightweight, local knowledge helper. Mounted
 * inside the app shell only (never on the landing website or onboarding). It
 * answers from an offline knowledge base; RAG / optional web search can be
 * plugged into the same UI later. It never uploads models or datasets.
 */
export function Assistant() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const ask = useAssistant();
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && suggestions.length === 0) {
      assistantSuggestions()
        .then((s) => setSuggestions(s.suggestions))
        .catch(() => setSuggestions([]));
    }
  }, [open, suggestions.length]);

  const submit = async (question: string) => {
    const q = question.trim();
    if (!q || ask.isPending) return;
    setInput('');
    try {
      const res = await ask.mutate({ question: q });
      setTurns((t) => [...t, { q, a: res?.answer ?? 'No answer available.' }]);
      requestAnimationFrame(() => bodyRef.current?.scrollTo({ top: 1e9, behavior: 'smooth' }));
    } catch {
      setTurns((t) => [...t, { q, a: 'The assistant is unavailable right now.' }]);
    }
  };

  return (
    <>
      {/* Launcher */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="Open RedForge Assistant"
          className="fixed bottom-6 right-6 z-[110] flex h-12 w-12 items-center justify-center rounded-full bg-red-600 text-white shadow-lg transition-transform hover:scale-105 hover:bg-red-500 rf-focus"
        >
          <MessageCircleQuestion size={20} />
        </button>
      )}

      {/* Panel */}
      {open && (
        <div className="fixed bottom-6 right-6 z-[110] flex h-[30rem] w-[22rem] max-w-[calc(100vw-3rem)] flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-red-600 text-white">
                <Sparkles size={13} />
              </span>
              <div className="leading-tight">
                <p className="text-sm font-semibold text-content">Assistant</p>
                <p className="text-[10px] text-content-faint">Local · private</p>
              </div>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="rounded p-1 text-content-subtle hover:bg-overlay hover:text-content rf-focus"
              aria-label="Close assistant"
            >
              <X size={16} />
            </button>
          </div>

          <div ref={bodyRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3 text-sm">
            {turns.length === 0 ? (
              <div className="text-content-subtle">
                <p className="mb-3">Ask about attacks, evaluations, errors, or provider setup.</p>
                <div className="space-y-1.5">
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => submit(s)}
                      className="block w-full rounded-lg border border-border bg-base px-3 py-2 text-left text-xs text-content-muted hover:border-border-strong hover:text-content rf-focus"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              turns.map((t, i) => (
                <div key={i} className="space-y-2">
                  <p className="ml-auto w-fit max-w-[85%] rounded-xl bg-overlay px-3 py-2 text-xs text-content">
                    {t.q}
                  </p>
                  <Markdown className="max-w-[90%] rounded-xl border border-border bg-base px-3 py-2 text-xs text-content-muted" >
                    {t.a}
                  </Markdown>
                </div>
              ))
            )}
            {ask.isPending && <p className="text-xs text-content-faint">Thinking…</p>}
          </div>

          <div className="border-t border-border p-2.5">
            <div className="flex items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submit(input)}
                placeholder="Ask a question…"
                className="flex-1 rounded-lg border border-border bg-base px-3 py-2 text-xs text-content placeholder:text-content-faint rf-focus"
              />
              <button
                onClick={() => submit(input)}
                disabled={!input.trim() || ask.isPending}
                className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-600 text-white hover:bg-red-500 disabled:opacity-50 rf-focus"
                aria-label="Send"
              >
                <SendHorizonal size={14} />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
