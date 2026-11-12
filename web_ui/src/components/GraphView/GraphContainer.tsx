"use client";

import React, { useCallback, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { GraphNode } from "@/types/websocket";
import { GraphNodePanel } from "@/components/layout/graph-node-panel";
import { GraphViewLoader as GraphView } from "./GraphViewLoader";
import { useGraphData } from "./useGraphData";
import { useGraphLiveUpdates } from "./useGraphLiveUpdates";
import { adaptGraphData } from "./graphViewAdapter";

export function GraphContainer() {
  const { data, loading, reload } = useGraphData();
  const { isConnected } = useGraphLiveUpdates(reload);
  const preparedData = useMemo(
    () => (data ? adaptGraphData(data) : null),
    [data],
  );
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [observedData, setObservedData] = useState(data);

  if (data !== observedData) {
    setObservedData(data);
    const selectedNodeStillExists = preparedData?.nodes.some(
      (node) => node.id === selectedNodeId,
    );
    if (selectedNodeId !== null && !selectedNodeStillExists) {
      setSelectedNodeId(null);
    }
  }

  const selectedNode = useMemo(
    () => preparedData?.nodes.find((node) => node.id === selectedNodeId) ?? null,
    [preparedData, selectedNodeId],
  );

  const relatedNodes = useMemo(() => {
    if (!data || !preparedData || !selectedNode) return [];

    const relatedNodeIds = new Set<string>();
    for (const edge of data.edges) {
      if (edge.source === selectedNode.id) relatedNodeIds.add(edge.target);
      if (edge.target === selectedNode.id) relatedNodeIds.add(edge.source);
    }

    return preparedData.nodes.filter((node) => relatedNodeIds.has(node.id));
  }, [data, preparedData, selectedNode]);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      setSelectedNodeId((currentNodeId) =>
        currentNodeId === node.id ? null : node.id,
      );
    },
    [],
  );

  const handleRelatedNodeSelect = useCallback(
    (node: GraphNode) => {
      if (preparedData?.nodes.some((renderedNode) => renderedNode.id === node.id)) {
        setSelectedNodeId(node.id);
      }
    },
    [preparedData],
  );

  const handlePanelClose = useCallback(() => setSelectedNodeId(null), []);

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
          <Button variant="outline" onClick={() => reload()} disabled={loading}>
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

      {preparedData && (
        <GraphView
          data={preparedData}
          onNodeClick={handleNodeClick}
          selectedNodeId={selectedNodeId}
        />
      )}
      <GraphNodePanel
        node={selectedNode}
        relatedNodes={relatedNodes}
        isOpen={selectedNode !== null}
        onClose={handlePanelClose}
        onNodeSelect={handleRelatedNodeSelect}
      />
    </div>
  );
}
