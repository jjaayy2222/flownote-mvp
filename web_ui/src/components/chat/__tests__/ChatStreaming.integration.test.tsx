import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatWindow } from '../ChatWindow';

const mocks = vi.hoisted(() => ({
  streamController: null as ReadableStreamDefaultController<Uint8Array> | null,
  scrollTo: vi.fn(),
}));

vi.mock('@ai-sdk/react', async () => {
  const React = await import('react');

  return {
    useChat: () => {
      const [messages, setMessages] = React.useState<Array<{
        id: string;
        role: 'assistant' | 'user';
        parts: Array<{ type: 'text'; text: string }>;
      }>>([]);

      return { messages, setMessages, sendMessage: vi.fn(), status: 'ready', error: null };
    },
  };
});

vi.mock('@/lib/constants', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/constants')>();
  return {
    ...actual,
    FEATURE_FLAGS: { ...actual.FEATURE_FLAGS, USE_STREAMING: true },
  };
});

vi.mock('@/components/ui/scroll-area', async () => {
  const React = await import('react');
  const ScrollArea = React.forwardRef<HTMLDivElement, React.ComponentProps<'div'>>(
    ({ children, ...props }, ref) => (
      <div {...props} ref={ref}>
        <div
          data-radix-scroll-area-viewport
          ref={(node) => {
            if (!node) return;
            Object.defineProperties(node, {
              scrollHeight: { configurable: true, value: 500 },
              clientHeight: { configurable: true, value: 200 },
              scrollTop: { configurable: true, writable: true, value: 300 },
              scrollTo: { configurable: true, value: mocks.scrollTo },
            });
          }}
        >
          {children}
        </div>
      </div>
    ),
  );
  ScrollArea.displayName = 'ScrollAreaIntegrationTest';
  return { ScrollArea };
});

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const chatProps = {
  externalSessionId: 'integration-session',
  externalUserId: 'integration-user',
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.streamController = null;
  vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      expect(body).toMatchObject({
        query: 'Show the latest note',
        user_id: chatProps.externalUserId,
        session_id: chatProps.externalSessionId,
      });

      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          mocks.streamController = controller;
          controller.enqueue(new TextEncoder().encode(
            'data: {"type":"token","data":"Your latest note is ready."}\n\n',
          ));
        },
      });
      return new Response(stream, {
        headers: { 'Content-Type': 'text/event-stream' },
      });
    }

    return new Response(JSON.stringify({ messages: [] }), {
      headers: { 'Content-Type': 'application/json' },
    });
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Chat streaming integration', () => {
  it('sends the configured identity and renders an SSE response through the chat UI', async () => {
    render(<ChatWindow {...chatProps} />);
    await waitFor(() => expect(screen.queryByText('로드 중...')).toBeNull());

    fireEvent.change(screen.getByPlaceholderText('메시지를 입력하세요...'), {
      target: { value: 'Show the latest note' },
    });
    fireEvent.click(screen.getByRole('button', { name: '메시지 전송' }));

    expect(await screen.findByText('Your latest note is ready.')).not.toBeNull();
    expect(screen.getByText('생성 중...')).not.toBeNull();

    await act(async () => {
      mocks.streamController?.enqueue(new TextEncoder().encode(
        'data: {"type":"done","data":""}\n\n',
      ));
      mocks.streamController?.close();
    });

    await waitFor(() => expect(screen.queryByText('생성 중...')).toBeNull());
    await waitFor(() => expect(screen.getByText('Your latest note is ready.')).not.toBeNull());
  });
});
