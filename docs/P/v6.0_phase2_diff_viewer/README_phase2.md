# Phase 2: Conflict Diff Viewer

## 📋 Overview

v6.0 Phase 2에서는 파일 충돌 발생 시 양쪽 버전을 시각적으로 비교하고 선택할 수 있는 UI를 구현합니다.

## 🎯 목표

- 충돌 파일의 차이점을 명확하게 시각화
- 3가지 해결 옵션 제공 (Keep Local / Keep Remote / Keep Both)
- Markdown 파일 렌더링 프리뷰 지원

## 🧪 구현 내용

### 1. Backend Diff API

#### **Diff 엔드포인트**
```python
# backend/api/endpoints/sync.py

@router.get("/conflicts/{conflict_id}/diff")
async def get_conflict_diff(conflict_id: str):
    """
    충돌 파일의 Diff 데이터 반환
    """
    conflict = await get_conflict_by_id(conflict_id)
    
    local_content = await read_file(conflict.local_path)
    remote_content = await read_file(conflict.remote_path)
    
    diff = generate_diff(local_content, remote_content)
    
    return {
        "conflict_id": conflict_id,
        "local_content": local_content,
        "remote_content": remote_content,
        "diff": diff,
        "file_type": conflict.file_type
    }
```

#### **Diff 생성 로직**
```python
# backend/services/diff_service.py

import difflib

def generate_diff(local: str, remote: str) -> dict:
    """
    Unified Diff 및 Side-by-Side Diff 생성
    """
    local_lines = local.splitlines(keepends=True)
    remote_lines = remote.splitlines(keepends=True)
    
    # Unified Diff (제너레이터를 리스트로 물질화하여 재사용 가능하게 함)
    unified_diff = list(difflib.unified_diff(
        local_lines, 
        remote_lines,
        fromfile='Local',
        tofile='Remote'
    ))
    
    # Side-by-Side Diff
    differ = difflib.HtmlDiff()
    html_diff = differ.make_table(
        local_lines,
        remote_lines,
        fromdesc='Local',
        todesc='Remote'
    )
    
    # Diff 헤더(+++, ---) 제외하고 실제 변경 라인만 카운트
    # (@@ hunk 헤더는 + 또는 -로 시작하지 않으므로 별도 체크 불필요)
    additions = sum(
        1 for line in unified_diff 
        if line.startswith('+') and not line.startswith('+++')
    )
    deletions = sum(
        1 for line in unified_diff 
        if line.startswith('-') and not line.startswith('---')
    )
    
    return {
        "unified": "".join(unified_diff),
        "html": html_diff,
        "stats": {
            "additions": additions,
            "deletions": deletions
        }
    }
```

#### **충돌 해결 API**
```python
# backend/api/endpoints/sync.py

@router.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    conflict_id: str,
    resolution: ConflictResolution
):
    """
    충돌 해결
    - keep_local: 로컬 버전 유지
    - keep_remote: 원격 버전 유지
    - keep_both: 두 버전 모두 유지 (rename)
    """
    conflict = await get_conflict_by_id(conflict_id)
    
    if resolution.strategy == "keep_local":
        await apply_local_version(conflict)
    elif resolution.strategy == "keep_remote":
        await apply_remote_version(conflict)
    elif resolution.strategy == "keep_both":
        await keep_both_versions(conflict)
    
    await mark_conflict_resolved(conflict_id)
    
    return {"status": "resolved", "strategy": resolution.strategy}
```

### 2. Frontend Diff Viewer Component

