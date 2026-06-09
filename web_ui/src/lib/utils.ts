import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export class ExhaustiveCheckError extends Error {
  // 에러 발생 위치(context)와 유발 인자(kind)를 개별적으로 노출 (기존 하위 호환성 및 다이렉트 접근용)
  public readonly context?: string;
  public readonly kind?: unknown;

  constructor(context?: string, kind?: unknown) {
    const detail = kind !== undefined ? ` (kind: ${String(kind)})` : '';
    const message = `[ExhaustiveCheck] Unhandled variant${context ? ` in ${context}` : ''}${detail}`;

    const hasMetadata = kind !== undefined || context !== undefined;
    const cause = hasMetadata ? { kind, context } : undefined;

    // 표준 ErrorOptions.cause를 통해 메타데이터를 노출하여 기존 error.cause 기반 도구/코드와의 호환성을 극대화
    super(message, cause ? { cause } : undefined);

    this.name = 'ExhaustiveCheckError';
    this.context = context;
    this.kind = kind;
    
    // TypeScript 내장 Error 클래스를 상속할 때 프로토타입 체인 유실을 방지하기 위한 보정
    Object.setPrototypeOf(this, ExhaustiveCheckError.prototype);
  }
}

/**
 * 컴파일 타임 보호 및 런타임 누락 분기(Fallthrough)를 막기 위한 엄격한 완전(Exhaustive) 검사 헬퍼.
 * 애플리케이션 전반의 판별 가능한 유니언(Discriminated Union) 보호 로직에 공용으로 재사용됩니다.
 */
export const assertNever = (x: never, context?: string): never => {
  // PII(개인정보)나 민감한 토큰 데이터 유출을 막기 위해 전체 구조체(stringify) 대신 `kind` 식별자만 참조
  const kind = (x as { kind?: unknown })?.kind;
  
  throw new ExhaustiveCheckError(context, kind);
};

/**
 * AbortError의 구조적 계약(Structural Contract)을 나타내는 타입 별칭.
 * isAbortError 타입 가드와 호출 측에서 동일한 계약을 일관되게 참조할 수 있습니다.
 *
 * [호출 지점 감사(Caller Audit) 결과]
 * 모든 호출 측(useFetch, useStreamingChat, stream-client, HybridSearch,
 * websocket-monitor, useGraphData, chat/route)은 isAbortError 통과 후
 * 즉시 early return 패턴만 사용하며 .message / .stack 등의 Error 전용
 * 속성에 접근하지 않습니다. 따라서 현재 { name: "AbortError" } 계약으로 충분합니다.
 */
export type AbortErrorLike = { name: "AbortError" };

/**
 * error가 문자열 "AbortError" name 속성을 가진 객체인지 확인하는 내부 헬퍼.
 * null/object 검사부터 name 문자열 검사까지 모든 가드를 한 곳에 집중시켜
 * isAbortError가 단순 위임(pure delegation)만 하도록 합니다.
 * 'name' in error → { name: unknown } 패턴으로 Record 광범위 캐스트 없이
 * 필요한 속성만 타입 안전하게 좁힙니다.
 */
function hasAbortErrorName(error: unknown): error is AbortErrorLike {
  if (typeof error !== "object" || error === null) return false;
  if (!("name" in error)) return false;
  const { name } = error as { name: unknown };
  return typeof name === "string" && name === "AbortError";
}

/**
 * 통신 취소(AbortError) 여부를 확인하는 타입 가드.
 * name 프로퍼티가 문자열 "AbortError"인 모든 객체를 감지하여
 * Error·DOMException 이외의 크로스-렐름 AbortError도 포착합니다.
 */
export const isAbortError = (error: unknown): error is AbortErrorLike => hasAbortErrorName(error);
