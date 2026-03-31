// web_ui/src/lib/auth.ts

import { AUTH_CONFIG } from './constants';
import { assertNever } from './utils';

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
export type CookieAuth =
  | { kind: 'ok'; raw: string; decoded: string }
  | { kind: 'decode_error'; raw: string; decoded: null }
  | { kind: 'not_found' }
  | { kind: 'server_side' };



// --- 중앙집중화된 판별 헬퍼 (Internal Checkers) ---
// CookieAuth 타입과 긴밀하게 결합된 도메인 로직이므로 선언부와 같은 위치에 선언.
// 외부 모듈에서 퍼블릭 API로 오용되는 것을 막기 위해 export 하지 않음.
const isServerSideAuth = (auth: CookieAuth): boolean => {
  switch (auth.kind) {
    case 'server_side':
      return true;
    case 'ok':
    case 'decode_error':
    case 'not_found':
      return false;
    default:
      return assertNever(auth, 'isServerSideAuth');
  }
};

const getDecodedValue = (auth: CookieAuth): string | null => {
  switch (auth.kind) {
    case 'ok':
      return auth.decoded;
    case 'server_side':
    case 'decode_error':
    case 'not_found':
      return null;
    default:
      return assertNever(auth, 'getDecodedValue');
  }
};

export const getAuthFromCookie = (
  name: string
): CookieAuth => {
  if (typeof document === 'undefined') return { kind: 'server_side' };
  
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    const raw = parts.pop()?.split(';').shift();
    if (!raw) return { kind: 'not_found' };

    try {
      const decoded = decodeURIComponent(raw);
      return { kind: 'ok', raw, decoded };
    } catch (error) {
      // 디코딩 실패 시 명확한 구분을 위해 판별 가능한 유니온 상태 반환
      if (process.env.NODE_ENV === 'development') {
        console.warn(`[getAuthFromCookie] URI decoding failed for cookie '${name}':`, error);
      }
      
      return { kind: 'decode_error', raw, decoded: null };
    }
  }
  
  return { kind: 'not_found' };
};


/**
 * 복잡한 switch/if 체인 없이, 순수하게 디코딩된 쿠키 값만 필요한 호출측(Consumer) 컴포넌트를 위한 단일 헬퍼 함수
 * 
 * @param name - 가져올 쿠키의 이름
 * @param options.throwOnSSR - 서버 환경에서 호출할 경우 명시적으로 에러를 발생시켜 조용히 null 처리되는 것을 방지
 * @returns 디코딩 성공 시 원본 문자열, 그 외 null 반환 (옵션에 따라 SSR 환경에서는 throw 발생 가능)
 */
export const getDecodedCookieOrNull = (
  name: string,
  options?: { throwOnSSR?: boolean }
): string | null => {
  const auth = getAuthFromCookie(name);
  if (options?.throwOnSSR && isServerSideAuth(auth)) {
    throw new Error(`[CookieAuth] Attempted to read browser cookie '${name}' in Server environment (SSR).`);
  }
  return getDecodedValue(auth);
};

/**
 * SSR 환경(브라우저 외부)과 실제 미인증 상태(쿠키 부재)를 명확히 구분하여 처리해야 하는 특수 렌더링 컨텍스트용 헬퍼
 * 
 * @param name - 가져올 쿠키의 이름
 * @returns 디코딩된 값(value)과 SSR 렌더링 환경 여부(isSSR)를 명시적으로 분리 반환
 */
export const getDecodedCookieState = (
  name: string
): { value: string | null; isSSR: boolean } => {
  const auth = getAuthFromCookie(name);
  return {
    value: getDecodedValue(auth),
    isSSR: isServerSideAuth(auth),
  };
};
