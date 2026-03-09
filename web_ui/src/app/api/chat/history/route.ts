import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

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

    // [Refactor] FastAPI는 기본적으로 에러 정보를 'detail' 필드에 담아 반환함
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      // detail 우선 순위로 에러 메시지 추출
      const errorMessage = errorData.detail || errorData.message || `Failed to ${method.toLowerCase()} history from backend`;
      
      return {
        error: errorMessage,
        status: response.status,
      };
    }

    // [Refactor] DELETE 요청 시에도 백엔드가 반환하는 실제 바디를 전달하여 투명성 확보
    const data = await response.json();
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
