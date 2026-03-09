import { NextResponse } from 'next/server';
import { createUIMessageStreamResponse, streamText } from 'ai';
import type { UIMessage, UIMessageChunk, ModelMessage } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { CHAT_CONFIG } from '@/lib/constants';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
/** Nginx 스타일의 비표준 상태 코드: 클라이언트가 연결을 조기에 닫았음을 나타냄 */
const HTTP_STATUS_CLIENT_CLOSED_REQUEST = 499;


function generateUniqueId(): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `uid-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

function isDebugChatEnabled(): boolean {
  const val = process.env.DEBUG_CHAT?.toLowerCase();
  return val === 'true' || val === '1' || val === 'yes';
}

function isAbortError(err: unknown): err is Error & { name: 'AbortError' } {
  return (
    (err instanceof Error && err.name === 'AbortError') ||
    (err as { name?: string })?.name === 'AbortError'
  );
}

function getOnlyTextFromMessage(message: UIMessage): string {
  const parts = message.parts ?? [];
  const textParts = parts.filter((p) => p.type === 'text');
  if (parts.length > textParts.length && isDebugChatEnabled()) {
    console.warn('[Chat Proxy] Extracting only text. Ignored non-text parts in message.');
  }
  return textParts
    .map((p) => (p as { type: 'text'; text: string }).text)
    .join('');
}

function mapUiMessagesToTextOnlyModel(messages: UIMessage[]): ModelMessage[] {
  return messages
    .filter((m) => ['system', 'user', 'assistant'].includes(m.role))
    .map((m) => ({
      role: m.role as 'user' | 'assistant' | 'system',
      content: getOnlyTextFromMessage(m),
    }));
}

function finishStream(
  controller: ReadableStreamDefaultController<UIMessageChunk>,
  textStarted: boolean,
  textPartId: string | null,
) {
  if (textStarted && textPartId) {
    controller.enqueue({ type: 'text-end', id: textPartId });
  }
  controller.enqueue({ type: 'finish-step' });
  controller.enqueue({ type: 'finish' });
  controller.close();
}

function handleSseEvent(
  currentEventType: string | null,
  dataPayload: string,
  controller: ReadableStreamDefaultController<UIMessageChunk>,
  ensureTextStarted: () => void,
  textPartId: string,
): boolean {
  if (dataPayload === '[DONE]') {
    return true; // signals stream is done
  }

  try {
    const parsed = JSON.parse(dataPayload) as {
      type: string;
      data?: unknown;
      message?: string;
    };
    
    const eventType = parsed.type ?? currentEventType ?? 'message';

    if (eventType === 'sources') {
      controller.enqueue({
        type: 'message-metadata',
        messageMetadata: { sources: parsed.data },
      } as UIMessageChunk);
    } else if (eventType === 'token') {
      ensureTextStarted();
      controller.enqueue({
        type: 'text-delta',
        id: textPartId,
        delta: String(parsed.data ?? ''),
      });
    } else if (eventType === 'error') {
      controller.enqueue({
        type: 'error',
        errorText: parsed.message ?? '서버 오류가 발생했습니다.',
      } as UIMessageChunk);
    }
  } catch (e) {
    if (isDebugChatEnabled()) {
      console.error('Failed to parse SSE data payload as JSON', {
        dataPayload,
        error: e,
      });
    }
  }
  return false;
}

function createUIChunkStream(backendRes: Response): ReadableStream<UIMessageChunk> {
  return new ReadableStream<UIMessageChunk>({
    async start(controller) {
      const reader = backendRes.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const textPartId = `text-${generateUniqueId()}`;
      let textStarted = false;
      let isFinished = false;

      const done = () => {
        if (isFinished) return;
        isFinished = true;

        if (reader) {
          reader.cancel().catch((err) => {
            if (isDebugChatEnabled()) {
              console.error('Error canceling stream reader:', err);
            }
          });
        }
        finishStream(controller, textStarted, textPartId);
      };

      if (!reader) {
        done();
        return;
      }

      const ensureTextStarted = () => {
        if (!textStarted) {
          controller.enqueue({ type: 'text-start', id: textPartId });
          textStarted = true;
        }
      };

      try {
        let currentEventType: string | null = null;
        let currentEventDataLines: string[] = [];

        const flushCurrentEvent = (): boolean => {
          if (currentEventDataLines.length > 0) {
            const dataPayload = currentEventDataLines.join('\n');
            const isDone = handleSseEvent(
              currentEventType,
              dataPayload,
              controller,
              ensureTextStarted,
              textPartId
            );
            currentEventDataLines = [];
            currentEventType = null;
            if (isDone) {
              done();
            }
            return isDone;
          }
          return false;
        };

        const processLine = (rawLine: string): boolean => {
          const line = rawLine.replace(/\r$/, '');

          if (line === '') {
            return flushCurrentEvent();
          }

          if (line.startsWith(':')) return false;

          if (line.startsWith('event:')) {
            currentEventType = line.slice('event:'.length).trimStart();
            return false;
          }

          if (line.startsWith('data:')) {
            currentEventDataLines.push(line.slice('data:'.length).trimStart());
          }
          return false;
        };

        while (true) {
          const { done: streamDone, value } = await reader.read();
          
          if (streamDone) {
            // [Fixed] Flush any remaining partial multi-line 이벤트 처리 
            // 스트림이 끊겼을 때 기존 buffer와 마지막 데이터(lastChunk)를 결합하여 데이터 유실을 방지합니다.
            const lastChunk = decoder.decode(new Uint8Array(0), { stream: false });
            const finalData = buffer + lastChunk;
            
            if (finalData) {
              const trailingLines = finalData.split('\n');
              for (const tl of trailingLines) {
                if (processLine(tl)) return;
              }
            }

            // 루프 종료 전 마지막 미처리 이벤트 플러시
            if (flushCurrentEvent()) {
              return;
            }
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const rawLines = buffer.split('\n');
          buffer = rawLines.pop() ?? '';

          for (const rawLine of rawLines) {
            if (processLine(rawLine)) return;
          }
        }
      } catch (err) {
        if (isAbortError(err)) {
          if (isDebugChatEnabled()) {
            console.log('[Chat Proxy] Stream reading aborted.');
          }
          // [Engineering Decision] 
          // 사용자 중단(Abort) 시에는 실시간 수신된 부분 데이터까지를 유효한 결과로 간주하고 
          // 불필요한 에러 팝업 없이 조용히 스트림을 닫는 것이 최상의 UX입니다.
          done();
          return;
        } else {
          controller.enqueue({
            type: 'error',
            errorText: '스트림 읽기 중 오류가 발생했습니다.',
          } as UIMessageChunk);
        }
      }

      done();
    },
  });
}

async function fallbackToGemini(messages: UIMessage[]) {
  const apiKey = process.env.GEMINI_3_PRO_API_KEY;
  const baseURL = process.env.GEMINI_3_PRO_BASE_URL;
  const modelId = process.env.GEMINI_3_PRO_MODEL;

  if (!apiKey || !baseURL || !modelId) {
    return NextResponse.json(
      { error: 'Gemini fallback configurations not found in .env' },
      { status: 500 }
    );
  }

  const customOpenAI = createOpenAI({ apiKey, baseURL });
  const model = customOpenAI(modelId);
  const coreMessages = mapUiMessagesToTextOnlyModel(messages);

  try {
    const result = streamText({
      model,
      messages: coreMessages,
    });
    return result.toUIMessageStreamResponse();
  } catch (e: unknown) {
    const errMsg = e instanceof Error ? e.message : 'Unknown error during Gemini fallback';
    return NextResponse.json({ error: errMsg }, { status: 500 });
  }
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const messages: UIMessage[] = body.messages ?? [];
    const lastMessage = messages[messages.length - 1];

    if (!lastMessage) {
      return NextResponse.json({ error: 'No messages provided' }, { status: 400 });
    }

    const queryText = getOnlyTextFromMessage(lastMessage);

    const payload = {
      query: queryText,
      user_id: body.user_id ?? CHAT_CONFIG.DEFAULT_USER_ID,
      session_id: body.session_id,
      k: body.k ?? CHAT_CONFIG.DEFAULT_K,
      alpha: body.alpha ?? CHAT_CONFIG.DEFAULT_ALPHA,
    };

    let backendRes: Response | null = null;
    let fallbackRequired = false;

    try {
      backendRes = await fetch(`${BACKEND_URL}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: req.signal || undefined,
      });

      if (!backendRes.ok) {
        console.warn(`[Chat Proxy] Backend returned ${backendRes.status}, falling back to Gemini...`);
        fallbackRequired = true;
      }
    } catch (e) {
      if (isAbortError(e)) {
        if (isDebugChatEnabled()) {
          console.log('[Chat Proxy] Fetch aborted by client.');
        }
        return new Response(null, { status: HTTP_STATUS_CLIENT_CLOSED_REQUEST });
      }
      console.warn('[Chat Proxy] Backend connection failed, falling back to Gemini...', e);
      fallbackRequired = true;
    }

    if (fallbackRequired || !backendRes) {
      return fallbackToGemini(messages);
    }

    const chunkStream = createUIChunkStream(backendRes);
    return createUIMessageStreamResponse({ stream: chunkStream });
  } catch (error) {
    console.error('[Chat Proxy Error]', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

