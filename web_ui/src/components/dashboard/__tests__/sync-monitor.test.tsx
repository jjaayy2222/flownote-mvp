// web_ui/src/components/dashboard/__tests__/sync-monitor.test.tsx

import { render, screen, waitFor, act, within } from '@testing-library/react';
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

// [Helper] Encapsulate DOM traversal for cleaner tests
// Changed name to accurately reflect usage of getByText
const getContainerByText = (
  text: string | RegExp, 
  selector: string = 'div'
): HTMLElement => {
  const element = screen.getByText(text);
  const container = element.closest(selector);
  
  if (!container) {
    throw new Error(
      `[Test Helper] Could not find parent container matching "${selector}" for element with text: "${text}"`
    );
  }
  
  return container as HTMLElement;
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
  active_clients: ['obsidian-client'], 
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

    // Dynamic Mock Implementation with Type Safety Check
    vi.mocked(apiLib.fetchAPI).mockImplementation(async (url) => {
        // Guard against invalid usage in tests
        if (typeof url !== 'string') {
            throw new Error(`[fetchAPI Mock] Invalid URL argument: ${JSON.stringify(url)}`);
        }
        
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

    // getByText implies assertion (throws if not found)
    screen.getByText(/loading sync status/i);

    await act(async () => {
        rejectApi(new Error('Test Cleanup'));
    });
  });

  it('renders dashboard with fetched data including details', async () => {
    render(<SyncMonitor />);

    await waitFor(() => {
        expect(screen.queryByText(/loading sync status/i)).toBeNull();
    });

    // 1. High-level sections
    screen.getByText('Sync Monitor');
    
    // 2. Validate Obsidian Connection Card Details
    const vaultPathContainer = getContainerByText('Vault Path');
    within(vaultPathContainer).getByText('/tmp/vault');

    const fileCountContainer = getContainerByText('Total Files');
    within(fileCountContainer).getByText('100');

    // 3. MCP Status Details
    const mcpCard = getContainerByText('MCP Server', 'div[class*="bg-card"]'); 
    within(mcpCard).getByText('Running');
    within(mcpCard).getByText('obsidian-client');
  });

  it('renders conflicts correctly when they exist', async () => {
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

    // Validates that specific conflict details are present
    screen.getByText('notes/important.md');
    screen.getByText(/unresolved/i);
    screen.getByText(/content_mismatch/);
  });

  it('shows "Live" badge when WebSocket is connected', async () => {
    render(<SyncMonitor />);

    await waitFor(() => {
        expect(screen.queryByText(/loading sync status/i)).toBeNull();
    });

    screen.getByText('Live');
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

    screen.getByText('Connecting...');
  });

  it('updates UI when "sync_status_changed" event is received', async () => {
    const { rerender } = render(<SyncMonitor />);

    await waitFor(() => {
        expect(screen.queryByText(/loading sync status/i)).toBeNull();
    });
    
    // Initial verification
    const fileCountContainer = getContainerByText('Total Files');
    within(fileCountContainer).getByText('100');

    // Prepare Update
    mockSyncStatus = { ...MOCK_SYNC_STATUS, file_count: 999 };
    
    const eventMessage = {
        type: 'sync_status_changed',
        data: mockSyncStatus 
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
        // Verify UI Update specifically in the Total Files section
        const updatedContainer = getContainerByText('Total Files');
        within(updatedContainer).getByText('999');
    });
  });
});
