// web_ui/src/config/monitoring.ts

/**
 * Monitoring Dashboard Configuration
 * Centralized configuration for dashboard metrics and polling behavior
 */

/**
 * Default polling interval for metrics fetch (milliseconds)
 */
export const DEFAULT_METRICS_POLL_INTERVAL = 5000;

/**
 * Minimum allowed polling interval (1 second)
 * Prevents excessive server load from too-frequent polling
 */
export const MIN_POLL_INTERVAL = 1000;

/**
 * Maximum allowed polling interval (1 minute)
 * Ensures dashboard remains reasonably up-to-date
 */
export const MAX_POLL_INTERVAL = 60000;

/**
 * Helper to validate and normalize polling interval from env var
 * Extracted for testability and reuse
 * 
 * @param envValue - Raw environment variable string
 * @returns Validated interval in milliseconds, clamped to safe range
 */
export function getMetricsPollInterval(envValue?: string): number {
  const parsed = envValue ? Number.parseInt(envValue, 10) : NaN;
  
  // Validate: must be finite positive number
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return DEFAULT_METRICS_POLL_INTERVAL;
  }
  
  // Clamp to safe range
  return Math.max(MIN_POLL_INTERVAL, Math.min(MAX_POLL_INTERVAL, parsed));
}
