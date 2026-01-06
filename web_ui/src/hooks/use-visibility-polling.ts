/* web_ui/src/hooks/use-visibility-polling.ts */

import { useEffect, useRef } from 'react';

/**
 * Polling hook that respects page visibility and prevents overlapping requests.
 * 
 * @param callback Async function to execute
 * @param delay Polling interval in milliseconds
 */
export function useVisibilityPolling(callback: () => Promise<void> | void, delay: number) {
  const savedCallback = useRef(callback);

  // Always keep the latest callback
  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout>;
    let cancelled = false;
    let inFlight = false;

    const poll = async () => {
      if (cancelled) return;

      // 1. SSR check & Visibility check
      // If hidden, reschedule and skip execution to save resources
      if (typeof document !== 'undefined' && document.hidden) {
        timeoutId = setTimeout(poll, delay);
        return;
      }

      // 2. Overlapping check
      // If a request is already in flight, skip this cycle (but reschedule)
      if (inFlight) {
        timeoutId = setTimeout(poll, delay);
        return;
      }

      try {
        inFlight = true;
        await savedCallback.current();
      } catch (error) {
        console.error("Polling execution error:", error);
      } finally {
        inFlight = false;
        // 3. Schedule next poll only if not cancelled
        if (!cancelled) {
          timeoutId = setTimeout(poll, delay);
        }
      }
    };

    const handleVisibilityChange = () => {
      // When tab becomes visible, try to poll immediately
      if (typeof document !== 'undefined' && !document.hidden && !inFlight) {
        clearTimeout(timeoutId);
        poll();
      }
    };

    if (typeof document !== 'undefined') {
      document.addEventListener("visibilitychange", handleVisibilityChange);
    }

    // Start the loop
    poll();

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
      if (typeof document !== 'undefined') {
        document.removeEventListener("visibilitychange", handleVisibilityChange);
      }
    };
  }, [delay]);
}
