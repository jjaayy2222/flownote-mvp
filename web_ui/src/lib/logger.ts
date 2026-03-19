// web_ui/src/lib/logger.ts

/**
 * Application Logger Utility
 * 
 * Provides centralized logging with environment-based filtering.
 * Debug and Info logs are suppressed in production environment.
 */

const isProduction = process.env.NODE_ENV === 'production';

export const logger = {
  log: (...args: unknown[]) => {
    if (!isProduction) {
      console.log(...args);
    }
  },
  debug: (...args: unknown[]) => {
    if (!isProduction) {
      console.debug(...args);
    }
  },
  info: (...args: unknown[]) => {
    if (!isProduction) {
      console.info(...args);
    }
  },
  warn: (...args: unknown[]) => {
    // Warnings are typically useful in production too
    console.warn(...args);
  },
  error: (...args: unknown[]) => {
    // Errors should always be visible
    console.error(...args);
  },
};
