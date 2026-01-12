import { renderHook, act, waitFor } from '@testing-library/react';
import { useWebSocket } from '../useWebSocket';
import { WebSocketStatus } from '@/types/websocket';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

// Mock WebSocket Class
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  static instances: MockWebSocket[] = [];
  url: string;
  readyState: number = 0; // CONNECTING
  onopen: (() => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close(code?: number, reason?: string) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ 
        code: code || 1000, 
        reason: reason || '', 
        wasClean: true, 
        bubbles: false,
        cancelBubble: false,
        cancelable: false,
        composed: false,
        currentTarget: null,
        defaultPrevented: false,
        eventPhase: 0,
        isTrusted: true,
        returnValue: true,
        srcElement: null,
        target: null,
        timeStamp: Date.now(),
        type: 'close',
        composedPath: () => [],
        initEvent: () => {},
        preventDefault: () => {},
        stopImmediatePropagation: () => {},
        stopPropagation: () => {},
        NONE: 0,
        CAPTURING_PHASE: 1,
        AT_TARGET: 2,
        BUBBLING_PHASE: 3
    } as unknown as CloseEvent);
  }

  send(_data: string) {
    void _data;
  }

  // Helpers to simulate server events
  simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  simulateError() {
    this.onerror?.(new Event('error'));
  }
  
  simulateClose() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code: 1000 } as CloseEvent);
  }
}

describe('useWebSocket Hook', () => {
  const TEST_URL = 'ws://localhost:8000/ws';

  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
    Object.defineProperty(window, 'WebSocket', {
      writable: true,
      value: MockWebSocket,
    });
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // 1. Connection & Status
  it('should connect to WebSocket and update status', async () => {
    const { result } = renderHook(() => useWebSocket(TEST_URL));
    
    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    }, { timeout: 1000 });

    const ws = MockWebSocket.instances[0];
    
    expect(result.current.status).toBe(WebSocketStatus.CONNECTING);
    expect(result.current.isConnected).toBe(false);

    act(() => {
      ws.simulateOpen();
    });

    expect(result.current.status).toBe(WebSocketStatus.CONNECTED);
    expect(result.current.isConnected).toBe(true);
  });

  // 2. Message Parsing
  it('should receive and parse messages', async () => {
    const { result } = renderHook(() => useWebSocket(TEST_URL));
    
    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });
    const ws = MockWebSocket.instances[0];
    
    act(() => {
      ws.simulateOpen();
    });

    const testMessage = { type: 'test', data: 'hello' };
    
    act(() => {
      ws.simulateMessage(testMessage);
    });

    expect(result.current.lastMessage).toEqual(testMessage);
  });

  // 3. Error Handling (JSON)
  it('should handle JSON parse errors gracefully', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { result } = renderHook(() => useWebSocket(TEST_URL));
    
    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });
    const ws = MockWebSocket.instances[0];

    act(() => {
      ws.simulateOpen();
    });

    act(() => {
      ws.onmessage?.({ data: '{ invalid json }' });
    });

    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('Failed to parse message'), expect.any(SyntaxError));
    expect(result.current.lastMessage).toBeNull();
    
    consoleSpy.mockRestore();
  });

  // 4. Auto-Reconnection
  it('should attempt to reconnect when connection is closed', async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useWebSocket(TEST_URL, { reconnect: true }));

    await act(async () => { vi.advanceTimersByTime(10); });
    
    expect(MockWebSocket.instances.length).toBe(1);
    const ws1 = MockWebSocket.instances[0];

    act(() => { ws1.simulateOpen(); });
    expect(result.current.isConnected).toBe(true);

    act(() => { ws1.simulateClose(); });
    expect(result.current.isConnected).toBe(false);
    
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    
    expect(MockWebSocket.instances.length).toBeGreaterThan(1);
    const ws2 = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    
    expect(result.current.status).toBe(WebSocketStatus.CONNECTING);
    
    act(() => { ws2.simulateOpen(); });
    expect(result.current.isConnected).toBe(true);
    
    vi.useRealTimers();
  });

  // 5. No Reconnect when disabled
  it('should not attempt to reconnect when reconnect option is disabled', async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useWebSocket(TEST_URL, { reconnect: false }));
    
    await act(async () => { vi.advanceTimersByTime(10); });
    
    const initialCount = MockWebSocket.instances.length;
    const ws = MockWebSocket.instances[0];
    
    act(() => { ws.simulateOpen(); });
    expect(result.current.isConnected).toBe(true);

    act(() => { ws.simulateClose(); });
    expect(result.current.isConnected).toBe(false);

    // Wait long time
    await act(async () => { vi.advanceTimersByTime(10000); });
    
    // Should NOT create new instance
    expect(MockWebSocket.instances.length).toBe(initialCount);
    expect(result.current.status).toBe(WebSocketStatus.DISCONNECTED);
    
    vi.useRealTimers();
  });

  // 6. Cleanup on Unmount
  it('should clean up WebSocket and timers on unmount', async () => {
    vi.useFakeTimers();
    const { unmount } = renderHook(() => useWebSocket(TEST_URL));
    
    await act(async () => { vi.advanceTimersByTime(10); });
    
    const ws = MockWebSocket.instances[0];
    const closeSpy = vi.spyOn(ws, 'close');
    
    unmount();
    
    expect(closeSpy).toHaveBeenCalled();
    
    // Ensure no reconnect attempt after unmount
    await act(async () => { vi.advanceTimersByTime(5000); });
    expect(MockWebSocket.instances.length).toBe(1);
    
    vi.useRealTimers();
  });

  // 7. Manual Disconnect
  it('should close connection when disconnect is called manually', async () => {
    const { result } = renderHook(() => useWebSocket(TEST_URL));
    
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    const ws = MockWebSocket.instances[0];
    const closeSpy = vi.spyOn(ws, 'close');
    
    act(() => {
      result.current.disconnect();
    });

    expect(closeSpy).toHaveBeenCalled();
    expect(result.current.status).toBe(WebSocketStatus.DISCONNECTED);
  });

  // 8. Connection Error Handling
  it('should handle connection errors', async () => {
    const { result } = renderHook(() => useWebSocket(TEST_URL));
    
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    const ws = MockWebSocket.instances[0];

    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    act(() => {
      ws.simulateError();
    });

    expect(result.current.status).toBe(WebSocketStatus.ERROR);
    
    consoleSpy.mockRestore();
  });
});
