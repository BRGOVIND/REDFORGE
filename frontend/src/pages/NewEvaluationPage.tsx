import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  Check,
  Clock,
  Cpu,
  Gauge,
  HardDrive,
  Layers,
  PlayCircle,
  Zap,
} from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
  Spinner,
} from '../components/ui';
import { KeyValue } from '../components/shared';
import { useModels, useProfiles, usePlanPreview, useStartEvaluation } from '../hooks/queries';
import { errorMessage } from '../api/client';
import { toast } from '../lib/toast';
import { formatDuration, formatMB, formatNumber, titleCase } from '../lib/format';
import { cn } from '../lib/cn';
import type { EvaluationProfile } from '../api/types';

export default function NewEvaluationPage() {
  const navigate = useNavigate();
  const models = useModels();
  const profiles = useProfiles();
  const start = useStartEvaluation();

  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [profileName, setProfileName] = useState<string | null>(null);

  const profile: EvaluationProfile | undefined = useMemo(
    () => profiles.data?.find((p) => p.name === profileName),
    [profiles.data, profileName]
  );

  const preview = usePlanPreview(profileName, selectedModels);

  const toggleModel = (name: string) => {
    setSelectedModels((prev) => {
      if (profile?.multi_model) {
        return prev.includes(name) ? prev.filter((m) => m !== name) : [...prev, name];
      }
      return prev.includes(name) && prev.length === 1 ? [] : [name];
    });
  };

  const canStart = !!profileName && selectedModels.length > 0 && !start.isPending;

  const onStart = async () => {
    if (!profileName) return;
    const res = await start.mutate({ profile: profileName, models: selectedModels });
    if (res) {
      toast.success('Evaluation started', `Session ${res.session_id.slice(0, 8)}`);
      navigate(`/live/${res.session_id}`);
    } else {
      toast.error('Could not start evaluation', errorMessage(start.error));
    }
  };

  const modelList = models.data?.models ?? [];

  return (
    <div>
      <PageHeader
        title="New Evaluation"
        description="Pick a model and a profile — RedForge plans and runs everything else."
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        {/* Left: selections */}
        <div className="space-y-6 lg:col-span-3">
          <Card>
            <CardHeader title="1 · Select Model" icon={<Cpu size={15} />} subtitle={profile?.multi_model ? 'Multiple allowed for this profile' : 'Choose one'} />
            <div className="p-4">
              {models.isLoading ? (
                <div className="grid grid-cols-2 gap-2">
                  {[0, 1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-12" />
                  ))}
                </div>
              ) : modelList.length === 0 ? (
                <EmptyState
                  icon={<Cpu size={26} />}
                  title="No models found"
                  description={models.data?.error ?? 'Add a model to your runtime (for Ollama: `ollama pull llama3`), then refresh.'}
                />
              ) : (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {modelList.map((m) => {
                    const active = selectedModels.includes(m.name);
                    return (
                      <button
                        key={m.name}
                        onClick={() => toggleModel(m.name)}
                        className={cn(
                          'flex items-center justify-between rounded-lg border px-3 py-2.5 text-left text-sm transition-colors rf-focus',
                          active
                            ? 'border-red-600 bg-red-soft text-content'
                            : 'border-border bg-elevated text-content-muted hover:border-border-strong'
                        )}
                      >
                        <span className="truncate font-mono text-[13px]">{m.name}</span>
                        {active && <Check size={15} className="shrink-0 text-red-400" />}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="2 · Select Evaluation Profile" icon={<Layers size={15} />} />
            <div className="p-4">
              {profiles.isLoading ? (
                <Spinner />
              ) : (
                <div className="space-y-2">
                  {profiles.data?.map((p) => {
                    const active = p.name === profileName;
                    return (
                      <button
                        key={p.name}
                        onClick={() => {
                          setProfileName(p.name);
                          if (!p.multi_model && selectedModels.length > 1) {
                            setSelectedModels(selectedModels.slice(0, 1));
                          }
                        }}
                        className={cn(
                          'w-full rounded-lg border px-4 py-3 text-left transition-colors rf-focus',
                          active
                            ? 'border-red-600 bg-red-soft'
                            : 'border-border bg-elevated hover:border-border-strong'
                        )}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-semibold text-content">{p.display_name}</span>
                          <div className="flex items-center gap-1.5">
                            {p.multi_model && <Badge tone="grey">multi-model</Badge>}
                            <Badge tone={p.evaluator === 'llm_judge' ? 'red' : 'grey'}>
                              {p.evaluator === 'llm_judge' ? 'LLM judge' : 'heuristic'}
                            </Badge>
                          </div>
                        </div>
                        <p className="mt-1 text-xs text-content-subtle">{p.description}</p>
                        <p className="mt-1.5 text-[11px] text-content-faint">
                          {titleCase(p.dataset)} · ~{p.estimated_runtime_hint}
                        </p>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Right: live preview */}
        <div className="lg:col-span-2">
          <Card className="sticky top-8">
            <CardHeader title="3 · Preview" icon={<Gauge size={15} />} subtitle="Estimated before running" />
            <div className="p-5">
              {!profileName || selectedModels.length === 0 ? (
                <EmptyState
                  icon={<Gauge size={26} />}
                  title="Select a model and profile"
                  description="Estimates for time, memory, and LLM calls appear here."
                />
              ) : preview.isLoading ? (
                <Spinner label="Estimating…" />
              ) : preview.isError ? (
                <ErrorState message={errorMessage(preview.error)} onRetry={preview.refetch} />
              ) : preview.data ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <PreviewStat icon={<Clock size={14} />} label="Est. Time" value={formatDuration(preview.data.estimated_time.seconds)} />
                    <PreviewStat icon={<Zap size={14} />} label="LLM Calls" value={formatNumber(preview.data.estimated_llm_calls)} />
                    <PreviewStat icon={<Cpu size={14} />} label="Est. RAM" value={formatMB(preview.data.estimated_ram_mb)} />
                    <PreviewStat icon={<HardDrive size={14} />} label="Est. GPU" value={formatMB(preview.data.estimated_gpu_mb)} />
                  </div>

                  <div className="rounded-lg border border-border bg-elevated p-3">
                    <KeyValue label="Attacks" value={preview.data.execution_steps.filter((s) => s.kind === 'attack').length} />
                    <KeyValue label="Models" value={selectedModels.length} />
                    <KeyValue label="Categories" value={new Set(preview.data.execution_steps.filter((s) => s.category).map((s) => s.category)).size} />
                  </div>

                  {preview.data.warnings.length > 0 && (
                    <div className="space-y-2">
                      {preview.data.warnings.map((w, i) => (
                        <div
                          key={i}
                          className="flex items-start gap-2 rounded-lg border border-uncertain/30 bg-uncertain/10 p-2.5 text-xs text-content"
                        >
                          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-uncertain" />
                          <span>{w}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <Button className="w-full" onClick={onStart} loading={start.isPending} disabled={!canStart}>
                    <PlayCircle size={16} />
                    Start Evaluation
                  </Button>
                </div>
              ) : null}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function PreviewStat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-elevated p-3">
      <div className="flex items-center gap-1.5 text-xs text-content-subtle">
        {icon}
        {label}
      </div>
      <p className="mt-1 text-lg font-semibold text-content">{value}</p>
    </div>
  );
}
