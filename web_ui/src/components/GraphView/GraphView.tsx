"use client";
// web_ui/src/components/GraphView/GraphView.tsx
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Phase 4-3 ➀: 지식 그래프 시각화 캔버스 컴포넌트
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//
// [역할]
// react-force-graph 의 ForceGraph2D 를 래핑하는 핵심 캔버스 컴포넌트입니다.
// 이 파일은 반드시 GraphViewLoader.tsx 를 통해 동적(dynamic) 로드되어야 하며,
// 직접 import 하면 Next.js SSR 단계에서 window 참조 오류가 발생합니다.
//
// [SSOT 연동]
// - 그래프 데이터 타입: backend/schemas/graph.py → websocket.ts (GraphNode, GraphEdge)
// - 설정 상수: src/config/graph.ts (MAX_GRAPH_NODES, 색상 등)
// - 어댑터 타입: ./types.ts (ForceGraphNode, ForceGraphLink)
//
// [하드코딩 금지]
// 모든 매직 넘버는 src/config/graph.ts 의 named export 를 참조합니다.
//
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import React, { useCallback, useRef, useState, useMemo } from "react";
import ForceGraph2D, {
  type ForceGraphMethods,
  type NodeObject,
  type LinkObject,
} from "react-force-graph-2d";

import type { GraphNode } from "@/types/websocket";
import { NodeType } from "@/types/websocket";
import {
  MAX_GRAPH_NODES,
  GRAPH_BG_COLOR,
  GRAPH_NODE_COLOR_NOTE,
  GRAPH_NODE_COLOR_KEYWORD,
  GRAPH_NODE_COLOR_TAG,
  GRAPH_NODE_COLOR_CATEGORY,
  GRAPH_LINK_COLOR,
  GRAPH_HIGHLIGHT_COLOR,
  GRAPH_NODE_RADIUS,
  GRAPH_NODE_SELECTED_SCALE,
  GRAPH_COOLDOWN_TICKS,
} from "@/config/graph";
import type {
  ForceGraphNode,
  ForceGraphLink,
  GraphViewData,
  OnNodeClickCallback,
} from "./types";

// ─────────────────────────────────────────
// 로컬 타입 별칭 (가독성 향상 및 런타임 캐스팅 방지)
// ─────────────────────────────────────────
type NodeObj = NodeObject<ForceGraphNode>;
type LinkObj = LinkObject<ForceGraphNode, ForceGraphLink>;
type FGMethods = ForceGraphMethods<NodeObj, LinkObj>;

// ─────────────────────────────────────────
// 헬퍼: NodeType → 색상 매핑
// ─────────────────────────────────────────

/** NodeType enum 값을 캔버스 렌더링 색상으로 변환합니다. */
function resolveNodeColor(nodeType: NodeType): string {
  switch (nodeType) {
    case NodeType.NOTE:
      return GRAPH_NODE_COLOR_NOTE;
    case NodeType.KEYWORD:
      return GRAPH_NODE_COLOR_KEYWORD;
    case NodeType.TAG:
      return GRAPH_NODE_COLOR_TAG;
    case NodeType.CATEGORY:
      return GRAPH_NODE_COLOR_CATEGORY;
    default: {
      const _exhaustiveCheck: never = nodeType;
      console.warn(`[GraphView] Unknown nodeType: ${_exhaustiveCheck}`);
      return GRAPH_NODE_COLOR_NOTE;
    }
  }
}

// ─────────────────────────────────────────
// 헬퍼: GraphViewData → ForceGraph 입력 변환
// ─────────────────────────────────────────

/**
 * 백엔드 GraphDataResponse 를 react-force-graph 입력 형태로 변환합니다.
 *
 * MAX_GRAPH_NODES 초과 시, OOM(Out of Memory) 방지를 위해
 * 연결 수(Degree)가 높은 중심 노드 위주로 상위 N개만 필터링합니다.
 */
function adaptGraphData(data: GraphViewData): {
  nodes: ForceGraphNode[];
  links: ForceGraphLink[];
} {
  const rawNodes = data.nodes;
  const truncated = rawNodes.length > MAX_GRAPH_NODES;

  let allowedNodes = rawNodes;

  if (truncated) {
    console.warn(
      `[GraphView] 노드 수(${rawNodes.length})가 MAX_GRAPH_NODES(${MAX_GRAPH_NODES})를 초과합니다. ` +
        `연결 수(Degree)가 높은 중심 노드 위주로 ${MAX_GRAPH_NODES}개만 필터링하여 렌더링합니다.`
    );

    // 1. 각 노드의 Degree(연결된 엣지 수) 계산
    const degreeMap = new Map<string, number>();
    for (const edge of data.edges) {
      degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1);
      degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1);
    }

    // 2. Degree 기준 내림차순 정렬 후 최대 개수만큼 슬라이싱
    // 원본 배열 불변성 유지를 위해 복사 후 정렬
    const sortedNodes = [...rawNodes].sort((a, b) => {
      const degA = degreeMap.get(a.id) || 0;
      const degB = degreeMap.get(b.id) || 0;
      return degB - degA; // 내림차순
    });

    allowedNodes = sortedNodes.slice(0, MAX_GRAPH_NODES);
  }

  const allowedNodeIds = new Set(allowedNodes.map((n) => n.id));

  // 양 끝점 노드가 모두 허용 범위 내에 있는 엣지만 포함
  const links: ForceGraphLink[] = data.edges
    .filter((e) => allowedNodeIds.has(e.source) && allowedNodeIds.has(e.target))
    .map((e) => ({ ...e }));

  return {
    nodes: allowedNodes.map((n) => ({ ...n })),
    links,
  };
}

