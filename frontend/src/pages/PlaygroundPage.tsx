import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Copy,
  Download,
  Loader2,
  SendHorizonal,
  ShieldAlert,
  Sparkles,
  Trash2,
  User,
} from 'lucide-react';
import { Boxes } from 'lucide-react';
import { Badge, Button, Card, PageHeader } from '../components/ui';
import {
  useModelCatalog,
  usePlaygroundChat,
  useRegisteredModels,
  useStartEvaluation,
} from '../hooks/queries';
import { toast } from '../lib/toast';
import type { ChatMessage } from '../api/types';

const DEFAULTS = { temperature: 0.7, top_p: 0.9, max_tokens: 512, seed: '' as number | '' };

export default function PlaygroundPage() {
  const navigate = useNavigate();
  const catalog = useModelCatalog(0, true);
  const chat = usePlaygroundChat();
  const startEval = useStartEvaluation();

  const groups = catalog.data?.providers ?? [];
  const online = groups.filter((g) => g.online && g.models.length > 0);
  const [provider, setProvider] = useState<string>('');
  const activeProvider = provider || catalog.data?.default || online[0]?.provider || '';
  const models = useMemo(
    () => groups.find((g) => g.provider === activeProvider)?.models ?? [],
    [groups, activeProvider]
  );
  const [model, setModel] = useState<string>('');
  const activeModel = model || models[0]?.name || '';

  // Runtime-registered checkpoints (Phase 2.5): every completed checkpoint that
  // was registered through the Runtime Manager can be chatted with here. Each one
  // resolves to a `runtime_model` usable exactly like any base model.
  const registered = useRegisteredModels();
  const checkpoints = registered.data ?? [];
  const [activeCheckpoint, setActiveCheckpoint] = useState<string | null>(null);

  const selectCheckpoint = (id: string, provider: string, runtimeModel: string) => {
    setActiveCheckpoint(id);
    setProvider(provider);
    setModel(runtimeModel);
  };

  const [system, setSystem] = useState('');
  const [temperature, setTemperature] = useState(DEFAULTS.temperature);
  const [topP, setTopP] = useState(DEFAULTS.top_p);
  const [maxTokens, setMaxTokens] = useState(DEFAULTS.max_tokens);
  const [seed, setSeed] = useState<number | ''>(DEFAULTS.seed);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollDown = () =>
    requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: 1e9, behavior: 'smooth' }));

  const send = async () => {
    const text = input.trim();
    if (!text || !activeModel || chat.isPending) return;
    const next: ChatMessage[] = [...messages, { role: 'user', content: text }];
    setMessages(next);
    setInput('');
    scrollDown();
    try {
      const res = await chat.mutate({
        model: activeModel,
        messages: next,
        params: {
          provider: activeProvider || undefined,
          system: system || undefined,
          temperature,
          top_p: topP,
          max_tokens: maxTokens,
          seed: seed === '' ? undefined : Number(seed),
        },
      });
      if (res) {
        setMessages((m) => [...m, { role: 'assistant', content: res.response }]);
        scrollDown();
      }
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: `⚠ Generation failed. Check the runtime on the Runtime page.` },
      ]);
      toast.error('Generation failed', String((e as Error)?.message ?? ''));
    }
  };

  const clear = () => setMessages([]);
  const copy = (text: string) => {
    void navigator.clipboard.writeText(text).then(
      () => toast.success('Copied'),
      () => toast.error('Copy failed')
    );
  };
  const exportConversation = () => {
    const blob = new Blob([JSON.stringify({ model: activeModel, provider: activeProvider, system, messages }, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `playground-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const runSecurityEval = async () => {
    if (!activeModel) return;
    try {
      const res = await startEval.mutate({ profile: 'quick_scan', models: [activeModel] });
      if (res?.session_id) {
        toast.success('Security evaluation started', activeModel);
        navigate(`/live/${res.session_id}`);
      }
    } catch {
      toast.error('Could not start evaluation', 'Is RedForge running with a reachable model?');
    }
  };

  return (
    <div>
      <PageHeader
        title="Playground"
        description="Chat with any configured provider, tune sampling, and jump straight into a security evaluation."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={exportConversation} disabled={!messages.length}>
              <Download size={14} /> Export
            </Button>
            <Button variant="ghost" size="sm" onClick={clear} disabled={!messages.length}>
              <Trash2 size={14} /> Clear
            </Button>
            <Button variant="danger" size="sm" onClick={runSecurityEval} loading={startEval.isPending} disabled={!activeModel}>
              <ShieldAlert size={14} /> Run Security Evaluation
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_300px]">
        {/* Chat column */}
        <Card className="flex h-[calc(100vh-300px)] min-h-[420px] flex-col overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border px-4 py-2.5 text-xs text-content-subtle">
            <Sparkles size={13} className="text-red-400" />
            {activeModel ? (
              <span>
                <span className="text-content">{activeProvider}</span> · {activeModel}
              </span>
            ) : (
              <span>No model available — configure a provider on the Runtime page.</span>
            )}
          </div>

          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
            {messages.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-content-subtle">
                <Sparkles size={26} className="text-content-faint" />
                <p>Start a conversation. Responses run through the Runtime Manager.</p>
              </div>
            ) : (
              messages.map((m, i) => <Bubble key={i} message={m} onCopy={() => copy(m.content)} />)
            )}
            {chat.isPending && (
              <div className="flex items-center gap-2 text-xs text-content-subtle">
                <Loader2 size={13} className="animate-spin" /> Generating…
              </div>
            )}
          </div>

          <div className="border-t border-border p-3">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
                rows={1}
                placeholder={activeModel ? 'Message… (Enter to send, Shift+Enter for newline)' : 'No model available'}
                disabled={!activeModel}
                className="max-h-40 flex-1 resize-none rounded-lg border border-border bg-base px-3 py-2 text-sm text-content placeholder:text-content-faint rf-focus disabled:opacity-50"
              />
              <Button onClick={send} loading={chat.isPending} disabled={!activeModel || !input.trim()}>
                <SendHorizonal size={15} />
              </Button>
            </div>
          </div>
        </Card>

        {/* Params column */}
        <div className="space-y-4">
          <Card className="p-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-content-subtle">Model</p>
            <label className="mb-2 block text-xs text-content-subtle">Provider</label>
            <select
              value={activeProvider}
              onChange={(e) => {
                setProvider(e.target.value);
                setModel('');
                setActiveCheckpoint(null);
              }}
              className="mb-3 w-full rounded-lg border border-border bg-base px-2 py-2 text-sm text-content rf-focus"
            >
              {online.length === 0 && <option value="">No online provider</option>}
              {online.map((g) => (
                <option key={g.provider} value={g.provider}>
                  {g.label}
                </option>
              ))}
            </select>
            <label className="mb-2 block text-xs text-content-subtle">Model</label>
            <select
              value={activeModel}
              onChange={(e) => {
                setModel(e.target.value);
                setActiveCheckpoint(null);
              }}
              disabled={!models.length}
              className="w-full rounded-lg border border-border bg-base px-2 py-2 text-sm text-content rf-focus disabled:opacity-50"
            >
              {models.length === 0 && <option value="">No models</option>}
              {models.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name}
                </option>
              ))}
            </select>
          </Card>

          {checkpoints.length > 0 && (
            <Card className="p-4">
              <p className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">
                <Boxes size={13} /> Runtime checkpoints
              </p>
              <p className="mb-3 text-[11px] text-content-faint">
                Chat with a trained checkpoint. Registered through the Runtime Manager — resolves to
                its runnable model.
              </p>
              <div className="space-y-1.5">
                {checkpoints.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => selectCheckpoint(c.id, c.provider, c.runtime_model)}
                    className={`flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-xs rf-focus ${
                      activeCheckpoint === c.id
                        ? 'border-red-500 bg-red-soft'
                        : 'border-border hover:border-border-strong'
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-content">{c.label}</span>
                      <span className="block truncate text-[11px] text-content-subtle">
                        {c.runtime_model}
                      </span>
                    </span>
                    {c.fallback && <Badge tone="grey">base</Badge>}
                  </button>
                ))}
              </div>
            </Card>
          )}

          <Card className="p-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-content-subtle">Parameters</p>
            <label className="mb-1 block text-xs text-content-subtle">System prompt</label>
            <textarea
              value={system}
              onChange={(e) => setSystem(e.target.value)}
              rows={3}
              placeholder="Optional system instructions…"
              className="mb-3 w-full resize-none rounded-lg border border-border bg-base px-2 py-2 text-xs text-content placeholder:text-content-faint rf-focus"
            />
            <Slider label="Temperature" value={temperature} min={0} max={2} step={0.05} onChange={setTemperature} />
            <Slider label="Top-p" value={topP} min={0} max={1} step={0.05} onChange={setTopP} />
            <NumberField label="Max tokens" value={maxTokens} onChange={setMaxTokens} min={1} />
            <div className="mt-3">
              <label className="mb-1 block text-xs text-content-subtle">Seed (optional)</label>
              <input
                type="number"
                value={seed}
                onChange={(e) => setSeed(e.target.value === '' ? '' : Number(e.target.value))}
                placeholder="random"
                className="w-full rounded-lg border border-border bg-base px-2 py-1.5 text-sm text-content rf-focus"
              />
            </div>
          </Card>

          <p className="px-1 text-[11px] text-content-faint">
            All generation flows through the Runtime Manager — providers are never called directly.
          </p>
        </div>
      </div>
    </div>
  );
}

