import axios from 'axios';
import type {
  OllamaModel,
  PingResult,
  AttacksResponse,
  RunResult,
  BatchRunRequest,
  JobStatus,
  HallucinationResult,
  DashboardMetrics,
  Report,
  ApiError,
} from '../types';

const API_BASE = '/api';

const client = axios.create({
  baseURL: API_BASE,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const apiError: ApiError = error.response?.data ?? {
      error: 'Network Error',
      detail: error.message ?? 'An unexpected error occurred',
    };
    return Promise.reject(apiError);
  }
);

// Models
export async function getModels(): Promise<{ models: OllamaModel[]; error?: string }> {
  const res = await client.get<{ models: OllamaModel[]; error?: string }>('/models');
  return res.data;
}

export async function pingModel(name: string): Promise<PingResult> {
  const res = await client.get<PingResult>(`/models/${encodeURIComponent(name)}/ping`);
  return res.data;
}

// Attacks
export async function getAttacks(): Promise<AttacksResponse> {
  const res = await client.get<AttacksResponse>('/attacks');
  return res.data;
}

// Runs
export async function runSingle(req: { model_name: string; attack_id: number }): Promise<RunResult> {
  const res = await client.post<RunResult>('/runs/single', req);
  return res.data;
}

export async function runBatch(req: BatchRunRequest): Promise<{ job_id: string; total: number }> {
  const res = await client.post<{ job_id: string; total: number }>('/runs/batch', req);
  return res.data;
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await client.get<JobStatus>(`/runs/batch/${encodeURIComponent(jobId)}`);
  return res.data;
}

export async function getRuns(modelName: string): Promise<RunResult[]> {
  const res = await client.get<RunResult[]>('/runs', { params: { model_name: modelName } });
  return res.data;
}

// Evaluate
export async function evaluateHallucination(req: {
  question: string;
  ground_truth: string;
  model_name: string;
}): Promise<HallucinationResult> {
  const res = await client.post<HallucinationResult>('/evaluate/hallucination', req);
  return res.data;
}

// Dashboard
export async function getDashboard(modelName: string): Promise<DashboardMetrics> {
  const res = await client.get<DashboardMetrics>('/dashboard', { params: { model_name: modelName } });
  return res.data;
}

// Reports
export async function createReport(modelName: string): Promise<Report> {
  const res = await client.post<Report>('/reports', { model_name: modelName });
  return res.data;
}

export async function getReport(id: number): Promise<Report> {
  const res = await client.get<Report>(`/reports/${id}`);
  return res.data;
}

export async function getReports(modelName?: string): Promise<Report[]> {
  const params = modelName ? { model_name: modelName } : undefined;
  const res = await client.get<Report[]>('/reports', { params });
  return res.data;
}

export function downloadReport(id: number): string {
  return `${API_BASE}/reports/${id}/download`;
}
