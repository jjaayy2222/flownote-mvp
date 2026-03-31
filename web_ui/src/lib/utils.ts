import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export class ExhaustiveCheckError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ExhaustiveCheckError';
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
  // 비원시(non-primitive) 값이 들어오더라도 [object Object]가 아니라 실제 값을 알아볼 수 있도록 명시적 String 변환
  const detail = kind !== undefined ? ` (kind: ${String(kind)})` : '';
  
  throw new ExhaustiveCheckError(`Unhandled variant${context ? ` in ${context}` : ''}${detail}`);
};
