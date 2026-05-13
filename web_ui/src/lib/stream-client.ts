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
      
      const lines = buffer.split(/\r?\n/);
      // 마지막 원소는 아직 완료되지 않은 줄일 수 있으므로 버퍼에 남겨둡니다.
      buffer = lines.pop() || '';

      let currentData: string[] = [];

      for (const line of lines) {
        if (line === '') {
          // 빈 줄은 SSE 블록의 끝(Dispatch)을 의미합니다.
          if (currentData.length > 0) {
            const dataStr = currentData.join('\n');
            currentData = []; // 리셋

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
          continue;
        }

        if (line.startsWith('data:')) {
          // 'data:' 바로 뒤에 공백이 있다면 하나만 제거 (스펙 준수)
          const dataContent = line.startsWith('data: ') ? line.slice(6) : line.slice(5);
          currentData.push(dataContent);
        }
        // event:, id: 등 기타 필드는 현재 무시합니다. (필요 시 확장 가능)
      }
    }
  } finally {
    reader.releaseLock();
  }
}
