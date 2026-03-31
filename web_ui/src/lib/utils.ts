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
