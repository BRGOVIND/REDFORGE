export type AttackCategory =
  | 'PROMPT_INJECTION'
  | 'JAILBREAK'
  | 'CONTEXT_MANIPULATION'
  | 'DATA_LEAKAGE';

export type AttackSeverity = 'low' | 'medium' | 'high' | 'critical';

export type Verdict = 'PASS' | 'FAIL' | 'UNCERTAIN';

export interface ApiError {
  error: string;
  detail: string;
}

export interface OllamaModel {
  name: string;
  size: number;
  modified_at: string;
  digest: string;
}

export interface PingResult {
  model: string;
  online: boolean;
  latency_ms: number | null;
  error?: string;
}

export interface Attack {
  id: number;
  name: string;
  category: AttackCategory;
  prompt: string;
  description: string;
  severity: AttackSeverity;
}

export interface AttacksResponse {
  categories: Record<AttackCategory, Attack[]>;
  total: number;
}

export interface RunResult {
  id: number;
  model_name: string;
  attack_id: number;
  attack_name: string;
  category: AttackCategory;
  prompt_sent: string;
  model_response: string;
  score: number;
  verdict: Verdict;
  reason: string;
  latency_ms: number;
  timestamp: string;
}

export interface JobStatus {
  job_id: string;
  status: 'running' | 'completed' | 'failed';
  total: number;
  completed: number;
  results: RunResult[];
}

export interface BatchRunRequest {
  model_name: string;
  category?: string;
}

export interface CategoryStats {
  total: number;
  pass: number;
  fail: number;
  failure_rate: number;
}

export interface DailyCount {
  date: string;
  count: number;
}

export interface DashboardMetrics {
  model_name: string;
  total_tests: number;
  pass_rate: number;
  fail_rate: number;
  prompt_injection_success_rate: number;
  jailbreak_success_rate: number;
  context_manipulation_success_rate: number;
  data_leakage_risk: number;
  avg_latency_ms: number;
  category_breakdown: Record<string, CategoryStats>;
  daily_counts: DailyCount[];
}

export interface HallucinationResult {
  hallucination_score: number;
  faithfulness_score: number;
  explanation: string;
  model_response: string;
}

export interface TopVulnerability {
  category: string;
  failure_rate: number;
  count: number;
}

export interface ReportData {
  model_name: string;
  generated_at: string;
  total_tests: number;
  pass_rate: number;
  fail_rate: number;
  pass_count: number;
  fail_count: number;
  uncertain_count: number;
  avg_latency_ms: number;
  category_breakdown: Record<string, CategoryStats>;
  top_vulnerabilities: TopVulnerability[];
  recommendations: string[];
}

export interface Report {
  id: number;
  model_name: string;
  generated_at: string;
  report_data: ReportData;
}
