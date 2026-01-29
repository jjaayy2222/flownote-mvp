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
 * - Uses partial "latest ref" pattern to avoid unnecessary re-fetches when fetchFn identity changes
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
  
  // Use a ref to store the latest fetch function.
  // This allows us to exclude fetchFn from the effect dependency array,
  // preventing re-fetches when the function is recreated (e.g. inline functions) 
  // but dependencies haven't changed.
  const fetchFnRef = useRef(fetchFn);
  useEffect(() => {
    fetchFnRef.current = fetchFn;
  }, [fetchFn]);

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
      const result = await fetchFnRef.current(controller.signal);
      
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
    // We intentionally spread deps here to trigger re-fetch only when deps change.
    // fetchFnRef is stable, so we don't need to include it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps]);

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
