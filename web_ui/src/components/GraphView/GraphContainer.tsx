"use client";

import React, { useCallback } from "react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { NodeType, GraphNode } from "@/types/websocket";
import { GraphViewLoader as GraphView } from "./GraphViewLoader";
import { useGraphData } from "./useGraphData";
import { useGraphLiveUpdates } from "./useGraphLiveUpdates";

export function GraphContainer() {
  const router = useRouter();
  const { data, loading, reload } = useGraphData();
  const { isConnected } = useGraphLiveUpdates(reload);

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
          <Button variant="outline" onClick={reload}>
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
