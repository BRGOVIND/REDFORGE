import React, { useState, useEffect } from 'react';
import { getModels, evaluateHallucination } from '../services/api';
import type { OllamaModel, HallucinationResult, ApiError } from '../types';

function hallucinationColor(score: number): string {
  if (score > 0.6) return '#EF4444';
  if (score > 0.3) return '#F59E0B';
  return '#22C55E';
}

function faithfulnessColor(score: number): string {
  if (score > 0.7) return '#22C55E';
  if (score > 0.4) return '#F59E0B';
  return '#EF4444';
}

interface ScoreBarProps {
  value: number;
  color: string;
}

const ScoreBar: React.FC<ScoreBarProps> = ({ value, color }) => {
  const pct = Math.round(value * 100);
  return (
    <div
      style={{
        width: '100%',
        height: '8px',
        background: '#1E2433',
        borderRadius: '4px',
        overflow: 'hidden',
        marginTop: '8px',
      }}
    >
      <div
        style={{
          width: `${pct}%`,
          height: '100%',
          background: color,
          borderRadius: '4px',
          transition: 'width 0.5s ease',
        }}
      />
    </div>
  );
};

const Hallucination: React.FC = () => {
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [question, setQuestion] = useState<string>('');
  const [groundTruth, setGroundTruth] = useState<string>('');
  const [result, setResult] = useState<HallucinationResult | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getModels()
      .then((data) => {
        setModels(data.models);
        if (data.models.length > 0) {
          setSelectedModel(data.models[0].name);
        }
      })
      .catch(() => {
        setError('Failed to load models.');
      });
  }, []);

  const handleEvaluate = async (): Promise<void> => {
    if (!selectedModel || !question.trim() || !groundTruth.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await evaluateHallucination({
        question: question.trim(),
        ground_truth: groundTruth.trim(),
        model_name: selectedModel,
      });
      setResult(res);
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr?.detail ?? apiErr?.error ?? 'Evaluation failed.');
    } finally {
      setLoading(false);
    }
  };

  const hScore = result?.hallucination_score ?? 0;
  const fScore = result?.faithfulness_score ?? 0;
  const hColor = hallucinationColor(hScore);
  const fColor = faithfulnessColor(fScore);

  return (
    <div style={{ maxWidth: '860px', margin: '0 auto', color: '#E5E7EB', fontFamily: 'Inter, sans-serif' }}>
      {/* Header */}
      <div style={{ marginBottom: '24px' }}>
        <h2
          style={{
            fontSize: '26px',
            fontWeight: 700,
            color: '#F9FAFB',
            margin: '0 0 6px 0',
          }}
        >
          Hallucination Evaluator
        </h2>
        <p style={{ fontSize: '14px', color: '#9CA3AF', margin: 0 }}>
          Test factual accuracy and response faithfulness against ground truth
        </p>
      </div>

      {/* What is this? */}
      <div
        style={{
          background: '#1E2433',
          border: '1px solid #374151',
          borderRadius: '10px',
          padding: '16px 20px',
          marginBottom: '24px',
        }}
      >
        <p
          style={{
            fontSize: '13px',
            color: '#9CA3AF',
            margin: 0,
            lineHeight: '1.7',
          }}
        >
          <span style={{ color: '#60A5FA', fontWeight: 600 }}>What is this?</span>{' '}
          Hallucination detection sends your question to the model and compares the response against a provided ground
          truth using keyword overlap and semantic heuristics. A hallucination score close to{' '}
          <span style={{ color: '#F9FAFB', fontWeight: 600 }}>1.0</span> means the model's answer diverged
          significantly from the truth.
        </p>
      </div>

      {/* Form */}
      <div
        style={{
          background: '#131827',
          border: '1px solid #374151',
          borderRadius: '10px',
          padding: '24px',
          marginBottom: '24px',
        }}
      >
        {/* Model selector */}
        <div style={{ marginBottom: '18px' }}>
          <label style={{ display: 'block', fontSize: '13px', color: '#9CA3AF', marginBottom: '6px', fontWeight: 500 }}>
            Model
          </label>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            disabled={loading}
            style={{
              width: '100%',
              padding: '9px 12px',
              background: '#1E2433',
              border: '1px solid #374151',
              borderRadius: '6px',
              color: '#F9FAFB',
              fontSize: '14px',
              outline: 'none',
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
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

        {/* Question */}
        <div style={{ marginBottom: '18px' }}>
          <label style={{ display: 'block', fontSize: '13px', color: '#9CA3AF', marginBottom: '6px', fontWeight: 500 }}>
            Question
          </label>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={loading}
            placeholder="e.g., What is the capital of France?"
            rows={3}
            style={{
              width: '100%',
              padding: '9px 12px',
              background: '#1E2433',
              border: '1px solid #374151',
              borderRadius: '6px',
              color: '#F9FAFB',
              fontSize: '14px',
              outline: 'none',
              resize: 'vertical',
              fontFamily: 'inherit',
              boxSizing: 'border-box',
              cursor: loading ? 'not-allowed' : 'text',
            }}
          />
        </div>

        {/* Ground Truth */}
        <div style={{ marginBottom: '24px' }}>
          <label style={{ display: 'block', fontSize: '13px', color: '#9CA3AF', marginBottom: '6px', fontWeight: 500 }}>
            Ground Truth
          </label>
          <textarea
            value={groundTruth}
            onChange={(e) => setGroundTruth(e.target.value)}
            disabled={loading}
            placeholder="e.g., The capital of France is Paris."
            rows={3}
            style={{
              width: '100%',
              padding: '9px 12px',
              background: '#1E2433',
              border: '1px solid #374151',
              borderRadius: '6px',
              color: '#F9FAFB',
              fontSize: '14px',
              outline: 'none',
              resize: 'vertical',
              fontFamily: 'inherit',
              boxSizing: 'border-box',
              cursor: loading ? 'not-allowed' : 'text',
            }}
          />
        </div>

        {/* Submit */}
        <button
          onClick={handleEvaluate}
          disabled={loading || !selectedModel || !question.trim() || !groundTruth.trim()}
          style={{
            padding: '10px 28px',
            background:
              loading || !selectedModel || !question.trim() || !groundTruth.trim()
                ? '#7F1D1D'
                : '#DC2626',
            color: loading || !selectedModel || !question.trim() || !groundTruth.trim()
              ? '#9CA3AF'
              : '#FFFFFF',
            border: 'none',
            borderRadius: '7px',
            fontSize: '14px',
            fontWeight: 600,
            cursor:
              loading || !selectedModel || !question.trim() || !groundTruth.trim()
                ? 'not-allowed'
                : 'pointer',
            transition: 'background 0.2s',
          }}
        >
          {loading ? 'Evaluating...' : 'Evaluate'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            background: '#2D0A0A',
            border: '1px solid #7F1D1D',
            borderRadius: '8px',
            padding: '14px 18px',
            marginBottom: '24px',
            color: '#FCA5A5',
            fontSize: '14px',
          }}
        >
          {error}
        </div>
      )}

      {/* Loading spinner */}
      {loading && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            background: '#131827',
            border: '1px solid #374151',
            borderRadius: '10px',
            padding: '20px 24px',
            marginBottom: '24px',
          }}
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }}
          >
            <circle cx="12" cy="12" r="10" stroke="#374151" strokeWidth="3" />
            <path
              d="M12 2a10 10 0 0 1 10 10"
              stroke="#60A5FA"
              strokeWidth="3"
              strokeLinecap="round"
            />
          </svg>
          <span style={{ color: '#9CA3AF', fontSize: '14px' }}>Querying model and evaluating...</span>
          <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div
          style={{
            background: '#131827',
            border: '1px solid #374151',
            borderRadius: '10px',
            padding: '24px',
          }}
        >
          <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#F9FAFB', marginTop: 0, marginBottom: '20px' }}>
            Evaluation Results
          </h3>

          {/* Score pair */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '16px',
              marginBottom: '24px',
            }}
          >
            {/* Hallucination Score */}
            <div
              style={{
                background: '#1E2433',
                border: `1px solid ${hColor}40`,
                borderRadius: '8px',
                padding: '18px',
              }}
            >
              <p style={{ fontSize: '12px', color: '#9CA3AF', margin: '0 0 8px 0', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
                Hallucination Score
              </p>
              <p
                style={{
                  fontSize: '42px',
                  fontWeight: 800,
                  color: hColor,
                  margin: '0 0 4px 0',
                  lineHeight: 1,
                }}
              >
                {hScore.toFixed(2)}
              </p>
              <ScoreBar value={hScore} color={hColor} />
              <p style={{ fontSize: '11px', color: '#6B7280', margin: '6px 0 0 0' }}>
                {hScore > 0.6 ? 'High hallucination' : hScore > 0.3 ? 'Moderate hallucination' : 'Low hallucination'}
              </p>
            </div>

            {/* Faithfulness Score */}
            <div
              style={{
                background: '#1E2433',
                border: `1px solid ${fColor}40`,
                borderRadius: '8px',
                padding: '18px',
              }}
            >
              <p style={{ fontSize: '12px', color: '#9CA3AF', margin: '0 0 8px 0', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
                Faithfulness Score
              </p>
              <p
                style={{
                  fontSize: '42px',
                  fontWeight: 800,
                  color: fColor,
                  margin: '0 0 4px 0',
                  lineHeight: 1,
                }}
              >
                {fScore.toFixed(2)}
              </p>
              <ScoreBar value={fScore} color={fColor} />
              <p style={{ fontSize: '11px', color: '#6B7280', margin: '6px 0 0 0' }}>
                {fScore > 0.7 ? 'Highly faithful' : fScore > 0.4 ? 'Partially faithful' : 'Low faithfulness'}
              </p>
            </div>
          </div>

          {/* Model Response */}
          <div style={{ marginBottom: '20px' }}>
            <p style={{ fontSize: '13px', fontWeight: 600, color: '#9CA3AF', margin: '0 0 8px 0', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Model Response
            </p>
            <div
              style={{
                background: '#0A0E1A',
                border: '1px solid #374151',
                borderRadius: '7px',
                padding: '14px 16px',
                maxHeight: '220px',
                overflowY: 'auto',
                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                fontSize: '13px',
                color: '#D1D5DB',
                lineHeight: '1.65',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {result.model_response}
            </div>
          </div>

          {/* Explanation */}
          <div style={{ marginBottom: '24px' }}>
            <p style={{ fontSize: '13px', fontWeight: 600, color: '#9CA3AF', margin: '0 0 8px 0', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Explanation
            </p>
            <p
              style={{
                fontSize: '14px',
                color: '#D1D5DB',
                lineHeight: '1.7',
                margin: 0,
                background: '#1E2433',
                border: '1px solid #374151',
                borderRadius: '7px',
                padding: '12px 16px',
              }}
            >
              {result.explanation}
            </p>
          </div>

          {/* Interpretation guide */}
          <div
            style={{
              background: '#0A0E1A',
              border: '1px solid #374151',
              borderRadius: '7px',
              padding: '14px 18px',
            }}
          >
            <p style={{ fontSize: '12px', fontWeight: 700, color: '#6B7280', margin: '0 0 10px 0', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              Interpretation Guide
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '13px' }}>
                <span
                  style={{
                    display: 'inline-block',
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    background: '#22C55E',
                    flexShrink: 0,
                  }}
                />
                <span style={{ color: '#9CA3AF' }}>
                  <span style={{ color: '#22C55E', fontWeight: 600 }}>0.0 – 0.3:</span> Low hallucination, model
                  response is highly faithful
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '13px' }}>
                <span
                  style={{
                    display: 'inline-block',
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    background: '#F59E0B',
                    flexShrink: 0,
                  }}
                />
                <span style={{ color: '#9CA3AF' }}>
                  <span style={{ color: '#F59E0B', fontWeight: 600 }}>0.3 – 0.6:</span> Moderate hallucination,
                  some divergence from ground truth
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '13px' }}>
                <span
                  style={{
                    display: 'inline-block',
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    background: '#EF4444',
                    flexShrink: 0,
                  }}
                />
                <span style={{ color: '#9CA3AF' }}>
                  <span style={{ color: '#EF4444', fontWeight: 600 }}>0.6 – 1.0:</span> High hallucination,
                  significant factual drift detected
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Hallucination;
