import { useState, useEffect, useRef, useCallback } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from 'recharts';
import { BarChart2, Play, RefreshCw, CheckCircle, AlertCircle, Clock } from 'lucide-react';
import {
  getModels,
  listBenchmarks,
  createBenchmark,
  getBenchmarkStatus,
  getBenchmark,
} from '../services/api';
import type { OllamaModel, BenchmarkRun, BenchmarkStatus } from '../types';

const POLL_INTERVAL_MS = 3000;

const CATEGORY_KEYS: { key: keyof BenchmarkRun['model_scores'][number]; label: string }[] = [
  { key: 'injection_rate', label: 'Prompt Injection' },
  { key: 'jailbreak_rate', label: 'Jailbreak' },
  { key: 'hallucination_rate', label: 'Context Manipulation' },
  { key: 'data_leakage_rate', label: 'Data Leakage' },
];

const BAR_COLORS = [
  '#EF4444', '#F97316', '#EAB308', '#22C55E',
  '#3B82F6', '#8B5CF6', '#EC4899', '#06B6D4',
];

function StatusBadge({ status }: { status: string }) {
  if (status === 'completed') {
    return (
      <span className="flex items-center gap-1 text-green-400 text-sm">
        <CheckCircle className="w-4 h-4" /> Completed
      </span>
    );
  }
  if (status === 'running' || status === 'pending') {
    return (
      <span className="flex items-center gap-1 text-yellow-400 text-sm animate-pulse">
        <Clock className="w-4 h-4" /> {status === 'running' ? 'Running…' : 'Pending…'}
      </span>
    );
  }
  if (status === 'failed') {
    return (
      <span className="flex items-center gap-1 text-red-400 text-sm">
        <AlertCircle className="w-4 h-4" /> Failed
      </span>
    );
  }
  return <span className="text-gray-400 text-sm">{status}</span>;
}

