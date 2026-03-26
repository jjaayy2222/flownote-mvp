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
 *   - 그 외: 백엔드 헤더 복제 + body 재구성에 무효화된 헤더 제거 후 전달
 */

import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

/**
 * [Helper] 백엔드 헤더를 복제하되, body 재구성 시 무효화되는 헤더를 제거합니다.
 *
 * `backendRes.text()`는 fetch가 내부적으로 압축 해제(decompress)를 수행합니다.
 * 원본 `content-encoding`(gzip 등)과 `content-length`는 해제된 body와 맞지 않으므로
 * 반드시 제거해야 클라이언트의 재해제 시도나 길이 불일치 오류를 방지할 수 있습니다.
 */
function cloneHeadersWithoutBodyMeta(source: Headers): Headers {
  const headers = new Headers(source);
  headers.delete('content-encoding'); // body가 이미 decode됨
  headers.delete('content-length');   // 재구성된 body의 길이와 다를 수 있음
  return headers;
}

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
    // body가 없으므로 content-encoding/content-length 제거도 불필요합니다.
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

    // non-JSON 응답: backendRes.text()로 body를 재구성하므로
    // content-encoding/content-length는 더 이상 유효하지 않습니다. 반드시 제거합니다.
    let text: string | null = null;
    try {
      text = await backendRes.text();
    } catch {
      text = null;
    }

    const headers = cloneHeadersWithoutBodyMeta(backendRes.headers);
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
