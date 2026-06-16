import React, { useEffect, useState, useCallback } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  LineChart,
  Line,
  ResponsiveContainer,
} from 'recharts';
import { Shield } from 'lucide-react';
import { getDashboard, getModels } from '../services/api';
import type { DashboardMetrics, OllamaModel } from '../types';

// ─── ThreatPulse ──────────────────────────────────────────────────────────────

const ThreatPulse: React.FC = () => (
  <span className="relative inline-flex items-center ml-3 align-middle">
    <span className="animate-ping absolute inline-flex h-3 w-3 rounded-full bg-red-500 opacity-75" />
    <span className="relative inline-flex rounded-full h-3 w-3 bg-red-600" />
  </span>
);

// ─── Risk level helpers ───────────────────────────────────────────────────────

type RiskLevel = 'safe' | 'low' | 'medium' | 'high' | 'critical';

function rateToRisk(rate: number): RiskLevel {
  if (rate === 0) return 'safe';
  if (rate < 20) return 'low';
  if (rate < 45) return 'medium';
  if (rate < 70) return 'high';
  return 'critical';
}

const RISK_COLORS: Record<RiskLevel, string> = {
  safe: '#10B981',
  low: '#34D399',
  medium: '#F59E0B',
  high: '#F97316',
  critical: '#EF4444',
};

const RISK_LABELS: Record<RiskLevel, string> = {
  safe: 'Safe',
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
};

// ─── MetricCard ───────────────────────────────────────────────────────────────

interface MetricCardProps {
  title: string;
  value: number;
  unit?: string;
  risk?: RiskLevel;
}

const MetricCard: React.FC<MetricCardProps> = ({ title, value, unit, risk }) => {
  const color = risk ? RISK_COLORS[risk] : RISK_COLORS.safe;
  const label = risk ? RISK_LABELS[risk] : undefined;

  return (
    <div
      style={{ borderColor: color + '33' }}
      className="rounded-xl border bg-[#111827] p-5 flex flex-col gap-2 shadow-md"
    >
      <span className="text-xs font-semibold uppercase tracking-widest text-gray-400">{title}</span>
      <div className="flex items-end gap-2">
        <span className="text-3xl font-bold" style={{ color, fontFamily: 'JetBrains Mono, monospace' }}>
          {Number.isFinite(value) ? value.toFixed(unit === 'ms' ? 1 : 1) : '—'}
        </span>
        {unit && (
          <span className="text-sm text-gray-500 mb-1">{unit}</span>
        )}
      </div>
      {label && (
        <span
          className="text-xs font-semibold px-2 py-0.5 rounded-full w-fit"
          style={{ background: color + '22', color }}
        >
          {label}
        </span>
      )}
    </div>
  );
};

// ─── Bar chart data builder ───────────────────────────────────────────────────

interface BarDataPoint {
  category: string;
  pass: number;
  fail: number;
}

