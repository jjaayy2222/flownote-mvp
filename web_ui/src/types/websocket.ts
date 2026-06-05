// web_ui/src/types/websocket.ts

/**
 * WebSocket 연결 상태
 * 
 * Native WebSocket readyState와의 매핑:
 * - CONNECTING: WebSocket.CONNECTING (0)
 * - CONNECTED: WebSocket.OPEN (1)
 * - DISCONNECTED: WebSocket.CLOSED (3)
 * - RECONNECTING: 커스텀 상태 (재연결 시도 중)
 * - ERROR: 커스텀 상태 (연결 오류)
 * 
 * @see https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/readyState
 */
export enum WebSocketStatus {
  /** 연결 시도 중 (readyState: 0) */
  CONNECTING = 'CONNECTING',
  
  /** 연결됨 (readyState: 1) */
  CONNECTED = 'CONNECTED',
  
  /** 연결 끊김 (readyState: 3) */
  DISCONNECTED = 'DISCONNECTED',
  
  /** 재연결 시도 중 (커스텀 상태) */
  RECONNECTING = 'RECONNECTING',
  
  /** 오류 발생 (커스텀 상태) */
  ERROR = 'ERROR',
}

/**
 * Native WebSocket readyState 상수
 * SSR 환경에서도 안전하게 사용 가능
 */
export const WS_READY_STATE = {
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3,
} as const;

/**
 * WebSocket readyState 타입
 * 유효한 readyState 값만 허용 (0-3)
 */
export type WebSocketReadyState = typeof WS_READY_STATE[keyof typeof WS_READY_STATE];

/**
 * 유효한 readyState 값들의 Set (동기화 보장)
 * Set<number>로 타입 지정하여 타입 가드에서 number 타입 인수 허용
 */
const VALID_READY_STATES: Set<number> = new Set(Object.values(WS_READY_STATE));

/**
 * readyState가 유효한 값인지 타입 가드
 * WS_READY_STATE에서 값을 파생하여 항상 동기화 유지
 * 
 * unknown 타입을 받아 typeof 체크를 수행하여 범용적으로 사용 가능
 * 
 * @param value - 검증할 값 (any type)
 * @returns 유효한 WebSocketReadyState인 경우 true
 * 
 * @example
 * ```typescript
 * const state = externalLib.getState(); // unknown
 * if (isValidReadyState(state)) {
 *   // state is WebSocketReadyState
 * }
 * ```
 */
export const isValidReadyState = (value: unknown): value is WebSocketReadyState => {
  return typeof value === 'number' && VALID_READY_STATES.has(value);
};

/**
 * Native WebSocket readyState를 WebSocketStatus로 변환
 * 
 * number 타입을 받아 실제 WebSocket API와 호환
 * (ws.readyState는 number 타입으로 반환됨)
 * 
 * @param readyState - WebSocket.readyState 값 (0-3)
 * @returns 해당하는 WebSocketStatus
 * 
 * @example
 * ```typescript
 * // nosemgrep: javascript.lang.security.detect-insecure-websocket
 * // 예시 코드: 실제로는 wss:// 사용 권장
 * const ws = new WebSocket('wss://example.com/ws');
 * const status = mapReadyStateToStatus(ws.readyState);
 * ```
 */
export const mapReadyStateToStatus = (readyState: number): WebSocketStatus => {
  // 런타임 타입 가드: 유효한 readyState 값인지 검증
  if (!isValidReadyState(readyState)) {
    console.error(`[WebSocket] Invalid readyState value: ${readyState}`);
    return WebSocketStatus.ERROR;
  }
  
  // 타입 안전한 switch: exhaustiveness check 보장
  // isValidReadyState 통과 후 readyState는 WebSocketReadyState로 narrowing됨
  switch (readyState) {
    case WS_READY_STATE.CONNECTING:
      return WebSocketStatus.CONNECTING;
    case WS_READY_STATE.OPEN:
      return WebSocketStatus.CONNECTED;
    case WS_READY_STATE.CLOSING:
    case WS_READY_STATE.CLOSED:
      return WebSocketStatus.DISCONNECTED;
  }
  
  // Exhaustiveness check: 모든 케이스가 처리되었음을 TypeScript에 증명
  // 새로운 WS_READY_STATE 값이 추가되면 컴파일 오류 발생
  const _exhaustiveCheck: never = readyState;
  
  // 런타임 안전성: 이 지점에 도달하는 것은 버그이므로 명시적으로 예외를 던진다
  throw new Error(`Unexpected WebSocket readyState: ${_exhaustiveCheck}`);
};

