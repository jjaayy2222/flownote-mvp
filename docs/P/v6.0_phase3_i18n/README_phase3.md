# Phase 3: 다국어 지원 (i18n)

## 📋 Overview

v6.0 Phase 3에서는 한국어/영어 다국어 지원을 구현하여 글로벌 사용자 확보를 목표로 합니다.

## 🎯 목표

- 한국어/영어 완벽 지원
- 언어 전환 시 즉시 UI 업데이트
- URL 기반 언어 라우팅 (`/ko/dashboard`, `/en/dashboard`)

## 📊 진행 현황 (Progress Status)

### Frontend
- [x] **Internationalization Setup**: `next-intl` 설정 및 Provider 구현
- [x] **Middleware & Routing**: 로케일 기반 라우팅 및 리다이렉션 (Matcher 최적화 완료)
- [x] **Metadata SEO**: 페이지별 동적 메타데이터(Title, Description) 다국어화
- [x] **404 Page**: 다국어 지원 `not-found.tsx` 구현 및 시맨틱 구조 개선
- [x] **QA**: 프로덕션 빌드 검증 및 린트 오류 해결

### Backend
- [x] **Infrastructure**: `Accept-Language` 헤더 파싱 로직(`deps.py`) 구현 (RFC 준수)
- [x] **Message Service**: 다국어 메시지 딕셔너리 및 조회 서비스(`i18n_service.py`) 구축
- [x] **API Integration**: 실제 API 엔드포인트에 다국어 응답 적용
- [x] API 응답 메시지 (100%)
- [x] 에러 메시지 (100%)

## 🧪 구현 내용

### 1. i18n 인프라 구축

#### **next-intl 설치 및 설정**
```bash
npm install next-intl
```

#### **i18n 설정 파일**
```typescript
// web_ui/src/i18n/config.ts

export const locales = ['ko', 'en'] as const;
export type Locale = typeof locales[number];

export const defaultLocale: Locale = 'ko';

export const localeNames: Record<Locale, string> = {
  ko: '한국어',
  en: 'English'
};
```

#### **미들웨어 설정**
```typescript
// web_ui/src/middleware.ts

import createMiddleware from 'next-intl/middleware';
import { locales, defaultLocale } from './i18n/config';

export default createMiddleware({
  locales,
  defaultLocale,
  localePrefix: 'always'
});

export const config = {
  matcher: ['/((?!api|_next|_vercel|.*\\..*).*)']
};
```

#### **Layout 업데이트**
```typescript
// web_ui/src/app/[locale]/layout.tsx

import { NextIntlClientProvider } from 'next-intl';
import { notFound } from 'next/navigation';

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params: { locale }
}: {
  children: React.ReactNode;
  params: { locale: string };
}) {
  let messages;
  try {
    messages = (await import(`@/locales/${locale}.json`)).default;
  } catch (error) {
    notFound();
  }

  return (
    <html lang={locale}>
      <body>
        <NextIntlClientProvider locale={locale} messages={messages}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
```

### 2. 번역 파일 구조

#### **한국어 (ko.json)**
```json
{
  "common": {
    "loading": "콘텐츠를 불러오는 중입니다...",
    "error": "오류가 발생했습니다",
    "save": "저장",
    "cancel": "취소",
    "delete": "삭제"
  },
  "navigation": {
    "dashboard": "대시보드",
    "graph": "그래프 뷰",
    "stats": "통계",
    "preferences": "설정"
  },
  "dashboard": {
    "title": "FlowNote 대시보드",
    "syncMonitor": {
      "title": "동기화 모니터",
      "obsidianStatus": "Obsidian 상태",
      "mcpStatus": "MCP 서버 상태",
      "lastSync": "마지막 동기화"
    }
  },
  "graph": {
    "title": "PARA 그래프 뷰",
    "zoom": "확대/축소",
    "pan": "이동",
    "nodeClick": "{label} 선택됨"
  },
  "stats": {
    "title": "통계",
    "activityHeatmap": "활동 히트맵",
    "weeklyTrend": "주간 추이",
    "paraDistribution": "PARA 분포"
  },
  "para": {
    "projects": "프로젝트",
    "areas": "분야",
    "resources": "자료",
    "archives": "보관"
  }
}
```

#### **영어 (en.json)**
```json
{
  "common": {
    "loading": "Loading content...",
    "error": "An error occurred",
    "save": "Save",
    "cancel": "Cancel",
    "delete": "Delete"
  },
  "navigation": {
    "dashboard": "Dashboard",
    "graph": "Graph View",
    "stats": "Statistics",
    "preferences": "Preferences"
  },
  "dashboard": {
    "title": "FlowNote Dashboard",
    "syncMonitor": {
      "title": "Sync Monitor",
      "obsidianStatus": "Obsidian Status",
      "mcpStatus": "MCP Server Status",
      "lastSync": "Last Sync"
    }
  },
  "graph": {
    "title": "PARA Graph View",
    "zoom": "Zoom",
    "pan": "Pan",
    "nodeClick": "{label} selected"
  },
  "stats": {
    "title": "Statistics",
    "activityHeatmap": "Activity Heatmap",
    "weeklyTrend": "Weekly Trend",
    "paraDistribution": "PARA Distribution"
  },
  "para": {
    "projects": "Projects",
    "areas": "Areas",
    "resources": "Resources",
    "archives": "Archives"
  }
}
```

### 3. 컴포넌트에서 사용

#### **useTranslations Hook**
```typescript
// web_ui/src/components/dashboard/SyncMonitor.tsx

import { useTranslations } from 'next-intl';

export function SyncMonitor() {
  const t = useTranslations('dashboard.syncMonitor');

  return (
    <div>
      <h2>{t('title')}</h2>
      <div>
        <label>{t('obsidianStatus')}</label>
        <span>{status}</span>
      </div>
      <div>
        <label>{t('lastSync')}</label>
        <span>{formatDate(lastSync)}</span>
      </div>
    </div>
  );
}
```

