// web_ui/src/lib/auth.ts

import { AUTH_CONFIG } from './constants';

/**
 * 전역 관리자 판별 함수 (Role 기반)
 * 
 * @param role - 사용자 역할 문자열
 * @returns 관리자 여부
 */
export const isAdmin = (role: string | null | undefined): boolean => {
  return role === AUTH_CONFIG.ADMIN_ROLE;
};

// 모듈 로드 시점에 환경변수에서 허용된 이메일 목록을 한 번만 정규화하여 캐싱 (성능 최적화)
const cachedAdminEmails = (process.env.ADMIN_EMAILS || '').split(',')
  .map(e => e.trim().toLowerCase())
  .filter(Boolean);

/**
 * 이메일 기반 관리자 판별 함수 (서버 사이드 환경변수 기준)
 * 
 * NEXT_PUBLIC_ 접두어가 붙지 않은 환경변수는 클라이언트 번들에 노출되지 않으므로 보안이 유지됩니다.
 * 
 * @param email - 사용자 이메일
 * @returns 관리자 여부
 */
export const isEmailAdmin = (email: string | null | undefined): boolean => {
  if (!email) return false;
  
  // 입력된 이메일 정규화 후 캐싱된 목록과 비교
  const normalizedInputEmail = email.trim().toLowerCase();
  return cachedAdminEmails.includes(normalizedInputEmail);
};

/**
 * 사용자 권한 종합 판별 (Role || Email)
 * 
 * @param role - 사용자 역할
 * @param email - 사용자 이메일
 * @returns 관리자 권한 확인 여부
 */
export const hasAdminAccess = (
  role: string | null | undefined, 
  email: string | null | undefined
): boolean => {
  return isAdmin(role) || isEmailAdmin(email);
};

/**
 * [Client-Side] 쿠키에서 인증 정보 가져오기
 * 
 * 브라우저 환경에서 cookie를 파싱하여 역할이나 이메일을 반환합니다.
 */
export const getAuthFromCookie = (name: string): string | null => {
  if (typeof document === 'undefined') return null;
  
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    const raw = parts.pop()?.split(';').shift();
    if (!raw) return null;

    try {
      return decodeURIComponent(raw);
    } catch (error) {
      // 디코딩 실패 시 호출자가 기대하는 예측 가능한 동작(null 반환) 보장 및 오류 추적을 위한 로깅
      console.warn(`[getAuthFromCookie] URI decoding failed for cookie '${name}':`, error);
      return null;
    }
  }
  
  return null;
};