export default function Comparison() {
  const [availableModels, setAvailableModels] = useState<OllamaModel[]>([]);
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [benchmarkName, setBenchmarkName] = useState('');
  const [pastRuns, setPastRuns] = useState<BenchmarkRun[]>([]);
  const [activeBenchmark, setActiveBenchmark] = useState<BenchmarkRun | null>(null);
  const [jobStatus, setJobStatus] = useState<BenchmarkStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback((benchmarkId: number) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const status = await getBenchmarkStatus(benchmarkId);
        setJobStatus(status);
        if (status.status === 'completed' || status.status === 'failed') {
          stopPolling();
          const full = await getBenchmark(benchmarkId);
          setActiveBenchmark(full);
          setPastRuns(prev => [full, ...prev.filter(r => r.id !== full.id)]);
        }
      } catch {
        stopPolling();
      }
    }, POLL_INTERVAL_MS);
  }, [stopPolling]);

  useEffect(() => {
    getModels().then(res => setAvailableModels(res.models ?? [])).catch(() => {});
    listBenchmarks().then(setPastRuns).catch(() => {});
    return () => stopPolling();
  }, [stopPolling]);

  const toggleModel = (name: string) => {
    setSelectedModels(prev =>
      prev.includes(name) ? prev.filter(m => m !== name) : [...prev, name]
    );
  };

  const handleRunBenchmark = async () => {
    if (selectedModels.length < 2) {
      setError('Select at least 2 models to compare.');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const run = await createBenchmark({
        name: benchmarkName.trim() || `Benchmark ${new Date().toLocaleString()}`,
        model_list: selectedModels,
      });
      setActiveBenchmark(run);
      setJobStatus({ benchmark_run_id: run.id, status: 'pending', progress: 0 });
      startPolling(run.id);
    } catch (e: unknown) {
      const err = e as { detail?: string };
      setError(err.detail ?? 'Failed to start benchmark');
    } finally {
      setLoading(false);
    }
  };

  const handleLoadRun = async (run: BenchmarkRun) => {
    if (run.status === 'running' || run.status === 'pending') {
      setActiveBenchmark(run);
      setJobStatus({ benchmark_run_id: run.id, status: run.status, progress: 0 });
      startPolling(run.id);
    } else {
      const full = await getBenchmark(run.id).catch(() => run);
      setActiveBenchmark(full);
      setJobStatus(null);
    }
  };

  // ---- chart data ----

  const barData = CATEGORY_KEYS.map(({ key, label }) => {
    const entry: Record<string, number | string> = { category: label };
    activeBenchmark?.model_scores.forEach(ms => {
      entry[ms.model_name] = Math.round((ms[key] as number) * 100);
    });
    return entry;
  });

  const radarData = CATEGORY_KEYS.map(({ key, label }) => {
    const entry: Record<string, number | string> = { subject: label };
    activeBenchmark?.model_scores.forEach(ms => {
      entry[ms.model_name] = Math.round((ms[key] as number) * 100);
    });
    return entry;
  });

  const modelNames = activeBenchmark?.model_scores.map(ms => ms.model_name) ?? [];

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6">
      <div className="max-w-7xl mx-auto space-y-8">

        {/* Header */}
        <div className="flex items-center gap-3">
          <BarChart2 className="w-8 h-8 text-red-500" />
          <div>
            <h1 className="text-2xl font-bold">Compare Models</h1>
            <p className="text-gray-400 text-sm">Run the full attack suite across multiple models and compare vulnerability rates</p>
          </div>
        </div>

        {/* Setup panel */}
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 space-y-4">
          <h2 className="text-lg font-semibold">New Benchmark</h2>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Benchmark Name (optional)</label>
            <input
              type="text"
              value={benchmarkName}
              onChange={e => setBenchmarkName(e.target.value)}
              placeholder="e.g. Sprint 42 models"
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-1 focus:ring-red-500"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-2">Select Models (≥ 2)</label>
            {availableModels.length === 0 ? (
              <p className="text-gray-500 text-sm">No models available — ensure Ollama is running.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {availableModels.map(m => (
                  <button
                    key={m.name}
                    onClick={() => toggleModel(m.name)}
                    className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                      selectedModels.includes(m.name)
                        ? 'bg-red-600 border-red-500 text-white'
                        : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-500'
                    }`}
                  >
                    {m.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          <button
            onClick={handleRunBenchmark}
            disabled={loading || selectedModels.length < 2}
            className="flex items-center gap-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed px-5 py-2 rounded-lg font-medium text-sm transition-colors"
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {loading ? 'Starting…' : 'Run Benchmark'}
          </button>
        </div>

        {/* Progress bar */}
        {jobStatus && (jobStatus.status === 'running' || jobStatus.status === 'pending') && (
          <div className="bg-gray-900 rounded-xl p-5 border border-gray-800 space-y-2">
            <div className="flex justify-between text-sm text-gray-400">
              <span>Running benchmark…</span>
              <span>{jobStatus.progress}%</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className="bg-red-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${jobStatus.progress}%` }}
              />
            </div>
          </div>
        )}

        {/* Results */}
        {activeBenchmark && activeBenchmark.status === 'completed' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">{activeBenchmark.name}</h2>
              <StatusBadge status={activeBenchmark.status} />
            </div>

            {/* Score table */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="text-left px-4 py-3 text-gray-400">Model</th>
                    <th className="text-right px-4 py-3 text-gray-400">Overall Score</th>
                    <th className="text-right px-4 py-3 text-gray-400">Injection %</th>
                    <th className="text-right px-4 py-3 text-gray-400">Jailbreak %</th>
                    <th className="text-right px-4 py-3 text-gray-400">Ctx Manip %</th>
                    <th className="text-right px-4 py-3 text-gray-400">Data Leak %</th>
                    <th className="text-right px-4 py-3 text-gray-400">Avg Latency</th>
                  </tr>
                </thead>
                <tbody>
                  {activeBenchmark.model_scores
                    .slice()
                    .sort((a, b) => b.overall_score - a.overall_score)
                    .map((ms, i) => (
                      <tr key={ms.model_name} className={i % 2 === 0 ? 'bg-gray-900' : 'bg-gray-950'}>
                        <td className="px-4 py-3 font-medium">{ms.model_name}</td>
                        <td className="text-right px-4 py-3">
                          <span className={`font-bold ${ms.overall_score >= 70 ? 'text-green-400' : ms.overall_score >= 40 ? 'text-yellow-400' : 'text-red-400'}`}>
                            {ms.overall_score.toFixed(1)}
                          </span>
                        </td>
                        <td className="text-right px-4 py-3 text-red-300">{(ms.injection_rate * 100).toFixed(1)}%</td>
                        <td className="text-right px-4 py-3 text-orange-300">{(ms.jailbreak_rate * 100).toFixed(1)}%</td>
                        <td className="text-right px-4 py-3 text-yellow-300">{(ms.hallucination_rate * 100).toFixed(1)}%</td>
                        <td className="text-right px-4 py-3 text-purple-300">{(ms.data_leakage_rate * 100).toFixed(1)}%</td>
                        <td className="text-right px-4 py-3 text-gray-300">{ms.avg_latency_ms.toFixed(0)} ms</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
                <h3 className="text-sm font-medium text-gray-400 mb-4">Failure Rate by Category (%)</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={barData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="category" tick={{ fill: '#9CA3AF', fontSize: 11 }} />
                    <YAxis domain={[0, 100]} tick={{ fill: '#9CA3AF', fontSize: 11 }} unit="%" />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151' }}
                      formatter={(v: number) => `${v}%`}
                    />
                    <Legend />
                    {modelNames.map((name, i) => (
                      <Bar key={name} dataKey={name} fill={BAR_COLORS[i % BAR_COLORS.length]} radius={[3, 3, 0, 0]} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
                <h3 className="text-sm font-medium text-gray-400 mb-4">Vulnerability Radar (%)</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="#374151" />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: '#9CA3AF', fontSize: 11 }} />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: '#6B7280', fontSize: 10 }} />
                    {modelNames.map((name, i) => (
                      <Radar
                        key={name}
                        name={name}
                        dataKey={name}
                        stroke={BAR_COLORS[i % BAR_COLORS.length]}
                        fill={BAR_COLORS[i % BAR_COLORS.length]}
                        fillOpacity={0.15}
                      />
                    ))}
                    <Legend />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151' }}
                      formatter={(v: number) => `${v}%`}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}

        {/* Past runs */}
        {pastRuns.length > 0 && (
          <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
            <h2 className="text-sm font-medium text-gray-400 mb-3">Past Benchmarks</h2>
            <div className="space-y-2">
              {pastRuns.map(run => (
                <button
                  key={run.id}
                  onClick={() => handleLoadRun(run)}
                  className="w-full flex items-center justify-between px-4 py-3 bg-gray-800 hover:bg-gray-750 rounded-lg text-left transition-colors"
                >
                  <div>
                    <p className="font-medium text-sm">{run.name}</p>
                    <p className="text-xs text-gray-500">{run.model_list.join(', ')} · {new Date(run.created_at).toLocaleString()}</p>
                  </div>
                  <StatusBadge status={run.status} />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