#### **ConflictDiffViewer.tsx**
```typescript
// web_ui/src/components/sync/ConflictDiffViewer.tsx

import { useState } from 'react';
import { DiffEditor } from '@monaco-editor/react';

interface ConflictDiffViewerProps {
  conflictId: string;
  onResolve: (strategy: 'keep_local' | 'keep_remote' | 'keep_both') => void;
}

export function ConflictDiffViewer({ conflictId, onResolve }: ConflictDiffViewerProps) {
  const [diffData, setDiffData] = useState<DiffData | null>(null);
  const [viewMode, setViewMode] = useState<'side-by-side' | 'inline'>('side-by-side');

  useEffect(() => {
    fetchDiff(conflictId).then(setDiffData);
  }, [conflictId]);

  if (!diffData) return <LoadingSpinner />;

  return (
    <div className="conflict-diff-viewer">
      <div className="diff-header">
        <h2>Conflict Resolution</h2>
        <div className="view-toggle">
          <Button onClick={() => setViewMode('side-by-side')}>
            Side by Side
          </Button>
          <Button onClick={() => setViewMode('inline')}>
            Inline
          </Button>
        </div>
      </div>

      <div className="diff-stats">
        <span className="additions">+{diffData.stats.additions}</span>
        <span className="deletions">-{diffData.stats.deletions}</span>
      </div>

      {viewMode === 'side-by-side' ? (
        <DiffEditor
          original={diffData.local_content}
          modified={diffData.remote_content}
          language="markdown"
          theme="vs-dark"
          options={{
            readOnly: true,
            renderSideBySide: true
          }}
        />
      ) : (
        <InlineDiffView diff={diffData.unified} />
      )}

      <div className="resolution-actions">
        <Button onClick={() => onResolve('keep_local')} variant="primary">
          Keep Local
        </Button>
        <Button onClick={() => onResolve('keep_remote')} variant="primary">
          Keep Remote
        </Button>
        <Button onClick={() => onResolve('keep_both')} variant="secondary">
          Keep Both
        </Button>
      </div>
    </div>
  );
}
```

#### **Markdown 프리뷰**
```typescript
// web_ui/src/components/sync/MarkdownPreview.tsx

import ReactMarkdown from 'react-markdown';

export function MarkdownPreview({ content }: { content: string }) {
  return (
    <div className="markdown-preview">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}
```

### 3. Sync Monitor 통합

#### **충돌 목록에서 Diff Viewer 열기**
```typescript
// web_ui/src/components/dashboard/SyncMonitor.tsx

export function SyncMonitor() {
  const [selectedConflict, setSelectedConflict] = useState<string | null>(null);

  return (
    <div>
      <h2>Conflicts</h2>
      <ul>
        {conflicts.map(conflict => (
          <li key={conflict.id}>
            <span>{conflict.file_name}</span>
            <Button onClick={() => setSelectedConflict(conflict.id)}>
              View Diff
            </Button>
          </li>
        ))}
      </ul>

      {selectedConflict && (
        <Sheet open={!!selectedConflict} onOpenChange={() => setSelectedConflict(null)}>
          <SheetContent side="right" className="w-full md:w-3/4">
            <ConflictDiffViewer
              conflictId={selectedConflict}
              onResolve={(strategy) => {
                resolveConflict(selectedConflict, strategy);
                setSelectedConflict(null);
              }}
            />
          </SheetContent>
        </Sheet>
      )}
    </div>
  );
}
```

### 4. WebSocket Stability & Performance (Refactored)

리뷰 피드백을 반영하여 WebSocket 통신의 안정성과 성능을 대폭 강화했습니다.

#### **Parallel Broadcasting**
- `asyncio.gather`를 도입하여 메시지 전송을 병렬화했습니다. 이를 통해 특정 클라이언트의 네트워크 지연이 전체 브로드캐스트 성능을 저하시키는 HoL(Head-of-Line) Blocking 문제를 해결했습니다.
- 메시지 사이즈 계산을 위한 UTF-8 인코딩을 루프 외부로 분리하여, 사이즈 측정 시 발생하는 불필요한 중복 연산을 제거했습니다.

#### **Robust Error Handling**
- `disconnect` 메서드에 `propagate_errors` 플래그를 추가하여, 연결 정리(`_prune_connection`) 시 발생하는 예외를 정확히 포착하고 로깅할 수 있도록 구조를 개선했습니다. `WebSocketDisconnect`를 명시적으로 처리하여 로그의 정확도를 높였습니다.

## 🚀 Running

### Backend
```bash
python -m uvicorn backend.main:app --reload
```

