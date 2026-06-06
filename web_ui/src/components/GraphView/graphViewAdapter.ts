// web_ui/src/components/GraphView/graphViewAdapter.ts

import type { GraphNode } from "@/types/websocket";
import { MAX_GRAPH_NODES } from "@/config/graph";
import type { ForceGraphNode, ForceGraphLink, GraphViewData } from "./types";

// ─────────────────────────────────────────
// 헬퍼: 구조화된 개발 환경 전용 로깅 (DRY 패턴 & 민감정보 보호)
// ─────────────────────────────────────────
export function devWarn(message: string, payload?: unknown) {
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
export function isValidGraphNode(node: Partial<GraphNode>): node is GraphNode {
  return typeof node.id === "string" && typeof node.node_type === "string";
}

export function isValidGraphLink(link: unknown): link is ForceGraphLink {
  if (typeof link !== "object" || link === null) return false;
  const l = link as Partial<ForceGraphLink>;
  // [Confirm] null과 undefined를 모두 차단 (nullish check)
  return l.source != null && l.target != null;
}

// ─────────────────────────────────────────
// 헬퍼: 직렬화 가능한 원시 타입(Primitive) 여부 확인
// ─────────────────────────────────────────
export function isSerializablePrimitive(val: unknown): val is string | number | boolean {
  switch (typeof val) {
    case "string":
    case "boolean":
      return true;
    case "number":
      // [Confirm] NaN과 Infinity를 제외하여 "NaN", "Infinity" 등 예측 불가능한 ID 붕괴 방어
      return Number.isFinite(val);
    default:
      return false;
  }
}

// ─────────────────────────────────────────
// 헬퍼: Link의 source/target 식별자 엄격한 추출
// ─────────────────────────────────────────
export function getLinkId(endpoint: unknown): string | null {
  if (endpoint == null) return null;

  // 1. 객체인 경우: 내부의 `id` 속성 추출
  if (typeof endpoint === "object") {
    const { id } = endpoint as { id?: unknown };
    if (id == null) return null;
    
    // [Confirm] 왕복 변환(Round-trip)이 불가능한 symbol/bigint 및 객체/함수 등은 모두 거부하고, 
    // 오직 직렬화 가능한 string, number, boolean 만 허용
    if (isSerializablePrimitive(id)) {
      return String(id);
    }
    return null;
  }

  // 2. 원시 타입(Primitive)이 직접 사용된 경우
  if (isSerializablePrimitive(endpoint)) {
    return String(endpoint);
  }

  // 3. 함수, symbol, bigint 등 기타 모든 예상치 못한 타입은 명시적 드롭
  return null;
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
export function adaptGraphData(data: GraphViewData): {
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

    // 1. 각 노드의 Degree(연결된 엣지 수) 계산 (유효한 엣지와 식별자만 카운트)
    const degreeMap = new Map<string, number>();
    for (const edge of data.edges) {
      if (!isValidGraphLink(edge)) continue;
      const sourceId = getLinkId(edge.source);
      const targetId = getLinkId(edge.target);
      if (sourceId !== null && targetId !== null) {
        degreeMap.set(sourceId, (degreeMap.get(sourceId) || 0) + 1);
        degreeMap.set(targetId, (degreeMap.get(targetId) || 0) + 1);
      }
    }

    // 2. Degree 기준 내림차순 정렬 후 최대 개수만큼 슬라이싱
    // 원본 배열 불변성 유지를 위해 복사 후 정렬
    const sortedNodes = [...rawNodes].sort((a, b) => {
      const degA = degreeMap.get(a.id) || 0;
      const degB = degreeMap.get(b.id) || 0;
      // 동일 degree일 경우 ID 기반 결정적 정렬(Deterministic sorting) 적용
      if (degB === degA) {
        return a.id.localeCompare(b.id);
      }
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
