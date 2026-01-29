// web_ui/src/utils/logger.ts

/**
 * 로거 생성 유틸리티
 * 
 * @param prefix - 로그 메시지 접두사
 * @returns 로거 객체
 */
export const createLogger = (prefix: string) => ({
  debug: (message: string, ...args: unknown[]) => {
    if (process.env.NODE_ENV === 'development') {
      console.log(`[${prefix}] ${message}`, ...args);
    }
  },
  warn: (message: string, ...args: unknown[]) => {
    console.warn(`[${prefix}] ${message}`, ...args);
  },
  error: (message: string, ...args: unknown[]) => {
    console.error(`[${prefix}] ${message}`, ...args);
  },
});
