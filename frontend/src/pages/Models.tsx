import React, { useEffect, useState, useCallback } from 'react';
import {
  AlertCircle,
  RefreshCw,
  Wifi,
  WifiOff,
  ChevronDown,
  ChevronUp,
  Loader2,
  Terminal,
} from 'lucide-react';
import { getModels, pingModel, getDashboard } from '../services/api';
import type { OllamaModel, PingResult, DashboardMetrics } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function inferProvider(name: string): string {
  const lower = name.toLowerCase();
  if (lower.includes('llama')) return 'Meta';
  if (lower.includes('mistral') || lower.includes('mixtral')) return 'Mistral AI';
  if (lower.includes('gemma')) return 'Google';
  if (lower.includes('phi')) return 'Microsoft';
  if (lower.includes('qwen')) return 'Alibaba';
  return 'Unknown';
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const gb = bytes / (1024 * 1024 * 1024);
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface PingBadgeProps {
  result: PingResult;
}

function PingBadge({ result }: PingBadgeProps) {
  if (result.online) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-900/50 text-emerald-400 border border-emerald-800">
        <Wifi size={11} />
        Online
        {result.latency_ms !== null && (
          <span className="text-emerald-300 ml-0.5">{result.latency_ms} ms</span>
        )}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-900/50 text-red-400 border border-red-800">
      <WifiOff size={11} />
      Offline
    </span>
  );
}

interface MetricCardProps {
  label: string;
  value: string | number;
  highlight?: boolean;
}

function MetricCard({ label, value, highlight = false }: MetricCardProps) {
  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p className={`text-xl font-semibold ${highlight ? 'text-red-400' : 'text-white'}`}>
        {value}
      </p>
    </div>
  );
}

interface MetricsPanelProps {
  metrics: DashboardMetrics;
  modelName: string;
  onClose: () => void;
}

