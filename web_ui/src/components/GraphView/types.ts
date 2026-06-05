// web_ui/src/components/GraphView/types.ts
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Phase 4-3: GraphView 내부 전용 타입 정의
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//
// [SSOT 연동]
// 이 파일의 GraphNode / GraphEdge 타입은
// backend/schemas/graph.py → OpenAPI → 자동 생성된
// web_ui/src/types/websocket.ts 의 타입을 재사용합니다.
// (수동 하드코딩 금지)
//
// react-force-graph 가 요구하는 `NodeObject` / `LinkObject` 형태로
// 매핑하는 어댑터 타입을 여기서 정의합니다.
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import type { GraphNode, GraphEdge } from "@/types/websocket";

// ─────────────────────────────────────────
// react-force-graph 어댑터 타입
// ─────────────────────────────────────────

/**
 * react-force-graph 의 `NodeObject` 로 사용할 어댑터 타입.
 *
 * react-force-graph 는 런타임에 `x`, `y`, `vx`, `vy` 등의 물리 시뮬레이션
 * 속성을 노드 객체에 직접 주입합니다. 이 타입은 그 시뮬레이션 속성을
 * 포함하면서 SSOT 타입인 GraphNode 를 확장합니다.
 *
 * `id` 는 react-force-graph 가 string | number 를 모두 허용하므로
 * GraphNode.id(string) 을 그대로 사용합니다.
 */
export type ForceGraphNode = GraphNode & {
  /** 시뮬레이션 X 좌표 (react-force-graph 런타임 주입) */
  x?: number;
  /** 시뮬레이션 Y 좌표 (react-force-graph 런타임 주입) */
  y?: number;
  /** X축 속도 벡터 (react-force-graph 런타임 주입) */
  vx?: number;
  /** Y축 속도 벡터 (react-force-graph 런타임 주입) */
  vy?: number;
};

/**
 * react-force-graph 의 `LinkObject` 로 사용할 어댑터 타입.
 *
 * react-force-graph 는 `source` / `target` 을 초기에 string 으로 받고,
 * 시뮬레이션 시작 후 실제 노드 객체 참조로 교체합니다.
 * 이 타입은 두 상태를 모두 수용합니다.
 */
export type ForceGraphLink = Omit<GraphEdge, "source" | "target"> & {
  /** 출발 노드 id (초기값) 또는 노드 객체 참조 (시뮬레이션 후) */
  source: string | ForceGraphNode;
  /** 도착 노드 id (초기값) 또는 노드 객체 참조 (시뮬레이션 후) */
  target: string | ForceGraphNode;
};

/**
 * GraphView 컴포넌트에 전달되는 그래프 데이터.
 * 백엔드 GraphDataResponse 와 1:1 대응합니다.
 */
export interface GraphViewData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ─────────────────────────────────────────
// 콜백 / 이벤트 타입
// ─────────────────────────────────────────

/**
 * 노드 클릭 시 호출되는 콜백 타입.
 * 클릭된 노드의 SSOT 타입(GraphNode) 을 그대로 전달합니다.
 */
export type OnNodeClickCallback = (node: GraphNode) => void;
