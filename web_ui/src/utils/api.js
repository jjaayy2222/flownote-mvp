// web_ui/src/utils/api.js

/**
 * API Configuration
 * 
 * 환경 변수를 통해 API Base URL을 관리합니다.
 * - Development: REACT_APP_API_BASE 환경 변수 사용
 * - Production: 환경 변수 또는 기본값 사용
 * 
 * @example
 * // .env.local 파일에 추가:
 * REACT_APP_API_BASE=http://localhost:8000
 */

export const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:8000';

/**
 * 공통 상태 매핑
 * 
 * 모든 상태 값을 정규화된 CSS 클래스명으로 매핑합니다.
 * 중복 제거: 동일한 키-값 쌍은 한 번만 정의
 */
export const STATUS_MAP = {
  // Connection status
  connected: 'connected',
  disconnected: 'disconnected',
  
  // Server/Task status
  running: 'running',
  stopped: 'stopped',
  success: 'success',
  failed: 'failed',
  pending: 'pending',
  completed: 'completed',
  resolved: 'resolved',
  
  // Fallback
  unknown: 'unknown',
};

/**
 * 상태 값을 CSS 클래스명으로 정규화
 * 
 * @param {any} status - 원본 상태 값 (문자열이 아니어도 문자열로 변환하여 처리)
 * @returns {string} 정규화된 CSS 클래스명
 * 
 * @example
 * normalizeStatus('Connected') // 'connected'
 * normalizeStatus('RUNNING')   // 'running'
 * normalizeStatus(null)        // 'unknown'
 * normalizeStatus(123)         // 'unknown' (숫자는 매핑되지 않음)
 */
export const normalizeStatus = (status) => {
  // null, undefined 체크
  if (status == null) return 'unknown';
  
  // 문자열로 변환 후 정규화
  const normalized = String(status).toLowerCase().trim();
  
  // STATUS_MAP에서 찾거나, 없으면 정규화된 값 그대로 반환
  return STATUS_MAP[normalized] || normalized;
};

/**
 * Fetch with error handling
 * 
 * @param {string} url - API endpoint URL (full URL)
 * @param {Object} options - fetch options
 * @returns {Promise<Object>} Response data
 * @throws {Error} Fetch error
 * 
 * @example
 * const data = await fetchAPI(`${API_BASE}/api/tasks`);
 */
export const fetchAPI = async (url, options = {}) => {
  try {
    const response = await fetch(url, options);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    return data;
  } catch (error) {
    console.error(`API Error [${url}]:`, error);
    throw error;
  }
};

/**
 * Response 데이터 검증 헬퍼
 * 
 * @param {any} data - 검증할 데이터
 * @param {Function} validator - 검증 함수
 * @param {string} errorMessage - 에러 메시지
 * @returns {any} 검증된 데이터
 * @throws {Error} 검증 실패 시
 * 
 * @example
 * const data = await fetchAPI(`${API_BASE}/api/tasks`);
 * validateResponse(data, (d) => Array.isArray(d.tasks), 'Invalid tasks response');
 */
export const validateResponse = (data, validator, errorMessage = 'Invalid response') => {
  if (!validator(data)) {
    throw new Error(errorMessage);
  }
  return data;
};
