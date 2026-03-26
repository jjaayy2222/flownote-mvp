// web_ui/src/app/api/chat/feedback/route.ts

/**
 * [Issue #777] AI 응답 피드백 프록시 라우트
 *
 * 프론트엔드에서 /api/chat/feedback으로 POST 요청을 수신하여
 * 파이썬 백엔드의 동일한 경로로 안전하게 중계합니다.
 *
 * [Robustness] 응답 유형에 따라 정확히 분기합니다:
 *   - 204/205: 바디 없이 status만 전달 (HTTP 명세 준수)
 *   - application/json: JSON 안전 파싱 후 NextResponse.json()
 *   - 그 외: 원본 바디 text + 원본 content-type 그대로 전달
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
    // NextResponse.json()은 content-type: application/json + null 바디를 강제하므로 사용 불가.
    if (backendRes.status === 204 || backendRes.status === 205) {
      return new NextResponse(null, { status: backendRes.status });
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

    // non-JSON 응답: 원본 바디와 content-type을 그대로 보존
    let text: string | null = null;
    try {
      text = await backendRes.text();
    } catch {
      text = null;
    }

    return new NextResponse(text, {
      status: backendRes.status,
      headers: { 'content-type': contentType || 'text/plain' },
    });
  } catch (error) {
    console.error('[Feedback Proxy Error]', error);
    return NextResponse.json(
      { error: 'Internal Server Error' },
      { status: 500 }
    );
  }
}
