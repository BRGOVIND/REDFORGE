import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAttacks } from '../services/api';
import type { Attack, AttackCategory, AttacksResponse } from '../types';

// ---------------------------------------------------------------------------
// AttackCard component (inline — no separate file required by the spec)
// ---------------------------------------------------------------------------

const SEVERITY_COLORS: Record<string, string> = {
  low: 'text-green-400 bg-green-400/10 border-green-400/30',
  medium: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
  high: 'text-orange-400 bg-orange-400/10 border-orange-400/30',
  critical: 'text-red-400 bg-red-400/10 border-red-400/30',
};

interface AttackCardProps {
  attack: Attack;
  onRun: (id: number) => void;
}

function AttackCard({ attack, onRun }: AttackCardProps) {
  const severityClass = SEVERITY_COLORS[attack.severity] ?? SEVERITY_COLORS.medium;

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-5 flex flex-col gap-3 hover:border-gray-500 transition-colors">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-white font-semibold text-sm leading-snug">{attack.name}</h3>
        <span
          className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded border capitalize ${severityClass}`}
        >
          {attack.severity}
        </span>
      </div>

      {/* Description */}
      <p className="text-gray-400 text-xs leading-relaxed flex-1">{attack.description}</p>

      {/* Prompt preview */}
      <div className="bg-gray-900 rounded p-3 border border-gray-700">
        <p className="text-gray-300 text-xs font-mono line-clamp-3 whitespace-pre-wrap break-words">
          {attack.prompt}
        </p>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between mt-1">
        <span className="text-gray-500 text-xs">ID #{attack.id}</span>
        <button
          onClick={() => onRun(attack.id)}
          className="text-xs font-medium px-3 py-1.5 rounded bg-red-600 hover:bg-red-500 text-white transition-colors"
        >
          Run Attack
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Category metadata
// ---------------------------------------------------------------------------

interface CategoryMeta {
  label: string;
  description: string;
}

const CATEGORY_META: Record<AttackCategory, CategoryMeta> = {
  PROMPT_INJECTION: {
    label: 'Prompt Injection',
    description: 'Tests model resistance to instruction override attempts',
  },
  JAILBREAK: {
    label: 'Jailbreak',
    description: 'Evaluates effectiveness of safety guardrail bypass techniques',
  },
  CONTEXT_MANIPULATION: {
    label: 'Context Manipulation',
    description: 'Probes susceptibility to false context and social engineering',
  },
  DATA_LEAKAGE: {
    label: 'Data Leakage',
    description: 'Assesses risk of system prompt and training data extraction',
  },
};

const CATEGORY_ORDER: AttackCategory[] = [
  'PROMPT_INJECTION',
  'JAILBREAK',
  'CONTEXT_MANIPULATION',
  'DATA_LEAKAGE',
];

// ---------------------------------------------------------------------------
// Attacks page
// ---------------------------------------------------------------------------

export default function Attacks() {
  const navigate = useNavigate();
  const [attacks, setAttacks] = useState<AttacksResponse | null>(null);
  const [activeCategory, setActiveCategory] = useState<AttackCategory>('PROMPT_INJECTION');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchAttacks() {
      setLoading(true);
      setError(null);
      try {
        const data = await getAttacks();
        if (!cancelled) {
          setAttacks(data);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const message =
            err !== null &&
            typeof err === 'object' &&
            'detail' in err &&
            typeof (err as Record<string, unknown>).detail === 'string'
              ? (err as Record<string, unknown>).detail as string
              : 'Failed to load attacks. Please try again.';
          setError(message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void fetchAttacks();
    return () => {
      cancelled = true;
    };
  }, []);

  function handleRun(id: number) {
    navigate(`/run?attack_id=${id}`);
  }

  const categoryAttacks: Attack[] = attacks?.categories[activeCategory] ?? [];

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 w-full">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-red-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-400 text-sm">Loading attack library…</p>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Error state
  // ---------------------------------------------------------------------------
  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/20 border border-red-700 rounded-lg p-5">
          <h3 className="text-red-400 font-semibold mb-1">Error loading attacks</h3>
          <p className="text-red-300 text-sm">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 text-xs font-medium px-3 py-1.5 rounded bg-red-700 hover:bg-red-600 text-white transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Empty state (data loaded but null — shouldn't normally happen)
  // ---------------------------------------------------------------------------
  if (!attacks) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
        No attacks loaded
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Main render
  // ---------------------------------------------------------------------------
  return (
    <div className="p-6 space-y-6">
      {/* Page header */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <h2 className="text-2xl font-bold text-white">Attack Library</h2>
          <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-red-600/20 text-red-400 border border-red-600/40">
            {attacks.total} total
          </span>
        </div>
        <p className="text-gray-400 text-sm">
          Pre-built adversarial prompts for LLM security testing
        </p>
      </div>

      {/* Category tabs */}
      <div>
        <div className="flex gap-0 border-b border-gray-700 overflow-x-auto">
          {CATEGORY_ORDER.map((cat) => {
            const count = (attacks.categories[cat] ?? []).length;
            const isActive = cat === activeCategory;
            return (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                className={[
                  'flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors focus:outline-none',
                  isActive
                    ? 'border-red-500 text-white'
                    : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500',
                ].join(' ')}
              >
                {CATEGORY_META[cat].label}
                <span
                  className={[
                    'text-xs px-1.5 py-0.5 rounded-full font-semibold',
                    isActive
                      ? 'bg-red-600/30 text-red-300'
                      : 'bg-gray-700 text-gray-400',
                  ].join(' ')}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Category description */}
        <p className="text-gray-500 text-xs mt-3">
          {CATEGORY_META[activeCategory].description}
        </p>
      </div>

      {/* Attacks grid */}
      {categoryAttacks.length === 0 ? (
        <div className="flex items-center justify-center h-40 text-gray-500 text-sm">
          No attacks loaded
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {categoryAttacks.map((attack) => (
            <AttackCard key={attack.id} attack={attack} onRun={handleRun} />
          ))}
        </div>
      )}
    </div>
  );
}
