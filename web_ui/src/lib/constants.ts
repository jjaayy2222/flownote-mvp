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
  // 임시 관리자 계정 리스트 (실제 운영 시 DB 또는 환경변수에서 관리 권장)
  ADMIN_EMAILS: ['jay@gmail.com', 'admin@flownote.com'],
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
