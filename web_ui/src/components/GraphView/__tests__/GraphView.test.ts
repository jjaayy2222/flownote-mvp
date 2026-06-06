// web_ui/src/components/GraphView/__tests__/GraphView.test.ts

/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, it, expect, vi } from "vitest";

// Mock MAX_GRAPH_NODES to 3 for testing truncation
vi.mock("@/config/graph", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/config/graph")>();
  return {
    ...original,
    MAX_GRAPH_NODES: 3,
  };
});

import { _adaptGraphData } from "../GraphView";
import { NodeType } from "@/types/websocket";
import type { GraphNode, GraphEdge } from "@/types/websocket";
import type { GraphViewData } from "../types";

// Helper functions for clean mocking
function createMockNode(id: string, label: string, nodeType: NodeType = NodeType.NOTE): GraphNode {
  return {
    id,
    label,
    node_type: nodeType,
    properties: {},
    position_x: null,
    position_y: null,
    user_id_hash: null,
  };
}

function createMockEdge(
  id: string,
  source: any,
  target: any,
  relType: string = "related_to",
  weight: number = 1
): GraphEdge {
  return {
    id,
    source,
    target,
    relationship_type: relType as any,
    weight,
    properties: {},
  };
}

describe("_adaptGraphData", () => {
  it("should filter out invalid nodes and links", () => {
    const data: GraphViewData = {
      nodes: [
        createMockNode("node1", "Node 1", NodeType.NOTE),
        // Malformed node: missing node_type
        { id: "node2", label: "Node 2" } as any,
      ],
      edges: [
        // Valid link
        createMockEdge("edge1", "node1", "node3"),
        // Invalid link: target is nullish
        createMockEdge("edge2", "node1", null),
        // Invalid link: source is unresolvable object structure without id
        createMockEdge("edge3", { name: "no-id" }, "node1"),
      ],
    };

    const result = _adaptGraphData(data);
    
    // node2 is dropped because it is malformed
    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].id).toBe("node1");

    // edge2 and edge3 are dropped because of invalid endpoints
    // edge1 is dropped because "node3" is not in the allowedNodeIds (not present in nodes)
    expect(result.links).toHaveLength(0);
  });

  it("should truncate nodes exceeding MAX_GRAPH_NODES based on degree", () => {
    // MAX_GRAPH_NODES is mocked to 3.
    // We provide 5 nodes: node1 (deg 3), node2 (deg 2), node3 (deg 1), node4 (deg 0), node5 (deg 4)
    // node5 has degree 4 (connected to node1, node2, node3, node4)
    // node1 has degree 3 (connected to node5, node2, node3)
    // node2 has degree 2 (connected to node5, node1)
    // node3 has degree 1 (connected to node5)
    // node4 has degree 0
    // Expected top 3: node5 (4), node1 (3), node2 (2)
    const data: GraphViewData = {
      nodes: [
        createMockNode("node1", "N1"),
        createMockNode("node2", "N2"),
        createMockNode("node3", "N3"),
        createMockNode("node4", "N4"),
        createMockNode("node5", "N5"),
      ],
      edges: [
        createMockEdge("e1", "node5", "node1"),
        createMockEdge("e2", "node5", "node2"),
        createMockEdge("e3", "node5", "node3"),
        createMockEdge("e4", "node5", "node4"),
        createMockEdge("e5", "node1", "node2"),
        createMockEdge("e6", "node1", "node3"),
      ],
    };

    const result = _adaptGraphData(data);

    // Top 3 nodes should be allowed
    expect(result.nodes).toHaveLength(3);
    
    const nodeIds = result.nodes.map((n) => n.id);
    expect(nodeIds).toContain("node5"); // deg 4
    expect(nodeIds).toContain("node1"); // deg 3
    expect(nodeIds).toContain("node2"); // deg 2
    expect(nodeIds).not.toContain("node3"); // deg 1 (sliced out)
    expect(nodeIds).not.toContain("node4"); // deg 0 (sliced out)

    // Edges should only exist between node5, node1, node2
    // Valid edges: e1 (node5-node1), e2 (node5-node2), e5 (node1-node2)
    expect(result.links).toHaveLength(3);
    const edgeIds = result.links.map((l) => l.id);
    expect(edgeIds).toContain("e1");
    expect(edgeIds).toContain("e2");
    expect(edgeIds).toContain("e5");
  });

  it("should secure degree calculation loop against malformed edges", () => {
    // MAX_GRAPH_NODES is mocked to 3.
    // node1, node2, node3, node4 (4 nodes > 3 limit)
    // We add invalid edges targeting node4, which should NOT count towards its degree.
    // If invalid edges counted, node4 degree would be high and it wouldn't be sliced.
    const data: GraphViewData = {
      nodes: [
        createMockNode("node1", "N1"),
        createMockNode("node2", "N2"),
        createMockNode("node3", "N3"),
        createMockNode("node4", "N4"),
      ],
      edges: [
        // Valid edge: node1 to node2 (deg 1 each)
        createMockEdge("e1", "node1", "node2"),
        // Valid edge: node1 to node3 (deg of node1=2, node3=1)
        createMockEdge("e2", "node1", "node3"),
        // Invalid edge targeting node4 (should be skipped)
        createMockEdge("e3", "node4", null),
        // Invalid edge targeting node4 (should be skipped)
        createMockEdge("e4", "node4", { invalid: true }),
      ],
    };

    const result = _adaptGraphData(data);

    expect(result.nodes).toHaveLength(3);
    const nodeIds = result.nodes.map((n) => n.id);
    expect(nodeIds).toContain("node1"); // deg 2
    expect(nodeIds).toContain("node2"); // deg 1
    expect(nodeIds).toContain("node3"); // deg 1
    expect(nodeIds).not.toContain("node4"); // deg 0 (skipped invalid degrees)
  });
});
