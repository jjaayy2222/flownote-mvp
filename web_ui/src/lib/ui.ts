// web_ui/src/lib/ui.ts

import { UI_CONFIG } from '@/config/ui';

/**
 * Type helper for Throttle keys
 * Excludes '_INTERNAL_FALLBACK' as it is an internal safety mechanism, not a valid toast type key.
 */
type ThrottleKey = Exclude<keyof typeof UI_CONFIG.TOAST.THROTTLE_MS, '_INTERNAL_FALLBACK'>;

/**
 * Calculates a safe throttle duration for a given toast type.
 * 
 * Applies multiple layers of fallback logic to ensure robustness:
 * 1. Specific configuration for the key
 * 2. Default override provided by caller (optional)
 * 3. FALLBACK configuration from ui.ts
 * 4. Hardcoded safety net (3000ms)
 * 
 * Also ensures the result is non-negative using Math.max.
 */
export function getToastThrottleDelay(key: ThrottleKey, defaultOverride?: number): number {
  const config = UI_CONFIG.TOAST.THROTTLE_MS;
  // 설정값 조회 우선 -> 오버라이드 -> 전역 폴백 -> 최후의 보루
  const val = config[key] ?? defaultOverride ?? config._INTERNAL_FALLBACK ?? 3000;
  return Math.max(0, val);
}
