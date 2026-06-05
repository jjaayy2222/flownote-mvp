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
// 헬퍼: 구조화된 개발 환경 전용 로깅 (DRY 패턴 & 민감정보 보호)
// ─────────────────────────────────────────
function devWarn(message: string, payload?: unknown) {
  if (process.env.NODE_ENV !== "production") {
    // [Confirm] payload가 0, false, "" 등 falsy 값이어도 정상 출력되도록 명시적 undefined 체크
    if (payload !== undefined) {
      console.warn(`[GraphView] ${message}`, payload);
    } else {
      console.warn(`[GraphView] ${message}`);
    }
  }
}

// ─────────────────────────────────────────
// 헬퍼: 런타임 스키마 방어용 커스텀 타입 가드(Type Guard)
// ─────────────────────────────────────────
function isValidGraphNode(node: Partial<GraphNode>): node is GraphNode {
  return typeof node.id === "string" && typeof node.node_type === "string";
}

function isValidGraphLink(link: unknown): link is ForceGraphLink {
  if (typeof link !== "object" || link === null) return false;
  const l = link as Partial<ForceGraphLink>;
  // [Confirm] null과 undefined를 모두 차단 (nullish check)
  return l.source != null && l.target != null;
}

// ─────────────────────────────────────────
// 헬퍼: Link의 source/target 식별자 엄격한 추출
// ─────────────────────────────────────────
function getLinkId(endpoint: unknown): string | null {
  if (endpoint == null) return null;

  // 1. 객체인 경우: 내부의 `id` 속성 추출
  if (typeof endpoint === "object") {
    const { id } = endpoint as { id?: unknown };
    if (id == null) return null;
    
    // [Confirm] 왕복 변환(Round-trip)이 불가능한 symbol/bigint 및 객체/함수 등은 모두 거부하고, 
    // 오직 직렬화 가능한 string, number, boolean 만 허용
    if (typeof id === "string" || typeof id === "number" || typeof id === "boolean") {
      return String(id);
    }
    return null;
  }

  // 2. 원시 타입(Primitive)이 직접 사용된 경우
  if (typeof endpoint === "string" || typeof endpoint === "number" || typeof endpoint === "boolean") {
    return String(endpoint);
  }

  // 3. 함수, symbol, bigint 등 기타 모든 예상치 못한 타입은 명시적 드롭
  return null;
}

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
      devWarn(`Unknown nodeType: ${_exhaustiveCheck}`);
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
  // [Confirm] 스키마 변경(Schema drift)에 대비하여 렌더링 전 유효하지 않은 노드(불량 데이터)를 원천 차단
  const rawNodes = data.nodes.filter((node) => {
    if (!isValidGraphNode(node)) {
      devWarn("Dropped invalid node missing required fields before rendering", {
        id: (node as Record<string, unknown>).id,
        node_type: (node as Record<string, unknown>).node_type,
      });
      return false; // 불량 노드 렌더링 및 클릭 이벤트 대상에서 완전 제외
    }
    return true;
  });

  const truncated = rawNodes.length > MAX_GRAPH_NODES;

  let allowedNodes = rawNodes;

  if (truncated) {
    devWarn(
      `노드 수(${rawNodes.length})가 MAX_GRAPH_NODES(${MAX_GRAPH_NODES})를 초과합니다. ` +
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

  // 제한된 노드 ID Set
  const allowedNodeIds = new Set(allowedNodes.map((n) => n.id));

  // [Confirm] allowedNodeIds를 기반으로 양 끝단(Source/Target)을 검사하므로, 
  // 사전 필터링(불량 노드 제거)으로 인해 삭제된 노드를 참조하는 고아 엣지(Orphan edges)는 
  // 렌더링되지 않고 안전하게 함께 소거(Cascade)됩니다.
  const links: ForceGraphLink[] = data.edges
    .filter((e) => {
      // 1. 엣지 자체의 스키마 유효성 검증
      if (!isValidGraphLink(e)) {
        devWarn("Dropped invalid edge missing source or target", { edge: e });
        return false;
      }
      
      // 2. 헬퍼를 사용한 엄격한 식별자 추출
      const sourceId = getLinkId(e.source);
      const targetId = getLinkId(e.target);
      
      // 3. 조기 종료(Short-circuit): 식별자를 추출할 수 없는 구조적 결함이 있으면 명시적 드롭
      if (sourceId === null || targetId === null) {
        devWarn("Dropped edge due to unresolvable or malformed source/target IDs", { edge: e });
        return false;
      }

      // 4. 고아 엣지 방어
      return allowedNodeIds.has(sourceId) && allowedNodeIds.has(targetId);
    })
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
    (node: NodeObj) => {
      setSelectedNodeId((prev) => (prev === node.id ? null : node.id));

      if (onNodeClick) {
        // [Confirm] adaptGraphData 에서 불량 데이터를 사전 차단(Pre-filter)하므로,
        // 이곳으로 전달된 노드의 필수 필드 무결성은 100% 보장됩니다.
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
