// web_ui/src/config/graph.ts
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Phase 4-3: 프론트엔드 지식 그래프 시각화 설정 (SSOT)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//
// [SSOT 정책]
// 이 파일은 GraphView 컴포넌트에 필요한 모든 설정 상수의 단일 진실 공급원입니다.
// - 하드코딩 절대 금지. 모든 매직 넘버는 이 파일의 상수를 참조해야 합니다.
// - 최대 노드 수(NEXT_PUBLIC_MAX_GRAPH_NODES)는 백엔드 GraphConfig와 동일한
//   환경 변수를 읽어 동기화합니다.
//
// [환경 변수 연동]
// 백엔드: backend/core/config/graph.py ENV_MAX_GRAPH_NODES = "NEXT_PUBLIC_MAX_GRAPH_NODES"
// 기본값: DEFAULT_MAX_GRAPH_NODES = 500  (유효 범위: 50 ~ 2000)
//
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

// ─────────────────────────────────────────
// 환경 변수 키 (문자열 하드코딩 금지)
// ─────────────────────────────────────────

/** 최대 렌더링 노드 수 환경 변수 키 (백엔드 ENV_MAX_GRAPH_NODES 와 동일) */
const ENV_KEY_MAX_GRAPH_NODES = "NEXT_PUBLIC_MAX_GRAPH_NODES";

// ─────────────────────────────────────────
// 유효 범위 (백엔드 MAX_GRAPH_NODES_RANGE 와 동기화)
// ─────────────────────────────────────────

/** 렌더링 노드 수 최솟값 (백엔드 MAX_GRAPH_NODES_RANGE.min = 50) */
export const GRAPH_NODES_MIN = 50;

/** 렌더링 노드 수 최댓값 (백엔드 MAX_GRAPH_NODES_RANGE.max = 2000) */
export const GRAPH_NODES_MAX = 2000;

/** 렌더링 노드 수 기본값 (백엔드 DEFAULT_MAX_GRAPH_NODES = 500) */
export const GRAPH_NODES_DEFAULT = 500;

// ─────────────────────────────────────────
// 환경 변수 로딩 (Clamping 적용)
// ─────────────────────────────────────────

/**
 * 환경 변수 `NEXT_PUBLIC_MAX_GRAPH_NODES` 를 읽어 렌더링 최대 노드 수를 반환합니다.
 *
 * - 값이 없거나 파싱 불가능한 경우: 기본값(GRAPH_NODES_DEFAULT) 사용.
 * - 유효 범위(GRAPH_NODES_MIN ~ GRAPH_NODES_MAX) 를 벗어날 경우: Clamping 후 경고 로그 출력.
 */
function loadMaxGraphNodes(): number {
  // Next.js 환경에서는 동적 키(process.env[Key])가 빌드 타임에 치환되지 않으므로 직접 명시해야 합니다.
  const raw = process.env.NEXT_PUBLIC_MAX_GRAPH_NODES;
  if (raw === undefined || raw === "") {
    return GRAPH_NODES_DEFAULT;
  }

  const parsed = parseInt(raw, 10);
  if (isNaN(parsed)) {
    console.warn(
      `[GraphConfig] ${ENV_KEY_MAX_GRAPH_NODES}="${raw}" 파싱 실패. ` +
        `기본값 ${GRAPH_NODES_DEFAULT} 을 사용합니다.`
    );
    return GRAPH_NODES_DEFAULT;
  }

  const clamped = Math.min(Math.max(parsed, GRAPH_NODES_MIN), GRAPH_NODES_MAX);
  if (clamped !== parsed) {
    console.warn(
      `[GraphConfig] ${ENV_KEY_MAX_GRAPH_NODES}=${parsed} 은 ` +
        `유효 범위 [${GRAPH_NODES_MIN}, ${GRAPH_NODES_MAX}] 를 벗어납니다. ` +
        `${clamped} 으로 조정합니다.`
    );
  }
  return clamped;
}

/** 렌더링 최대 노드 수 (환경 변수 기반, Clamping 적용) */
export const MAX_GRAPH_NODES: number = loadMaxGraphNodes();

// ─────────────────────────────────────────
// 시각화 레이아웃 상수
// ─────────────────────────────────────────

/** 캔버스 초기 배경색 */
export const GRAPH_BG_COLOR = "#0f0f14";

/** 노드 기본 색상 (NOTE 타입) */
export const GRAPH_NODE_COLOR_NOTE = "#6c63ff";

/** 노드 색상 — KEYWORD 타입 */
export const GRAPH_NODE_COLOR_KEYWORD = "#00c896";

/** 노드 색상 — TAG 타입 */
export const GRAPH_NODE_COLOR_TAG = "#f4a261";

/** 노드 색상 — CATEGORY 타입 */
export const GRAPH_NODE_COLOR_CATEGORY = "#e76f51";

/** 엣지(링크) 기본 색상 */
export const GRAPH_LINK_COLOR = "rgba(150, 150, 200, 0.4)";

/** 호버/선택 시 하이라이트 색상 */
export const GRAPH_HIGHLIGHT_COLOR = "#ffffff";

/** 노드 기본 크기(반경) */
export const GRAPH_NODE_RADIUS = 6;

/** 선택된 노드 크기 배율 */
export const GRAPH_NODE_SELECTED_SCALE = 1.8;

/** 캔버스 워밍업(물리 시뮬레이션 냉각) 이후 정지까지 대기 틱 수 */
export const GRAPH_COOLDOWN_TICKS = 120;
