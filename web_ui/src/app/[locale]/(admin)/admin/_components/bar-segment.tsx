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
  if (percentage <= 0) return null;

  // 0~100 사이의 올바른 클래스 이름 생성 (Math.round로 안전하게 반올림)
  const pctClass = `bar-pct-${Math.max(0, Math.min(100, Math.round(percentage)))}`;

  return (
    <div className={`${pctClass} ${className}`} />
  );
}
