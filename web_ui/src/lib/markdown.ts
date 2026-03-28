/**
 * [Pure Function] 점진적으로 수신되는 마크다운의 구조적 안정성을 보강합니다.
 * - 예: 스트리밍 중 코드 블록(```)이 열린 채로 중단된 경우 이를 닫아주어 렌더링 깨짐을 방지합니다.
 */
export function stabilizeIncompleteMarkdown(markdown: string): string {
  if (!markdown) return "";
  
  const lines = markdown.split('\n');
  let inCodeBlock = false;
  
  for (const line of lines) {
    // 마크다운 표준에 따라 줄 시작 부분이 3개 이상의 백틱(```)이면 코드 블록 토글
    if (line.trim().startsWith('```')) {
      inCodeBlock = !inCodeBlock;
    }
  }

  // 코드 블록이 열린 채로 끝났다면 닫는 펜스를 추가
  return inCodeBlock ? `${markdown}\n\n\n\`\`\`` : markdown;
}