/**
 * WebSocket 이벤트 타입 상수 (Single Source of Truth)
 * 모든 이벤트 타입은 이 객체를 참조하여 정의해야 합니다.
 */
export const WS_EVENT_TYPE = {
  FILE_CLASSIFIED: 'file_classified',
  SYNC_STATUS_CHANGED: 'sync_status_changed',
  CONFLICT_DETECTED: 'conflict_detected',
  GRAPH_UPDATED: 'graph_updated',
} as const;

/**
 * 유효한 WebSocket 이벤트 타입 목록 (Runtime Check용)
 * WS_EVENT_TYPE 객체에서 자동으로 파생됩니다.
 * Literal Type 정보를 유지하기 위해 readonly 타입을 단언합니다.
 */
export const WEBSOCKET_EVENT_TYPES = Object.values(WS_EVENT_TYPE) as readonly WebSocketEventType[];

/**
 * WebSocket 이벤트 타입 문자열
 */
export type WebSocketEventType = typeof WS_EVENT_TYPE[keyof typeof WS_EVENT_TYPE];

/**
 * 파일 분류 결과 데이터 타입
 */
export interface FileClassification {
  id: string;
  fileName: string;
  category: string;
  confidence: number;
  processedAt: string;
}

/**
 * 동기화 상태 데이터 타입
 */
export interface SyncStatus {
  isSyncing: boolean;
  lastSyncedAt: string | null;
  error: string | null;
  pendingChanges: number;
}

/**
 * 충돌 정보 데이터 타입 (WebSocket Payload)
 * REST API의 Conflict 타입과 구분을 위해 WsConflict로 명명
 */
export interface WsConflict {
  id: string;
  fileId: string;
  baseVersion: string;
  remoteVersion: string;
  localVersion: string;
  timestamp: string;
}

/**
 * 지식 그래프 노드 타입 (백엔드 SSOT 연동)
 */
export enum NodeType {
  CATEGORY = "category",
  NOTE = "note",
  KEYWORD = "keyword",
  TAG = "tag",
}

/**
 * 지식 그래프 엣지 관계 타입 (백엔드 SSOT 연동)
 */
export enum EdgeRelationshipType {
  RELATED_TO = "related_to",
  // 백엔드 확장에 따라 추가 가능
}

/**
 * 향후 다른 브랜드 타입이 추가될 때 우연한 이름 충돌이나 전역 스코프 오염을 방지하기 위한
 * 모듈 내부 전용 고유 식별자(Symbol)입니다. 
 * 외부 모듈과의 결합도(Coupling)를 낮추고 정보 은닉(Encapsulation)을 강제하기 위해 export 하지 않습니다.
 * 런타임 코드에서는 삭제되며 오직 컴파일 타임의 타입 구분에만 사용됩니다.
 */
declare const UnknownRelationshipBrand: unique symbol;

/**
 * 백엔드에서 프론트엔드가 모르는 새로운 관계 타입 문자열을 보낼 경우를 대비한 Fallback 타입.
 * 모듈 스코프 내에 캡슐화된 Unique Symbol을 사용하여 외부와의 충돌을 막고, 
 * 브랜드 값을 명시적 리터럴 문자열('UnknownRelationshipType')로 지정하여 IDE의 에러 툴팁 가독성을 극대화합니다.
 * 
 * @example
 * // 런타임 사용 권장 패턴 (Exhaustive Check 방지)
 * function handleEdge(edge: GraphEdge) {
 *   switch (edge.relationship_type) {
 *     case EdgeRelationshipType.RELATED_TO:
 *       // 알려진 타입 처리
 *       break;
 *     default:
 *       // 알 수 없는 타입(UnknownRelationshipType)에 대한 안전한 폴백 처리
 *       console.warn("Unknown relationship:", edge.relationship_type);
 *       break;
 *   }
 * }
 */
export type UnknownRelationshipType = string & { 
  readonly [UnknownRelationshipBrand]: 'UnknownRelationshipType' 
};

