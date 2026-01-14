// web_ui/src/components/dashboard/__tests__/sync-monitor.test.tsx

import { render, screen, waitFor, act } from '@testing-library/react';
import { SyncMonitor } from '../sync-monitor';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as useWebSocketHook from '@/hooks/useWebSocket';
import * as apiLib from '@/lib/api';
import { WebSocketStatus } from '@/types/websocket';

// --- Mocks Setup ---

// 1. Mock useWebSocket
vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(),
}));

// 2. Mock API
vi.mock('@/lib/api', () => ({
  API_BASE: 'http://localhost:8000',
  fetchAPI: vi.fn(),
}));

// 3. Mock Toast
vi.mock('sonner', () => ({
  toast: {
    warning: vi.fn(),
    success: vi.fn(),
  },
}));

// 4. Mock ResizeObserver
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Local Interface for Test (matching sync-monitor.tsx)
interface Conflict {
  conflict_id: string;
  file_path: string;
  conflict_type: string;
  status: string;
  timestamp: string;
  resolution_method?: string;
  notes?: string;
  local_hash: string;
  remote_hash: string;
}

// Default Mock Data
const MOCK_SYNC_STATUS = {
  connected: true,
  vault_path: '/tmp/vault',
  last_sync: new Date().toISOString(),
  file_count: 100,
  sync_interval: 300,
  enabled: true,
};

const MOCK_MCP_STATUS = {
  running: true,
  active_clients: ['obsidian'],
  tools_registered: ['read_file'],
  resources_registered: ['notes'],
};

const MOCK_CONFLICTS: Conflict[] = [];

describe('SyncMonitor Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(apiLib.fetchAPI).mockImplementation(async (url) => {
        if (url.includes('/status') && !url.includes('/mcp')) return MOCK_SYNC_STATUS;
        if (url.includes('/mcp')) return MOCK_MCP_STATUS;
        if (url.includes('/conflicts')) return MOCK_CONFLICTS;
        return {};
    });

    vi.mocked(useWebSocketHook.useWebSocket).mockReturnValue({
      isConnected: true,
      lastMessage: null,
      status: WebSocketStatus.CONNECTED,
      sendMessage: vi.fn(),
      connect: vi.fn(),
      disconnect: vi.fn(),
      reconnectCount: 0,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading state initially', async () => {
    let rejectApi: (reason: Error) => void = () => {};
    // any 사용을 피하기 위해 unknown as ... 패턴 사용하거나 Promise 생성자 타입 활용
    const pendingPromise = new Promise<unknown>((_, reject) => { rejectApi = reject; });
    
    // fetchAPI는 Promise를 반환하므로 타입 호환성 확보
    vi.mocked(apiLib.fetchAPI).mockReturnValue(pendingPromise as Promise<never>);

    render(<SyncMonitor />);

    // Check for loading text using standard matchers (without jest-dom)
    expect(screen.getByText(/loading sync status/i)).toBeTruthy();

    // Cleanup: Reject promise to finish fetchData execution flow
    await act(async () => {
        rejectApi(new Error('Test Cleanup'));
    });
  });

  it('renders dashboard with fetched data', async () => {
    render(<SyncMonitor />);

    await waitFor(() => {
        // queryByText returns null if not found
        expect(screen.queryByText(/loading sync status/i)).toBeNull();
    });

    // Check for presence
    expect(screen.getByText('Sync Monitor')).toBeTruthy();
    expect(screen.getByText('Obsidian Connection')).toBeTruthy();
    expect(screen.getByText('/tmp/vault')).toBeTruthy();
  });

  it('shows "Live" badge when WebSocket is connected', async () => {
    render(<SyncMonitor />);

    await waitFor(() => {
        expect(screen.queryByText(/loading sync status/i)).toBeNull();
    });

    expect(screen.getByText('Live')).toBeTruthy();
  });

  it('shows "Connecting..." badge when WebSocket is disconnected', async () => {
    vi.mocked(useWebSocketHook.useWebSocket).mockReturnValue({
        isConnected: false,
        lastMessage: null,
        status: WebSocketStatus.CONNECTING,
        sendMessage: vi.fn(),
        connect: vi.fn(),
        disconnect: vi.fn(),
        reconnectCount: 0,
    });

    render(<SyncMonitor />);
    
    await waitFor(() => {
        expect(screen.queryByText(/loading sync status/i)).toBeNull();
    });

    expect(screen.getByText('Connecting...')).toBeTruthy();
  });

  it('refetches data when "sync_status_changed" event is received', async () => {
    const { rerender } = render(<SyncMonitor />);

    await waitFor(() => {
        expect(screen.queryByText(/loading sync status/i)).toBeNull();
    });

    const initialCallCount = vi.mocked(apiLib.fetchAPI).mock.calls.length;
    expect(initialCallCount).toBeGreaterThanOrEqual(3);

    const eventMessage = {
        type: 'sync_status_changed',
        data: { ...MOCK_SYNC_STATUS, file_count: 999 }
    };

    vi.mocked(useWebSocketHook.useWebSocket).mockReturnValue({
        isConnected: true,
        lastMessage: eventMessage,
        status: WebSocketStatus.CONNECTED,
        sendMessage: vi.fn(),
        connect: vi.fn(),
        disconnect: vi.fn(),
        reconnectCount: 0,
    });

    rerender(<SyncMonitor />);

    await waitFor(() => {
        expect(vi.mocked(apiLib.fetchAPI).mock.calls.length).toBeGreaterThan(initialCallCount);
    });
  });
});
