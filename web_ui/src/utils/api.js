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
 * 상태 값을 CSS 클래스명으로 정규화
 * 
 * @param {string} status - 원본 상태 값
 * @param {Object} statusMap - 상태 매핑 객체
 * @returns {string} 정규화된 CSS 클래스명
 */
export const normalizeStatus = (status, statusMap = {}) => {
  if (!status) return 'unknown';
  
  const normalized = status.toLowerCase().trim();
  return statusMap[normalized] || normalized;
};

/**
 * 공통 상태 매핑
 */
export const STATUS_MAP = {
  // Sync status
  'connected': 'connected',
  'disconnected': 'disconnected',
  
  // MCP status
  'running': 'running',
  'stopped': 'stopped',
  
  // Task status
  'success': 'success',
  'running': 'running',
  'failed': 'failed',
  'pending': 'pending',
  
  // Event status
  'completed': 'completed',
  'pending': 'pending',
  'failed': 'failed',
  
  // Conflict status
  'resolved': 'resolved',
  'pending': 'pending',
};

/**
 * Fetch with error handling
 * 
 * @param {string} url - API endpoint URL
 * @param {Object} options - fetch options
 * @returns {Promise<Object>} Response data
 * @throws {Error} Fetch error
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
