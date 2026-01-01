# Step 3 Phase 3: Visualization & Mobile Support

## 📋 Overview

Step 3 Phase 3에서는 프로젝트의 데이터를 시각적으로 표현하고 모바일 환경에서도 원활하게 접근할 수 있도록 UI/UX를 고도화했습니다. PARA 구조를 직관적으로 파악할 수 있는 Graph View와 데이터 흐름을 보여주는 통계 차트, 그리고 반응형 모바일 내비게이션이 핵심입니다.

## 🎯 구현 내용

### **2.1 Advanced Visualization** (New!)

- **🕸️ PARA Graph View (`/graph`)**
    - **Tech**: `reactflow`
    - **Feature**:
        - 파일과 카테고리(Projects, Areas, Resources, Archives) 간의 연결 관계 시각화
        - Deterministic Layout: 페이지 새로고침 시에도 노드 위치 유지 (File ID 기반)
        - **Interactive Node**: 노드 클릭 시 Toast 알림으로 상세 정보(파일명, 타입) 표시
        - Zoom In/Out, Panning 지원

- **📈 Advanced Stats (`/stats`)**
    - **Tech**: `recharts`
    - **Charts**:
        1.  **Activity Heatmap**: GitHub 스타일의 연간 활동(파일 생성/수정) 빈도 시각화
        2.  **Weekly Trend**: 최근 12주간의 파일 처리량 추이 (Line Chart)
        3.  **PARA Distribution**: 현재 보관함의 카테고리별 비중 (Pie Chart)

### **2.2 Mobile Responsiveness** (New!)

- **📱 Adaptive Navigation**
    - **Desktop**: 좌측 고정 사이드바 (`Sidebar`)
    - **Mobile**: 상단 헤더 및 좌측 슬라이드 메뉴 (`MobileNav` + Shadcn UI `Sheet`)
    - **Auto Switch**: 화면 너비(`md` breakpoint)에 따라 자동으로 최적의 내비게이션 전환

- **🔧 UX Polish**
    - **Drawer Scroll**: 모바일 메뉴가 길어질 경우 스크롤(`overflow-y-auto`) 지원
    - **Prevent Layout Shift**: 내비게이션 전환 시 레이아웃 흔들림 방지 처리

## 🏗️ 아키텍처 (Frontend Update)

```
Frontend (Next.js)
    ├── /graph  --> React Flow Component
    ├── /stats  --> Recharts Components
    └── Layout  --> Responsive (Sidebar / MobileNav)
```

## 📂 파일 구조 (Updates)

```
web_ui/src/
├── app/
│   ├── graph/page.tsx          # Graph View Page
│   └── stats/page.tsx          # Statistics Page
├── components/
│   ├── para/GraphView.tsx      # Graph Component
│   ├── dashboard/stats/        # Stats Components
│   └── layout/
│       ├── mobile-nav.tsx      # Mobile Navigation
│       └── sidebar.tsx         # Desktop Sidebar
└── config/
    └── navigation.ts           # Navigation Config (Menu Items)
```

## 🚀 Testing Features

1. **Graph Interaction**
   - `/graph` 페이지 접속 -> 노드 클릭 -> "Selected: [Filename]" Toast 확인

2. **Mobile Layout**
   - 개발자 도구(F12) -> Device Mode -> Mobile(375px) 설정
   - 햄버거 메뉴 클릭 -> Drawer 열림/닫힘 및 스크롤 확인

## 📊 Features Checklist

- ✅ PARA Graph View (Deterministic Layout)
- ✅ Node Click Interaction (Toast)
- ✅ 3 Types of Charts (Heatmap, Line, Pie)
- ✅ Mobile Responsive Navigation
- ✅ Accessible Markup (Semantic Buttons)

## 🔗 Related

- [Step 3 Phase 2 Detail](../v5_phase2_frontend/README.md) (Frontend Basics)
- [Project Issue #214](https://github.com/jjaayy2222/flownote-mvp/issues/214)
