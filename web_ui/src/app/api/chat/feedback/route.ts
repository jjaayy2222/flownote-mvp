// web_ui/src/app/api/chat/feedback/route.ts

/**
 * [Issue #777] AI 응답 피드백 프록시 라우트
 *
 * 프론트엔드에서 /api/chat/feedback으로 POST 요청을 수신하여
 * 파이썬 백엔드의 동일한 경로로 안전하게 중계합니다.
 *
 * [Robustness] 응답 유형에 따라 정확히 분기하며, 백엔드의 모든 헤더를 보존합니다:
 *   - 204/205: 백엔드 헤더 복제 후 바디 없이 전달 (HTTP 명세 준수)
 *   - application/json: JSON 안전 파싱 후 NextResponse.json()
 *   - 그 외: 백엔드 헤더 전체 보존 + 원본 바디 그대로 전달
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

    const contentType = backendRes.headers.get('content-type') ?? '';

    // 204/205 No Content: HTTP 명세상 바디가 없어야 합니다.
    // 백엔드 헤더(캐시, CORS 등)는 그대로 복제하여 보존합니다.
    if (backendRes.status === 204 || backendRes.status === 205) {
      return new NextResponse(null, {
        status: backendRes.status,
        headers: new Headers(backendRes.headers),
      });
    }

    // JSON 응답: 안전하게 파싱 후 그대로 전달
    if (contentType.includes('application/json')) {
      let data: unknown = null;
      try {
        data = await backendRes.json();
      } catch {
        // JSON 파싱 실패 시 null로 폴백 (원본 status 유지)
        data = null;
      }
      return NextResponse.json(data, { status: backendRes.status });
    }

    // non-JSON 응답: 백엔드 헤더 전체를 복제하여 보존
    // content-type이 없는 경우에만 text/plain으로 보완합니다.
    let text: string | null = null;
    try {
      text = await backendRes.text();
    } catch {
      text = null;
    }

    const headers = new Headers(backendRes.headers);
    if (!contentType) {
      headers.set('content-type', 'text/plain');
    }

    return new NextResponse(text, {
      status: backendRes.status,
      headers,
    });
  } catch (error) {
    console.error('[Feedback Proxy Error]', error);
    return NextResponse.json(
      { error: 'Internal Server Error' },
      { status: 500 }
    );
  }
}
