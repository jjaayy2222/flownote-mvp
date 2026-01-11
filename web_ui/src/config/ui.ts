// web_ui/src/config/ui.ts

/**
 * UI Configuration Constants
 * 
 * Shared configuration for UI elements like Toasts, Animations, etc.
 */

export const UI_CONFIG = {
  TOAST: {
    /** Minimum time (ms) between generic update toasts to prevent spamming */
    THROTTLE_MS: 3000,
    
    /** Specific IDs for toasts to prevent stacking (de-duplication) */
    IDS: {
      GRAPH_UPDATE: 'live-graph-update',
      SYNC_STATUS: 'sync-status-update',
    },
  },
} as const;
