import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

/**
 * 백엔드 히스토리 응답 데이터를 문자열 에러 메시지로 정규화하는 헬퍼
 */
function normalizeErrorMessage(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;
  
  const record = data as Record<string, unknown>;
  const detail = record.detail || record.message;
  if (!detail) return null;

  if (typeof detail === 'string') return detail;
  
  if (Array.isArray(detail)) {
    // FastAPI validation error(422)는 [{msg, loc, type}, ...] 형태를 가집니다.
    return detail
      .map((d: unknown) => {
        if (typeof d === 'string') return d;
        if (d && typeof d === 'object') {
          return (d as Record<string, unknown>).msg || JSON.stringify(d);
        }
        return JSON.stringify(d);
      })
      .join(', ');
  }

  if (typeof detail === 'object') {
     return JSON.stringify(detail);
  }

  return String(detail);
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

    // [Refactor] 204 No Content 또는 빈 바디 응답 시 Safe Handling
    // JSON 필드가 없는 경우 response.json() 호출 시 발생하는 예외를 방지합니다.
    if (response.status === 204) {
      return { data: { status: 'success' }, status: 204 };
    }

    const responseText = await response.text();
    const hasBody = responseText.trim().length > 0;
    let data;
    
    try {
      data = hasBody ? JSON.parse(responseText) : (method === 'DELETE' ? { status: 'success' } : {});
    } catch (e) {
      console.warn(`[Chat History ${method}] Failed to parse JSON body`, e);
      data = { message: responseText || 'No clear message' };
    }

    // [Refactor] FastAPI는 기본적으로 에러 정보를 'detail' 필드에 담아 반환함
    if (!response.ok) {
      // detail 우선 순위로 에러 메시지 추출
      const errorMessage = data.detail || data.message || `Failed to ${method.toLowerCase()} history from backend`;
      
      return {
        error: errorMessage,
        status: response.status,
      };
    }

    return { data, status: 200 };
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

  if (error) {
    return NextResponse.json({ error }, { status });
  }

  return NextResponse.json(data);
}

export async function DELETE(req: Request) {
  const { searchParams } = new URL(req.url);
  const sessionId = searchParams.get('session_id');

  if (!sessionId) {
    return NextResponse.json({ error: 'session_id is required' }, { status: 400 });
  }

  const { data, error, status } = await callBackendHistory('DELETE', sessionId);

  if (error) {
    return NextResponse.json({ error }, { status });
  }

  return NextResponse.json(data);
}
