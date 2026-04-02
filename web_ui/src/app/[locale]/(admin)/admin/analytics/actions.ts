'use server';

import { cookies } from 'next/headers';
import { STORAGE_KEYS } from '@/lib/constants';
import { hasAdminAccess } from '@/lib/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export interface FeedbackTrend {
  date: string;
  up: number;
  down: number;
}

export type FeedbackRating = 'up' | 'down' | 'none';

export interface FeedbackDetail {
  session_id: string;
  message_id: string;
  rating: FeedbackRating;
  text: string | null;
  timestamp: string;
}

export interface FeedbackStatsResponse {
  status: string;
  total_up: number;
  total_down: number;
  trends: FeedbackTrend[];
  recent_feedbacks: FeedbackDetail[];
  is_monitoring_active: boolean;
}


/**
 * [Server Action] AI 피드백 통계 차트 데이터를 백엔드로부터 가져온다.
 * 관리자 권한(Cookie)을 먼저 검증한 후, 인증된 요청에 한해 파이썬 백엔드 API를 호출한다.
 */
export async function fetchFeedbackStats(limit: number = 50): Promise<FeedbackStatsResponse> {
  const fallbackResponse: FeedbackStatsResponse = {
    status: 'error',
    total_up: 0,
    total_down: 0,
    trends: [],
    recent_feedbacks: [],
    is_monitoring_active: false,
  };


  try {
    const cookieStore = await cookies();
    
    // Server-Side 환경에서만 동작하므로, 클라이언트 헬퍼 대신 next/headers 의 cookies 사용
    const rawRole = cookieStore.get(STORAGE_KEYS.AUTH_ROLE)?.value;
    const rawEmail = cookieStore.get(STORAGE_KEYS.AUTH_EMAIL)?.value;
    
    // 쿠키 값 디코딩 처리 (특수 문자 및 URI 인코딩 방어용)
    const role = rawRole ? decodeURIComponent(rawRole) : null;
    const email = rawEmail ? decodeURIComponent(rawEmail) : null;

    if (!hasAdminAccess(role, email)) {
      console.warn("[Admin Actions] Unauthorized attempt to fetch feedback stats.");
      return fallbackResponse;
    }

    const adminKey = process.env.ADMIN_API_KEY;
    if (!adminKey) {
      console.error("[OBS] ADMIN_API_KEY is missing from environment variables.");
      return fallbackResponse;
    }

    const res = await fetch(`${BACKEND_URL}/api/chat/feedback/stats?limit=${limit}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'X-Admin-Key': adminKey,
      },
      // 통계는 실시간 성격이 강하므로 브라우저/루터 캐시 무효화 적용
      cache: 'no-store',
    });

    if (!res.ok) {
      throw new Error(`Backend returned status ${res.status}`);
    }

    const data: FeedbackStatsResponse = await res.json();
    return data;
    
  } catch (error) {
    if (process.env.NODE_ENV === 'development') {
      console.error("[OBS] Server Action `fetchFeedbackStats` failed:", error);
    }
    return fallbackResponse;
  }
}

/**
 * [Server Action] Discord 알림 시스템이 정상 작동하는지 테스트 로그를 발생시킨다.
 */
export async function triggerTestAlert(): Promise<{ success: boolean; message: string }> {
  try {
    const cookieStore = await cookies();
    const role = cookieStore.get(STORAGE_KEYS.AUTH_ROLE)?.value ? decodeURIComponent(cookieStore.get(STORAGE_KEYS.AUTH_ROLE)!.value) : null;
    const email = cookieStore.get(STORAGE_KEYS.AUTH_EMAIL)?.value ? decodeURIComponent(cookieStore.get(STORAGE_KEYS.AUTH_EMAIL)!.value) : null;

    if (!hasAdminAccess(role, email)) {
      return { success: false, message: 'Unauthorized' };
    }

    const adminKey = process.env.ADMIN_API_KEY;
    if (!adminKey) return { success: false, message: 'Server Config Error' };

    const res = await fetch(`${BACKEND_URL}/api/chat/alert/test`, {
      method: 'POST',
      headers: {
        'X-Admin-Key': adminKey,
      },
      cache: 'no-store',
    });

    if (!res.ok) throw new Error('Failed to trigger');

    return { success: true, message: 'Test alert sent to Discord!' };
  } catch (error) {
    console.error("[OBS] triggerTestAlert failed:", error);
    return { success: false, message: 'Error triggering alert' };
  }
}
