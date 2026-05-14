/**
 * localStorage 키 설정
 */
export const STORAGE_KEYS = {
  CHAT_SESSION_ID: 'flownote_chat_session_id',
  USER_ID: 'flownote_user_id',
  AUTH_ROLE: 'flownote_auth_role',
  AUTH_EMAIL: 'flownote_auth_email',
} as const;

/**
 * Auth 관련 기본 설정값
 */
export const AUTH_CONFIG = {
  ADMIN_ROLE: 'admin',
  USER_ROLE: 'user',
  // 관리자 계정 식별(이메일 등)은 클라이언트 번들에 포함되지 않도록 서버(Middleware 등) 환경변수에서 관리합니다.
} as const;

/**
 * Chat 서비스 관련 기본 설정값
 */
export const CHAT_CONFIG = {
  DEFAULT_K: 3,
  DEFAULT_ALPHA: 0.5,
  DEFAULT_USER_ID: process.env.NODE_ENV === 'production' ? undefined : 'test_user_123',
} as const;

/**
 * UI/UX 관련 상수 설정
 */
export const UI_CONFIG = {
  SCROLL_THRESHOLD: 100, // UX 바닥 인식 임계치 (px)
} as const;

/**
 * 기능 플래그(Feature Flags) - 환경변수 기반 점진적 롤아웃 관리
 *
 * NEXT_PUBLIC_USE_STREAMING=true 로 설정 시 SSE 기반 스트리밍 훅을 활성화합니다.
 * 미설정 또는 'false'일 경우 기존 useChat 방식으로 폴백됩니다.
 */
export const FEATURE_FLAGS = {
  USE_STREAMING: process.env.NEXT_PUBLIC_USE_STREAMING === 'true',
} as const;
