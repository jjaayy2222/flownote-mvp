// web_ui/src/components/common/ErrorMessage.js

import React from 'react';
import './ErrorMessage.css';

/**
 * 공통 에러 메시지 컴포넌트
 * 
 * @param {Object} props
 * @param {string} props.message - 에러 메시지
 * @param {Function} props.onRetry - 재시도 콜백 함수
 */
const ErrorMessage = ({ message, onRetry }) => {
  return (
    <div className="common-error">
      <h2 className="error-title">⚠️ Error</h2>
      <p className="error-message">{message}</p>
      {onRetry && (
        <button className="error-retry-btn" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
};

export default ErrorMessage;
