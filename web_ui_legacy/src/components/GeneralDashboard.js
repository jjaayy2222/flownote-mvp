// web_ui/src/components/GeneralDashboard.js

import React, { useState, useEffect } from 'react';
import { API_BASE, fetchAPI, getStatusClassName } from '../utils/api';
import LoadingSpinner from './common/LoadingSpinner';
import ErrorMessage from './common/ErrorMessage';
import './GeneralDashboard.css';

const GeneralDashboard = () => {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch dashboard summary
  const fetchSummary = async () => {
    const data = await fetchAPI(`${API_BASE}/api/automation/dashboard/summary`);
    setSummary(data);
  };

  // Initial load and polling
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null); // Clear previous errors
      
      try {
        await fetchSummary();
        setError(null); // Explicitly clear error on success
      } catch (err) {
        console.error('General dashboard error:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    loadData();

    // Poll every 30 seconds
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return <LoadingSpinner message="Loading dashboard..." color="#e67e22" />;
  }

  if (error) {
    return (
      <ErrorMessage 
        message={error} 
        onRetry={() => window.location.reload()} 
        buttonColor="#e67e22"
      />
    );
  }

  return (
    <div className="general-dashboard">
      <h1>📊 General Dashboard</h1>

      {/* Summary Cards */}
      <div className="summary-cards">
        <div className="summary-card">
          <div className="card-icon">📁</div>
          <div className="card-content">
            <h3>Total Files</h3>
            <p className="card-value">{summary?.total_files || 0}</p>
          </div>
        </div>

        <div className="summary-card">
          <div className="card-icon">🏷️</div>
          <div className="card-content">
            <h3>Classifications</h3>
            <p className="card-value">{summary?.total_classifications || 0}</p>
          </div>
        </div>

        <div className="summary-card">
          <div className="card-icon">⚠️</div>
          <div className="card-content">
            <h3>Conflicts</h3>
            <p className="card-value">{summary?.total_conflicts || 0}</p>
          </div>
        </div>

        <div className="summary-card">
          <div className="card-icon">🤖</div>
          <div className="card-content">
            <h3>Tasks Today</h3>
            <p className="card-value">{summary?.automation_tasks_today || 0}</p>
          </div>
        </div>
      </div>

      {/* Sync Status */}
      <section className="status-section">
        <h2>🔄 Sync Status</h2>
        <div className="status-info">
          <div className="status-item">
            <span className="label">Status:</span>
            <span className={`value ${getStatusClassName(summary?.sync_status)}`}>
              {summary?.sync_status || 'Unknown'}
            </span>
          </div>
          <div className="status-item">
            <span className="label">Last Sync:</span>
            <span className="value">
              {summary?.last_sync 
                ? new Date(summary.last_sync).toLocaleString()
                : 'Never'}
            </span>
          </div>
        </div>
      </section>

      {/* Usage Chart Placeholder */}
      <section className="chart-section">
        <h2>📈 Usage Chart</h2>
        <div className="chart-placeholder">
          <p>Chart visualization coming soon...</p>
          <div className="chart-bars">
            <div className="bar" style={{height: '60%'}}></div>
            <div className="bar" style={{height: '80%'}}></div>
            <div className="bar" style={{height: '45%'}}></div>
            <div className="bar" style={{height: '90%'}}></div>
            <div className="bar" style={{height: '70%'}}></div>
            <div className="bar" style={{height: '55%'}}></div>
            <div className="bar" style={{height: '85%'}}></div>
          </div>
          <p className="chart-note">Daily classification activity (last 7 days)</p>
        </div>
      </section>
    </div>
  );
};

export default GeneralDashboard;
