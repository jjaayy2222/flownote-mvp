import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatWindow } from '../ChatWindow';

const mocks = vi.hoisted(() => ({
  messages: [] as Array<{
    id: string;
    role: 'assistant' | 'user';
    parts: Array<{ type: 'text'; text: string }>;
  }>,
  sendMessage: vi.fn(),
  setMessages: vi.fn(),
  startStream: vi.fn(),
  cancelStream: vi.fn(),
  streamState: {
    tokens: '' as string,
    isStreaming: false,
    sources: [] as Array<{ title?: string; url?: string; [key: string]: unknown }>,
    error: null as { errorCode: string; message: string } | null,
  },
  chatError: null as Error | null,
  scrollTo: vi.fn(),
}));

vi.mock('@ai-sdk/react', () => ({
  useChat: () => ({
    messages: mocks.messages,
    sendMessage: mocks.sendMessage,
    status: 'ready',
    setMessages: mocks.setMessages,
    error: mocks.chatError,
  }),
}));

vi.mock('@/hooks/useStreamingChat', () => ({
  useStreamingChat: () => ({
    ...mocks.streamState,
    startStream: mocks.startStream,
    cancelStream: mocks.cancelStream,
  }),
}));

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
          data-testid="chat-viewport"
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
  ScrollArea.displayName = 'ScrollAreaTestMock';

  return { ScrollArea };
});

vi.mock('../MessageBubble', () => ({
  MessageBubble: ({ message }: {
    message: {
      id: string;
      parts: Array<{ type: string; text?: string }>;
    };
  }) => (
    <div data-testid={`message-${message.id}`}>
      {message.parts.map((part, index) =>
        part.type === 'text' ? <span key={index}>{part.text}</span> : null,
      )}
    </div>
  ),
}));

vi.mock('react-markdown', async () => {
  const React = await import('react');
  return {
    default: ({ children }: { children: React.ReactNode }) =>
      React.createElement('div', null, children),
  };
});

vi.mock('./markdown-components', () => ({
  REMARK_PLUGINS: [],
  REHYPE_PLUGINS: [],
  useMarkdownComponents: () => ({}),
}));

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

const chatMessages = [
  {
    id: 'hist-0-session-test',
    role: 'user' as const,
    parts: [{ type: 'text' as const, text: 'A saved question' }],
  },
  {
    id: 'hist-1-session-test',
    role: 'assistant' as const,
    parts: [{ type: 'text' as const, text: 'A saved answer' }],
  },
];

const chatProps = {
  externalSessionId: 'session-test',
  externalUserId: 'user-test',
};

async function renderChatWindow() {
  const view = render(<ChatWindow {...chatProps} />);
  await waitFor(() => expect(screen.queryByText('로드 중...')).toBeNull());
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.messages = chatMessages;
  mocks.streamState = {
    tokens: '',
    isStreaming: false,
    sources: [],
    error: null,
  };
  mocks.chatError = null;
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'application/json' },
      json: vi.fn().mockResolvedValue({ messages: [] }),
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ChatWindow', () => {
  it('renders saved messages and keeps sending disabled until text is entered', async () => {
    const { rerender } = await renderChatWindow();

    const savedQuestion = screen.getByTestId('message-hist-0-session-test');
    const savedAnswer = screen.getByTestId('message-hist-1-session-test');
    expect(savedQuestion.textContent).toContain('A saved question');
    expect(savedAnswer.textContent).toContain('A saved answer');
    const conversationLog = screen.getByRole('log');
    expect(conversationLog.getAttribute('aria-live')).toBe('polite');
    expect(conversationLog.getAttribute('aria-relevant')).toBe('additions');
    expect(conversationLog.contains(savedQuestion)).toBe(false);
    expect(conversationLog.contains(savedAnswer)).toBe(false);
    expect(screen.getByRole('button', { name: '메시지 전송' }).hasAttribute('disabled')).toBe(true);

    mocks.messages = [
      ...chatMessages,
      {
        id: 'current-user-message',
        role: 'user',
        parts: [{ type: 'text', text: 'A new question' }],
      },
    ];
    rerender(<ChatWindow {...chatProps} />);

    const currentMessage = screen.getByTestId('message-current-user-message');
    expect(currentMessage.textContent).toContain('A new question');
    expect(conversationLog.contains(currentMessage)).toBe(true);
  });

  it('starts a stream with the entered query and configured session identity', async () => {
    await renderChatWindow();

    fireEvent.change(screen.getByPlaceholderText('메시지를 입력하세요...'), {
      target: { value: '  Find my notes  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: '메시지 전송' }));

    expect(mocks.startStream).toHaveBeenCalledWith({
      query: 'Find my notes',
      user_id: chatProps.externalUserId,
      session_id: chatProps.externalSessionId,
      k: expect.any(Number),
      alpha: expect.any(Number),
    });
  });

  it('renders streaming tokens and cancels the active response on request', async () => {
    mocks.streamState = {
      tokens: 'Streaming response',
      isStreaming: true,
      sources: [],
      error: null,
    };

    await renderChatWindow();

    expect(screen.getByText('Streaming response')).not.toBeNull();
    const stopButton = screen.getByRole('button', { name: '응답 중지' });
    expect(stopButton.getAttribute('aria-label')).toBe('응답 중지');
    fireEvent.click(stopButton);
    expect(mocks.cancelStream).toHaveBeenCalledOnce();
  });

  it('keeps chat errors in one assertive region outside the polite conversation log', async () => {
    mocks.streamState = {
      ...mocks.streamState,
      error: { errorCode: 'STREAM_FAILED', message: 'The response could not be completed.' },
    };

    await renderChatWindow();

    const conversationLog = screen.getByRole('log');
    const errorBanner = screen.getByText('The response could not be completed.');
    const assertiveRegion = errorBanner.closest('[aria-live="assertive"]');

    expect(assertiveRegion).not.toBeNull();
    expect(conversationLog.contains(errorBanner)).toBe(false);
    expect(document.querySelectorAll('[aria-live="assertive"]')).toHaveLength(1);
  });

  it('pauses following when the user scrolls up and resumes from the recent-messages button', async () => {
    mocks.streamState = {
      tokens: 'First streamed token',
      isStreaming: true,
      sources: [],
      error: null,
    };

    const { rerender } = await renderChatWindow();
    const viewport = screen.getByTestId('chat-viewport');
    const scrollTo = mocks.scrollTo;

    mocks.streamState = {
      ...mocks.streamState,
      tokens: 'Token while following',
    };
    rerender(<ChatWindow {...chatProps} />);

    expect(scrollTo).toHaveBeenLastCalledWith({
      top: viewport.scrollHeight,
      behavior: 'auto',
    });
    const followingScrollCalls = scrollTo.mock.calls.length;

    Object.defineProperty(viewport, 'scrollTop', {
      configurable: true,
      writable: true,
      value: 0,
    });
    fireEvent.scroll(viewport);

    mocks.streamState = {
      ...mocks.streamState,
      tokens: 'Next streamed token',
    };
    rerender(<ChatWindow {...chatProps} />);

    expect(await screen.findByRole('button', { name: '최근 메시지로 이동' })).not.toBeNull();
    expect(screen.getByText('새 메시지 도착')).not.toBeNull();
    expect(scrollTo).toHaveBeenCalledTimes(followingScrollCalls);

    fireEvent.click(screen.getByRole('button', { name: '최근 메시지로 이동' }));

    expect(scrollTo).toHaveBeenLastCalledWith({
      top: viewport.scrollHeight,
      behavior: 'smooth',
    });
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '최근 메시지로 이동' })).toBeNull();
    });
  });
});
