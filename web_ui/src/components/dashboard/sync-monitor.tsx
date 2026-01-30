// web_ui/src/components/dashboard/sync-monitor.tsx

"use client"

import React, { useState, useEffect } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { getWebSocketUrl } from '@/config/websocket';
import { WebSocketEvent, isWebSocketEvent } from '@/types/websocket';
import { API_BASE, fetchAPI } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { RefreshCw, CheckCircle2, XCircle, FileText, Server } from "lucide-react"
import { toast } from "sonner"
import { useTranslations, useLocale } from "next-intl"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { ConflictDiffViewer } from "@/components/sync/ConflictDiffViewer"
import { type ConflictResolutionStrategy, CONFLICT_STATUS } from '@/types/sync';

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



export function SyncMonitor() {
  const t = useTranslations('sync_monitor');
  const locale = useLocale();
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [mcpStatus, setMcpStatus] = useState<MCPStatus | null>(null);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // State for Conflict Resolution
  const [selectedConflictId, setSelectedConflictId] = useState<string | null>(null);

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

  // WebSocket Integration
  const { isConnected, lastMessage } = useWebSocket(getWebSocketUrl(), {
    autoConnect: true,
    reconnect: true,
  });

  // Initial fetch
  useEffect(() => {
    fetchData();
  }, []);

  // Handle WebSocket events
  useEffect(() => {
    if (!lastMessage) return;

    // 런타임 타입 검증 (Type Guard) - 안전성 강화
    if (!isWebSocketEvent(lastMessage)) {
      console.warn('[SyncMonitor] Received invalid WebSocket message structure:', lastMessage);
      return;
    }

    // 타입 가드 통과 후 lastMessage는 WebSocketEvent로 자동 추론됨
    const event: WebSocketEvent = lastMessage;

    switch (event.type) {
      case 'sync_status_changed':
        console.log('[SyncMonitor] Sync status changed, refreshing data...');
        fetchData();
        break;
      case 'conflict_detected':
        console.log('[SyncMonitor] Conflict detected, refreshing list...');
        fetchData();
        toast.warning('New conflict detected!', {
          description: `Conflict ID: ${event.data.id}`
        });
        break;
      case 'file_classified':
      case 'graph_updated':
        // 이 컴포넌트에서는 모니터링하지 않는 이벤트
        break;
      default:
        // Exhaustiveness Check (Dead Code in Runtime): 
        // 모든 케이스가 처리되지 않으면 여기서 컴파일 에러가 발생합니다.
        // 런타임에는 이 분기에 도달할 수 없습니다 (isWebSocketEvent 가드가 보장).
        const _exhaustiveCheck: never = event;
        void _exhaustiveCheck;
        break;
    }
  }, [lastMessage]);

  const handleResolveClick = (conflict: Conflict) => {
    setSelectedConflictId(conflict.conflict_id);
  };

  const handleResolution = async (strategy: ConflictResolutionStrategy) => {
      if (!selectedConflictId) return;

      try {
        // Call backend API to resolve conflict
        const params = new URLSearchParams({ resolution_method: strategy });
        await fetchAPI(`${API_BASE}/api/sync/conflicts/${selectedConflictId}/resolve?${params.toString()}`, {
            method: 'POST',
        });
        
        toast.success(t('conflicts.resolved_toast', { decision: strategy }), {
            description: `${t('conflicts.file')}: ${selectedConflictId}`
        });
        
        setSelectedConflictId(null);
        // Refresh list
        fetchData();
      } catch (err) {
        console.error('Resolution failed:', err);
        toast.error('Failed to resolve conflict');
      }
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
        <div className="flex items-center gap-4">
          <h2 className="text-3xl font-bold tracking-tight">{t('title')}</h2>
          {isConnected ? (
            <Badge variant="outline" className="text-green-600 border-green-200 bg-green-50">
              <div className="w-2 h-2 rounded-full bg-green-500 mr-2 animate-pulse" />
              Live
            </Badge>
          ) : (
            <Badge variant="outline" className="text-gray-500">
              Connecting...
            </Badge>
          )}
        </div>
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
                  {syncStatus?.last_sync 
                    ? new Intl.DateTimeFormat(locale, {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      }).format(new Date(syncStatus.last_sync))
                    : t('connection.never')}
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
                      <Badge variant={conflict.status === CONFLICT_STATUS.RESOLVED ? 'default' : 'destructive'} 
                             className={conflict.status === CONFLICT_STATUS.RESOLVED ? 'bg-green-500' : ''}>
                        {conflict.status}
                      </Badge>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {conflict.conflict_type} • {new Intl.DateTimeFormat(locale, {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      }).format(new Date(conflict.timestamp))}
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
                    {conflict.status !== CONFLICT_STATUS.RESOLVED && (
                        <Button size="sm" onClick={() => handleResolveClick(conflict)}>{t('conflicts.resolve_btn')}</Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Conflict Resolver Dialog (Integrated Diff Viewer) */}
      <Sheet open={!!selectedConflictId} onOpenChange={(open) => !open && setSelectedConflictId(null)}>
        <SheetContent className="w-full sm:max-w-[90vw] md:max-w-[1000px] p-0">
            <div className="h-full flex flex-col p-6">
                <SheetHeader className="mb-4">
                    <SheetTitle>{t('conflicts.resolve_btn')}</SheetTitle>
                </SheetHeader>
                <div className="flex-1 overflow-hidden">
                    {selectedConflictId && (
                        <ConflictDiffViewer 
                            conflictId={selectedConflictId} 
                            onResolve={handleResolution}
                        />
                    )}
                </div>
            </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
