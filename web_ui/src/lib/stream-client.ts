// web_ui/src/lib/stream-client.ts

import { API_BASE } from './api';
import type { SourceItem } from '@/types/chat';

export type StreamChunkToken = { type: 'token'; data: string };
export type StreamChunkSources = { type: 'sources'; data: SourceItem[] };
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

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (err: unknown) {
    const error = err as Error;
    if (error.name === 'AbortError') {
      console.debug('[StreamClient] fetch aborted by user');
      return;
    }
    throw err;
  }

  if (!response.ok) {
    throw new Error(`Failed to start stream: ${response.status} ${response.statusText}`);
  }

  const contentType = response.headers.get('content-type');
  if (!contentType || !contentType.includes('text/event-stream')) {
    throw new Error(`Expected text/event-stream but received ${contentType}`);
  }

  if (!response.body) {
    throw new Error('Response body is null');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  // [Bugfix] 상태 변수들을 while 루프 외부로 이동하여 
  // 네트워크 청크(frame) 분할 시에도 데이터가 유실되지 않고 온전히 누적되도록 수정
  let currentData: string[] = [];
  let currentEvent: string | null = null;
  let currentId: string | null = null;

  try {
    while (true) {
      let readResult;
      try {
        readResult = await reader.read();
      } catch (err: unknown) {
        const error = err as Error;
        if (error.name === 'AbortError') {
          console.debug('[StreamClient] Stream read aborted by user');
          return;
        }
        throw err;
      }

      const { done, value } = readResult;
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line === '') {
          // 빈 줄은 SSE 블록의 끝(Dispatch)을 의미합니다.
          if (currentData.length > 0) {
            const dataStr = currentData.join('\n');
            currentData = []; // 리셋

            if (currentEvent || currentId) {
              // 추후 reconnection이나 event-type 라우팅을 지원하기 위해 파싱해둠
              console.debug(`[StreamClient] event: ${currentEvent}, id: ${currentId}`);
              currentEvent = null; // SSE 스펙상 event는 블록 끝에서 리셋됨
            }

            if (dataStr === '[DONE]') {
              yield { type: 'done' };
              return;
            }

            try {
              const parsed = JSON.parse(dataStr) as StreamChunk;
              yield parsed;
            } catch (e) {
              console.error('[StreamClient] Failed to parse stream chunk JSON:', e, dataStr);
            }
          }
          continue;
        }

        if (line.startsWith('data:')) {
          const dataContent = line.startsWith('data: ') ? line.slice(6) : line.slice(5);
          currentData.push(dataContent);
        } else if (line.startsWith('event:')) {
          currentEvent = line.startsWith('event: ') ? line.slice(7) : line.slice(6);
        } else if (line.startsWith('id:')) {
          currentId = line.startsWith('id: ') ? line.slice(4) : line.slice(3);
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
