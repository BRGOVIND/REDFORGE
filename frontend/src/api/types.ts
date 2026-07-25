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

// --- RedForge V2 · AI Studio (projects) ------------------------------------

export interface Project {
  id: string;
  name: string;
  description: string;
  models: string[];
  datasets: unknown[];
  settings: Record<string, unknown>;
  last_scan: Record<string, unknown> | null;
  created_at: string | null;
  updated_at: string | null;
  opened_at: string | null;
}

export interface ProjectCreate {
  name: string;
  description?: string;
  models?: string[];
  settings?: Record<string, unknown>;
}

// --- RedForge V2 · Playground ----------------------------------------------

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface ChatParams {
  provider?: string | null;
  system?: string;
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  seed?: number;
}

export interface ChatResponse {
  response: string;
  model: string;
  provider: string;
  latency_ms: number;
  eval_count: number | null;
}

// --- RedForge V2 · Assistant -----------------------------------------------

export interface AssistantSource {
  id: string;
  title: string;
}

export interface AssistantAnswer {
  answer: string;
  sources: AssistantSource[];
  suggestions: string[];
}

// --- RedForge V2 · Dataset Lab ---------------------------------------------

export interface Dataset {
  id: string;
  project_id: string | null;
  name: string;
  description: string;
  source_format: string;
  kind: 'records' | 'text';
  columns: string[];
  record_count: number;
  byte_size: number;
  current_version: number;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface DatasetPreview {
  dataset_id: string;
  kind: 'records' | 'text';
  columns: string[];
  total: number;
  offset: number;
  limit: number;
  rows: unknown[];
}

export interface DatasetIssues {
  duplicates: number;
  empty_records: number;
  missing_values: number;
  formatting_issues: number;
  prompt_leakage: number;
  unsafe_samples: number;
  malformed_conversations: number;
}

export interface DatasetStats {
  record_count: number;
  kind: string;
  file_size_bytes: number;
  total_chars: number;
  estimated_tokens: number;
  avg_length: number;
  min_length: number;
  max_length: number;
  languages: Record<string, number>;
}

export interface DatasetAnalysis {
  score: number;
  grade: string;
  issues: DatasetIssues;
  statistics: DatasetStats;
  suggestions: string[];
}

export interface DatasetVersionInfo {
  version: number;
  record_count: number;
  note: string;
  is_current: boolean;
  created_at: string | null;
}

export interface CleanResult {
  dataset_id: string;
  before_count: number;
  after_count: number;
  notes: string[];
  preview: unknown[];
  saved: boolean;
}

export interface SplitStats {
  statistics: {
    total: number;
    train: number;
    validation: number;
    test: number;
    ratios: { train: number; validation: number; test: number };
    seed: number;
    shuffled: boolean;
  };
}

// --- RedForge V2 · Training Lab --------------------------------------------

export interface TrainingBackend {
  name: string;
  label: string;
  available: boolean;
  reason: string;
}

export interface TrainingDiagnosticCheck {
  name: string;
  ok: boolean;
  detail: string;
  required: boolean;
}

export interface TrainingDiagnostics {
  backend: string;
  label: string;
  checks: TrainingDiagnosticCheck[];
  ready: boolean;
  missing_required: string[];
  status: string;
  install_hint: string;
}

export interface TrainingParams {
  epochs: number;
  learning_rate: number;
  batch_size: number;
  gradient_accumulation: number;
  rank: number;
  alpha: number;
  dropout: number;
  scheduler: string;
  optimizer: string;
  warmup_steps: number;
  max_seq_length: number;
  seed: number;
  validation_split: number;
  output_dir: string;
}

export interface TrainingRun {
  id: string;
  project_id: string | null;
  name: string;
  base_model: string;
  dataset_id: string | null;
  method: 'lora' | 'qlora';
  backend: string;
  config: Record<string, unknown>;
  status: string;
  metrics: Record<string, number | null>;
  output_dir: string;
  notes: string;
  duration_seconds: number | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface TrainingProgressPoint {
  step: number;
  epoch: number | null;
  loss: number | null;
  val_loss: number | null;
  learning_rate: number | null;
}

export interface TrainingProgress {
  run_id: string;
  status: string;
  latest: {
    step?: number;
    total_steps?: number;
    epoch?: number;
    total_epochs?: number;
    loss?: number;
    val_loss?: number;
    learning_rate?: number;
    steps_per_sec?: number | null;
    eta_seconds?: number | null;
    message?: string;
  };
  history: TrainingProgressPoint[];
  logs: string[];
  paused: boolean;
}

export interface TrainingCheckpoint {
  id: string;
  run_id: string;
  step: number;
  epoch: number;
  loss: number | null;
  val_loss: number | null;
  path: string;
  is_best: boolean;
  note: string;
  created_at: string | null;
}

// --- RedForge V2 · Continuous Security -------------------------------------

export interface CheckpointSecurity {
  id: string;
  run_id: string;
  checkpoint_id: string | null;
  step: number;
  target_model: string;
  profile: string;
  status: string;
  score: number | null;
  categories: { category: string; score: number; fail_rate: number; risk_level: string }[];
  findings: { category: string; attack_name: string; severity: string }[];
  session_id: string | null;
  error: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface SecurityCompare {
  run_id: string;
  a: { step: number; score: number | null };
  b: { step: number; score: number | null };
  score_delta: number | null;
  improved_categories: string[];
  regressed_categories: string[];
  resolved_vulnerabilities: string[];
  new_vulnerabilities: string[];
}

// --- RedForge V2 · Recommendation Engine -----------------------------------

export interface RecommendationPayload {
  target_model: string;
  summary: string;
  weaknesses: { category: string; severity: string; score: number | null; description: string }[];
  strategy: { method: string; reason: string };
  hyperparameters: {
    rank: number; alpha: number; epochs: number; learning_rate: number;
    batch_size: number; gradient_accumulation: number; scheduler: string;
    optimizer: string; warmup_steps: number; rationale: Record<string, string>;
  };
  datasets: {
    project: { id: string; name: string; fit: string; quality: number | null; records: number | null }[];
    public: { name: string; url: string; reason: string; theme: string }[];
  };
  attacks: { recommend_more: boolean; categories: string[]; reason: string };
  prediction: {
    expected_security_gain: number; expected_benchmark_gain: number;
    confidence: number; explanation: string; disclaimer: string;
  };
}

export interface Recommendation {
  id: string;
  project_id: string | null;
  run_id: string | null;
  target_model: string;
  source: string;
  status: string;
  payload: RecommendationPayload;
  outcome: Record<string, unknown> | null;
  created_at: string | null;
  decided_at: string | null;
}

export interface RecommendationAccuracy {
  count: number;
  mean_accuracy: number | null;
  best_recommendation: {
    id: string;
    target_model: string;
    outcome: Record<string, unknown> | null;
  } | null;
}

// --- RedForge V2 · Runtime Registry (Phase 2.5) ----------------------------

export interface RegisteredModel {
  id: string;
  run_id: string | null;
  checkpoint_id: string | null;
  project_id: string | null;
  label: string;
  step: number;
  base_model: string;
  provider: string;
  runtime_model: string;
  adapter_path: string | null;
  fallback: boolean;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string | null;
}

// --- RedForge V2 · Benchmark Center (Phase 3) ------------------------------

export interface BenchmarkSuiteInfo {
  key: string;
  label: string;
  dimension: string;
  description: string;
  real: boolean;
}

export interface BenchmarkResult {
  id: string;
  project_id: string | null;
  run_id: string | null;
  registry_id: string | null;
  target_model: string;
  provider: string | null;
  runtime: string | null;
  label: string | null;
  suites: string[];
  status: string;
  overall_score: number | null;
  scores: Record<string, number | null>;
  metrics: Record<string, Record<string, unknown>>;
  duration_seconds: number | null;
  config: Record<string, unknown>;
  error: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface BenchmarkLeaderboardEntry extends BenchmarkResult {
  rank_score: number | null;
}

export interface BenchmarkComparison {
  suites: string[];
  models: {
    id: string;
    label: string;
    target_model: string;
    registry_id: string | null;
    overall_score: number | null;
    scores: Record<string, number | null>;
    metrics: Record<string, Record<string, unknown>>;
  }[];
}

export interface BenchmarkTrends {
  suite: string | null;
  series: Record<string, { at: string | null; score: number; id: string }[]>;
}

export interface BenchmarkRequest {
  models?: string[];
  registry_ids?: string[];
  project_id?: string;
  suites?: string[];
  config?: Record<string, unknown>;
}

// --- RedForge V2 · Evaluation Workbench (Phase 4) --------------------------

export interface SimilarityProviderInfo {
  key: string;
  label: string;
  description: string;
  available: boolean;
}

export interface EvaluationCollection {
  id: string;
  project_id: string | null;
  name: string;
  category: string;
  description: string;
  tags: string[];
  notes: string;
  created_at: string | null;
  updated_at: string | null;
  prompt_set_count?: number;
  prompt_sets?: PromptSet[];
}

export interface PromptSet {
  id: string;
  collection_id: string;
  project_id: string | null;
  title: string;
  description: string;
  category: string;
  tags: string[];
  notes: string;
  priority: string;
  owner: string;
  created_at: string | null;
  updated_at: string | null;
  prompt_count?: number;
  prompts?: Prompt[];
}

export interface PromptAcceptance {
  min_similarity?: number;
  must_include?: string[];
  must_exclude?: string[];
  require_json?: boolean;
  category?: string;
}

export interface Prompt {
  id: string;
  prompt_set_id: string;
  title: string;
  prompt: string;
  system_prompt: string;
  context: string;
  expected_behavior: string;
  expected_output: string;
  golden_response: string;
  acceptance_criteria: PromptAcceptance;
  tags: string[];
  priority: string;
  difficulty: string;
  notes: string;
  enabled: boolean;
  current_version: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface PromptVersion {
  id: number;
  version: number;
  note: string;
  snapshot: Record<string, unknown>;
  created_at: string | null;
}

export interface Regression {
  type: string;
  label: string;
  severity: string;
  summary: string;
  attribution: string;
}

export interface EvaluationResult {
  id: string;
  session_id: string;
  prompt_id: string | null;
  prompt_set_id: string | null;
  prompt_version: number;
  prompt_title: string;
  target_model: string;
  registry_id: string | null;
  provider: string | null;
  runtime: string | null;
  label: string;
  response: string;
  metrics: {
    latency_ms?: number | null;
    ttft_ms?: number | null;
    completion_ms?: number | null;
    prompt_tokens?: number | null;
    completion_tokens?: number | null;
    total_tokens?: number | null;
  };
  similarity_score: number | null;
  baseline_type: string | null;
  verdict: string;
  regressions: Regression[];
  warnings: string[];
  error: string | null;
  created_at: string | null;
}

export interface WorkbenchModelSummary {
  label: string;
  target_model: string;
  registry_id: string | null;
  pass_rate: number | null;
  fails: number;
  regressions: number;
  mean_similarity: number | null;
  results: number;
}

export interface WorkbenchSummary {
  pass_rate: number | null;
  fail_rate: number | null;
  warn_rate: number | null;
  regression_score: number | null;
  consistency_score: number | null;
  quality_score: number | null;
  overall_score: number | null;
  total_results: number;
  graded_results: number;
  regression_breakdown: Record<string, number>;
  models: WorkbenchModelSummary[];
  best_model: WorkbenchModelSummary | null;
  closest_to_baseline: WorkbenchModelSummary | null;
}

export interface WorkbenchSession {
  id: string;
  project_id: string | null;
  run_id: string | null;
  name: string;
  models: { target_model: string; registry_id?: string | null; provider?: string | null; runtime?: string | null; label?: string }[];
  prompt_set_ids: string[];
  similarity: string;
  status: string;
  config: Record<string, unknown>;
  summary: WorkbenchSummary;
  total_tasks: number;
  completed_tasks: number;
  duration_seconds: number | null;
  error: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface SessionRegressions {
  session_id: string;
  total: number;
  by_type: {
    type: string;
    label: string;
    count: number;
    items: {
      label: string;
      severity: string;
      summary: string;
      attribution: string;
      prompt_title: string;
      target_model: string;
      result_id: string;
    }[];
  }[];
}

export interface GoldenDiff {
  unified_diff: string[];
  missing_content: string[];
  additional_content: string[];
  length_delta: number;
  baseline_is_json: boolean;
  response_is_json: boolean;
  json_diff?: { valid: boolean; missing_keys?: string[]; added_keys?: string[]; changed_keys?: string[]; note?: string };
  formatting: {
    baseline_has_code_block: boolean;
    response_has_code_block: boolean;
    baseline_bullets: number;
    response_bullets: number;
  };
}

export interface SessionCreateRequest {
  prompt_set_ids: string[];
  models?: string[];
  registry_ids?: string[];
  project_id?: string;
  run_id?: string;
  name?: string;
  similarity?: string;
  config?: Record<string, unknown>;
}

// --- RedForge V2 · Training Report (Phase 2.5) -----------------------------
// Composed on the fly from existing run/security/recommendation/registry data.

export interface TrainingReport {
  run_id: string;
  executive_summary: string;
  training_summary: {
    name: string;
    base_model: string;
    method: string;
    backend: string;
    status: string;
    metrics: Record<string, number | null>;
    duration_seconds: number | null;
  };
  final_configuration: Record<string, unknown>;
  dataset_summary: {
    id: string;
    name: string;
    record_count: number | null;
    quality_score: number | null;
  } | null;
  security_timeline: {
    step: number;
    score: number | null;
    runtime_id: string | null;
    provider: string | null;
    categories: { category: string; score: number; risk_level: string }[];
  }[];
  checkpoint_comparison: {
    first: { step: number; score: number | null };
    last: { step: number; score: number | null };
    delta: number | null;
  } | null;
  recommendations: {
    id: string;
    status: string;
    predicted: number | null;
    outcome: Record<string, unknown> | null;
    hyperparameters: Record<string, unknown> | null;
  }[];
  accepted_recommendations: TrainingReport['recommendations'];
  rejected_recommendations: TrainingReport['recommendations'];
  final_models: { id: string; label: string; runtime_model: string; fallback: boolean }[];
  benchmarks: {
    id: string;
    label: string;
    target_model: string;
    registry_id: string | null;
    overall_score: number | null;
    scores: Record<string, number | null>;
    suites: string[];
  }[];
  best_benchmark: {
    id: string;
    label: string;
    target_model: string;
    overall_score: number | null;
    scores: Record<string, number | null>;
    suites: string[];
  } | null;
  evaluation: {
    session_id: string;
    name: string;
    pass_rate: number | null;
    fail_rate: number | null;
    regression_score: number | null;
    consistency_score: number | null;
    quality_score: number | null;
    overall_score: number | null;
    regression_breakdown: Record<string, number>;
    best_model: WorkbenchModelSummary | null;
    closest_to_baseline: WorkbenchModelSummary | null;
    models: WorkbenchModelSummary[];
  } | null;
  deployment_recommendation: string | null;
  remaining_risks: string[];
}

// --- RedForge V3 · Foundation Platform (Epic 1) ----------------------------

export interface FoundationModel {
  id: string;
  hf_repo: string;
  revision: string | null;
  architecture: string | null;
  parameter_count: number | null;
  format: string;
  quantization: string;
  status: string; // referenced | downloading | local | invalid
  source: string; // hf_hub | local_import | resolved_from_runtime
  license: string | null;
  cache_path: string | null;
  checksum: string | null;
  metadata: Record<string, unknown>;
  identity_key: string;
  is_local: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface ResolutionCandidate {
  hf_repo: string;
  confidence: number;
  reason: string;
  architecture: string | null;
  parameter_count: number | null;
}

export interface ResolutionResult {
  runtime_ref: string;
  candidates: ResolutionCandidate[];
  resolved: ResolutionCandidate | null;
  is_ambiguous: boolean;
  facts: Record<string, unknown>;
}

export interface FoundationDiscovery {
  runtime_ref: string;
  suggested: ResolutionCandidate | null;
  candidate_count: number;
  is_ambiguous: boolean;
}

export interface FoundationRuntimeLink {
  registry_id: string | null;
  runtime_model: string | null;
  label: string | null;
  provider: string | null;
  fallback: number | null;
  match: string;
}

// --- RedForge V3 · Automatic Model Discovery (Epic 4.5) --------------------

export interface RuntimeModel {
  id: string;
  runtime_ref: string;
  provider: string;             // detected from, e.g. "ollama"
  resolution: string;           // resolved | needs_resolution | unresolved
  available: boolean;           // currently served by the runtime
  status: string;               // display: resolved | needs_resolution | unavailable
  foundation_model_id: string | null;
  confidence: number | null;
  candidates: ResolutionCandidate[];
  facts: Record<string, unknown>;
  last_synced_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface DiscoverySummary {
  provider: string;
  online: boolean;
  discovered: number;
  resolved: number;
  needs_resolution: number;
  registered: number;
  unavailable: number;
  error?: string;
}

export interface RuntimeResolveResult {
  runtime_model: RuntimeModel;
  foundation_model: FoundationModel | null;
  note?: string;
}

// --- RedForge V3 · Artifact Registry (Epic 2) ------------------------------

export interface ArtifactLocation {
  kind: string; // "file" | "data"
  file_path: string | null;
  table: string | null;
  row_id: string | null;
}

export interface ArtifactChecksum {
  algorithm: string;
  value: string;
}

export interface Artifact {
  id: string;
  type: string;
  name: string;
  status: string; // draft | ready | invalid | archived
  location: ArtifactLocation;
  producer: string;
  project_id: string | null;
  experiment_id: string | null;
  description: string;
  size_bytes: number | null;
  checksum: ArtifactChecksum | null;
  tags: string[];
  lineage_id: string;
  version: number;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
  archived_at: string | null;
}

export interface ArtifactReference {
  id: string;
  type: string;
  name: string;
  version: number;
  status: string;
}

export interface ArtifactEdge {
  id: string;
  parent_id: string;
  child_id: string;
  relationship: string;
  metadata: Record<string, unknown>;
  created_at: string | null;
}

export interface ArtifactLineage {
  artifact_id: string;
  ancestors: ArtifactReference[];
  descendants: ArtifactReference[];
  parents: ArtifactReference[];
  children: ArtifactReference[];
  edges: ArtifactEdge[];
}

export interface ArtifactTypeInfo {
  key: string;
  label: string;
  backing: string;
  category: string;
}

// --- RedForge V3 · Job System (Epic 2) -------------------------------------

export interface JobProgress {
  fraction: number;
  step: number | null;
  total: number | null;
  message: string;
  updated_at: string | null;
}

export interface JobResult {
  success: boolean;
  data: Record<string, unknown>;
  artifact_ids: string[];
  message: string;
}

export interface JobError {
  message: string;
  kind: string;
  traceback: string;
}

export interface Job {
  id: string;
  type: string;
  status: string; // queued | running | paused | completed | failed | cancelled | interrupted
  params: Record<string, unknown>;
  target_ref: string | null;
  project_id: string | null;
  priority: number;
  progress: JobProgress;
  result: JobResult | null;
  error: JobError | null;
  logs: string[];
  attempts: number;
  max_attempts: number;
  metadata: Record<string, unknown>;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface JobTypeInfo {
  key: string;
  label: string;
  concurrency: number;
  default_max_attempts: number;
}

// --- RedForge V3 · Dataset Platform (Epic 3) -------------------------------

export interface V3Dataset {
  id: string;
  name: string;
  format: string;
  kind: string;
  status: string;
  description: string;
  project_id: string | null;
  current_version: number;
  schema: { kind: string; columns: string[] };
  statistics: { record_count: number; byte_size: number; estimated_tokens: number; avg_length: number; column_count: number };
  content_hash: string;
  tags: string[];
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
  version_id?: string;
  artifact_id?: string;
}

export interface V3DatasetVersion {
  id: string;
  dataset_id: string;
  version: number;
  record_count: number;
  note: string;
  content_hash: string;
  artifact_id: string | null;
  created_at: string | null;
}

export interface V3DatasetValidation {
  valid: boolean;
  score: number;
  grade: string;
  issues: Record<string, number>;
  suggestions: string[];
}

// --- RedForge V3 · Training Platform (Epic 3) ------------------------------

export interface TrainingStrategyInfo {
  key: string;
  label: string;
  adapter_based: boolean;
  dataset_shape: string;
  providers: string[];
  implemented: boolean;
}

export interface TrainingProviderInfo {
  name: string;
  label: string;
  available: boolean;
  reason: string;
  dev_only: boolean;
}

export interface TrainingEstimate {
  vram_mb: number;
  disk_mb: number;
  duration_seconds: number;
  checkpoint_size_mb: number;
  adapter_size_mb: number;
  fits_hardware: boolean;
  warnings: string[];
}

export interface V3TrainingRun {
  id: string;
  name: string;
  configuration: {
    foundation_model_id: string | null;
    base_model: string;
    dataset_id: string | null;
    dataset_version: number | null;
    strategy: string;
    provider: string;
    hyperparameters: Record<string, unknown>;
    adapter: { rank: number; alpha: number; dropout: number };
    strategy_params: Record<string, unknown>;
  };
  status: string;
  metrics: Record<string, unknown>;
  estimate: TrainingEstimate | null;
  job_id: string | null;
  project_id: string | null;
  output_dir: string;
  logs: string[];
  error: string | null;
  run_artifact_id: string | null;
  adapter_artifact_id: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface V3TrainingCheckpoint {
  id: string;
  run_id: string;
  step: number;
  epoch: number;
  loss: number | null;
  val_loss: number | null;
  path: string;
  is_best: boolean;
  artifact_id: string | null;
  created_at: string | null;
}

// --- RedForge V3 · Export Engine (Epic 3) ----------------------------------

export interface ExportProviderInfo {
  target: string;
  name: string;
  available: boolean;
  reason: string;
}

// --- RedForge V3 · Experiment Platform (Epic 4) ----------------------------

export interface ExperimentConfiguration {
  foundation_model_id: string | null;
  base_model: string;
  dataset_id: string | null;
  dataset_version: number | null;
  strategy: string;
  provider: string | null;
  hyperparameters: Record<string, unknown>;
  adapter: Record<string, unknown>;
}

export interface ExperimentSnapshot {
  foundation_model: Record<string, unknown>;
  dataset_version: number | null;
  dataset_content_hash: string;
  strategy: string;
  provider: string;
  hyperparameters: Record<string, unknown>;
  resource_estimate: Record<string, unknown>;
  gpu: Record<string, unknown>;
  redforge_version: string;
  platform: Record<string, unknown>;
  captured_at: string | null;
}

export interface Experiment {
  id: string;
  name: string;
  status: string; // draft | active | concluded | archived
  description: string;
  configuration: ExperimentConfiguration;
  snapshot: ExperimentSnapshot | null;
  tags: string[];
  metrics: Record<string, unknown>;
  project_id: string | null;
  parent_experiment_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  concluded_at: string | null;
}

export interface ExperimentTimelineEvent {
  id: string;
  experiment_id: string;
  kind: string;
  title: string;
  payload: Record<string, unknown>;
  source: string; // system | user
  at: string | null;
}

export interface ExperimentNote {
  id: string;
  experiment_id: string;
  body: string;
  created_at: string | null;
}

export interface ExperimentJobRef {
  experiment_id: string;
  job_id: string;
  job_type: string;
  status: string;
  updated_at: string | null;
}

export interface ExperimentComparisonColumn {
  id: string;
  name: string;
  status: string;
  strategy: string;
  provider: string | null;
  base_model: string;
  hyperparameters: Record<string, unknown>;
  metrics: Record<string, unknown>;
  artifact_counts: Record<string, number>;
  artifacts_total: number;
  jobs_total: number;
  training_duration: number | null;
  final_loss: number | null;
  gpu: Record<string, unknown>;
}

export interface ExperimentComparison {
  experiments: ExperimentComparisonColumn[];
}

// --- Global Task Manager --------------------------------------------------
export interface Task {
  id: string;
  kind: string;
  label: string;
  title: string;
  status: 'queued' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled' | 'interrupted';
  progress: number; // 0–100
  step?: number | null;
  total?: number | null;
  current_step: string;
  elapsed_seconds?: number | null;
  eta_seconds?: number | null;
  cancellable: boolean;
  retryable: boolean;
  logs_tail: string[];
  logs?: string[];
  error?: string | null;
  artifact_ids: string[];
  project_id?: string | null;
  experiment_id?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface TaskSummary {
  running: number;
  queued: number;
  paused: number;
  active: number;
  failed: number;
  completed: number;
  by_status: Record<string, number>;
}

export interface TaskList {
  tasks: Task[];
  summary: TaskSummary;
}

// --- Model Hub ------------------------------------------------------------
export interface ModelHubModel {
  id: string;
  name: string;
  family: string;
  parameters_b: number;
  category: string;
  quantization: string;
  download_size_gb: number;
  required_vram_gb: number;
  estimated_ram_gb: number;
  hf_repo?: string | null;
  ollama_tag?: string | null;
  sources: string[];
  recommended_hardware: string;
  training_suitability: 'recommended' | 'supported' | 'not supported';
  benchmark_suitability: 'recommended' | 'limited';
  trainable: boolean;
  benchmarkable: boolean;
  badges: string[];
  description: string;
}

export interface ModelHubCategory {
  key: string;
  label: string;
  models: ModelHubModel[];
}

export interface ModelHubCatalog {
  categories: ModelHubCategory[];
}
