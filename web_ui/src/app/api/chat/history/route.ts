import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

/** 바디가 없어야 하는 HTTP 상태 코드 규격 (RFC 7231) */
const NO_BODY_STATUS_SET = new Set([204, 205, 304]);

function isNoBodyStatus(status: number): boolean {
  return NO_BODY_STATUS_SET.has(status);
}

/**
 * 백엔드 히스토리 응답 데이터를 문자열 에러 메시지로 정규화하는 헬퍼
 */
function normalizeErrorMessage(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;

  const record = data as Record<string, unknown>;
  // Nullish coalescing 사용: 빈 문자열('') 등 falsy 하지만 유효한 값을 보존
  const detail = record.detail ?? record.message;
  if (detail == null) return null;

  // 1. 단순 문자열인 경우
  if (typeof detail === 'string') return detail;

  // 2. FastAPI validation error 형태인 경우: [{ msg, loc, type }, ...]
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (typeof d === 'string') return d;
        if (d && typeof d === 'object' && 'msg' in d) {
          return String((d as { msg: unknown }).msg);
        }
        return JSON.stringify(d);
      })
      .join(', ');
  }

  // 3. 단일 객체이면서 msg 필드가 있는 경우
  if (typeof detail === 'object' && detail !== null && 'msg' in detail) {
    return String((detail as { msg: unknown }).msg);
  }

  return JSON.stringify(detail);
}

/**
 * 백엔드 결과를 Next.js NextResponse로 변환하는 공통 직렬화 헬퍼
 */
function toNextResponse({
  data,
  error,
  status,
}: {
  data?: unknown;
  error?: string;
  status: number;
}) {
  if (error) {
    return NextResponse.json({ error }, { status });
  }

  // RFC 7231 규격 준수: 바디가 없어야 하는 상태 코드인 경우 빈 응답 반환
  if (isNoBodyStatus(status)) {
    return new NextResponse(null, { status });
  }

  return NextResponse.json(data, { status });
}

/**
 * 백엔드 히스토리 API 호출을 처리하는 공통 헬퍼 함수
 */
async function callBackendHistory(method: 'GET' | 'DELETE', sessionId: string) {
  const url = `${BACKEND_URL}/api/chat/history/${sessionId}`;
  const options: RequestInit = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };

  try {
    const response = await fetch(url, options);
    const noBody = isNoBodyStatus(response.status);
    
    let data: unknown = null;

    if (!noBody) {
      // 텍스트로 먼저 읽어 바디 존재 확인 후 JSON 파싱 (가장 견고한 방법)
      const text = await response.text();
      if (text.trim()) {
        try {
          data = JSON.parse(text);
        } catch (e) {
          console.warn(`[Chat History ${method}] Failed to parse JSON body`, e);
          data = { message: text };
        }
      }
    }

    // 성공 또는 304 상태 시 처리
    if (response.ok || response.status === 304) {
      // [Review 반영] 바디가 필요한 경우에만 기본값 설정 (304 등은 skip)
      if (data == null && !noBody) {
        data = { status: 'success' };
      }
      return { data, status: response.status };
    }

    // 에러 발생(status >= 400) 시 처리
    const errorMessage =
      normalizeErrorMessage(data) ||
      `Failed to ${method.toLowerCase()} history from backend (Status: ${response.status})`;

    return { error: errorMessage, status: response.status };
  } catch (error) {
    console.error(`[Chat History ${method} Proxy Error]`, error);
    return { error: 'Internal Server Error', status: 500 };
  }
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const sessionId = searchParams.get('session_id');

  if (!sessionId) {
    return NextResponse.json({ error: 'session_id is required' }, { status: 400 });
  }

  const result = await callBackendHistory('GET', sessionId);
  return toNextResponse(result);
}

export async function DELETE(req: Request) {
  const { searchParams } = new URL(req.url);
  const sessionId = searchParams.get('session_id');

  if (!sessionId) {
    return NextResponse.json({ error: 'session_id is required' }, { status: 400 });
  }

  const result = await callBackendHistory('DELETE', sessionId);
  return toNextResponse(result);
}
