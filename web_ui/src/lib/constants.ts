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
