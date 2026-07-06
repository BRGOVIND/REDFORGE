/**
 * Minimal React-Query-style data layer.
 *
 * The Sprint 4 spec asks for @tanstack/react-query, but this environment has no
 * network access to install it, so this provides the same ergonomics we rely on
 * — a shared cache, request de-duplication, background refetch, and polling —
 * in a small, dependency-free module. The public API (`useQuery`, `useMutation`,
 * `QueryProvider`, `queryClient.invalidate`) mirrors react-query closely so a
 * future swap is mechanical.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';

type Status = 'idle' | 'loading' | 'success' | 'error';

interface CacheEntry<T = unknown> {
  data?: T;
  error?: unknown;
  status: Status;
  updatedAt: number;
  promise?: Promise<T>;
}

export type QueryKey = ReadonlyArray<string | number | boolean | null | undefined>;

function keyToString(key: QueryKey): string {
  return JSON.stringify(key);
}

class QueryClient {
  private cache = new Map<string, CacheEntry>();
  private listeners = new Map<string, Set<() => void>>();

  getEntry<T>(key: string): CacheEntry<T> | undefined {
    return this.cache.get(key) as CacheEntry<T> | undefined;
  }

  private setEntry(key: string, entry: CacheEntry): void {
    this.cache.set(key, entry);
    this.listeners.get(key)?.forEach((fn) => fn());
  }

  subscribe(key: string, fn: () => void): () => void {
    let set = this.listeners.get(key);
    if (!set) {
      set = new Set();
      this.listeners.set(key, set);
    }
    set.add(fn);
    return () => set!.delete(fn);
  }

  async fetch<T>(key: string, fn: () => Promise<T>): Promise<T> {
    const existing = this.cache.get(key) as CacheEntry<T> | undefined;
    if (existing?.promise) return existing.promise;

    const promise = fn()
      .then((data) => {
        this.setEntry(key, { data, status: 'success', updatedAt: Date.now() });
        return data;
      })
      .catch((error) => {
        this.setEntry(key, {
          data: existing?.data,
          error,
          status: 'error',
          updatedAt: Date.now(),
        });
        throw error;
      });

    this.setEntry(key, {
      data: existing?.data,
      status: 'loading',
      updatedAt: existing?.updatedAt ?? 0,
      promise,
    });
    return promise;
  }

  invalidate(prefix?: QueryKey): void {
    const p = prefix ? keyToString(prefix).slice(0, -1) : '';
    for (const key of this.cache.keys()) {
      if (!prefix || key.startsWith(p)) {
        const entry = this.cache.get(key);
        if (entry) this.setEntry(key, { ...entry, updatedAt: 0, promise: undefined });
      }
    }
  }
}

export const queryClient = new QueryClient();

const QueryContext = createContext<QueryClient>(queryClient);

export function QueryProvider({ children }: { children: React.ReactNode }) {
  return <QueryContext.Provider value={queryClient}>{children}</QueryContext.Provider>;
}

interface UseQueryOptions<T> {
  queryKey: QueryKey;
  queryFn: () => Promise<T>;
  enabled?: boolean;
  /** Poll interval in ms (0 = off). Enables the "live" feel across the app. */
  refetchInterval?: number;
  /** How long cached data is considered fresh before a background refetch. */
  staleTime?: number;
}

export interface UseQueryResult<T> {
  data: T | undefined;
  error: unknown;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  refetch: () => void;
}

export function useQuery<T>({
  queryKey,
  queryFn,
  enabled = true,
  refetchInterval = 0,
  staleTime = 3000,
}: UseQueryOptions<T>): UseQueryResult<T> {
  const client = useContext(QueryContext);
  const key = keyToString(queryKey);
  const fnRef = useRef(queryFn);
  fnRef.current = queryFn;

  const [, forceRender] = useState(0);
  const rerender = useCallback(() => forceRender((n) => n + 1), []);

  const run = useCallback(() => {
    if (!enabled) return;
    const entry = client.getEntry<T>(key);
    const fresh = entry && entry.status === 'success' && Date.now() - entry.updatedAt < staleTime;
    if (fresh || entry?.promise) return;
    void client.fetch<T>(key, () => fnRef.current()).catch(() => undefined);
  }, [client, key, enabled, staleTime]);

  useEffect(() => client.subscribe(key, rerender), [client, key, rerender]);

  useEffect(() => {
    run();
  }, [run]);

  useEffect(() => {
    if (!enabled || !refetchInterval) return;
    const id = window.setInterval(() => {
      void client.fetch<T>(key, () => fnRef.current()).catch(() => undefined);
    }, refetchInterval);
    return () => window.clearInterval(id);
  }, [client, key, enabled, refetchInterval]);

  const entry = client.getEntry<T>(key);
  const refetch = useCallback(() => {
    void client.fetch<T>(key, () => fnRef.current()).catch(() => undefined);
  }, [client, key]);

  return {
    data: entry?.data,
    error: entry?.error,
    isLoading: (entry?.status ?? 'idle') === 'loading' && entry?.data === undefined,
    isFetching: entry?.status === 'loading',
    isError: entry?.status === 'error',
    refetch,
  };
}

interface UseMutationOptions<TArgs, TData> {
  mutationFn: (args: TArgs) => Promise<TData>;
  onSuccess?: (data: TData, args: TArgs) => void;
  onError?: (error: unknown, args: TArgs) => void;
}

export interface UseMutationResult<TArgs, TData> {
  mutate: (args: TArgs) => Promise<TData | undefined>;
  isPending: boolean;
  error: unknown;
  data: TData | undefined;
}

export function useMutation<TArgs, TData>({
  mutationFn,
  onSuccess,
  onError,
}: UseMutationOptions<TArgs, TData>): UseMutationResult<TArgs, TData> {
  const [isPending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(undefined);
  const [data, setData] = useState<TData | undefined>(undefined);

  const mutate = useCallback(
    async (args: TArgs) => {
      setPending(true);
      setError(undefined);
      try {
        const result = await mutationFn(args);
        setData(result);
        onSuccess?.(result, args);
        return result;
      } catch (err) {
        setError(err);
        onError?.(err, args);
        return undefined;
      } finally {
        setPending(false);
      }
    },
    [mutationFn, onSuccess, onError]
  );

  return { mutate, isPending, error, data };
}
