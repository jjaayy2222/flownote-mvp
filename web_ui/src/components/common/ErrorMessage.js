// web_ui/src/components/common/ErrorMessage.js

import React from 'react';
import './ErrorMessage.css';

/**
 * 공통 에러 메시지 컴포넌트
 * 
 * @param {Object} props
 * @param {string} props.message - 에러 메시지
 * @param {Function} props.onRetry - 재시도 콜백 함수
 * @param {string} props.buttonColor - 버튼 색상 (기본: #3498db)
 * @param {string} props.minHeight - 최소 높이 (기본: 400px)
 */
const ErrorMessage = ({ 
  message, 
  onRetry,
  buttonColor = '#3498db',
  minHeight = '400px'
}) => {
  return (
    <div className="common-error" style={{ minHeight }}>
      <h2 className="error-title">⚠️ Error</h2>
      <p className="error-message">{message}</p>
      {onRetry && (
        <button 
          className="error-retry-btn" 
          onClick={onRetry}
          style={{ 
            backgroundColor: buttonColor,
            borderColor: buttonColor
          }}
        >
          Retry
        </button>
      )}
    </div>
  );
};

export default ErrorMessage;
