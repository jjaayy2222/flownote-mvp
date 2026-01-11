// web_ui/src/components/para/GraphView.tsx

'use client';

import React, { useCallback, useEffect, useState, useRef } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Edge,
  Node,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { useWebSocket } from '@/hooks/useWebSocket';
import { getWebSocketUrl } from '@/config/websocket';
import { isWebSocketEvent, WS_EVENT_TYPE } from '@/types/websocket';
import { logger } from '@/lib/logger';
import { UI_CONFIG } from '@/config/ui';
import { API_BASE } from '@/lib/api';

// Review Reflection: Calculate throttle duration outside component to avoid recalculation
// Ensures robustness by validating nonnegative value with Math.max
const GRAPH_UPDATE_THROTTLE = Math.max(
  0,
  UI_CONFIG.TOAST.THROTTLE_MS.GRAPH_UPDATE ?? UI_CONFIG.TOAST.THROTTLE_MS.DEFAULT ?? 3000
);

interface GraphData {
  nodes: Node[];
  edges: Edge[];
}

export default function GraphView() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/graph/data`);
      if (!res.ok) {
        throw new Error('Failed to fetch graph data');
      }
      const data: GraphData = await res.json();
      setNodes(data.nodes);
      setEdges(data.edges);
    } catch (error) {
      console.error('Error fetching graph data:', error);
      toast.error("Failed to load graph data");
    } finally {
      setLoading(false);
    }
  }, [setNodes, setEdges]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // WebSocket Integration
  const { isConnected, lastMessage } = useWebSocket(getWebSocketUrl(), {
    autoConnect: true,
    reconnect: true,
  });

  // Reference for throttling toasts
  const lastToastTimeRef = useRef<number>(0);

  // Handle WebSocket events
  useEffect(() => {
    if (!lastMessage) return;

    // 런타임 타입 가드
    if (!isWebSocketEvent(lastMessage)) return;

    // 싱글 소스 상수(WS_EVENT_TYPE)를 사용하여 이벤트 처리
    if (lastMessage.type === WS_EVENT_TYPE.GRAPH_UPDATED) {
      logger.debug('[GraphView] Graph updated event received, reloading data...');
      
      fetchData();

      // Toast Throttling & Stacking Prevention
      const now = Date.now();
      
      if (now - lastToastTimeRef.current > GRAPH_UPDATE_THROTTLE) {
        toast.info("Graph data updated", {
          description: "Real-time sync from backend",
          id: UI_CONFIG.TOAST.IDS.GRAPH_UPDATE, // 동일 ID 사용으로 스택킹 방지
        });
        lastToastTimeRef.current = now;
      }
    }
  }, [lastMessage, fetchData]);

  // Helper to determine node type label
  const getNodeTypeLabel = (node: Node) => {
    if (node.type === "input") return "Category";
    if (!node.type || node.type === "default") return "File";
    return "Unknown Type";
  };

  const onNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
    // 1. Null Safety: Use nullish coalescing to allow empty strings if valid
    const label = node.data?.label ?? "Unknown Node";

    // 2. Type Mapping: Use helper function
    const typeLabel = getNodeTypeLabel(node);
    
    // 3. Prevent Toast Stacking: Use a consistent ID includes type context
    toast(`Selected: ${label}`, {
      description: `Type: ${typeLabel}`,
      id: `node-click-${node.id}-${typeLabel}`, 
    });
  }, []);

  if (loading) {
    return <div className="flex h-full w-full items-center justify-center p-10">Loading Graph...</div>;
  }

  return (
    <div className="relative h-[600px] w-full border border-gray-200 rounded-lg shadow-sm bg-white">
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
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        fitView
        attributionPosition="bottom-right"
      >
        <Background gap={12} size={1} />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  );
}
