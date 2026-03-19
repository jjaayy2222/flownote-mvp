/**
 * localStorage 키 설정
 */
export const STORAGE_KEYS = {
  CHAT_SESSION_ID: 'flownote_chat_session_id',
  USER_ID: 'flownote_user_id',
} as const;

/**
 * Chat 서비스 관련 기본 설정값
 */
export const CHAT_CONFIG = {
  DEFAULT_K: 3,
  DEFAULT_ALPHA: 0.5,
  DEFAULT_USER_ID: process.env.NODE_ENV === 'production' ? undefined : 'test_user_123',
} as const;
