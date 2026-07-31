import { useEffect, useMemo, useState } from 'react';
import { RotateCcw, Save } from 'lucide-react';
import { Badge, Button, PageHeader, Skeleton } from '../components/ui';
import { AboutPanel } from '../components/AboutPanel';
import { errorMessage } from '../api/client';
import { toast } from '../lib/toast';
import * as api from '../api/endpoints';
import type { Setting, SettingsResponse } from '../api/types';

const INPUT = 'w-full max-w-xs rounded-lg border border-border bg-base px-3 py-2 text-xs text-content rf-focus';

/** Pseudo-category: rendered by AboutPanel, not backed by the settings schema. */
const ABOUT_KEY = '__about__';

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors rf-focus ${on ? 'bg-red-500' : 'bg-overlay'}`}
    >
      <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${on ? 'left-[18px]' : 'left-0.5'}`} />
    </button>
  );
}

function Control({ s, value, error, onChange }:
  { s: Setting; value: unknown; error?: string; onChange: (v: unknown) => void }) {
  const common = error ? `${INPUT} border-fail` : INPUT;
  let control: React.ReactNode;
  if (s.type === 'bool') {
    control = <Toggle on={!!value} onChange={onChange} />;
  } else if (s.type === 'enum') {
    control = (
      <select className={common} value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}>
        {(s.options ?? []).map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  } else if (s.type === 'int' || s.type === 'float') {
    control = (
      <div className="flex items-center gap-2">
        <input type="number" className={common} value={value as number}
          min={s.min ?? undefined} max={s.max ?? undefined}
          step={s.type === 'float' ? 'any' : 1}
          onChange={(e) => onChange(s.type === 'int' ? parseInt(e.target.value || '0', 10) : parseFloat(e.target.value || '0'))} />
        {s.unit && <span className="text-[11px] text-content-faint">{s.unit}</span>}
      </div>
    );
  } else if (s.type === 'secret') {
    control = (
      <input type="password" className={common} value={String(value ?? '')} placeholder={s.is_set ? '••••••••' : 'Not set'}
        onChange={(e) => onChange(e.target.value)} />
    );
  } else {
    control = <input type="text" className={common} value={String(value ?? '')} placeholder={s.type === 'path' ? 'path…' : ''}
      onChange={(e) => onChange(e.target.value)} />;
  }

  return (
    <div className="flex items-start justify-between gap-6 border-b border-border py-4 last:border-0">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <label className="text-[13px] font-medium text-content">{s.label}</label>
          {s.restart && <Badge tone="amber" title="Requires a restart to take effect">restart</Badge>}
          {s.is_overridden && <span className="text-[10px] text-content-faint">· customized</span>}
        </div>
        {s.description && <p className="mt-0.5 max-w-md text-[11px] leading-relaxed text-content-subtle">{s.description}</p>}
        {error && <p className="mt-1 text-[11px] text-fail">{error}</p>}
      </div>
      <div className="shrink-0 pt-0.5">{control}</div>
    </div>
  );
}

export default function SettingsPage() {
  const [data, setData] = useState<SettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<string>('');
  const [dirty, setDirty] = useState<Record<string, unknown>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.getSettings();
      setData(res);
      setActive((a) => a || res.categories[0]?.key || '');
    } catch (e) {
      toast.error('Could not load settings', errorMessage(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void load(); }, []);

  const cat = useMemo(() => data?.categories.find((c) => c.key === active), [data, active]);
  const dirtyCount = Object.keys(dirty).length;
  const valueOf = (s: Setting) => (s.key in dirty ? dirty[s.key] : s.value);

  const save = async () => {
    setSaving(true);
    setErrors({});
    try {
      const res = await api.updateSettings(dirty);
      setData(res);
      setDirty({});
      toast.success('Settings saved');
    } catch (e) {
      const detail = (e as { details?: { fields?: Record<string, string> } })?.details;
      if (detail?.fields) {
        setErrors(detail.fields);
        toast.error('Some settings could not be saved', 'Fix the highlighted fields.');
      } else {
        toast.error('Could not save settings', errorMessage(e));
      }
    } finally {
      setSaving(false);
    }
  };

  const resetAll = async () => {
    try {
      const res = await api.resetSettings();
      setData(res); setDirty({}); setErrors({});
      toast.success('Settings reset to defaults');
    } catch (e) {
      toast.error('Could not reset settings', errorMessage(e));
    }
  };

  const visible = (s: Setting) => showAdvanced || !s.advanced;

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Configure paths, behavior, and preferences. Changes persist locally."
        actions={
          active === ABOUT_KEY ? null : (
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={resetAll}><RotateCcw size={14} /> Reset all</Button>
              <Button size="sm" onClick={save} loading={saving} disabled={dirtyCount === 0}>
                <Save size={14} /> Save{dirtyCount > 0 ? ` (${dirtyCount})` : ''}
              </Button>
            </div>
          )
        }
      />

      {loading || !data ? (
        <Skeleton className="h-96" />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[200px_1fr]">
          {/* Category nav */}
          <nav className="flex flex-row flex-wrap gap-1 lg:flex-col">
            {data.categories.map((c) => (
              <button key={c.key} onClick={() => setActive(c.key)}
                className={`rounded-md px-2.5 py-1.5 text-left text-[13px] rf-focus ${
                  active === c.key ? 'bg-overlay text-content' : 'text-content-muted hover:text-content'
                }`}>
                {c.label}
              </button>
            ))}
            {/* Not a stored-settings category — version, updates and diagnostics. */}
            <button onClick={() => setActive(ABOUT_KEY)}
              className={`rounded-md px-2.5 py-1.5 text-left text-[13px] rf-focus ${
                active === ABOUT_KEY ? 'bg-overlay text-content' : 'text-content-muted hover:text-content'
              }`}>
              About &amp; Updates
            </button>
            <label className="mt-2 flex items-center gap-2 px-2.5 text-[11px] text-content-subtle">
              <input type="checkbox" checked={showAdvanced} onChange={(e) => setShowAdvanced(e.target.checked)} />
              Show advanced
            </label>
          </nav>

          {/* Settings for the active category */}
          {active === ABOUT_KEY ? <AboutPanel /> : (
          <section className="rf-card p-5">
            {cat && (
              <>
                <h2 className="text-sm font-semibold text-content">{cat.label}</h2>
                <p className="mb-3 text-[11px] text-content-subtle">{cat.description}</p>
                <div>
                  {cat.settings.filter(visible).map((s) => (
                    <Control key={s.key} s={s} value={valueOf(s)} error={errors[s.key]}
                      onChange={(v) => setDirty((d) => ({ ...d, [s.key]: v }))} />
                  ))}
                  {cat.settings.filter(visible).length === 0 && (
                    <p className="py-8 text-center text-[12px] text-content-subtle">No settings in this category.</p>
                  )}
                </div>
              </>
            )}
          </section>
          )}
        </div>
      )}
    </div>
  );
}
