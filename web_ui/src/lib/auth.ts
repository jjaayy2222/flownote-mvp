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
  
  // 서버 환경변수에서 허용된 이메일 목록을 가져옴 (콤마로 구분된 형태 가정)
  const allowedEmails = process.env.ADMIN_EMAILS?.split(',') || [];
  return allowedEmails.includes(email);
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
  if (parts.length === 2) return parts.pop()?.split(';').shift() || null;
  return null;
};
