import { NextResponse } from 'next/server';
import { createUIMessageStreamResponse, streamText } from 'ai';
import type { UIMessage, UIMessageChunk, ModelMessage } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

function generateUniqueId(): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `uid-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

function getOnlyTextFromMessage(message: UIMessage): string {
  const parts = message.parts ?? [];
  const textParts = parts.filter((p) => p.type === 'text');
  if (parts.length > textParts.length && process.env.DEBUG_CHAT === 'true') {
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
    console.error('Failed to parse SSE data payload as JSON', {
      dataPayload,
      error: e,
    });
  }
  return false;
}

function createUIChunkStream(backendRes: Response): ReadableStream<UIMessageChunk> {
  return new ReadableStream<UIMessageChunk>({
    async start(controller) {
      if (!backendRes.body) {
        finishStream(controller, false, null);
        return;
      }

      const reader = backendRes.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const textPartId = `text-${generateUniqueId()}`;
      let textStarted = false;

      const done = () => {
        reader.cancel().catch((err) => {
          if (process.env.DEBUG_CHAT === 'true') {
            console.error('Error canceling stream reader:', err);
          }
        });
        finishStream(controller, textStarted, textPartId);
      };
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

        while (true) {
          const { done: streamDone, value } = await reader.read();
          
          if (streamDone) {
            // Flush any remaining partial multi-line event if stream dropped
            buffer += decoder.decode(new Uint8Array(0), { stream: false });
            const trailingLines = buffer.split('\n');
            for (const trailingLine of trailingLines) {
              const line = trailingLine.replace(/\r$/, '');
              if (line.startsWith('data:')) {
                currentEventDataLines.push(line.slice('data:'.length).trimStart());
              }
            }

            if (flushCurrentEvent()) {
              return;
            }
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const rawLines = buffer.split('\n');
          buffer = rawLines.pop() ?? '';

          for (const rawLine of rawLines) {
            const line = rawLine.replace(/\r$/, '');

            if (line === '') {
              if (flushCurrentEvent()) {
                return;
              }
              continue;
            }

            if (line.startsWith(':')) continue;

            if (line.startsWith('event:')) {
              currentEventType = line.slice('event:'.length).trimStart();
              continue;
            }

            if (line.startsWith('data:')) {
              currentEventDataLines.push(line.slice('data:'.length).trimStart());
            }
          }
        }
      } catch {
        controller.enqueue({
          type: 'error',
          errorText: '스트림 읽기 중 오류가 발생했습니다.',
        } as UIMessageChunk);
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
      user_id: 'test_user_123', // TODO: 인증 연동 시 세션 사용자 ID로 교체
      k: 3,
      alpha: 0.5,
    };

    let backendRes: Response | null = null;
    let fallbackRequired = false;

    try {
      backendRes = await fetch(`${BACKEND_URL}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!backendRes.ok) {
        console.warn(`[Chat Proxy] Backend returned ${backendRes.status}, falling back to Gemini...`);
        fallbackRequired = true;
      }
    } catch (e) {
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
