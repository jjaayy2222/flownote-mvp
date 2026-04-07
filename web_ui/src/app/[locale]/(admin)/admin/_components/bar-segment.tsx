import React from 'react';
import './bar-pct.css';

interface BarSegmentProps {
  percentage: number;
  className: string;
}

/**
 * [Review 990 반영 & IDE 린트 완전 해결] 
 * 0%~100%까지의 사전 정의된 CSS 클래스(bar-pct-X)를 사용하여 'style' 속성을 완전히 제거합니다.
 * 이를 통해 모든 IDE 차원의 인라인 스타일 경고를 원천적으로 차단합니다.
 */
export function BarSegment({ percentage, className }: BarSegmentProps) {
  // [Review 991 반영] NaN, undefined 등에 대한 방어 코드 및 0~100 범위 클램핑
  const safePct = isNaN(percentage) ? 0 : Math.max(0, Math.min(100, Math.round(percentage)));

  // [Review 991 반영] 0%일 때도 null을 반환하지 않고 렌더링을 유지하여 DOM 구조(라운드 처리 등)의 일관성 확보
  const pctClass = `bar-pct-${safePct}`;

  return (
    <div className={`${pctClass} ${className}`} />
  );
}
