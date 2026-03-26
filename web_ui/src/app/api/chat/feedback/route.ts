// web_ui/src/app/api/chat/feedback/route.ts

/**
 * [Issue #777] AI 응답 피드백 프록시 라우트
 *
 * 프론트엔드에서 /api/chat/feedback으로 POST 요청을 수신하여
 * 파이썬 백엔드의 동일한 경로로 안전하게 중계합니다.
 */

import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function POST(req: Request) {
  try {
    const body = await req.json();

    const backendRes = await fetch(`${BACKEND_URL}/api/chat/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    // [Robustness] Content-Type 검사 후 안전하게 파싱
    // 204/205 No Content, 비JSON 응답 시 원본 status code를 그대로 보존합니다.
    const contentType = backendRes.headers.get('content-type') ?? '';
    let data: unknown = null;

    if (backendRes.status === 204 || backendRes.status === 205) {
      // No Content - 파싱 생략
      data = null;
    } else if (contentType.includes('application/json')) {
      try {
        data = await backendRes.json();
      } catch {
        // JSON 파싱 실패 시 null로 폴백 (원본 status 유지)
        data = null;
      }
    } else {
      try {
        // non-JSON 응답은 텍스트로 보존
        data = await backendRes.text();
      } catch {
        data = null;
      }
    }

    return NextResponse.json(data, { status: backendRes.status });
  } catch (error) {
    console.error('[Feedback Proxy Error]', error);
    return NextResponse.json(
      { error: 'Internal Server Error' },
      { status: 500 }
    );
  }
}
