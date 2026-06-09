"use client";

import React, { useCallback, useEffect, useState, useRef } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { useWebSocket } from "@/hooks/useWebSocket";
import { getWebSocketUrl } from "@/config/websocket";
import { isWebSocketEvent, WS_EVENT_TYPE, NodeType, GraphNode } from "@/types/websocket";
import { logger } from "@/lib/logger";
import { UI_CONFIG } from "@/config/ui";
import { API_BASE } from "@/lib/api";
import { getToastThrottleDelay } from "@/lib/ui";
import { GraphViewLoader as GraphView } from "./GraphViewLoader";
import { GraphViewData } from "./types";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

const GRAPH_UPDATE_THROTTLE = getToastThrottleDelay("GRAPH_UPDATE");

export function GraphContainer() {
  const router = useRouter();
  const [data, setData] = useState<GraphViewData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/graph/data`);
      if (!res.ok) {
        throw new Error("Failed to fetch graph data");
      }
      const fetchedData: GraphViewData = await res.json();
      setData(fetchedData);
    } catch (error) {
      console.error("Error fetching graph data:", error);
      toast.error("Failed to load graph data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // WebSocket Integration
  const { isConnected, lastMessage } = useWebSocket(getWebSocketUrl(), {
    autoConnect: true,
    reconnect: true,
  });

  const lastToastTimeRef = useRef<number>(0);

  useEffect(() => {
    if (!lastMessage) return;

    if (!isWebSocketEvent(lastMessage)) return;

    if (lastMessage.type === WS_EVENT_TYPE.GRAPH_UPDATED) {
      logger.debug("[GraphView] Graph updated event received, reloading data...");
      
      fetchData();

      const now = Date.now();
      
      if (now - lastToastTimeRef.current > GRAPH_UPDATE_THROTTLE) {
        toast.info("Graph data updated", {
          description: "Real-time sync from backend",
          id: UI_CONFIG.TOAST.IDS.GRAPH_UPDATE,
        });
        lastToastTimeRef.current = now;
      }
    }
  }, [lastMessage, fetchData]);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      // 캔버스 내 노드 클릭 시
      if (node.node_type === NodeType.NOTE) {
        toast.success(`노트로 이동: ${node.label}`);
        // 해당 마크다운 노트의 라우팅 경로로 이동
        router.push("/chat");
      } else {
        toast(`선택됨: ${node.label}`, {
          description: `타입: ${node.node_type}`,
          id: `node-click-${node.id}`
        });
      }
    },
    [router]
  );

  if (loading && !data) {
    return (
      <div className="flex h-[600px] w-full items-center justify-center p-10 bg-white border border-gray-200 rounded-lg shadow-sm">
        <div className="flex flex-col items-center gap-4 text-muted-foreground">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p>Loading Graph...</p>
        </div>
      </div>
    );
  }

  if (!loading && !data) {
    return (
      <div className="flex h-[600px] w-full items-center justify-center p-10 bg-white border border-gray-200 rounded-lg shadow-sm">
        <div className="flex flex-col items-center gap-4 text-muted-foreground">
          <p>Failed to load graph data.</p>
          <Button variant="outline" onClick={fetchData}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-[600px] w-full border border-gray-200 rounded-lg shadow-sm bg-white overflow-hidden">
      <div className="absolute top-4 right-4 z-10 pointer-events-none">
        {isConnected ? (
          <Badge variant="outline" className="bg-white/90 backdrop-blur text-green-600 border-green-200 shadow-sm">
            <div className="w-2 h-2 rounded-full bg-green-500 mr-2 animate-pulse" />
            Live
          </Badge>
        ) : (
          <Badge variant="outline" className="bg-white/90 backdrop-blur text-gray-500 shadow-sm">
            Connecting...
          </Badge>
        )}
      </div>
      
      {data && (
        <GraphView 
          data={data} 
          onNodeClick={handleNodeClick} 
        />
      )}
    </div>
  );
}
