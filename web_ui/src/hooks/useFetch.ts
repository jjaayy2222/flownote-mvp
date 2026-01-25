// web_ui/src/hooks/useFetch.ts

import { useState, useEffect, useCallback, useRef } from 'react';

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/**
 * Custom hook for abortable fetch
 * - Handles AbortController automatically
 * - Prevents race conditions
 * - Initial loading state is true
 */
export function useFetch<T>(
  fetchFn: (signal: AbortSignal) => Promise<T>,
  deps: ReadonlyArray<unknown> = []
) {
  const [state, setState] = useState<FetchState<T>>({
    data: null,
    loading: true,
    error: null,
  });

  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchData = useCallback(async () => {
    // Cancel previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    // Reset data to avoid showing stale content
    setState(prev => ({ ...prev, loading: true, error: null, data: null }));

    try {
      const result = await fetchFn(controller.signal);
      
      // Update state only if this is the latest request
      if (abortControllerRef.current === controller) {
        setState({ data: result, loading: false, error: null });
        abortControllerRef.current = null;
      }
    } catch (err) {
      // Ignore abort errors
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }
      
      // Update error state only if this is the latest request
      if (abortControllerRef.current === controller) {
        setState(prev => ({
           ...prev,
           loading: false,
           error: err instanceof Error ? err.message : 'Unknown error'
        }));
        abortControllerRef.current = null;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchFn, ...deps]);

  useEffect(() => {
    fetchData();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchData]);

  return { ...state, refetch: fetchData };
}
