/** Shared API types — mirror the Sprint 1–3 backend response shapes. */

export interface OllamaModel {
  name: string;
  size?: number;
  digest?: string;
  modified_at?: string;
}

export interface ModelsResponse {
  models: OllamaModel[];
  error?: string;
}

// --- Sessions (Sprint 1) ---------------------------------------------------

export type SessionStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface SessionResponse {
  id: string;
  session_type: string;
  status: SessionStatus;
  selected_models: string[];
  selected_categories: string[];
  selected_tier: string | null;
  total_tasks: number;
  completed_tasks: number;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  estimated_seconds: number | null;
  actual_seconds: number | null;
  metadata: Record<string, unknown> | null;
}

export interface EvaluationEvent {
  id: number;
  session_id: string;
  timestamp: string | null;
  event_type: string;
  model_name: string | null;
  category: string | null;
  attack_name: string | null;
  response_excerpt: string | null;
  verdict: string | null;
  latency_ms: number | null;
  metadata: Record<string, unknown> | null;
}

// --- Evaluation profiles & engine (Sprint 2) -------------------------------

export interface MutationConfig {
  enabled: boolean;
  count: number;
  mode: string;
}

export interface EvaluationProfile {
  name: string;
  display_name: string;
  description: string;
  purpose: string;
  dataset: string;
  categories: string[];
  attacks_per_category: number | null;
  benchmark_sample_size: number | null;
  evaluator: string;
  judge_model: string | null;
  mutation: MutationConfig;
  checkpoint: { enabled: boolean; frequency: number };
  retry: { enabled: boolean; max_retries: number; retry_on: string[] };
  timeout_seconds: number;
  passes: number;
  multi_model: boolean;
  adaptive_agent: boolean;
  generate_leaderboard: boolean;
  generate_report: boolean;
  estimated_runtime_hint: string;
}

export interface PlanStep {
  order: number;
  kind: string;
  description: string;
  model?: string | null;
  category?: string | null;
  base_attacks?: number;
  total_prompts?: number;
  evaluator?: string | null;
}

export interface EnginePreview {
  profile: string;
  models: string[];
  estimated_time: { seconds: number; minutes: number };
  estimated_ram_mb: number;
  estimated_gpu_mb: number;
  estimated_llm_calls: number;
  execution_steps: PlanStep[];
  warnings: string[];
  plan: Record<string, unknown>;
  estimate: Record<string, unknown> & { assumptions?: string[] };
  resources: ResourceSnapshot;
}

export interface ResourceSnapshot {
  platform: string;
  source: string;
  ram_total_mb: number | null;
  ram_available_mb: number | null;
  cpu_count: number | null;
  load_avg_1m: number | null;
  disk_total_mb: number | null;
  disk_free_mb: number | null;
  gpu: {
    available: boolean;
    name: string | null;
    total_mb: number | null;
    free_mb: number | null;
    backend: string | null;
  };
}

// --- Pipeline (Sprint 3) ---------------------------------------------------

export interface EvaluateResponse {
  session_id: string;
  status: string;
  profile: string;
  models: string[];
}

export interface PlannedAttack {
  order: number;
  model: string;
  category: string;
  attack_name: string;
  severity: string;
  priority_rank: number;
}

export interface EvaluationPlan {
  profile: string;
  models: string[];
  dataset: string;
  category_order: string[];
  evaluator: string;
  judge_model: string | null;
  mutation_level: number;
  escalation_strategies: string[];
  max_retries: number;
  checkpoint_frequency: number;
  attack_sequence: PlannedAttack[];
  total_attacks: number;
  decisions: Record<string, unknown>;
  deterministic_key: string;
}

export interface PlanResponse {
  session_id: string;
  stage: string;
  plan: EvaluationPlan;
}

export interface Finding {
  id: string;
  category: string;
  title: string;
  severity: string;
  risk_level: string;
  reason: string;
  evidence: { attack_name: string; verdict: string; excerpt: string }[];
  recommendation: string;
}

export interface FindingsResponse {
  session_id: string;
  stage: string;
  findings: Finding[];
  analyses: Record<string, { analysis: AnalysisResult; findings: Finding[] }>;
  leaderboard: { model: string; overall_security_score: number }[] | null;
}

export interface CategoryScore {
  category: string;
  total: number;
  failed: number;
  fail_rate: number;
  score: number;
  risk_level: string;
}

export interface AnalysisResult {
  model_name: string;
  overall_security_score: number;
  total_tests: number;
  failed_tests: number;
  category_scores: CategoryScore[];
  top_vulnerabilities: {
    category: string;
    attack_name: string;
    severity: string;
    verdict: string;
    excerpt: string;
  }[];
  most_successful_attacks: Record<string, unknown>[];
  failure_patterns: string[];
  risk_levels: Record<string, string>;
}

export interface SecurityReport {
  executive_summary: string;
  model_overview: Record<string, unknown>;
  evaluation_summary: Record<string, unknown>;
  security_score: {
    overall: number;
    risk_band: string;
    categories: CategoryScore[];
    risk_levels: Record<string, string>;
  };
  findings: Finding[];
  recommendations: string[];
  appendix: Record<string, unknown>;
  generated_at: string | null;
  report_version: string;
}

export interface ReportResponse {
  session_id: string;
  report: SecurityReport;
}

// --- Leaderboard & history (existing) --------------------------------------

export interface LeaderboardEntry {
  rank: number;
  model_name: string;
  avg_overall_score: number;
  avg_injection_rate: number;
  avg_jailbreak_rate: number;
  avg_hallucination_rate: number;
  avg_data_leakage_rate: number;
  avg_latency_ms: number;
  benchmark_count: number;
}

export interface HistoryPoint {
  overall_score: number;
  timestamp: string;
  benchmark_name?: string;
}

export interface HistoryResponse {
  model_name: string;
  data_points: HistoryPoint[];
}

export interface ApiError {
  error?: string;
  detail?: string;
}

// --- System checks (Sprint 5, onboarding) ----------------------------------

export type CheckStatus = 'ok' | 'warning' | 'failed';

export interface SystemCheck {
  key: string;
  label: string;
  status: CheckStatus;
  detail: string;
  hint: string;
}

export interface SystemChecksResponse {
  ready: boolean;
  platform: string;
  checks: SystemCheck[];
  installed_models: string[];
  recommended_models: string[];
  ollama_download_url: string;
}

// --- Live terminal (Sprint 5) ----------------------------------------------

export type TerminalLevel = 'info' | 'success' | 'warning' | 'failure' | 'system';

export interface TerminalLine {
  id: number;
  ts: string | null;
  level: TerminalLevel;
  text: string;
}

export interface TerminalResponse {
  session_id: string;
  status: string;
  cursor: number;
  lines: TerminalLine[];
}
