// web_ui/src/components/sync/ConflictDiffViewer.tsx

'use client';

import React from 'react';
import { CONFLICT_RESOLUTION_STRATEGIES, type ConflictResolutionStrategy } from '../../types/sync';

interface ConflictDiffViewerProps {
  conflictId: string;
  onResolve?: (strategy: ConflictResolutionStrategy) => void;
}

/**
 * Conflict Diff Viewer Component
 * - Displays side-by-side or inline diffs
 * - Provides resolution actions (Local, Remote, Both)
 * - Uses centralized constants for resolution strategies
 */
export function ConflictDiffViewer({ conflictId, onResolve }: ConflictDiffViewerProps) {
  return (
    <div className="conflict-diff-viewer w-full h-full flex flex-col gap-4 p-4 border rounded-lg bg-background">
      <div className="flex justify-between items-center header">
        <h2 className="text-lg font-semibold">Conflict Resolution</h2>
        <div className="text-sm text-muted-foreground">ID: {conflictId}</div>
      </div>

      <div className="diff-area flex-1 min-h-[400px] border border-border rounded-md bg-muted/20 flex items-center justify-center">
        <span className="text-muted-foreground">
          Diff Viewer Placeholder (Integration Pending)
        </span>
      </div>

      <div className="actions flex justify-end gap-2">
        <button 
          type="button"
          className="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90"
          onClick={() => onResolve?.(CONFLICT_RESOLUTION_STRATEGIES.KEEP_LOCAL)}
        >
          Keep Local
        </button>
        <button 
          type="button"
          className="px-4 py-2 bg-secondary text-secondary-foreground rounded hover:bg-secondary/80"
          onClick={() => onResolve?.(CONFLICT_RESOLUTION_STRATEGIES.KEEP_REMOTE)}
        >
          Keep Remote
        </button>
        <button 
          type="button"
          className="px-4 py-2 border border-input bg-background hover:bg-accent hover:text-accent-foreground rounded"
          onClick={() => onResolve?.(CONFLICT_RESOLUTION_STRATEGIES.KEEP_BOTH)}
        >
          Keep Both
        </button>
      </div>
    </div>
  );
}
