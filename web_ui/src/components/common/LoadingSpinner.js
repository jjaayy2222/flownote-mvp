// web_ui/src/components/common/LoadingSpinner.js

import React from 'react';
import './LoadingSpinner.css';

/**
 * 공통 로딩 스피너 컴포넌트
 * 
 * @param {Object} props
 * @param {string} props.message - 로딩 메시지
 * @param {string} props.color - 스피너 색상 (기본: #3498db)
 */
const LoadingSpinner = ({ message = 'Loading...', color = '#3498db' }) => {
  return (
    <div className="common-loading">
      <div 
        className="common-spinner" 
        style={{ borderTopColor: color }}
      ></div>
      <p className="loading-message">{message}</p>
    </div>
  );
};

export default LoadingSpinner;
