// web_ui/src/components/dashboard/sync-monitor.tsx

"use client"

import React, { useState } from 'react';
import { useVisibilityPolling } from '@/hooks/use-visibility-polling';
import { API_BASE, fetchAPI } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { RefreshCw, CheckCircle2, XCircle, FileText, Server } from "lucide-react"
import { ConflictResolver } from "@/components/dashboard/conflict-resolver"
import { toast } from "sonner"
import { useTranslations } from "next-intl"

// Types
interface SyncStatus {
  connected: boolean;
  vault_path: string;
  last_sync: string;
  file_count: number;
  sync_interval: number;
  enabled: boolean;
}

interface MCPStatus {
  running: boolean;
  active_clients: string[];
  tools_registered: string[];
  resources_registered: string[];
}

interface Conflict {
  conflict_id: string;
  file_path: string;
  conflict_type: string;
  status: string;
  timestamp: string;
  resolution_method?: string;
  notes?: string;
  local_hash: string;
  remote_hash: string;
}

const POLLING_INTERVAL = 5000;

export function SyncMonitor() {
  const t = useTranslations('sync_monitor');
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [mcpStatus, setMcpStatus] = useState<MCPStatus | null>(null);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // State for Conflict Resolution
  const [selectedConflict, setSelectedConflict] = useState<{
    id: string; 
    path: string; 
    localContent: string; 
    remoteContent: string
  } | null>(null);

  const fetchData = async () => {
    try {
      // Parallel fetch for dashboard data
      const [syncData, mcpData, conflictData] = await Promise.all([
        fetchAPI<SyncStatus>(`${API_BASE}/api/sync/status`),
        fetchAPI<MCPStatus>(`${API_BASE}/api/sync/mcp/status`),
        fetchAPI<Conflict[]>(`${API_BASE}/api/sync/conflicts?limit=10`)
      ]);
      
      setSyncStatus(syncData);
      setMcpStatus(mcpData);
      setConflicts(conflictData);
      setError(null);
    } catch (err) {
      console.error('Sync monitor error:', err);
      const message = err instanceof Error ? err.message : 'Failed to fetch data';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  // Optimized polling with visibility check
  useVisibilityPolling(fetchData, POLLING_INTERVAL);

  const handleResolveClick = (conflict: Conflict) => {
    // In a real scenario, we would fetch the actual file content diff here.
    // For Phase 6 Mockup, we use placeholder text.
    setSelectedConflict({
        id: conflict.conflict_id,
        path: conflict.file_path,
        localContent: `# Local Version\n\nThis is the current content of ${conflict.file_path} on your local machine.\n\n- It has some local edits.\n- Last modified: Today`,
        remoteContent: `# Remote Version\n\nThis is the incoming content for ${conflict.file_path} from the remote vault.\n\n- It has conflicting changes.\n- Last modified: Yesterday`
    });
  };

  const handleResolution = async (decision: 'local' | 'remote' | 'both') => {
      // TODO: Call backend API to resolve conflict
      console.log(`Resolving conflict ${selectedConflict?.id} with decision: ${decision}`);
      
      toast.success(t('conflicts.resolved_toast', { decision }), {
        description: `${t('conflicts.file')}: ${selectedConflict?.path}`
      });
      
      setSelectedConflict(null);
      // Refresh list
      fetchData();
  };

  if (loading && !syncStatus) {
    return <div className="flex justify-center p-8 text-muted-foreground">{t('loading')}</div>;
  }

  if (error && !syncStatus) {
    return (
      <div className="p-4 border border-red-200 rounded-md bg-red-50 text-red-700">
        <h3 className="font-bold flex items-center gap-2">
          <XCircle className="h-4 w-4" /> {t('error_title')}
        </h3>
        <p>{error}</p>
        <Button onClick={fetchData} variant="outline" className="mt-2 bg-white">{t('retry')}</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">{t('title')}</h2>
        <Button onClick={fetchData} variant="outline" size="sm">
          <RefreshCw className="mr-2 h-4 w-4" /> {t('refresh')}
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
        {/* Obsidian Connection Status */}
        <Card className="col-span-4 lg:col-span-3">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-muted-foreground" />
                {t('connection.title')}
              </span>
              {syncStatus?.connected ? 
                <Badge className="bg-green-500 hover:bg-green-600">{t('connection.connected')}</Badge> : 
                <Badge variant="destructive">{t('connection.disconnected')}</Badge>
              }
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex justify-between items-center border-b pb-2">
                <span className="text-sm font-medium text-muted-foreground">{t('connection.vault_path')}</span>
                <span className="text-sm font-mono bg-muted px-2 py-1 rounded">
                  {syncStatus?.vault_path || 'N/A'}
                </span>
              </div>
              <div className="flex justify-between items-center border-b pb-2">
                <span className="text-sm font-medium text-muted-foreground">{t('connection.last_sync')}</span>
                <span className="text-sm">
                  {syncStatus?.last_sync ? new Date(syncStatus.last_sync).toLocaleString() : t('connection.never')}
                </span>
              </div>
              <div className="flex justify-between items-center pb-2">
                <span className="text-sm font-medium text-muted-foreground">{t('connection.total_files')}</span>
                <span className="text-sm font-bold">{syncStatus?.file_count || 0}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* MCP Server Status */}
        <Card className="col-span-4 lg:col-span-4">
          <CardHeader>
             <CardTitle className="flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Server className="h-5 w-5 text-muted-foreground" />
                {t('mcp.title')}
              </span>
              {mcpStatus?.running ? 
                <Badge className="bg-blue-500 hover:bg-blue-600">{t('mcp.running')}</Badge> : 
                <Badge variant="destructive">{t('mcp.stopped')}</Badge>
              }
            </CardTitle>
          </CardHeader>
          <CardContent>
             <div className="space-y-4">
               <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-2">{t('mcp.active_clients')}</h4>
                  <div className="flex flex-wrap gap-2">
                    {mcpStatus?.active_clients?.length ? (
                      mcpStatus.active_clients.map((client, i) => (
                        <Badge key={i} variant="secondary">{client}</Badge>
                      ))
                    ) : <span className="text-xs text-muted-foreground italic">{t('mcp.no_clients')}</span>}
                  </div>
               </div>
               <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-2">{t('mcp.registered_tools')}</h4>
                  <div className="flex flex-wrap gap-2">
                    {mcpStatus?.tools_registered?.map((tool, i) => (
                      <Badge key={i} variant="outline" className="border-purple-200 text-purple-700 bg-purple-50">
                        {tool}
                      </Badge>
                    ))}
                  </div>
               </div>
             </div>
          </CardContent>
        </Card>
      </div>

      {/* Conflict History */}
      <Card className="col-span-7">
        <CardHeader>
          <CardTitle>{t('conflicts.title')}</CardTitle>
          <CardDescription>{t('conflicts.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          {conflicts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center text-muted-foreground">
              <CheckCircle2 className="h-12 w-12 text-green-500 mb-2 opacity-20" />
              <p>{t('conflicts.no_conflicts')}</p>
            </div>
          ) : (
            <div className="space-y-4">
              {conflicts.map((conflict) => (
                <div key={conflict.conflict_id} className="flex items-start justify-between p-4 rounded-lg border bg-card text-card-foreground shadow-sm">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{conflict.file_path}</span>
                      <Badge variant={conflict.status === 'resolved' ? 'default' : 'destructive'} 
                             className={conflict.status === 'resolved' ? 'bg-green-500' : ''}>
                        {conflict.status}
                      </Badge>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {conflict.conflict_type} • {new Date(conflict.timestamp).toLocaleString()}
                    </div>
                    {conflict.resolution_method && (
                       <div className="text-xs text-muted-foreground mt-1">
                         {t('conflicts.resolved_via')}: <span className="font-medium">{conflict.resolution_method}</span>
                       </div>
                    )}
                  </div>
                  
                  <div className="flex items-center gap-4">
                    <div className="text-xs font-mono text-muted-foreground text-right hidden md:block">
                        <div>L: {conflict.local_hash.substring(0, 7)}</div>
                        <div>R: {conflict.remote_hash.substring(0, 7)}</div>
                    </div>
                    {conflict.status !== 'resolved' && (
                        <Button size="sm" onClick={() => handleResolveClick(conflict)}>{t('conflicts.resolve_btn')}</Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Conflict Resolver Dialog */}
      <ConflictResolver 
        isOpen={!!selectedConflict} 
        onClose={() => setSelectedConflict(null)}
        conflict={selectedConflict}
        onResolve={handleResolution}
      />
    </div>
  );
}
