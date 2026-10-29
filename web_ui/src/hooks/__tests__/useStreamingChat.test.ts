import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  fetchChatStream,
  type StreamChatRequest,
  type StreamChunk,
} from '@/lib/stream-client';
import type { SourceItem } from '@/types/chat';
import { useStreamingChat } from '../useStreamingChat';

vi.mock('@/lib/stream-client', () => ({
  fetchChatStream: vi.fn(),
}));

const mockFetchChatStream = vi.mocked(fetchChatStream);

const request: StreamChatRequest = {
  query: 'test query',
  user_id: 'test-user',
  session_id: 'test-session',
};

const source: SourceItem = {
  id: 'source-1',
  title: 'Test source',
};

async function* streamOf(...chunks: StreamChunk[]): AsyncGenerator<StreamChunk> {
  yield* chunks;
}

function abortError(): Error {
  return Object.assign(new Error('Aborted'), { name: 'AbortError' });
}

function waitForAbort(signal: AbortSignal | undefined): Promise<never> {
  return new Promise((_, reject) => {
    if (!signal || signal.aborted) {
      reject(abortError());
      return;
    }
    signal.addEventListener('abort', () => reject(abortError()), { once: true });
  });
}

beforeEach(() => {
  mockFetchChatStream.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useStreamingChat', () => {
  it('accumulates tokens and sources, then reports a successful finish', async () => {
    const onFinish = vi.fn();
    mockFetchChatStream.mockReturnValueOnce(
      streamOf(
        { type: 'token', data: 'hello' },
        { type: 'token', data: ' world' },
        { type: 'sources', data: [source] },
        { type: 'done' },
      ),
    );

    const { result } = renderHook(() => useStreamingChat({ onFinish }));

    act(() => result.current.startStream(request));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.tokens).toBe('hello world');
    expect(result.current.sources).toEqual([source]);
    expect(result.current.error).toBeNull();
    expect(onFinish).toHaveBeenCalledExactlyOnceWith('hello world', [source], false);
  });

  it('aborts the active stream and reports the accumulated response as partial', async () => {
    const onFinish = vi.fn();
    let streamSignal: AbortSignal | undefined;
    mockFetchChatStream.mockImplementationOnce(async function* (_payload, signal) {
      streamSignal = signal;
      yield { type: 'token', data: 'partial answer' };
      await waitForAbort(signal);
    });

    const { result } = renderHook(() => useStreamingChat({ onFinish }));
    act(() => result.current.startStream(request));
    await waitFor(() => expect(result.current.tokens).toBe('partial answer'));

    act(() => result.current.cancelStream());

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(streamSignal?.aborted).toBe(true);
    expect(result.current.tokens).toBe('partial answer...');
    expect(result.current.error).toBeNull();
    expect(onFinish).toHaveBeenCalledExactlyOnceWith('partial answer...', [], true);
  });

  it('aborts the replaced stream and ignores its late results', async () => {
    let firstSignal: AbortSignal | undefined;
    const onFinish = vi.fn();
    mockFetchChatStream
      .mockImplementationOnce(async function* (_payload, signal) {
        firstSignal = signal;
        yield { type: 'token', data: 'old' };
        await waitForAbort(signal);
        yield { type: 'token', data: ' stale' };
      })
      .mockReturnValueOnce(
        streamOf({ type: 'token', data: 'new' }, { type: 'done' }),
      );

    const { result } = renderHook(() => useStreamingChat({ onFinish }));
    act(() => result.current.startStream(request));
    await waitFor(() => expect(result.current.tokens).toBe('old'));

    act(() => result.current.startStream({ ...request, query: 'replacement' }));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(firstSignal?.aborted).toBe(true);
    expect(result.current.tokens).toBe('new');
    expect(onFinish).toHaveBeenCalledExactlyOnceWith('new', [], false);
  });

  it('retains completed output when cancel is called after the stream ends', async () => {
    const onFinish = vi.fn();
    mockFetchChatStream.mockReturnValueOnce(
      streamOf(
        { type: 'token', data: 'complete' },
        { type: 'sources', data: [source] },
        { type: 'done' },
      ),
    );

    const { result, rerender } = renderHook(
      ({ finish }) => useStreamingChat({ onFinish: finish }),
      { initialProps: { finish: onFinish } },
    );
    const startStream = result.current.startStream;
    const cancelStream = result.current.cancelStream;

    act(() => result.current.startStream(request));
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    rerender({ finish: vi.fn() });

    expect(result.current.startStream).toBe(startStream);
    expect(result.current.cancelStream).toBe(cancelStream);
    act(() => result.current.cancelStream());
    expect(result.current.tokens).toBe('complete');
    expect(result.current.sources).toEqual([source]);
  });

  it('converts stream I/O failures into a user-facing error and invokes onError', async () => {
    const onError = vi.fn();
    const ioError = Object.assign(new Error('stream transport failed'), {
      name: 'OSError',
    });
    mockFetchChatStream.mockImplementationOnce(async function* () {
      throw ioError;
    });

    const { result } = renderHook(() => useStreamingChat({ onError }));
    act(() => result.current.startStream(request));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.error).toEqual({
      errorCode: 'STREAM_ERROR',
      message: 'stream transport failed',
    });
    expect(onError).toHaveBeenCalledExactlyOnceWith(result.current.error, ioError);
  });

  it('stores an error chunk and aborts without treating it as a transport failure', async () => {
    const onError = vi.fn();
    let streamSignal: AbortSignal | undefined;
    mockFetchChatStream.mockImplementationOnce(async function* (_payload, signal) {
      streamSignal = signal;
      yield {
        type: 'error',
        error_code: 'BACKEND_ERROR',
        message: 'The stream could not be completed.',
      };
    });

    const { result } = renderHook(() => useStreamingChat({ onError }));
    act(() => result.current.startStream(request));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(streamSignal?.aborted).toBe(true);
    expect(result.current.error).toEqual({
      errorCode: 'BACKEND_ERROR',
      message: 'The stream could not be completed.',
    });
    expect(onError).not.toHaveBeenCalled();
  });

  it('sets stream error state even when the onError callback throws', async () => {
    const onError = vi.fn(() => {
      throw new Error('reporter failed');
    });
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    mockFetchChatStream.mockImplementationOnce(async function* () {
      throw new Error('stream failed');
    });

    const { result } = renderHook(() => useStreamingChat({ onError }));
    act(() => result.current.startStream(request));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.error?.errorCode).toBe('STREAM_ERROR');
    expect(onError).toHaveBeenCalledOnce();
    expect(consoleError).toHaveBeenCalledOnce();
  });

  it('aborts the active request on unmount', async () => {
    let streamSignal: AbortSignal | undefined;
    mockFetchChatStream.mockImplementationOnce(async function* (_payload, signal) {
      streamSignal = signal;
      await waitForAbort(signal);
    });

    const { result, unmount } = renderHook(() => useStreamingChat());
    act(() => result.current.startStream(request));
    await waitFor(() => expect(streamSignal).toBeDefined());

    unmount();

    expect(streamSignal?.aborted).toBe(true);
  });
});
