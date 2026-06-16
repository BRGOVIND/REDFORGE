import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { getModels, getAttacks, runBatch, getJobStatus, createReport } from '../services/api';
import type {
  OllamaModel,
  Attack,
  AttacksResponse,
  JobStatus,
  RunResult,
} from '../types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type RunMode = 'single' | 'category' | 'full';

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

function scoreColor(score: number): string {
  if (score >= 0.7) return '#22c55e'; // green-500
  if (score >= 0.4) return '#f59e0b'; // amber-500
  return '#ef4444'; // red-500
}

function formatPercent(score: number): string {
  return `${Math.round(score * 100)}%`;
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + '…';
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface VerdictBadgeProps {
  verdict: string;
}

const VerdictBadge: React.FC<VerdictBadgeProps> = ({ verdict }) => {
  let bg = '#374151';
  let color = '#d1d5db';
  let label = verdict;

  if (verdict === 'PASS') {
    bg = '#14532d';
    color = '#4ade80';
    label = 'PASS';
  } else if (verdict === 'FAIL') {
    bg = '#450a0a';
    color = '#f87171';
    label = 'FAIL';
  } else if (verdict === 'UNCERTAIN') {
    bg = '#451a03';
    color = '#fbbf24';
    label = 'UNCERTAIN';
  }

  return (
    <span
      style={{
        background: bg,
        color,
        fontSize: '0.7rem',
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        fontWeight: 700,
        padding: '2px 8px',
        borderRadius: '4px',
        letterSpacing: '0.05em',
        display: 'inline-block',
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  );
};

interface CategoryChipProps {
  category: string;
}

const CategoryChip: React.FC<CategoryChipProps> = ({ category }) => (
  <span
    style={{
      background: '#1e293b',
      color: '#94a3b8',
      fontSize: '0.65rem',
      fontWeight: 600,
      padding: '2px 6px',
      borderRadius: '4px',
      letterSpacing: '0.03em',
      display: 'inline-block',
      whiteSpace: 'nowrap',
    }}
  >
    {category.replace(/_/g, ' ')}
  </span>
);

interface StatusBadgeProps {
  status: 'running' | 'completed' | 'failed';
}

const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  if (status === 'running') {
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          background: '#451a03',
          color: '#fbbf24',
          fontSize: '0.75rem',
          fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          fontWeight: 700,
          padding: '4px 12px',
          borderRadius: '6px',
          letterSpacing: '0.08em',
        }}
      >
        <span
          style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: '#fbbf24',
            display: 'inline-block',
            animation: 'pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
          }}
        />
        RUNNING
      </span>
    );
  }

  if (status === 'completed') {
    return (
      <span
        style={{
          background: '#14532d',
          color: '#4ade80',
          fontSize: '0.75rem',
          fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          fontWeight: 700,
          padding: '4px 12px',
          borderRadius: '6px',
          letterSpacing: '0.08em',
        }}
      >
        COMPLETED
      </span>
    );
  }

  return (
    <span
      style={{
        background: '#450a0a',
        color: '#f87171',
        fontSize: '0.75rem',
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        fontWeight: 700,
        padding: '4px 12px',
        borderRadius: '6px',
        letterSpacing: '0.08em',
      }}
    >
      FAILED
    </span>
  );
};

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const RunTests: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // Remote data
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [attacks, setAttacks] = useState<Attack[]>([]);

  // Config panel state
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [runMode, setRunMode] = useState<RunMode>('full');
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedAttackId, setSelectedAttackId] = useState<number | null>(null);

  // Job state
  const [_jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [polling, setPolling] = useState<boolean>(false);

  // Report state
  const [reportGenerated, setReportGenerated] = useState<boolean>(false);
  const [reportId, setReportId] = useState<number | null>(null);
  const [reportGenerating, setReportGenerating] = useState<boolean>(false);

  // UI state
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ---------------------------------------------------------------------------
  // Initial data load
  // ---------------------------------------------------------------------------

  useEffect(() => {
    let mounted = true;

    async function load() {
      try {
        const [modelsRes, attacksRes] = await Promise.all([
          getModels(),
          getAttacks(),
        ]);

        if (!mounted) return;

        if (modelsRes.models) {
          setModels(modelsRes.models);
          if (modelsRes.models.length > 0) {
            setSelectedModel(modelsRes.models[0].name);
          }
        }

        const allAttacks: Attack[] = Object.values(
          (attacksRes as AttacksResponse).categories
        ).flat();
        setAttacks(allAttacks);

        // Pre-select attack from query param
        const paramId = searchParams.get('attack_id');
        if (paramId) {
          const id = parseInt(paramId, 10);
          if (!isNaN(id)) {
            setSelectedAttackId(id);
            setRunMode('single');
          }
        }
      } catch {
        if (mounted) setError('Failed to load models or attacks.');
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, [searchParams]);

  // ---------------------------------------------------------------------------
  // Polling
  // ---------------------------------------------------------------------------

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current !== null) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    setPolling(false);
  }, []);

  const startPolling = useCallback(
    (id: string) => {
      setPolling(true);

      pollIntervalRef.current = setInterval(async () => {
        try {
          const status = await getJobStatus(id);
          setJobStatus(status);

          if (status.status === 'completed' || status.status === 'failed') {
            stopPolling();
          }
        } catch {
          setError('Lost connection to job. Polling stopped.');
          stopPolling();
        }
      }, 2000);
    },
    [stopPolling]
  );

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current !== null) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Run handler
  // ---------------------------------------------------------------------------

  const handleRun = async () => {
    if (!selectedModel || polling || loading) return;

    setError(null);
    setJobId(null);
    setJobStatus(null);
    setReportGenerated(false);
    setReportId(null);
    setLoading(true);

    try {
      let category: string | undefined;

      if (runMode === 'category' && selectedCategory) {
        category = selectedCategory;
      } else if (runMode === 'single' && selectedAttackId !== null) {
        // Find the attack's category so we can filter by it (single attack not
        // directly supported by batch endpoint; we filter by category as a
        // reasonable proxy, or pass no filter to run all)
        const found = attacks.find((a) => a.id === selectedAttackId);
        category = found?.category;
      }
      // 'full' → no category filter

      const res = await runBatch({ model_name: selectedModel, category });
      setJobId(res.job_id);
      setJobStatus({
        job_id: res.job_id,
        status: 'running',
        total: res.total,
        completed: 0,
        results: [],
      });
      startPolling(res.job_id);
    } catch (err: unknown) {
      const msg =
        err && typeof err === 'object' && 'detail' in err
          ? String((err as { detail: unknown }).detail)
          : 'Failed to start test run.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Report handler
  // ---------------------------------------------------------------------------

  const handleGenerateReport = async () => {
    if (!selectedModel || reportGenerating) return;
    setReportGenerating(true);
    setError(null);
    try {
      const report = await createReport(selectedModel);
      setReportId(report.id);
      setReportGenerated(true);
    } catch (err: unknown) {
      const msg =
        err && typeof err === 'object' && 'detail' in err
          ? String((err as { detail: unknown }).detail)
          : 'Failed to generate report.';
      setError(msg);
    } finally {
      setReportGenerating(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Derived data
  // ---------------------------------------------------------------------------

  const categories = Array.from(new Set(attacks.map((a) => a.category)));
  const isRunning = polling || loading;
  const canRun = Boolean(selectedModel) && !isRunning;

  const results: RunResult[] = jobStatus?.results ?? [];
  const passCount = results.filter((r) => r.verdict === 'PASS').length;
  const failCount = results.filter((r) => r.verdict === 'FAIL').length;
  const total = jobStatus?.total ?? 0;
  const completed = jobStatus?.completed ?? 0;
  const progressPct = total > 0 ? Math.round((completed / total) * 100) : 0;
  const passRate = results.length > 0 ? Math.round((passCount / results.length) * 100) : 0;

  const isComplete = jobStatus?.status === 'completed';
  const isFailed = jobStatus?.status === 'failed';

  // ---------------------------------------------------------------------------
  // Styles (inline — consistent with the codebase's Layout.tsx approach)
  // ---------------------------------------------------------------------------

  const cardStyle: React.CSSProperties = {
    background: '#111827',
    border: '1px solid #1f2937',
    borderRadius: '12px',
    padding: '24px',
    marginBottom: '20px',
  };

  const labelStyle: React.CSSProperties = {
    color: '#9ca3af',
    fontSize: '0.75rem',
    fontWeight: 600,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    marginBottom: '8px',
    display: 'block',
  };

  const selectStyle: React.CSSProperties = {
    background: '#1e2433',
    border: '1px solid #374151',
    borderRadius: '8px',
    color: '#f3f4f6',
    fontSize: '0.875rem',
    padding: '10px 14px',
    width: '100%',
    outline: 'none',
    cursor: 'pointer',
    appearance: 'none',
  };

  const toggleBtnBase: React.CSSProperties = {
    padding: '8px 18px',
    fontSize: '0.8rem',
    fontWeight: 600,
    borderRadius: '6px',
    cursor: 'pointer',
    border: '1px solid #374151',
    transition: 'all 0.15s ease',
    letterSpacing: '0.02em',
  };

  const toggleBtnActive: React.CSSProperties = {
    ...toggleBtnBase,
    background: '#ef4444',
    color: '#fff',
    borderColor: '#ef4444',
  };

  const toggleBtnInactive: React.CSSProperties = {
    ...toggleBtnBase,
    background: 'transparent',
    color: '#9ca3af',
  };

  const runBtnStyle: React.CSSProperties = {
    padding: '11px 28px',
    background: canRun ? '#ef4444' : '#374151',
    color: canRun ? '#fff' : '#6b7280',
    border: 'none',
    borderRadius: '8px',
    fontSize: '0.875rem',
    fontWeight: 700,
    cursor: canRun ? 'pointer' : 'not-allowed',
    letterSpacing: '0.06em',
    transition: 'background 0.15s ease',
  };

  const thStyle: React.CSSProperties = {
    color: '#6b7280',
    fontSize: '0.7rem',
    fontWeight: 700,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    padding: '10px 12px',
    textAlign: 'left',
    borderBottom: '1px solid #1f2937',
    whiteSpace: 'nowrap',
  };

  const tdStyle: React.CSSProperties = {
    padding: '10px 12px',
    color: '#d1d5db',
    fontSize: '0.8rem',
    borderBottom: '1px solid #111827',
    verticalAlign: 'middle',
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div style={{ maxWidth: '1100px', margin: '0 auto' }}>
      {/* Page header */}
      <div style={{ marginBottom: '28px' }}>
        <h1
          style={{
            color: '#f9fafb',
            fontSize: '1.6rem',
            fontWeight: 700,
            margin: 0,
            letterSpacing: '-0.02em',
          }}
        >
          Run Tests
        </h1>
        <p style={{ color: '#6b7280', fontSize: '0.875rem', marginTop: '6px' }}>
          Execute adversarial attack suites against a local Ollama model.
        </p>
      </div>

      {/* Global error */}
      {error && (
        <div
          style={{
            background: '#450a0a',
            border: '1px solid #7f1d1d',
            borderRadius: '8px',
            color: '#fca5a5',
            fontSize: '0.875rem',
            padding: '12px 16px',
            marginBottom: '20px',
          }}
        >
          {error}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Config panel                                                         */}
      {/* ------------------------------------------------------------------ */}
      <div style={cardStyle}>
        <h2
          style={{
            color: '#f3f4f6',
            fontSize: '0.95rem',
            fontWeight: 700,
            margin: '0 0 20px',
            letterSpacing: '-0.01em',
          }}
        >
          Configuration
        </h2>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '20px',
            marginBottom: '20px',
          }}
        >
          {/* Model selector */}
          <div>
            <label style={labelStyle}>Model</label>
            <div style={{ position: 'relative' }}>
              <select
                style={selectStyle}
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                disabled={isRunning}
              >
                {models.length === 0 && (
                  <option value="">No models available</option>
                )}
                {models.map((m) => (
                  <option key={m.name} value={m.name}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>
            {!selectedModel && (
              <p
                style={{
                  color: '#f59e0b',
                  fontSize: '0.75rem',
                  marginTop: '6px',
                }}
              >
                Select a model to begin testing
              </p>
            )}
          </div>

          {/* Run mode */}
          <div>
            <label style={labelStyle}>Run Mode</label>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {(['single', 'category', 'full'] as RunMode[]).map((mode) => {
                const labels: Record<RunMode, string> = {
                  single: 'Single Attack',
                  category: 'By Category',
                  full: 'Full Suite',
                };
                return (
                  <button
                    key={mode}
                    style={runMode === mode ? toggleBtnActive : toggleBtnInactive}
                    onClick={() => setRunMode(mode)}
                    disabled={isRunning}
                  >
                    {labels[mode]}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Conditional selectors */}
        {runMode === 'single' && (
          <div style={{ marginBottom: '20px' }}>
            <label style={labelStyle}>Attack</label>
            <select
              style={{ ...selectStyle, maxWidth: '480px' }}
              value={selectedAttackId ?? ''}
              onChange={(e) =>
                setSelectedAttackId(e.target.value ? parseInt(e.target.value, 10) : null)
              }
              disabled={isRunning}
            >
              <option value="">Select an attack…</option>
              {attacks.map((a) => (
                <option key={a.id} value={a.id}>
                  [{a.category.replace(/_/g, ' ')}] {a.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {runMode === 'category' && (
          <div style={{ marginBottom: '20px' }}>
            <label style={labelStyle}>Category</label>
            <select
              style={{ ...selectStyle, maxWidth: '320px' }}
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              disabled={isRunning}
            >
              <option value="">Select a category…</option>
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Run button */}
        <button style={runBtnStyle} onClick={handleRun} disabled={!canRun}>
          {loading ? 'Starting…' : polling ? 'Running…' : 'Run'}
        </button>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Progress section                                                     */}
      {/* ------------------------------------------------------------------ */}
      {jobStatus && (
        <div style={cardStyle}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '16px',
              flexWrap: 'wrap',
              gap: '10px',
            }}
          >
            <h2
              style={{
                color: '#f3f4f6',
                fontSize: '0.95rem',
                fontWeight: 700,
                margin: 0,
              }}
            >
              Progress
            </h2>
            <StatusBadge status={jobStatus.status} />
          </div>

          {/* Progress bar */}
          <div
            style={{
              background: '#1f2937',
              borderRadius: '999px',
              height: '8px',
              overflow: 'hidden',
              marginBottom: '10px',
            }}
          >
            <div
              style={{
                height: '100%',
                width: `${progressPct}%`,
                background: isComplete
                  ? '#22c55e'
                  : isFailed
                  ? '#ef4444'
                  : '#ef4444',
                borderRadius: '999px',
                transition: 'width 0.4s ease',
                backgroundImage:
                  polling
                    ? 'linear-gradient(90deg, #ef4444 0%, #f87171 50%, #ef4444 100%)'
                    : undefined,
                backgroundSize: polling ? '200% 100%' : undefined,
                animation: polling ? 'shimmer 1.5s linear infinite' : undefined,
              }}
            />
          </div>

          <p
            style={{
              color: '#9ca3af',
              fontSize: '0.85rem',
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              margin: 0,
            }}
          >
            {completed} / {total} attacks complete
          </p>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Live results table                                                   */}
      {/* ------------------------------------------------------------------ */}
      {results.length > 0 && (
        <div style={cardStyle}>
          <h2
            style={{
              color: '#f3f4f6',
              fontSize: '0.95rem',
              fontWeight: 700,
              margin: '0 0 16px',
            }}
          >
            Results
          </h2>

          <div style={{ overflowX: 'auto' }}>
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                fontSize: '0.82rem',
              }}
            >
              <thead>
                <tr>
                  <th style={{ ...thStyle, width: '40px' }}>#</th>
                  <th style={thStyle}>Attack Name</th>
                  <th style={thStyle}>Category</th>
                  <th style={thStyle}>Verdict</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Score</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Latency</th>
                  <th style={thStyle}>Response Preview</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, idx) => (
                  <tr
                    key={r.id}
                    style={{
                      animation: 'fadeIn 0.3s ease forwards',
                      opacity: 1,
                    }}
                  >
                    <td
                      style={{
                        ...tdStyle,
                        color: '#6b7280',
                        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                        fontSize: '0.75rem',
                      }}
                    >
                      {idx + 1}
                    </td>
                    <td style={{ ...tdStyle, fontWeight: 600, color: '#f3f4f6' }}>
                      {r.attack_name}
                    </td>
                    <td style={tdStyle}>
                      <CategoryChip category={r.category} />
                    </td>
                    <td style={tdStyle}>
                      <VerdictBadge verdict={r.verdict} />
                    </td>
                    <td
                      style={{
                        ...tdStyle,
                        textAlign: 'right',
                        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                        fontWeight: 700,
                        color: scoreColor(r.score),
                      }}
                    >
                      {formatPercent(r.score)}
                    </td>
                    <td
                      style={{
                        ...tdStyle,
                        textAlign: 'right',
                        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                        color: '#9ca3af',
                        fontSize: '0.75rem',
                      }}
                    >
                      {r.latency_ms}ms
                    </td>
                    <td
                      style={{
                        ...tdStyle,
                        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                        color: '#6b7280',
                        fontSize: '0.72rem',
                        maxWidth: '260px',
                      }}
                    >
                      {truncate(r.model_response, 80)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* ---------------------------------------------------------------- */}
          {/* Completion summary                                                */}
          {/* ---------------------------------------------------------------- */}
          {isComplete && (
            <div
              style={{
                marginTop: '20px',
                padding: '16px',
                background: '#0f172a',
                borderRadius: '8px',
                border: '1px solid #1e293b',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '12px',
              }}
            >
              <div>
                <p
                  style={{
                    color: '#f3f4f6',
                    fontSize: '0.9rem',
                    fontWeight: 700,
                    margin: 0,
                    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  }}
                >
                  {passCount}/{results.length} passed ({passRate}%)
                </p>
                <p style={{ color: '#6b7280', fontSize: '0.8rem', margin: '4px 0 0' }}>
                  {failCount} failed · {results.length - passCount - failCount} uncertain
                </p>
              </div>

              {!reportGenerated ? (
                <button
                  style={{
                    padding: '10px 22px',
                    background: reportGenerating ? '#374151' : '#1d4ed8',
                    color: reportGenerating ? '#6b7280' : '#fff',
                    border: 'none',
                    borderRadius: '8px',
                    fontSize: '0.85rem',
                    fontWeight: 700,
                    cursor: reportGenerating ? 'not-allowed' : 'pointer',
                    letterSpacing: '0.04em',
                    transition: 'background 0.15s ease',
                  }}
                  onClick={handleGenerateReport}
                  disabled={reportGenerating}
                >
                  {reportGenerating ? 'Generating…' : 'Generate Report'}
                </button>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <span
                    style={{
                      color: '#4ade80',
                      fontSize: '0.85rem',
                      fontWeight: 600,
                    }}
                  >
                    Report generated
                  </span>
                  {reportId !== null && (
                    <button
                      style={{
                        padding: '8px 16px',
                        background: 'transparent',
                        color: '#60a5fa',
                        border: '1px solid #1d4ed8',
                        borderRadius: '6px',
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                        letterSpacing: '0.02em',
                      }}
                      onClick={() => navigate('/reports')}
                    >
                      View Reports →
                    </button>
                  )}
                </div>
              )}
            </div>
          )}

          {isFailed && (
            <div
              style={{
                marginTop: '16px',
                padding: '14px',
                background: '#450a0a',
                borderRadius: '8px',
                border: '1px solid #7f1d1d',
                color: '#fca5a5',
                fontSize: '0.875rem',
              }}
            >
              The test run failed. Check that Ollama is running and the selected model is
              available.
            </div>
          )}
        </div>
      )}

      {/* Keyframe styles injected once */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
};

export default RunTests;
