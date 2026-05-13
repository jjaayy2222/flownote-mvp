// web_ui/src/lib/stream-client.ts

import { API_BASE } from './api';

export type StreamChunkToken = { type: 'token'; data: string };
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type StreamChunkSources = { type: 'sources'; data: any[] };
export type StreamChunkError = { type: 'error'; error_code: string; message: string };
export type StreamChunkDone = { type: 'done' };
export type StreamChunk = StreamChunkToken | StreamChunkSources | StreamChunkError | StreamChunkDone;

export interface StreamChatRequest {
  query: string;
  user_id: string;
  session_id?: string;
  k?: number;
  alpha?: number;
}

/**
 * 표준 fetch API를 사용하여 백엔드의 SSE(Server-Sent Events) 스트림을 소비합니다.
 * EventSource 객체 대신 fetch를 사용하여 POST 요청과 커스텀 헤더 인증을 지원합니다.
 */
export async function* fetchChatStream(
  payload: StreamChatRequest,
  signal?: AbortSignal
): AsyncGenerator<StreamChunk, void, unknown> {
  const url = `${API_BASE}/api/chat/stream`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Failed to start stream: ${response.status} ${response.statusText}`);
  }

  if (!response.body) {
    throw new Error('Response body is null');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      
      let newlineIndex;
      // SSE 이벤트는 \n\n으로 구분됨
      while ((newlineIndex = buffer.indexOf('\n\n')) >= 0) {
        const chunk = buffer.slice(0, newlineIndex).trim();
        buffer = buffer.slice(newlineIndex + 2);

        if (!chunk) continue;
        
        // SSE 규격 "data: <json>"
        if (chunk.startsWith('data: ')) {
          const dataStr = chunk.slice(6).trim();
          
          if (dataStr === '[DONE]') {
            yield { type: 'done' };
            return;
          }
          
          try {
            const parsed = JSON.parse(dataStr) as StreamChunk;
            // 에러 청크인 경우 여기서 변환을 추가할 수 있습니다.
            // (보안을 위해 내부 에러 코드는 클라이언트에서 마스킹)
            yield parsed;
          } catch (e) {
            console.error('[StreamClient] Failed to parse stream chunk JSON:', e, dataStr);
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
