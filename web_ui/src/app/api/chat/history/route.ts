import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

/**
 * 백엔드 히스토리 응답 데이터를 문자열 에러 메시지로 정규화하는 헬퍼
 */
function normalizeErrorMessage(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;

  const record = data as Record<string, unknown>;
  // Nullish coalescing 사용: 빈 문자열('') 등 falsy 하지만 유효한 값을 보존
  const detail = record.detail ?? record.message;
  if (!detail) return null;

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

    // 바디가 없는 상태 코드 확인 (204 No Content, 205, 304 등)
    const isNoContent = [204, 205, 304].includes(response.status);
    let data: unknown = null;

    if (!isNoContent) {
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

    // 성공 시 기본 데이터 설정
    if (response.ok) {
      if (!data) data = { status: 'success' };
      // [Refactor] 성공 상태 노멀라이즈 해제: 원본 상태 코드를 전파하여 투명성 유지
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

  const { data, error, status } = await callBackendHistory('GET', sessionId);
  return error ? NextResponse.json({ error }, { status }) : NextResponse.json(data, { status });
}

export async function DELETE(req: Request) {
  const { searchParams } = new URL(req.url);
  const sessionId = searchParams.get('session_id');

  if (!sessionId) {
    return NextResponse.json({ error: 'session_id is required' }, { status: 400 });
  }

  const { data, error, status } = await callBackendHistory('DELETE', sessionId);
  return error ? NextResponse.json({ error }, { status }) : NextResponse.json(data, { status });
}
