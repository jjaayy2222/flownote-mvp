// web_ui/src/components/dashboard/__tests__/sync-monitor.test.tsx

import { render, screen, waitFor, act } from '@testing-library/react';
import { SyncMonitor } from '../sync-monitor';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as useWebSocketHook from '@/hooks/useWebSocket';
import * as apiLib from '@/lib/api';
import { WebSocketStatus } from '@/types/websocket';

// --- Mocks Setup ---

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  API_BASE: 'http://localhost:8000',
  fetchAPI: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    warning: vi.fn(),
    success: vi.fn(),
  },
}));

global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Local Interface (Test Only)
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
  active_clients: ['obsidian-client'], // Changed for specific testing
  tools_registered: ['read_file'],
  resources_registered: ['notes'],
};

// Mutable variables for test state
let mockConflicts: Conflict[] = [];
let mockSyncStatus = { ...MOCK_SYNC_STATUS };

describe('SyncMonitor Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Reset mutable mock data
    mockConflicts = [];
    mockSyncStatus = { ...MOCK_SYNC_STATUS };

    // Dynamic Mock Implementation
    vi.mocked(apiLib.fetchAPI).mockImplementation(async (url) => {
        if (typeof url !== 'string') return {};
        
        if (url.includes('/status') && !url.includes('/mcp')) return mockSyncStatus;
        if (url.includes('/mcp')) return MOCK_MCP_STATUS;
        if (url.includes('/conflicts')) return mockConflicts;
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
    const pendingPromise = new Promise<unknown>((_, reject) => { rejectApi = reject; });
    
    vi.mocked(apiLib.fetchAPI).mockReturnValue(pendingPromise as Promise<never>);

    render(<SyncMonitor />);

    expect(screen.getByText(/loading sync status/i)).toBeTruthy();

    await act(async () => {
        rejectApi(new Error('Test Cleanup'));
    });
  });

  // [Review Comment 2] Detailed Assertions
  it('renders dashboard with fetched data including details', async () => {
    render(<SyncMonitor />);

    await waitFor(() => {
        expect(screen.queryByText(/loading sync status/i)).toBeNull();
    });

    // 1. High-level sections
    expect(screen.getByText('Sync Monitor')).toBeTruthy();
    expect(screen.getByText('Obsidian Connection')).toBeTruthy();

    // 2. Sync Status Details
    expect(screen.getByText('/tmp/vault')).toBeTruthy(); // vault_path
    // Note: file_count might be rendered as just "100" or within a sentence. 
    // Assuming accurate text match or regex for "100"
    expect(screen.getByText('100')).toBeTruthy(); 

    // 3. MCP Status Details
    expect(screen.getByText('Running')).toBeTruthy(); // Badge
    expect(screen.getByText('obsidian-client')).toBeTruthy(); // Active Client
  });

  // [Review Comment 1] Conflict Rendering
  it('renders conflicts correctly when they exist', async () => {
    // Setup conflicts
    mockConflicts = [{
        conflict_id: 'conf1',
        file_path: 'notes/important.md',
        conflict_type: 'content_mismatch',
        status: 'unresolved',
        timestamp: new Date().toISOString(),
        local_hash: 'abc1234',
        remote_hash: 'def5678'
    }];

    render(<SyncMonitor />);

    await waitFor(() => {
        expect(screen.queryByText(/loading sync status/i)).toBeNull();
    });

    // Assert Conflict UI
    expect(screen.getByText('notes/important.md')).toBeTruthy();
    expect(screen.getByText('unresolved')).toBeTruthy();
    expect(screen.getByText(/content_mismatch/)).toBeTruthy(); // Verify type rendering
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

  // [Review Comment 3] UI-based Refetch Test
  it('updates UI when "sync_status_changed" event is received', async () => {
    const { rerender } = render(<SyncMonitor />);

    // 1. Initial State Check
    await waitFor(() => {
        expect(screen.queryByText(/loading sync status/i)).toBeNull();
    });
    expect(screen.getByText('100')).toBeTruthy(); // Initial file count

    // 2. Prepare for Update
    // Update the mock data source so next fetch returns new value
    mockSyncStatus = { ...MOCK_SYNC_STATUS, file_count: 999 };
    
    // Simulate WebSocket Event
    const eventMessage = {
        type: 'sync_status_changed',
        data: mockSyncStatus // The event itself usually carries the new data, or triggers a fetch
    };

    // Update WebSocket Mock to deliver the message
    vi.mocked(useWebSocketHook.useWebSocket).mockReturnValue({
        isConnected: true,
        lastMessage: eventMessage,
        status: WebSocketStatus.CONNECTED,
        sendMessage: vi.fn(),
        connect: vi.fn(),
        disconnect: vi.fn(),
        reconnectCount: 0,
    });

    // 3. Trigger Rerender (to consume useWebSocket new return value)
    rerender(<SyncMonitor />);

    // 4. Assert UI Update (Wait for fetchAPI and re-render)
    await waitFor(() => {
        // Should eventually display the new file count
        expect(screen.getByText('999')).toBeTruthy();
    });
  });
});
