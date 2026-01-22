// web_ui/src/types/sync.ts

/**
 * Sync & Conflict Resolution Types
 * Centralized constants and types to prevent magic string drift.
 */

// Resolution Strategies
export const CONFLICT_RESOLUTION_STRATEGIES = {
  KEEP_LOCAL: 'keep_local',
  KEEP_REMOTE: 'keep_remote',
  KEEP_BOTH: 'keep_both',
} as const;

// Type derived from constants
export type ConflictResolutionStrategy = typeof CONFLICT_RESOLUTION_STRATEGIES[keyof typeof CONFLICT_RESOLUTION_STRATEGIES];

// Conflict Statuses
export const CONFLICT_STATUS = {
  PENDING: 'pending',
  RESOLVED: 'resolved',
} as const;

export type ConflictStatus = typeof CONFLICT_STATUS[keyof typeof CONFLICT_STATUS];

// Models
export interface ConflictLog {
  id: string;
  filePath: string;
  status: ConflictStatus;
  resolutionStrategy?: ConflictResolutionStrategy;
  timestamp?: string;
}
