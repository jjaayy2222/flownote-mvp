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

// 모듈 로드(서버/엣지 실행) 시점에 환경변수에서 허용된 이메일 목록을 정규화하여 Set으로 캐싱.
// NOTE: 이 캐시 목록은 정적(static)으로 유지되며, 런타임에 동적으로 변경해야 할 경우 서버/앱 재배포(또는 재실행)가 필요합니다.
const cachedAdminEmails = new Set(
  (process.env.ADMIN_EMAILS || '').split(',')
    .map(e => e.trim().toLowerCase())
    .filter(Boolean)
);

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
  
  // 입력된 이메일 정규화 후 캐싱된 Set에서 O(1) 시간 복잡도로 비교
  const normalizedInputEmail = email.trim().toLowerCase();
  return cachedAdminEmails.has(normalizedInputEmail);
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
      // 디코딩 실패 시 개발 환경에서 오류 추적을 위한 로깅 (프로덕션 로그 스팸 방지)
      if (process.env.NODE_ENV === 'development') {
        console.warn(`[getAuthFromCookie] URI decoding failed for cookie '${name}':`, error);
      }
      
      // 기존 API Contract(계약) 유지를 위해 에러 시 null 대신 디코딩되지 않은 원본(raw) 유지
      return raw;
    }
  }
  
  return null;
};
