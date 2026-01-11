// web_ui/src/config/ui.ts

/**
 * UI Configuration Constants
 * 
 * Shared configuration for UI elements like Toasts, Animations, etc.
 */

export const UI_CONFIG = {
  TOAST: {
    /** 
     * Throttle durations (ms) for different types of toasts 
     * to prevent spamming in high-update scenarios.
     */
    THROTTLE_MS: {
      /** Standard throttle time for generic toasts */
      DEFAULT: 2000,
      GRAPH_UPDATE: 3000,
      SYNC_UPDATE: 3000,
      /** 
       * [INTERNAL USE ONLY] 
       * Safety fallback value used when configuration is missing or invalid 
       */
      _INTERNAL_FALLBACK: 3000,
    },
    
    /** Specific IDs for toasts to prevent stacking (de-duplication) */
    IDS: {
      GRAPH_UPDATE: 'live-graph-update',
      SYNC_STATUS: 'sync-status-update',
    },
  },
} as const;
