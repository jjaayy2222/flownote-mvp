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

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
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

  it('ignores a late result from a replaced concurrent stream', async () => {
    let firstSignal: AbortSignal | undefined;
    const releaseFirstStream = deferred<void>();
    const firstStreamSettled = deferred<void>();
    const releaseReplacementStream = deferred<void>();
    const onFinish = vi.fn();
    mockFetchChatStream
      .mockImplementationOnce(async function* (_payload, signal) {
        firstSignal = signal;
        try {
          yield { type: 'token', data: 'old' };
          // Simulate a transport that delivers a buffered chunk after abort.
          await releaseFirstStream.promise;
          yield { type: 'token', data: ' stale' };
        } finally {
          firstStreamSettled.resolve();
        }
      })
      .mockImplementationOnce(async function* () {
        yield { type: 'token', data: 'new' };
        await releaseReplacementStream.promise;
        yield { type: 'done' };
      });

    const { result } = renderHook(() => useStreamingChat({ onFinish }));
    act(() => result.current.startStream(request));
    await waitFor(() => expect(result.current.tokens).toBe('old'));

    act(() => result.current.startStream({ ...request, query: 'replacement' }));

    expect(firstSignal?.aborted).toBe(true);
    await waitFor(() => expect(result.current.tokens).toBe('new'));
    expect(result.current.isStreaming).toBe(true);
    expect(onFinish).not.toHaveBeenCalled();

    // Resolve the replaced stream while its replacement is still active.
    // The stale stream must not clear the replacement's loading state.
    await act(async () => {
      releaseFirstStream.resolve();
      await firstStreamSettled.promise;
    });

    expect(result.current.isStreaming).toBe(true);
    expect(result.current.tokens).toBe('new');
    expect(result.current.error).toBeNull();
    expect(onFinish).not.toHaveBeenCalled();

    await act(async () => {
      releaseReplacementStream.resolve();
    });

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.tokens).toBe('new');
    expect(result.current.error).toBeNull();
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

  it('normalizes a network timeout and always clears the active stream state', async () => {
    const onError = vi.fn();
    const timeoutError = new DOMException('The operation timed out', 'TimeoutError');
    mockFetchChatStream.mockImplementationOnce(async function* () {
      yield { type: 'token', data: 'partial response' };
      throw timeoutError;
    });

    const { result } = renderHook(() => useStreamingChat({ onError }));
    act(() => result.current.startStream(request));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    expect(result.current.tokens).toBe('partial response');
    expect(result.current.error?.errorCode).toBe('STREAM_ERROR');
    expect(result.current.error?.message).toBeTruthy();
    expect(result.current.error?.message).not.toBe(timeoutError.message);
    expect(onError).toHaveBeenCalledExactlyOnceWith(result.current.error, timeoutError);
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

  it('ignores a transport error that races with unmount cleanup', async () => {
    let streamSignal: AbortSignal | undefined;
    const streamSettled = deferred<void>();
    const onError = vi.fn();
    const onFinish = vi.fn();
    const lateTransportError = new Error('stream failed while unmounting');
    mockFetchChatStream.mockImplementationOnce(async function* (_payload, signal) {
      streamSignal = signal;
      try {
        yield { type: 'token', data: 'partial response' };
        await waitForAbort(signal);
      } catch {
        // Simulate a transport error racing with abort during component cleanup.
        throw lateTransportError;
      } finally {
        streamSettled.resolve();
      }
    });

    const { result, unmount } = renderHook(() =>
      useStreamingChat({ onError, onFinish }),
    );
    act(() => result.current.startStream(request));
    await waitFor(() => expect(result.current.tokens).toBe('partial response'));

    unmount();
    await streamSettled.promise;
    // Flush the consumer's rejection handler after the async generator settles.
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(streamSignal?.aborted).toBe(true);
    expect(onError).not.toHaveBeenCalled();
    expect(onFinish).not.toHaveBeenCalled();
  });
});