function Bubble({ message, onCopy }: { message: ChatMessage; onCopy: () => void }) {
  const isUser = message.role === 'user';
  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <span
        className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
          isUser ? 'bg-overlay text-content-muted' : 'bg-red-600 text-white'
        }`}
      >
        {isUser ? <User size={14} /> : <Sparkles size={14} />}
      </span>
      <div className={`group max-w-[80%] ${isUser ? 'text-right' : ''}`}>
        <div
          className={`whitespace-pre-wrap rounded-xl px-3.5 py-2.5 text-sm ${
            isUser ? 'bg-overlay text-content' : 'border border-border bg-surface text-content'
          }`}
        >
          {message.content}
        </div>
        {!isUser && (
          <button
            onClick={onCopy}
            className="mt-1 inline-flex items-center gap-1 text-[11px] text-content-faint opacity-0 transition-opacity hover:text-content group-hover:opacity-100 rf-focus"
          >
            <Copy size={11} /> Copy
          </button>
        )}
      </div>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="mb-3">
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-content-subtle">{label}</span>
        <span className="font-mono text-content">{value.toFixed(2)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-red-500"
      />
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-content-subtle">{label}</label>
      <input
        type="number"
        min={min}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded-lg border border-border bg-base px-2 py-1.5 text-sm text-content rf-focus"
      />
    </div>
  );
}