#### **동적 파라미터**
```typescript
// web_ui/src/components/para/GraphView.tsx

const t = useTranslations('graph');

const handleNodeClick = (node: Node) => {
  toast(t('nodeClick', { label: node.data.label }));
};
```

### 4. 언어 전환 UI

#### **LanguageSwitcher 컴포넌트**
```typescript
// web_ui/src/components/layout/LanguageSwitcher.tsx

import { useLocale } from 'next-intl';
import { usePathname, useRouter } from 'next/navigation';
import { locales, localeNames } from '@/i18n/config';

export function LanguageSwitcher() {
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();

  const switchLocale = (newLocale: string) => {
    const newPathname = pathname.replace(`/${locale}`, `/${newLocale}`);
    router.push(newPathname);
  };

  return (
    <div className="language-switcher">
      {locales.map((loc) => (
        <button
          key={loc}
          onClick={() => switchLocale(loc)}
          className={locale === loc ? 'active' : ''}
        >
          {localeNames[loc]}
        </button>
      ))}
    </div>
  );
}
```

#### **Header에 통합**
```typescript
// web_ui/src/components/layout/Header.tsx

export function Header() {
  return (
    <header>
      <Logo />
      <Navigation />
      <LanguageSwitcher />
    </header>
  );
}
```

### 5. 날짜/숫자 포맷

#### **날짜 포맷**
```typescript
// web_ui/src/lib/formatters.ts

import { useFormatter } from 'next-intl';

export function useDateFormatter() {
  const format = useFormatter();

  return {
    formatDate: (date: Date) => format.dateTime(date, {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    }),
    formatRelative: (date: Date) => format.relativeTime(date)
  };
}
```

#### **숫자 포맷**
```typescript
export function useNumberFormatter() {
  const format = useFormatter();

  return {
    formatNumber: (num: number) => format.number(num, {
      notation: 'standard'
    }),
    formatPercent: (num: number) => format.number(num, {
      style: 'percent'
    })
  };
}
```

### 6. Backend API 다국어화

#### **Accept-Language 헤더 처리**
```python
# backend/api/dependencies.py

from fastapi import Header

async def get_locale(accept_language: str = Header(default="ko")):
    # Parse Accept-Language header
    locale = accept_language.split(',')[0].split('-')[0]
    return locale if locale in ['ko', 'en'] else 'ko'
```

#### **다국어 응답 메시지**
```python
# backend/services/i18n_service.py

MESSAGES = {
    "ko": {
        "file_classified": "파일이 {category}로 분류되었습니다.",
        "sync_completed": "동기화가 완료되었습니다.",
        "conflict_detected": "충돌이 감지되었습니다."
    },
    "en": {
        "file_classified": "File classified as {category}.",
        "sync_completed": "Sync completed.",
        "conflict_detected": "Conflict detected."
    }
}

def get_message(key: str, locale: str, **kwargs) -> str:
    template = MESSAGES.get(locale, MESSAGES['ko']).get(key, key)
    return template.format(**kwargs)
```

## 🚀 Running

### Frontend
```bash
cd web_ui
npm install next-intl
npm run dev

# 한국어: http://localhost:3000/ko
# 영어: http://localhost:3000/en
```

## 🧪 Testing

### Unit Tests
```bash
# i18n 설정 테스트
npm test -- i18n.test.ts

# 번역 키 누락 검사
npm run test:i18n
```

### Manual Testing

#### **Scenario 1: 언어 전환**
1. `/ko/dashboard` 접속
2. 언어 스위처에서 "English" 선택
3. URL이 `/en/dashboard`로 변경되는지 확인
4. 모든 UI 텍스트가 영어로 표시되는지 확인

#### **Scenario 2: 브라우저 언어 자동 감지**
1. 브라우저 언어 설정을 영어로 변경
2. `/` 접속
3. 자동으로 `/en`으로 리다이렉트되는지 확인

#### **Scenario 3: 날짜 포맷**
1. 한국어: "2026년 1월 8일"
2. 영어: "January 8, 2026"

## 📊 번역 완료율

### Frontend
- [x] Navigation (100%)
- [x] Dashboard (100%)
- [x] Graph View (100%)
- [x] Stats (100%)
- [x] Settings (100%)
- [x] Error Messages (100%)

### Backend
- [x] API 응답 메시지 (100%)
- [x] 에러 메시지 (100%)

### Documentation
- [ ] README.md (영문 버전)
- [ ] USER_GUIDE.md (영문 버전)

## 🐛 Troubleshooting

### **번역 키 누락**

**원인:**
- JSON 파일에 키가 없음

**해결:**
```typescript
// Fallback 메시지 설정
<NextIntlClientProvider 
  messages={messages}
  onError={(error) => {
    console.warn('Translation missing:', error);
  }}
>
```

### **URL 리다이렉트 루프**

**원인:**
- 미들웨어 설정 오류

**해결:**
```typescript
// matcher 패턴 수정
export const config = {
  matcher: ['/((?!api|_next|_vercel|favicon.ico|.*\\..*).*)']
};
```

## 📝 Next Steps

- [ ] 추가 언어 지원 (일본어, 중국어)
- [ ] RTL 언어 지원 (아랍어, 히브리어)
- [ ] 번역 관리 도구 통합 (Crowdin, Lokalise)
- [ ] AI 기반 자동 번역

## 🔗 Related Documentation

- [next-intl Documentation](https://next-intl-docs.vercel.app/)
- [i18n Best Practices](https://www.i18next.com/principles/fallback)
- [Intl API](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl)
