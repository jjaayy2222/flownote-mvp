import { NextResponse } from 'next/server';
import { createUIMessageStreamResponse, streamText } from 'ai';
import type { UIMessage, UIMessageChunk, ModelMessage } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import dotenv from 'dotenv';
import path from 'path';
import fs from 'fs';

// 모듈 진입 시 1회만 한 곳에서 일관되게 환경변수(root .env) 로드
const envPath = path.resolve(process.cwd(), '../.env');
if (fs.existsSync(envPath)) {
  dotenv.config({ path: envPath });
}

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

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

  const customOpenAI = createOpenAI({
    apiKey,
    baseURL,
  });

  const model = customOpenAI(modelId);

  // UIMessage -> ModelMessage 변환 (지원하지 않는 role 필터링 가능, 예: system/user/assistant만)
  const coreMessages: ModelMessage[] = messages
    .filter((m) => ['system', 'user', 'assistant'].includes(m.role))
    .map((m) => {
      const textContent = (m.parts ?? [])
        .filter((p) => p.type === 'text')
        .map((p) => (p as { type: 'text'; text: string }).text)
        .join('');
      return {
        role: m.role as 'user' | 'assistant' | 'system',
        content: textContent,
      };
    });

  try {
    const result = streamText({
      model,
      messages: coreMessages,
    });
    
    // ai SDK v6 - UIMessage 스트림 형태로 응답
    return result.toUIMessageStreamResponse();
  } catch (e: unknown) {
    const errMsg = e instanceof Error ? e.message : 'Unknown error during Gemini fallback';
    return NextResponse.json({ error: errMsg }, { status: 500 });
  }
}

export async function POST(req: Request) {
  try {
    const body = await req.json();

    // ai v6 DefaultChatTransport는 { messages } 형태로 전송
    const messages: UIMessage[] = body.messages ?? [];
    const lastMessage = messages[messages.length - 1];

    if (!lastMessage) {
      return NextResponse.json({ error: 'No messages provided' }, { status: 400 });
    }

    // TextUIPart에서 텍스트 추출
    const queryText = (lastMessage.parts ?? [])
      .filter((p) => p.type === 'text')
      .map((p) => (p as { type: 'text'; text: string }).text)
      .join('');

    const payload = {
      query: queryText,
      user_id: 'test_user_123', // TODO: 인증 연동 시 세션 사용자 ID로 교체
      k: 3,
      alpha: 0.5,
    };

    let backendRes: Response | null = null;
    let fallbackRequired = false;

    // 백엔드 SSE 스트리밍 요청 시도
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

    /**
     * UIMessageChunk 오브젝트 스트림을 생성합니다.
     * 백엔드 SSE(sources/token/error/[DONE]) → UIMessageChunk 변환:
     *  - sources 이벤트 → metadata 청크
     *  - token  이벤트 → text-start + text-delta 청크
     *  - error  이벤트 → error 청크  
     *  - [DONE]        → finish-step + finish 청크
     */
    const chunkStream = new ReadableStream<UIMessageChunk>({
      async start(controller) {
        if (!backendRes?.body) {
          controller.enqueue({ type: 'finish-step' });
          controller.enqueue({ type: 'finish' });
          controller.close();
          return;
        }

        const reader = backendRes.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        const textPartId = `text-${Date.now()}`;
        let textStarted = false;

        const done = () => {
          if (textStarted) {
            controller.enqueue({ type: 'text-end', id: textPartId });
          }
          controller.enqueue({ type: 'finish-step' });
          controller.enqueue({ type: 'finish' });
          controller.close();
        };

        try {
          // SSE parsing state for accumulating multiline data fields
          let currentEventType: string | null = null;
          let currentEventDataLines: string[] = [];

          while (true) {
            const { done: streamDone, value } = await reader.read();
            if (streamDone) break;

            // Decode the incoming chunk and append to the rolling buffer
            buffer += decoder.decode(value, { stream: true });

            // Split into lines; keep the last partial line in the buffer
            const rawLines = buffer.split('\n');
            buffer = rawLines.pop() ?? '';

            for (const rawLine of rawLines) {
              // Trim trailing CR for CRLF endings
              const line = rawLine.replace(/\r$/, '');

              // Empty line indicates end of one SSE event
              if (line === '') {
                if (currentEventDataLines.length > 0) {
                  const dataPayload = currentEventDataLines.join('\n');

                  if (dataPayload === '[DONE]') {
                    done();
                    return;
                  }

                  // Hand off the aggregated payload for further handling
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
                      if (!textStarted) {
                        controller.enqueue({ type: 'text-start', id: textPartId });
                        textStarted = true;
                      }
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

                  currentEventDataLines = [];
                  currentEventType = null;
                }
                continue;
              }

              // Comment line (ignored)
              if (line.startsWith(':')) continue;

              // Explicit event type (optional; default is "message")
              if (line.startsWith('event:')) {
                currentEventType = line.slice('event:'.length).trimStart();
                continue;
              }

              // Data line (may be repeated; concatenate with newlines)
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

    return createUIMessageStreamResponse({ stream: chunkStream });
  } catch (error) {
    console.error('[Chat Proxy Error]', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