### Frontend
```bash
cd web_ui
npm install @monaco-editor/react react-markdown
npm run dev
```

## 🧪 Testing

### Unit Tests
```bash
# Backend Diff 생성 테스트
pytest tests/unit/test_diff_service.py -v

# Frontend Component 테스트
npm test -- ConflictDiffViewer.test.tsx
```

### Integration Tests
```bash
# E2E 충돌 해결 테스트
pytest tests/integration/test_conflict_resolution.py -v
```

### Manual Testing Scenarios

#### **Scenario 1: Side-by-Side Diff**
1. Sync Monitor에서 충돌 파일 선택
2. "View Diff" 버튼 클릭
3. Side-by-Side 뷰에서 차이점 확인
4. "Keep Local" 선택하여 해결

#### **Scenario 2: Markdown 프리뷰**
1. Markdown 파일 충돌 선택
2. Diff Viewer에서 "Preview" 탭 클릭
3. 렌더링된 Markdown 비교
4. "Keep Remote" 선택

#### **Scenario 3: Keep Both**
1. 충돌 파일 선택
2. "Keep Both" 선택
3. 두 파일이 모두 유지되는지 확인
   - `file.md` (remote)
   - `file_local_timestamp.md` (local)

## 📊 UI/UX 고려사항

### Diff 색상 코드
- **추가된 라인**: 녹색 배경 (`bg-green-100`)
- **삭제된 라인**: 빨간색 배경 (`bg-red-100`)
- **변경된 라인**: 노란색 배경 (`bg-yellow-100`)

### 키보드 단축키
- `Ctrl/Cmd + 1`: Keep Local
- `Ctrl/Cmd + 2`: Keep Remote
- `Ctrl/Cmd + 3`: Keep Both
- `Esc`: 닫기

## 🐛 Troubleshooting

### **Diff 생성 실패**

**원인:**
- 파일 인코딩 문제
- 바이너리 파일

**해결:**
```python
# UTF-8 강제 인코딩
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()
```

### **Monaco Editor 로딩 느림**

**원인:**
- CDN 로딩 지연

**해결:**
```typescript
// Dynamic import로 최적화
const DiffEditor = dynamic(
  () => import('@monaco-editor/react').then(mod => mod.DiffEditor),
  { ssr: false }
);
```

## 📅 Task Progress

### Day 1 (01/22)
- [x] Backend Diff Service 구현 (`diff_service.py`)
- [x] Backend Unit Tests 작성 (`test_diff_service.py`)
- [x] WebSocket Monitor 최적화 (Phase 1 Code Review 반영)

### Day 2 (01/23)
- [x] Backend Diff Endpoint 추가 (`GET /conflicts/{id}/diff`)
- [x] Frontend Dependency 설치 (`@monaco-editor/react`, `react-markdown`)
- [x] Frontend Component Scaffolding (`ConflictDiffViewer.tsx`)
- [x] Frontend Refactoring: Strategy Constants 도입 및 Backend Protocol 통일
- [x] Backend Refactoring: `ResolutionStrategy` Enum 위 도입 (Validation 강화)
- [x] Frontend Refactoring: `SyncMonitor` 및 `api.ts` 매직 스트링 제거 (Status 상수 적용)
- [x] Backend Fix: 중복 Route Decorator 제거 및 최종 점검 완료
- [ ] Frontend Integration (API 연동 및 Diff 렌더링)

### Day 3 (01/24)
- [x] Frontend Integration 계획 수립 및 문서화

### Day 4 (01/25)
- [x] Frontend: Monaco Diff Editor UI 구현 (DiffEditor Integration)
- [x] Frontend: Conflict Resolution API Integration (GET /diff)
- [x] Frontend Refactoring: Retry Logic 개선 & Type Safety 강화 (DiffResult)
- [x] Frontend Refactoring: Race Condition 방지 & Custom Hook 도입 (`useFetch`)
- [ ] Frontend: Resolution Action 핸들링 및 E2E Test (-> Day 5 이동)