function buildBarData(breakdown: DashboardMetrics['category_breakdown']): BarDataPoint[] {
  return Object.entries(breakdown).map(([cat, stats]) => ({
    category: cat.replace(/_/g, ' '),
    pass: stats.pass,
    fail: stats.fail,
  }));
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

const Dashboard: React.FC = () => {
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [ollamaOffline, setOllamaOffline] = useState<boolean>(false);

  // Fetch models on mount
  useEffect(() => {
    (async () => {
      try {
        const result = await getModels();
        if (result.error) {
          setOllamaOffline(true);
          setModels([]);
        } else {
          setModels(result.models ?? []);
          if (result.models && result.models.length > 0) {
            setSelectedModel(result.models[0].name);
          }
        }
      } catch {
        setOllamaOffline(true);
        setModels([]);
      }
    })();
  }, []);

  // Fetch dashboard metrics when selectedModel changes
  const fetchMetrics = useCallback(async (model: string) => {
    if (!model) return;
    setLoading(true);
    setError('');
    try {
      const data = await getDashboard(model);
      setMetrics(data);
    } catch (err: unknown) {
      const apiErr = err as { detail?: string; error?: string };
      setError(apiErr?.detail ?? apiErr?.error ?? 'Failed to fetch dashboard metrics.');
      setMetrics(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedModel) {
      fetchMetrics(selectedModel);
    } else {
      setMetrics(null);
    }
  }, [selectedModel, fetchMetrics]);

  const barData: BarDataPoint[] = metrics ? buildBarData(metrics.category_breakdown) : [];
  const lineData = metrics?.daily_counts ?? [];

  const hallucinationRate = 0; // Not in DashboardMetrics; reserved slot

  return (
    <div className="min-h-screen bg-[#0A0E1A] text-gray-100 p-0">
      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div>
          <h1
            className="text-3xl font-bold text-white tracking-tight flex items-center"
            style={{ fontFamily: 'JetBrains Mono, monospace' }}
          >
            RedForge
            <ThreatPulse />
          </h1>
          <p className="text-sm text-gray-400 mt-1">LLM Security Evaluation Platform</p>
        </div>

        {/* ── Model selector ── */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500 uppercase tracking-widest">Active Model</label>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className="bg-[#1E2433] border border-[#374151] text-gray-100 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-red-600 min-w-[200px]"
            style={{ fontFamily: 'JetBrains Mono, monospace' }}
            disabled={models.length === 0}
          >
            {models.length === 0 ? (
              <option value="">No models available</option>
            ) : (
              models.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name}
                </option>
              ))
            )}
          </select>
        </div>
      </div>

      {/* ── Ollama offline banner ── */}
      {ollamaOffline && (
        <div className="mb-6 flex items-center gap-3 rounded-lg border border-red-700 bg-red-950/40 px-4 py-3 text-sm text-red-400">
          <Shield className="h-4 w-4 shrink-0" />
          Cannot connect to Ollama. Ensure it is running on port 11434.
        </div>
      )}

      {/* ── API error banner ── */}
      {error && !ollamaOffline && (
        <div className="mb-6 flex items-center gap-3 rounded-lg border border-yellow-700 bg-yellow-950/40 px-4 py-3 text-sm text-yellow-400">
          <Shield className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* ── Loading state ── */}
      {loading && (
        <div className="flex items-center gap-3 text-gray-400 text-sm mb-8 animate-pulse">
          <div className="h-2 w-2 rounded-full bg-red-500 animate-ping" />
          Loading threat data...
        </div>
      )}

      {/* ── Empty state ── */}
      {!loading && !metrics && !error && !ollamaOffline && (
        <div className="flex flex-col items-center justify-center py-24 text-gray-500 gap-4">
          <Shield className="h-12 w-12 text-gray-600" />
          <p className="text-base">Select a model to view security metrics.</p>
        </div>
      )}

      {/* ── Main content ── */}
      {!loading && metrics && (
        <>
          {/* ── Metric cards grid ── */}
          <div className="grid grid-cols-2 xl:grid-cols-3 gap-4 mb-8">
            <MetricCard
              title="Prompt Injection Rate"
              value={metrics.prompt_injection_success_rate}
              unit="%"
              risk={rateToRisk(metrics.prompt_injection_success_rate)}
            />
            <MetricCard
              title="Jailbreak Rate"
              value={metrics.jailbreak_success_rate}
              unit="%"
              risk={rateToRisk(metrics.jailbreak_success_rate)}
            />
            <MetricCard
              title="Data Leakage Risk"
              value={metrics.data_leakage_risk}
              unit="%"
              risk={rateToRisk(metrics.data_leakage_risk)}
            />
            <MetricCard
              title="Hallucination Rate"
              value={hallucinationRate}
              unit="%"
              risk={rateToRisk(hallucinationRate)}
            />
            <MetricCard
              title="Avg Latency"
              value={metrics.avg_latency_ms}
              unit="ms"
              risk="safe"
            />
            <MetricCard
              title="Total Tests"
              value={metrics.total_tests}
              risk="safe"
            />
          </div>

          {/* ── Bar chart: Category pass vs fail ── */}
          {barData.length > 0 && (
            <div className="rounded-xl border border-[#374151] bg-[#111827] p-5 mb-6">
              <h2
                className="text-sm font-semibold uppercase tracking-widest text-gray-400 mb-4"
                style={{ fontFamily: 'JetBrains Mono, monospace' }}
              >
                Attack Category Breakdown
              </h2>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={barData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis
                    dataKey="category"
                    tick={{ fill: '#9CA3AF', fontSize: 11 }}
                    axisLine={{ stroke: '#374151' }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: '#9CA3AF', fontSize: 11 }}
                    axisLine={{ stroke: '#374151' }}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{ background: '#1E2433', border: '1px solid #374151', borderRadius: 8 }}
                    labelStyle={{ color: '#F9FAFB', fontWeight: 600 }}
                    itemStyle={{ color: '#9CA3AF' }}
                  />
                  <Legend
                    wrapperStyle={{ color: '#9CA3AF', fontSize: 12 }}
                  />
                  <Bar dataKey="pass" name="Pass" fill="#10B981" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="fail" name="Fail" fill="#EF4444" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* ── Line chart: Daily test counts ── */}
          {lineData.length > 0 && (
            <div className="rounded-xl border border-[#374151] bg-[#111827] p-5">
              <h2
                className="text-sm font-semibold uppercase tracking-widest text-gray-400 mb-4"
                style={{ fontFamily: 'JetBrains Mono, monospace' }}
              >
                Daily Test Activity
              </h2>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={lineData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: '#9CA3AF', fontSize: 11 }}
                    axisLine={{ stroke: '#374151' }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: '#9CA3AF', fontSize: 11 }}
                    axisLine={{ stroke: '#374151' }}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{ background: '#1E2433', border: '1px solid #374151', borderRadius: 8 }}
                    labelStyle={{ color: '#F9FAFB', fontWeight: 600 }}
                    itemStyle={{ color: '#9CA3AF' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="count"
                    name="Tests Run"
                    stroke="#6366F1"
                    strokeWidth={2}
                    dot={{ fill: '#6366F1', r: 3 }}
                    activeDot={{ r: 5, fill: '#818CF8' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Empty chart state */}
          {barData.length === 0 && lineData.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-gray-500 gap-4">
              <Shield className="h-10 w-10 text-gray-600" />
              <p className="text-sm">No test data available for {metrics.model_name}. Run some attacks to populate metrics.</p>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default Dashboard;
