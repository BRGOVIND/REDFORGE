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

/** Extract a human-readable message from any rejected API value.
 *  Handles the standardized `{ error: { message } }` envelope and the older
 *  `{ detail }` / `{ error: string }` shapes (e.g. network errors). */
export function errorMessage(err: unknown): string {
  const e = err as ApiError;
  if (e && typeof e.error === 'object' && e.error?.message) return e.error.message;
  if (typeof e?.detail === 'string') return e.detail;
  if (typeof e?.error === 'string') return e.error;
  return 'Something went wrong';
}
