// web_ui/src/lib/__tests__/api.test.ts

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  API_BASE,
  STATUS_MAP,
  getStatusClassName,
  fetchAPI,
  validateResponse,
} from '../api';
import { CONFLICT_STATUS } from '@/types/sync';

describe('api.ts - API_BASE & STATUS_MAP', () => {
  it('API_BASE should be a defined string', () => {
    expect(typeof API_BASE).toBe('string');
    expect(API_BASE.length).toBeGreaterThan(0);
  });

  it('STATUS_MAP should contain all expected status mappings', () => {
    expect(STATUS_MAP.connected).toBe('connected');
    expect(STATUS_MAP.disconnected).toBe('disconnected');
    expect(STATUS_MAP.running).toBe('running');
    expect(STATUS_MAP.stopped).toBe('stopped');
    expect(STATUS_MAP.success).toBe('success');
    expect(STATUS_MAP.failed).toBe('failed');
    expect(STATUS_MAP.pending).toBe(CONFLICT_STATUS.PENDING);
    expect(STATUS_MAP.completed).toBe('completed');
    expect(STATUS_MAP.resolved).toBe(CONFLICT_STATUS.RESOLVED);
    expect(STATUS_MAP.unknown).toBe('unknown');
  });
});

describe('api.ts - getStatusClassName', () => {
  it('should return correct class name for known valid statuses', () => {
    expect(getStatusClassName('running')).toBe('status-running');
    expect(getStatusClassName('connected')).toBe('status-connected');
    expect(getStatusClassName('disconnected')).toBe('status-disconnected');
    expect(getStatusClassName('stopped')).toBe('status-stopped');
    expect(getStatusClassName('success')).toBe('status-success');
    expect(getStatusClassName('failed')).toBe('status-failed');
    expect(getStatusClassName('pending')).toBe(`status-${CONFLICT_STATUS.PENDING}`);
    expect(getStatusClassName('completed')).toBe('status-completed');
    expect(getStatusClassName('resolved')).toBe(`status-${CONFLICT_STATUS.RESOLVED}`);
  });

  it('should normalize case and trim whitespace', () => {
    expect(getStatusClassName('  RUNNING  ')).toBe('status-running');
    expect(getStatusClassName('Connected')).toBe('status-connected');
    expect(getStatusClassName('  FAILED\n')).toBe('status-failed');
  });

  it('should fallback to status-unknown for unknown or empty statuses', () => {
    expect(getStatusClassName('unexpected_status')).toBe('status-unknown');
    expect(getStatusClassName('')).toBe('status-unknown');
    expect(getStatusClassName('   ')).toBe('status-unknown');
    expect(getStatusClassName(null)).toBe('status-unknown');
    expect(getStatusClassName(undefined)).toBe('status-unknown');
  });

  it('should handle non-string primitive and object values safely', () => {
    expect(getStatusClassName(123)).toBe('status-unknown');
    expect(getStatusClassName({})).toBe('status-unknown');
    expect(getStatusClassName(false)).toBe('status-unknown');
  });
});

describe('api.ts - fetchAPI', () => {
  const originalFetch = globalThis.fetch;
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('should fetch and return JSON data successfully', async () => {
    const mockData = { id: 1, name: 'FlowNote Test' };
    const mockResponse = {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: vi.fn().mockResolvedValue(mockData),
    } as unknown as Response;

    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    const result = await fetchAPI<typeof mockData>('http://localhost:8000/api/test');

    expect(globalThis.fetch).toHaveBeenCalledWith('http://localhost:8000/api/test', {});
    expect(result).toEqual(mockData);
    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });

  it('should forward request options to fetch', async () => {
    const mockResponse = {
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ status: 'ok' }),
    } as unknown as Response;

    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    const options: RequestInit = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'ping' }),
    };

    await fetchAPI('http://localhost:8000/api/test', options);

    expect(globalThis.fetch).toHaveBeenCalledWith('http://localhost:8000/api/test', options);
  });

  it('should throw an error and log to console when response is not ok', async () => {
    const mockResponse = {
      ok: false,
      status: 404,
      statusText: 'Not Found',
    } as unknown as Response;

    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    await expect(fetchAPI('http://localhost:8000/api/missing')).rejects.toThrow(
      'HTTP 404: Not Found'
    );

    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'API Error [http://localhost:8000/api/missing]:',
      expect.any(Error)
    );
  });

  it('should propagate network errors and log to console', async () => {
    const networkError = new Error('Network failure');
    globalThis.fetch = vi.fn().mockRejectedValue(networkError);

    await expect(fetchAPI('http://localhost:8000/api/network-error')).rejects.toThrow(
      'Network failure'
    );

    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'API Error [http://localhost:8000/api/network-error]:',
      networkError
    );
  });

  it('should propagate JSON parsing errors when response body is malformed', async () => {
    const jsonError = new SyntaxError('Unexpected token < in JSON at position 0');
    const mockResponse = {
      ok: true,
      status: 200,
      json: vi.fn().mockRejectedValue(jsonError),
    } as unknown as Response;

    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse);

    await expect(fetchAPI('http://localhost:8000/api/bad-json')).rejects.toThrow(
      jsonError
    );

    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'API Error [http://localhost:8000/api/bad-json]:',
      jsonError
    );
  });
});

describe('api.ts - validateResponse', () => {
  interface User {
    id: number;
    name: string;
  }

  const isUser = (data: unknown): data is User => {
    if (typeof data !== 'object' || data === null) return false;
    const obj = data as Record<string, unknown>;
    return typeof obj.id === 'number' && typeof obj.name === 'string';
  };

  it('should return validated data when validator returns true', () => {
    const validData = { id: 42, name: 'FlowNote' };
    const result = validateResponse<User>(validData, isUser);

    expect(result).toEqual(validData);
  });

  it('should throw default error message when validation fails', () => {
    const invalidData = { id: 'not-a-number', name: 123 };

    expect(() => validateResponse(invalidData, isUser)).toThrow('Invalid response');
  });

  it('should throw custom error message when validation fails', () => {
    const invalidData = null;

    expect(() =>
      validateResponse(invalidData, isUser, 'Custom user validation failed')
    ).toThrow('Custom user validation failed');
  });
});
