// frontend/components/ParaClassifier.jsx

import React, { useState } from 'react';
import './ParaClassifier.css';

export default function ParaClassifier() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
  };

  const handleClassify = async () => {
    if (!file) {
      alert('파일을 선택해주세요');
      return;
    }

    setLoading(true);
    
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://localhost:8000/api/classify', {
        method: 'POST',
        body: formData,
      });
      
      const data = await response.json();
      setResult(data);
    } catch (error) {
      console.error('분류 오류:', error);
      alert('분류 중 오류가 발생했습니다');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="para-classifier">
      <h2>📋 PARA 분류기</h2>
      
      <div className="input-group">
        <input 
          type="file" 
          onChange={handleFileChange}
          accept=".txt,.md,.pdf"
        />
        <span className="file-name">
          {file ? file.name : '파일을 선택하세요'}
        </span>
      </div>
      
      <button 
        onClick={handleClassify}
        disabled={loading}
        className={`classify-btn ${loading ? 'loading' : ''}`}
      >
        {loading ? '분류 중...' : '분류하기'}
      </button>

      {result && (
        <div className="result">
          <div className="result-header">
            <h3>분류 결과</h3>
          </div>
          
          <div className="result-content">
            <div className="category">
              <span className="label">카테고리:</span>
              <span className="value">{result.category}</span>
            </div>
            
            <div className="confidence">
              <span className="label">신뢰도:</span>
              <div className="progress-bar">
                <div 
                  className="progress-fill"
                  style={{ width: `${result.confidence * 100}%` }}
                ></div>
              </div>
              <span className="value">{(result.confidence * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}