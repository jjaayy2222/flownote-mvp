// web_ui/src/components/GeneralDashboard.js

import React, { useState, useEffect } from 'react';
import './GeneralDashboard.css';

const GeneralDashboard = () => {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const API_BASE = 'http://localhost:8000';

  // Fetch dashboard summary
  const fetchSummary = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/automation/dashboard/summary`);
      if (!response.ok) throw new Error('Failed to fetch dashboard summary');
      const data = await response.json();
      setSummary(data);
    } catch (err) {
      console.error('Dashboard summary error:', err);
      setError(err.message);
    }
  };

  // Initial load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await fetchSummary();
      setLoading(false);
    };

    loadData();

    // Poll every 30 seconds
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="general-dashboard loading">
        <div className="spinner"></div>
        <p>Loading dashboard...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="general-dashboard error">
        <h2>⚠️ Error</h2>
        <p>{error}</p>
        <button onClick={() => window.location.reload()}>Retry</button>
      </div>
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
            <span className={`value status-${summary?.sync_status?.toLowerCase()}`}>
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