// ─────────────────────────────────────────
// Props 정의
// ─────────────────────────────────────────

export interface GraphViewProps {
  /** 렌더링할 그래프 데이터 (백엔드 GraphDataResponse 형태) */
  data: GraphViewData;
  /** 캔버스 너비 (px). 미지정 시 부모 컨테이너 너비 사용. */
  width?: number;
  /** 캔버스 높이 (px). 기본값은 컨테이너에서 CSS로 제어. */
  height?: number;
  /** 노드 클릭 시 호출되는 콜백 */
  onNodeClick?: OnNodeClickCallback;
}

// ─────────────────────────────────────────
// GraphView 메인 컴포넌트
// ─────────────────────────────────────────

/**
 * 지식 그래프 2D 캔버스 시각화 컴포넌트.
 *
 * [사용 방법]
 * 반드시 GraphViewLoader(SSR-safe wrapper) 를 통해 렌더링하세요.
 * ```tsx
 * import { GraphViewLoader } from "@/components/GraphView";
 * <GraphViewLoader data={graphData} onNodeClick={handleClick} />
 * ```
 */
export function GraphView({ data, width, height = 600, onNodeClick }: GraphViewProps) {
  const graphRef = useRef<FGMethods | undefined>(undefined);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // SSOT 에서 변환한 데이터 (재계산 방지를 위해 메모이제이션)
  const { nodes, links } = useMemo(() => adaptGraphData(data), [data]);

  // ── 노드 클릭 핸들러 ──────────────────────────────────────
  const handleNodeClick = useCallback(
    (rawNode: NodeObj) => {
      const node = rawNode as ForceGraphNode;
      setSelectedNodeId((prev) => (prev === node.id ? null : node.id));

      if (onNodeClick) {
        // ForceGraphNode 는 GraphNode 를 상속하므로 안전하게 캐스팅
        onNodeClick(node as GraphNode);
      }
    },
    [onNodeClick]
  );

  // ── 노드 캔버스 렌더러 ───────────────────────────────────
  const paintNode = useCallback(
    (node: NodeObj, ctx: CanvasRenderingContext2D) => {
      const nx = node.x ?? 0;
      const ny = node.y ?? 0;
      const isSelected = node.id === selectedNodeId;
      const radius = GRAPH_NODE_RADIUS * (isSelected ? GRAPH_NODE_SELECTED_SCALE : 1);
      const color = resolveNodeColor(node.node_type);

      // 선택 시 후광(glow) 효과
      if (isSelected) {
        ctx.beginPath();
        ctx.arc(nx, ny, radius + 4, 0, Math.PI * 2);
        ctx.fillStyle = `${GRAPH_HIGHLIGHT_COLOR}22`;
        ctx.fill();
      }

      // 노드 원
      ctx.beginPath();
      ctx.arc(nx, ny, radius, 0, Math.PI * 2);
      ctx.fillStyle = isSelected ? GRAPH_HIGHLIGHT_COLOR : color;
      ctx.fill();

      // 라벨 (작은 폰트로 노드 아래에 표시)
      const fontSize = Math.max(4, radius * 0.9);
      ctx.font = `${fontSize}px Inter, sans-serif`;
      ctx.fillStyle = isSelected ? GRAPH_HIGHLIGHT_COLOR : "rgba(220,220,240,0.85)";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(node.label, nx, ny + radius + 2);
    },
    [selectedNodeId]
  );

  return (
    <ForceGraph2D<ForceGraphNode, ForceGraphLink>
      ref={graphRef}
      graphData={{ nodes, links }}
      width={width}
      height={height}
      backgroundColor={GRAPH_BG_COLOR}
      // 링크 스타일
      linkColor={() => GRAPH_LINK_COLOR}
      linkWidth={(link: LinkObj) => {
        // 엣지 weight(0~1)를 링크 두께(0.5~3px)에 선형 매핑
        return 0.5 + (link.weight ?? 1) * 2.5;
      }}
      // 노드 커스텀 렌더러
      nodeCanvasObject={paintNode}
      nodeCanvasObjectMode={() => "replace"}
      // 노드 포인터 영역 — 라벨 영역까지 포함하도록 반경 확장
      nodePointerAreaPaint={(node: NodeObj, color: string, ctx: CanvasRenderingContext2D) => {
        const nx = node.x ?? 0;
        const ny = node.y ?? 0;
        const radius = GRAPH_NODE_RADIUS * GRAPH_NODE_SELECTED_SCALE + 6;
        ctx.beginPath();
        ctx.arc(nx, ny, radius, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      }}
      // 이벤트
      onNodeClick={handleNodeClick}
      // 물리 시뮬레이션 설정
      cooldownTicks={GRAPH_COOLDOWN_TICKS}
      // 성능: 줌/패닝 시 라벨 렌더링 일시 중단
      enableNodeDrag
      enableZoomInteraction
      enablePanInteraction
    />
  );
}
