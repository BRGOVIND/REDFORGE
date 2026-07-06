import axios, { type AxiosResponse } from 'axios';
import type { ApiError } from './types';

/** Single axios instance for the whole app. All API access flows through here. */
export const http = axios.create({
  baseURL: '/api',
  timeout: 60_000,
  headers: { 'Content-Type': 'application/json' },
});

http.interceptors.response.use(
  (r: AxiosResponse) => r,
  (error: unknown) => {
    const e = error as { response?: { data?: ApiError; status?: number }; message?: string };
    const apiError: ApiError = e.response?.data ?? {
      error: 'Network Error',
      detail: e.message ?? 'An unexpected error occurred',
    };
    return Promise.reject(apiError);
  }
);

/** Extract a human-readable message from any rejected API value. */
export function errorMessage(err: unknown): string {
  const e = err as ApiError;
  return e?.detail || e?.error || 'Something went wrong';
}
