// web_ui/src/hooks/__tests__/useWebSocket.test.ts

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
  onclose: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }

  send(_data: string) {
    void _data;
    // no-op
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
    this.onclose?.();
  }
}

describe('useWebSocket Hook', () => {
  const TEST_URL = 'ws://localhost:8000/ws';

  beforeEach(() => {
    MockWebSocket.instances = [];
    
    // Stub global WebSocket
    vi.stubGlobal('WebSocket', MockWebSocket);
    
    // Ensure window.WebSocket is also mocked for jsdom environment
    Object.defineProperty(window, 'WebSocket', {
      writable: true,
      value: MockWebSocket,
    });

    vi.useRealTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

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

    // Simulate malformed JSON
    act(() => {
      ws.onmessage?.({ data: '{ invalid json }' });
    });

    // We only check if it didn't crash and logged error
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('Failed to parse message'), expect.any(SyntaxError));
    expect(result.current.lastMessage).toBeNull();
    
    consoleSpy.mockRestore();
  });

  it('should attempt to reconnect when connection is closed', async () => {
    vi.useFakeTimers();
    
    const { result } = renderHook(() => 
      useWebSocket(TEST_URL, { reconnect: true })
    );

    // Initial connect
    await act(async () => {
        vi.advanceTimersByTime(10); 
    });
    
    expect(MockWebSocket.instances.length).toBe(1);
    const ws1 = MockWebSocket.instances[0];

    act(() => { ws1.simulateOpen(); });
    expect(result.current.isConnected).toBe(true);

    // Simulate server disconnection
    act(() => { ws1.simulateClose(); });
    expect(result.current.isConnected).toBe(false);
    
    // Fast-forward time to trigger reconnect
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    
    expect(MockWebSocket.instances.length).toBeGreaterThan(1);
    const ws2 = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    
    // Status should be CONNECTING as it is actively creating new connection
    expect(result.current.status).toBe(WebSocketStatus.CONNECTING);
    
    act(() => { ws2.simulateOpen(); });
    expect(result.current.isConnected).toBe(true);
    expect(result.current.status).toBe(WebSocketStatus.CONNECTED);
    
    vi.useRealTimers();
  });
});