function MetricsPanel({ metrics, modelName, onClose }: MetricsPanelProps) {
  return (
    <tr>
      <td colSpan={7} className="px-0 py-0">
        <div className="mx-4 my-3 bg-gray-800/60 rounded-xl border border-gray-700 p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-200">
              Metrics for{' '}
              <span className="text-blue-400 font-mono">{modelName}</span>
            </h3>
            <button
              onClick={onClose}
              className="text-xs text-gray-400 hover:text-gray-200 transition-colors"
            >
              Close
            </button>
          </div>

          {metrics.total_tests === 0 ? (
            <p className="text-sm text-gray-400 italic">
              No tests have been run for this model yet.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                <MetricCard label="Total Tests" value={metrics.total_tests} />
                <MetricCard
                  label="Pass Rate"
                  value={`${metrics.pass_rate}%`}
                />
                <MetricCard
                  label="Fail Rate"
                  value={`${metrics.fail_rate}%`}
                  highlight={metrics.fail_rate > 40}
                />
                <MetricCard
                  label="Avg Latency"
                  value={`${metrics.avg_latency_ms} ms`}
                />
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <MetricCard
                  label="Prompt Injection"
                  value={`${metrics.prompt_injection_success_rate}%`}
                  highlight={metrics.prompt_injection_success_rate > 50}
                />
                <MetricCard
                  label="Jailbreak"
                  value={`${metrics.jailbreak_success_rate}%`}
                  highlight={metrics.jailbreak_success_rate > 50}
                />
                <MetricCard
                  label="Context Manipulation"
                  value={`${metrics.context_manipulation_success_rate}%`}
                  highlight={metrics.context_manipulation_success_rate > 50}
                />
                <MetricCard
                  label="Data Leakage Risk"
                  value={`${metrics.data_leakage_risk}%`}
                  highlight={metrics.data_leakage_risk > 50}
                />
              </div>
            </>
          )}
        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Models() {
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [pingResults, setPingResults] = useState<Record<string, PingResult>>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [pingingModel, setPingingModel] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [modelMetrics, setModelMetrics] = useState<DashboardMetrics | null>(null);
  const [metricsLoading, setMetricsLoading] = useState<boolean>(false);

  const fetchModels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getModels();
      if (data.error) {
        setError(data.error);
        setModels([]);
      } else {
        setModels(data.models);
      }
    } catch {
      setError('Failed to connect to the backend. Is the server running?');
      setModels([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchModels();
  }, [fetchModels]);

  const handlePing = async (modelName: string) => {
    if (pingingModel !== null) return;
    setPingingModel(modelName);
    try {
      const result = await pingModel(modelName);
      setPingResults((prev) => ({ ...prev, [modelName]: result }));
    } catch {
      const fallback: PingResult = {
        model: modelName,
        online: false,
        latency_ms: null,
        error: 'Request failed',
      };
      setPingResults((prev) => ({ ...prev, [modelName]: fallback }));
    } finally {
      setPingingModel(null);
    }
  };

  const handleRowClick = async (modelName: string) => {
    if (selectedModel === modelName) {
      setSelectedModel(null);
      setModelMetrics(null);
      return;
    }
    setSelectedModel(modelName);
    setModelMetrics(null);
    setMetricsLoading(true);
    try {
      const metrics = await getDashboard(modelName);
      setModelMetrics(metrics);
    } catch {
      setModelMetrics(null);
    } finally {
      setMetricsLoading(false);
    }
  };

  const isOllamaOffline =
    error !== null && error.toLowerCase().includes('offline');

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="p-6 space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">
            Model Manager
          </h2>
          <p className="text-sm text-gray-400 mt-1">
            Ollama models available for security testing
          </p>
        </div>
        <button
          onClick={() => void fetchModels()}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-sm text-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Ollama offline error card */}
      {isOllamaOffline && (
        <div className="w-full rounded-xl border border-red-700 bg-red-950/40 p-5 flex gap-4 items-start">
          <AlertCircle className="text-red-400 mt-0.5 shrink-0" size={20} />
          <div className="space-y-2">
            <p className="text-red-300 font-semibold text-sm">
              Ollama is not reachable
            </p>
            <p className="text-red-400 text-sm">
              Cannot connect to Ollama at{' '}
              <code className="bg-red-900/60 px-1 rounded text-red-200">
                localhost:11434
              </code>
              . Make sure the Ollama service is running.
            </p>
            <div className="mt-3 bg-gray-900 rounded-lg p-3 border border-gray-700">
              <div className="flex items-center gap-2 mb-1.5">
                <Terminal size={13} className="text-gray-400" />
                <span className="text-xs text-gray-400 font-medium">
                  Start Ollama
                </span>
              </div>
              <code className="text-xs text-emerald-400 font-mono">
                ollama serve
              </code>
            </div>
            <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
              <div className="flex items-center gap-2 mb-1.5">
                <Terminal size={13} className="text-gray-400" />
                <span className="text-xs text-gray-400 font-medium">
                  Pull a model
                </span>
              </div>
              <code className="text-xs text-emerald-400 font-mono">
                ollama pull llama3
              </code>
            </div>
          </div>
        </div>
      )}

      {/* Generic (non-offline) error */}
      {error !== null && !isOllamaOffline && (
        <div className="rounded-xl border border-red-700 bg-red-950/40 p-4 flex gap-3 items-center">
          <AlertCircle className="text-red-400 shrink-0" size={18} />
          <p className="text-red-300 text-sm">{error}</p>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="animate-spin text-gray-400" size={24} />
          <span className="ml-3 text-gray-400 text-sm">
            Fetching models...
          </span>
        </div>
      )}

      {/* Table */}
      {!loading && !isOllamaOffline && (
        <div className="overflow-x-auto rounded-xl border border-gray-700">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="bg-gray-800/80 border-b border-gray-700">
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Model Name
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Provider
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Size
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Last Modified
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Tests Run
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700/50 bg-gray-900">
              {models.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center">
                    <p className="text-gray-400 text-sm">
                      No models found. Pull a model with:{' '}
                      <code className="bg-gray-800 px-2 py-0.5 rounded text-emerald-400 font-mono">
                        ollama pull llama3
                      </code>
                    </p>
                  </td>
                </tr>
              ) : (
                models.flatMap((model) => {
                  const pingResult = pingResults[model.name];
                  const isSelected = selectedModel === model.name;
                  const isPinging = pingingModel === model.name;

                  const rows: React.ReactNode[] = [
                    <tr
                      key={`row-${model.name}`}
                      onClick={() => void handleRowClick(model.name)}
                      className={`cursor-pointer transition-colors border-b border-gray-700/50 ${
                        isSelected
                          ? 'bg-gray-700/40'
                          : 'hover:bg-[#374151]/30'
                      }`}
                    >
                      {/* Model Name */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-blue-300 font-medium">
                            {model.name}
                          </span>
                          {isSelected ? (
                            <ChevronUp size={14} className="text-gray-400" />
                          ) : (
                            <ChevronDown size={14} className="text-gray-400" />
                          )}
                        </div>
                      </td>

                      {/* Provider */}
                      <td className="px-4 py-3 text-gray-300">
                        {inferProvider(model.name)}
                      </td>

                      {/* Size */}
                      <td className="px-4 py-3 text-gray-300">
                        {formatBytes(model.size)}
                      </td>

                      {/* Last Modified */}
                      <td className="px-4 py-3 text-gray-400">
                        {formatDate(model.modified_at)}
                      </td>

                      {/* Status */}
                      <td className="px-4 py-3">
                        {pingResult ? (
                          <PingBadge result={pingResult} />
                        ) : (
                          <span className="text-gray-500">—</span>
                        )}
                      </td>

                      {/* Tests Run */}
                      <td className="px-4 py-3">
                        {isSelected && metricsLoading ? (
                          <Loader2
                            size={14}
                            className="animate-spin text-gray-400"
                          />
                        ) : isSelected && modelMetrics !== null ? (
                          <span className="text-gray-200 font-medium">
                            {modelMetrics.total_tests}
                          </span>
                        ) : (
                          <span className="text-gray-500">—</span>
                        )}
                      </td>

                      {/* Actions */}
                      <td
                        className="px-4 py-3"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          onClick={() => void handlePing(model.name)}
                          disabled={isPinging || pingingModel !== null}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-700/30 hover:bg-blue-700/50 text-blue-300 border border-blue-700/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {isPinging ? (
                            <>
                              <Loader2 size={11} className="animate-spin" />
                              Pinging...
                            </>
                          ) : pingResult ? (
                            <>
                              <Wifi size={11} />
                              {pingResult.online && pingResult.latency_ms !== null
                                ? `${pingResult.latency_ms} ms`
                                : 'Ping Again'}
                            </>
                          ) : (
                            <>
                              <Wifi size={11} />
                              Ping
                            </>
                          )}
                        </button>
                      </td>
                    </tr>,
                  ];

                  // Expanded metrics panel
                  if (isSelected) {
                    if (metricsLoading) {
                      rows.push(
                        <tr key={`metrics-loading-${model.name}`}>
                          <td colSpan={7} className="px-6 py-4">
                            <div className="flex items-center gap-2 text-gray-400 text-sm">
                              <Loader2 size={14} className="animate-spin" />
                              Loading metrics...
                            </div>
                          </td>
                        </tr>
                      );
                    } else if (modelMetrics !== null) {
                      rows.push(
                        <MetricsPanel
                          key={`metrics-${model.name}`}
                          metrics={modelMetrics}
                          modelName={model.name}
                          onClose={() => {
                            setSelectedModel(null);
                            setModelMetrics(null);
                          }}
                        />
                      );
                    }
                  }

                  return rows;
                })
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
