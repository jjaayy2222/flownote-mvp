// web_ui/src/types/sync.ts

/**
 * Sync & Conflict Resolution Types
 */

export type ConflictResolutionStrategy = 'keep_local' | 'keep_remote' | 'keep_both';

export interface ConflictLog {
  id: string;
  filePath: string;
  status: 'resolved' | 'pending';
  // ... other fields can be added as needed
}
