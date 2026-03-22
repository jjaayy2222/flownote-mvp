git add backend/services/chat_history_service.py
git commit -m "☘️ refactor [#11.5.8]: 5차 개선 - NoReturn 및 list_sessions 파싱 헬퍼 (핑퐁 방지)

- **[backend/services/chat_history_service.py]**:
  - [타입 체커]: _log_and_reraise_generic의 반환 타입을 NoReturn으로 지정. 이를 통해 각 public 메서드에서 도달 불가능한 더미 return 문(return [], return False) 제거 가능.
  - [리팩토링]: _parse_session_meta_for_list 헬퍼 추출. list_sessions 내부의 JSON 파싱과 예외 처리, 교차 유저 검증 중첩 블록을 헬퍼로 이동시킴으로써 핵심 비즈니스 로직(mget 활용 등)을 평탄화.
  - [의사결정 - 핑퐁 방지]: 3, 4차 코드 리뷰 시 데코레이터에서 발생하는 *args 위치 결합도 문제로 인해 명시적 try/except로 변경한 바 있음. 5차 리뷰에서 데코레이터 복원을 제안하나 구조적 복잡도 제거와 명시성 유지를 위해 기존 방식을 택함.

🔗 Related:
- Issue [#776]

Co-authored-by: Claude 3.5 Sonnet, Gemini 2.5 Pro"
git push origin feature/issue-776-session-sidebar
