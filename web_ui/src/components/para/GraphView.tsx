'use client';

import React, { useCallback, useEffect, useState } from 'react';
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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

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
      const res = await fetch(`${API_BASE_URL}/api/graph/data`);
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
    <div className="h-[600px] w-full border border-gray-200 rounded-lg shadow-sm bg-white">
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
