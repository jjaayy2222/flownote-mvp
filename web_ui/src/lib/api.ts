// web_ui/src/lib/api.ts

/**
 * API Configuration
 * 
 * Next.js uses NEXT_PUBLIC_ prefix for client-side environment variables.
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

/**
 * 공통 상태 매핑
 */
export const STATUS_MAP: Record<string, string> = {
  connected: 'connected',
  disconnected: 'disconnected',
  running: 'running',
  stopped: 'stopped',
  success: 'success',
  failed: 'failed',
  pending: 'pending',
  completed: 'completed',
  resolved: 'resolved',
  unknown: 'unknown',
};

/**
 * 상태 값에 해당하는 CSS 클래스명 반환
 * 
 * @param status - 원본 상태 값
 * @returns CSS 클래스명 (예: 'status-running', 'status-unknown')
 */
export const getStatusClassName = (status: unknown): string => {
  if (status == null) return `status-${STATUS_MAP.unknown}`;
  
  const normalized = String(status).toLowerCase().trim();
  if (!normalized) return `status-${STATUS_MAP.unknown}`;
  
  const key = STATUS_MAP[normalized] || STATUS_MAP.unknown;
  return `status-${key}`;
};

/**
 * Fetch with error handling
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const fetchAPI = async <T = any>(url: string, options: RequestInit = {}): Promise<T> => {
  try {
    const response = await fetch(url, options);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error(`API Error [${url}]:`, error);
    throw error;
  }
};

/**
 * Response 데이터 검증 헬퍼
 */
export const validateResponse = <T>(
  data: unknown, 
  validator: (d: unknown) => boolean, 
  errorMessage: string = 'Invalid response'
): T => {
  if (!validator(data)) {
    throw new Error(errorMessage);
  }
  return data as T;
};