### Day 5 (01/26) - Integration Flow
- [x] Integration: `SyncMonitor` 내 `ConflictDiffViewer` 연동 (Sheet UI, Responsive/Smooth Width)
- [x] Logic: `POST /resolve` API 호출 (Safe URL Encoding) 및 상태 갱신 로직 구현
- [x] Test: Integration Test 강화 (Parametrization, Schema Deep Check, Robust Error Validation Helper v2)

### Day 6 (01/27) - Final Verification
- [x] Integration Test 최종 검증 (5 passed, 1 warning)
- [x] 모든 Resolution Strategy 테스트 통과 (`keep_local`, `keep_remote`, `keep_both`, `invalid_method`)
- [x] Schema Deep Validation 및 Error Structure 검증 완료
- [x] Phase 2 완료 확인 및 문서화

## ✅ Phase 2 완료 (2026-01-27)

### 구현 완료 항목
- ✅ **Backend Diff API**: `/api/sync/conflicts/{id}/diff` 엔드포인트 구현
- ✅ **Backend Resolution API**: `/api/sync/conflicts/{id}/resolve` 엔드포인트 구현
- ✅ **Diff Service**: Python `difflib` 기반 Unified/Side-by-Side Diff 생성
- ✅ **Frontend Diff Viewer**: Monaco Diff Editor 통합 (`ConflictDiffViewer.tsx`)
- ✅ **Custom Hook**: `useFetch` - Abortable async data fetching with race condition prevention
- ✅ **SyncMonitor Integration**: Sheet UI를 통한 Diff Viewer 모달 표시
- ✅ **Resolution Logic**: 3가지 전략 (`keep_local`, `keep_remote`, `keep_both`) 구현 및 API 호출
- ✅ **Integration Tests**: Parametrized tests with deep schema validation
- ✅ **Test Utilities**: `validate_pydantic_error_structure` helper for robust error validation

### 테스트 결과
```bash
# Integration Test (01/27)
pytest tests/integration/test_diff_viewer_flow.py
========================= 5 passed, 1 warning in 0.61s =========================

Test Coverage:
- ✅ GET /api/sync/conflicts/{id}/diff - 200 OK with valid diff data
- ✅ POST /api/sync/conflicts/{id}/resolve?resolution_method=keep_local - 200 OK
- ✅ POST /api/sync/conflicts/{id}/resolve?resolution_method=keep_remote - 200 OK
- ✅ POST /api/sync/conflicts/{id}/resolve?resolution_method=keep_both - 200 OK
- ✅ POST /api/sync/conflicts/{id}/resolve?resolution_method=invalid - 422 Validation Error
```

### 주요 개선 사항
1. **Race Condition 방지**: `useFetch` Hook의 AbortController 패턴 적용
2. **URL 안전성**: `URLSearchParams` 사용으로 쿼리 파라미터 인코딩 보장
3. **반응형 UI**: Sheet 컴포넌트의 Smooth Width Transition (모바일 대응)
4. **테스트 품질**: Parametrization, Deep Schema Validation, Robust Error Handling
5. **코드 재사용성**: Test Helper 함수 분리 (`tests/test_utils.py`)

### 완료 조건 (DoD) 달성
- ✅ 충돌 파일의 차이점을 시각적으로 명확히 확인 가능 (Monaco Diff Editor)
- ✅ 3가지 해결 옵션 모두 정상 동작 (`keep_local`, `keep_remote`, `keep_both`)
- ✅ Markdown 파일 Syntax Highlighting 지원
- ✅ Integration Test 통과 (Backend API + Frontend Component)
- ✅ 반응형 UI 구현 (모바일/데스크톱 대응)

## 📝 Future Tasks
- [ ] 3-way Merge 알고리즘 연구 및 적용
- [ ] 충돌 이력(History) 저장 기능
- [ ] AI 기반 충돌 해결 가이드 제공
- [ ] 대용량 파일 Diff 렌더링 최적화

## 🔗 Related Documentation

- [Monaco Editor](https://microsoft.github.io/monaco-editor/)
- [Python difflib](https://docs.python.org/3/library/difflib.html)
- [React Markdown](https://github.com/remarkjs/react-markdown)
