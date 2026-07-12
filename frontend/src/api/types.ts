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
  /** Standardized envelope: `{ error: { code, message, details } }`;
   *  legacy/network errors may use a plain string or `detail`. */
  error?: string | { code?: string; message?: string; details?: unknown };
  detail?: string;
  success?: boolean;
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

export interface SystemProvider {
  name: string;
  label: string;
  base_url: string | null;
  reachable: boolean;
  requires_api_key: boolean;
  api_key_present: boolean;
  supports_pull: boolean;
  docs_url: string | null;
  setup_hint: string | null;
}

export interface SystemChecksResponse {
  ready: boolean;
  platform: string;
  /** The active runtime provider (from the Runtime Manager). */
  provider: SystemProvider;
  checks: SystemCheck[];
  installed_models: string[];
  /** Starter models — only populated for providers that can download models. */
  recommended_models: string[];
  /** Present only when requested with `?include_health=true`. */
  health?: HealthReport | null;
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

// --- Runtime Manager (V1.2) -------------------------------------------------

export interface ProviderHealth {
  name: string;
  online: boolean;
  healthy: boolean;
  version: string | null;
  model_count: number | null;
  models: string[];
  base_url: string | null;
  latency_ms: number | null;
  checked_at: string | null;
  error: string | null;
}

export interface ProviderInfo {
  name: string;
  label: string;
  is_default: boolean;
  base_url: string | null;
  requires_api_key: boolean;
  api_key_env: string | null;
  api_key_present: boolean;
  health: ProviderHealth | null;
}

export interface ProvidersResponse {
  default: string;
  providers: ProviderInfo[];
}

export interface RuntimeStatusResponse {
  provider: string;
  concurrency_per_model: number;
  metrics: Record<string, number>;
}

export interface RuntimeLogLine {
  ts: string | null;
  level: string;
  logger: string;
  message: string;
}

export interface RuntimeLogsResponse {
  lines: RuntimeLogLine[];
}

// --- Model Manager (V1.2) ---------------------------------------------------

export interface ModelCapabilities {
  supports_delete: boolean;
  supports_metadata: boolean;
  supports_context_length: boolean;
  supports_streaming: boolean;
  supports_embeddings: boolean;
}

export interface CatalogModel {
  name: string;
  provider: string;
  provider_label: string;
  size: number | null;
  quantization: string | null;
  family: string | null;
  modified_at: string | null;
  digest: string | null;
  status: string;
  capabilities: ModelCapabilities;
}

export interface ProviderGroup {
  provider: string;
  label: string;
  online: boolean;
  healthy: boolean;
  can_delete: boolean;
  capabilities: ModelCapabilities;
  error: string | null;
  model_count: number;
  models: CatalogModel[];
}

export interface ModelCatalogResponse {
  providers: ProviderGroup[];
  total: number;
  default: string;
}

export interface ModelDetail extends CatalogModel {
  context_length: number | null;
  parameter_count: string | null;
  architecture: string | null;
  template: string | null;
  license: string | null;
  families: string[] | null;
  tokenizer: string | null;
  modelfile: string | null;
  stop_tokens: string[];
  provider_metadata: Record<string, unknown>;
}

// --- System Health Engine (V1.2) -------------------------------------------

export type HealthStatus = 'healthy' | 'warning' | 'error';
export type HealthSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export interface HealthCheck {
  id: string;
  name: string;
  status: HealthStatus;
  severity: HealthSeverity;
  message: string;
  suggested_fix: string | null;
  metadata: Record<string, unknown>;
}

export interface HealthSummary {
  total: number;
  healthy: number;
  warning: number;
  error: number;
}

export interface HealthReport {
  status: HealthStatus;
  ready: boolean;
  generated_at: string;
  summary: HealthSummary;
  checks: HealthCheck[];
}

// --- Onboarding recommendations (V1.2.1) -----------------------------------

export interface HardwareInfo {
  python_version: string;
  python_ok: boolean;
  platform: string;
  cpu_count: number | null;
  ram_total_mb: number | null;
  ram_available_mb: number | null;
  gpu: {
    available: boolean;
    name: string | null;
    vram_total_mb: number | null;
    backend: string | null;
  };
}

export interface RuntimeRecommendation {
  provider: string;
  state: 'running' | 'not_running' | 'missing';
  reason: string;
  action: string | null;
}

export interface ModelRecommendation {
  name: string;
  label: string;
  params_b: number;
  estimated_ram_mb: number;
  fits: boolean;
  note: string;
  recommended: boolean;
}

export interface ModelRecommendations {
  budget_mb: number | null;
  budget_source: string;
  usable_mb: number | null;
  recommended: string | null;
  models: ModelRecommendation[];
}

export interface OnboardingRecommendations {
  hardware: HardwareInfo;
  runtime: RuntimeRecommendation;
  models: ModelRecommendations;
}

export interface PullStatus {
  model: string;
  status: string;
  percent: number | null;
  completed_mb: number | null;
  total_mb: number | null;
  done: boolean;
  error: string | null;
}
