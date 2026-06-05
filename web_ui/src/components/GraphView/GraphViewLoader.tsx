"use client";
// web_ui/src/components/GraphView/GraphViewLoader.tsx
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Phase 4-3: SSR 회피용 래퍼 컴포넌트
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import dynamic from "next/dynamic";
import { type GraphViewProps } from "./GraphView";

// react-force-graph 는 window/document 객체에 의존하므로
// Next.js 의 서버 사이드 렌더링(SSR) 단계에서 로드하면 에러가 발생합니다.
// ssr: false 옵션을 통해 클라이언트 사이드에서만 로드되도록 강제합니다.
const GraphViewDynamic = dynamic<GraphViewProps>(
  () => import("./GraphView").then((mod) => mod.GraphView),
  { ssr: false }
);

/**
 * GraphView 의 SSR-safe 래퍼 컴포넌트입니다.
 * 외부에서는 항상 이 컴포넌트를 import 하여 사용해야 합니다.
 */
export function GraphViewLoader(props: GraphViewProps) {
  return <GraphViewDynamic {...props} />;
}