/**
 * 백엔드에서 전달된 알 수 없는 문자열을 UnknownRelationshipType 브랜드 타입으로 안전하게 변환하는 헬퍼 함수입니다.
 * 코드베이스 전반에 불안전한 타입 단언(as)이 흩어지는 것을 방지하고 캐스팅 지점을 단일화(Centralize)합니다.
 * 
 * @internal 이 함수는 오직 백엔드 API 응답(WebSocket, Fetch 등)을 파싱하는 최전방 경계(Boundary Layer)에서만 사용되어야 합니다.
 * 비즈니스 로직 내부에서 임의로 호출하여 캐스팅하는 것을 엄격히 금지합니다.
 * 
 * @param value 백엔드에서 전달된 임의의 문자열
 * @returns 브랜딩이 적용된 UnknownRelationshipType
 */
export function asUnknownRelationshipType(value: string): UnknownRelationshipType {
  return value as UnknownRelationshipType;
}

/**
 * 그래프 노드 데이터 타입 (백엔드 schemas/graph.py SSOT 연동)
 * @template TProps 속성(properties)의 구체적인 타입 (기본값: Record<string, unknown>)
 */
export interface GraphNode<TProps extends Record<string, unknown> = Record<string, unknown>> {
  id: string;
  label: string;
  node_type: NodeType;
  properties: TProps;
  position_x: number | null;
  position_y: number | null;
  user_id_hash: string | null;
}

/**
 * 그래프 엣지 데이터 타입 (백엔드 schemas/graph.py SSOT 연동)
 * @template TProps 속성(properties)의 구체적인 타입 (기본값: Record<string, unknown>)
 */
export interface GraphEdge<TProps extends Record<string, unknown> = Record<string, unknown>> {
  id: string;
  source: string;
  target: string;
  relationship_type: EdgeRelationshipType | UnknownRelationshipType;
  weight: number;
  properties: TProps;
}

/**
 * 그래프 전체 데이터 타입 (백엔드 GraphDataResponse 호환)
 * @template TNodeProps 노드 속성의 확장 타입
 * @template TEdgeProps 엣지 속성의 확장 타입
 */
export interface GraphData<
  TNodeProps extends Record<string, unknown> = Record<string, unknown>,
  TEdgeProps extends Record<string, unknown> = Record<string, unknown>
> {
  nodes: GraphNode<TNodeProps>[];
  edges: GraphEdge<TEdgeProps>[];
}

/**
 * WebSocket 이벤트 타입 정의 (Discriminated Union)
 * 서버에서 전송되는 메시지의 구조를 정의합니다.
 */
export type WebSocketEvent = 
  | { type: typeof WS_EVENT_TYPE.FILE_CLASSIFIED; data: FileClassification }
  | { type: typeof WS_EVENT_TYPE.SYNC_STATUS_CHANGED; data: SyncStatus }
  | { type: typeof WS_EVENT_TYPE.CONFLICT_DETECTED; data: WsConflict }
  | { type: typeof WS_EVENT_TYPE.GRAPH_UPDATED; data: GraphData };

/**
 * WebSocket 이벤트 타입 가드
 * 런타임에 메시지가 유효한 WebSocketEvent 구조인지 검증합니다.
 */
export const isWebSocketEvent = (message: unknown): message is WebSocketEvent => {
  // 0. 기본 객체 검사 (null 및 원시 타입 제외)
  // !message 체크 대신 명시적으로 null 체크를 수행하여 의도를 분명히 함
  if (message === null || typeof message !== 'object') {
    return false;
  }

  const candidate = message as { type?: unknown; data?: unknown };

  // 1. type 필드가 문자열인지 확인
  if (typeof candidate.type !== 'string') {
    return false;
  }

  // 2. data 필드 존재 여부 확인
  // 주의: data의 내부 구조(필드 등)는 검증하지 않는 "얕은 검사"입니다.
  if (!('data' in candidate)) {
    return false;
  }

  // WEBSOCKET_EVENT_TYPES에 포함된 타입인지 확인
  // 주의: data 필드의 구체적인 내부 구조(속성 존재 여부 등)까지는 검증하지 않습니다.
  // 단순히 type이 유효하고 data 속성이 존재하는지만 확인합니다.
  return WEBSOCKET_EVENT_TYPES.includes(candidate.type as WebSocketEventType);
};
