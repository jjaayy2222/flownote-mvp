/**
 * [Review 994 반영] 수치 데이터 정규화를 위한 공용 유틸리티.
 * 단순 Number(val)의 자바스크립트 강제 형변환(true -> 1 등) 부작용을 방지하기 위해 
 * 엄격한 타입 체크가 포함된 정규화 로직을 수행합니다.
 */
export const toSafeNumber = (val: unknown): number | null => {
  // 숫자와 문자열 타입만 허용 (boolean, object 등에서 의도치 않은 0/1 변환 방지)
  if (typeof val !== 'number' && typeof val !== 'string') {
    return null;
  }
  
  const num = Number(val);
  
  // NaN, Infinity 등 비유한 값은 배제
  return Number.isFinite(num) ? num : null;
};
