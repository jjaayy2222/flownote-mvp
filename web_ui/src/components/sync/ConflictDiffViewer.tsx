// web_ui/src/components/sync/ConflictDiffViewer.tsx

'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { DiffEditor } from '@monaco-editor/react';
import { CONFLICT_RESOLUTION_STRATEGIES, type ConflictResolutionStrategy, type ConflictDiffResponse } from '../../types/sync';
import { API_BASE, fetchAPI } from '@/lib/api';

interface ConflictDiffViewerProps {
  conflictId: string;
  onResolve?: (strategy: ConflictResolutionStrategy) => void;
}

/**
 * Conflict Diff Viewer Component
 * - Fetches diff data from backend
 * - Displays side-by-side diff using Monaco DiffEditor
 * - Provides resolution actions (Local, Remote, Both)
 */
export function ConflictDiffViewer({ conflictId, onResolve }: ConflictDiffViewerProps) {
  const [data, setData] = useState<ConflictDiffResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDiff = useCallback(async () => {
    if (!conflictId) return;
    
    try {
      setLoading(true);
      setError(null);
      // GET /api/sync/conflicts/{id}/diff
      const response = await fetchAPI<ConflictDiffResponse>(`${API_BASE}/api/sync/conflicts/${conflictId}/diff`);
      setData(response);
    } catch (err) {
      console.error('Failed to load diff:', err);
      setError(err instanceof Error ? err.message : 'Failed to load diff data');
    } finally {
      setLoading(false);
    }
  }, [conflictId]);

  useEffect(() => {
    loadDiff();
  }, [loadDiff]);

  if (loading) {
    return (
      <div className="w-full h-full flex items-center justify-center p-8 border rounded-lg bg-muted/10">
        <span className="text-muted-foreground animate-pulse">Loading diff data...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full h-[400px] flex flex-col items-center justify-center p-8 border border-red-200 rounded-lg bg-red-50 text-red-600 gap-2">
        <span className="font-semibold">Error loading content</span>
        <span className="text-sm">{error}</span>
        <button 
           type="button"
           onClick={loadDiff}
           className="mt-4 px-4 py-2 bg-white border border-red-200 rounded hover:bg-red-50 text-sm"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) {
    return <div className="p-8 text-center text-muted-foreground">No diff data available</div>;
  }

  return (
    <div className="conflict-diff-viewer w-full h-full flex flex-col gap-4 p-4 border rounded-lg bg-background">
      <div className="flex justify-between items-center header">
        <h2 className="text-lg font-semibold">Conflict Resolution</h2>
        <div className="text-sm text-muted-foreground">ID: {conflictId}</div>
      </div>

      <div className="diff-area flex-1 min-h-[500px] border border-border rounded-md overflow-hidden bg-zinc-900">
        <DiffEditor
          height="100%"
          language={data.file_type || 'markdown'}
          // Mapping: Original -> Remote (Incoming/Left), Modified -> Local (Current/Right)
          original={data.remote_content}
          modified={data.local_content}
          options={{
            readOnly: true,
            renderSideBySide: true,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            automaticLayout: true,
            diffWordWrap: 'on',
          }}
          theme="vs-dark"
        />
      </div>

      <div className="actions flex justify-end gap-2 pt-2">
        <button 
          type="button"
          className="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90 font-medium transition-colors"
          onClick={() => onResolve?.(CONFLICT_RESOLUTION_STRATEGIES.KEEP_LOCAL)}
        >
          Keep Local (Modified)
        </button>
        <button 
          type="button"
          className="px-4 py-2 bg-secondary text-secondary-foreground rounded hover:bg-secondary/80 font-medium transition-colors"
          onClick={() => onResolve?.(CONFLICT_RESOLUTION_STRATEGIES.KEEP_REMOTE)}
        >
          Keep Remote (Original)
        </button>
        <button 
          type="button"
          className="px-4 py-2 border border-input bg-background hover:bg-accent hover:text-accent-foreground rounded font-medium transition-colors"
          onClick={() => onResolve?.(CONFLICT_RESOLUTION_STRATEGIES.KEEP_BOTH)}
        >
          Keep Both
        </button>
      </div>
    </div>
  );
}
