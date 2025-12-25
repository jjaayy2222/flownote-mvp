// web_ui/src/components/AutomationDashboard.js

import React, { useState, useEffect } from 'react';
import { API_BASE, normalizeStatus, STATUS_MAP } from '../utils/api';
import LoadingSpinner from './common/LoadingSpinner';
import ErrorMessage from './common/ErrorMessage';
import './AutomationDashboard.css';

const AutomationDashboard = () => {
  const [automationLogs, setAutomationLogs] = useState([]);
  const [watchdogEvents, setWatchdogEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch automation logs
  const fetchAutomationLogs = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/automation/logs?limit=10`);
      if (!response.ok) throw new Error('Failed to fetch automation logs');
      const data = await response.json();
      
      // Validate response data
      if (!data || !Array.isArray(data.logs)) {
        throw new Error('Invalid response format');
      }
      
      setAutomationLogs(data.logs);
      return true;
    } catch (err) {
      console.error('Automation logs error:', err);
      throw err;
    }
  };

  // Fetch watchdog events
  const fetchWatchdogEvents = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/automation/watchdog/events?limit=10`);
      if (!response.ok) throw new Error('Failed to fetch watchdog events');
      const data = await response.json();
      
      // Validate response data
      if (!data || !Array.isArray(data.events)) {
        throw new Error('Invalid response format');
      }
      
      setWatchdogEvents(data.events);
      return true;
    } catch (err) {
      console.error('Watchdog events error:', err);
      throw err;
    }
  };

  // Initial load and polling
  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      setError(null); // Clear previous errors
      
      try {
        await Promise.all([
          fetchAutomationLogs(),
          fetchWatchdogEvents()
        ]);
        setError(null); // Explicitly clear error on success
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    loadAll();

    // Poll every 10 seconds
    const interval = setInterval(loadAll, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return <LoadingSpinner message="Loading automation data..." color="#9b59b6" />;
  }

  if (error) {
    return <ErrorMessage message={error} onRetry={() => window.location.reload()} />;
  }

  return (
    <div className="automation-dashboard">
      <h1>🤖 Automation Dashboard</h1>

      {/* Celery Task Status */}
      <section className="dashboard-card">
        <h2>📋 Celery Task Logs</h2>
        {automationLogs.length === 0 ? (
          <p className="empty-state">No automation tasks yet.</p>
        ) : (
          <div className="log-list">
            {automationLogs.map((log) => (
              <div key={log.log_id} className="log-item">
                <div className="log-header">
                  <span className="log-id">{log.log_id}</span>
                  <span className={`log-status status-${normalizeStatus(log.status, STATUS_MAP)}`}>
                    {log.status}
                  </span>
                </div>
                <div className="log-body">
                  <p><strong>Task:</strong> {log.task_type}</p>
                  <p><strong>Time:</strong> {new Date(log.start_time).toLocaleString()}</p>
                  {log.duration && (
                    <p><strong>Duration:</strong> {log.duration.toFixed(2)}s</p>
                  )}
                  {log.files_processed !== undefined && (
                    <p><strong>Files Processed:</strong> {log.files_processed}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Watchdog Event Logs */}
      <section className="dashboard-card">
        <h2>👁️ Watchdog Event Logs</h2>
        <p className="subtitle">Real-time file system monitoring</p>
        {watchdogEvents.length === 0 ? (
          <p className="empty-state">No watchdog events detected.</p>
        ) : (
          <div className="event-list">
            {watchdogEvents.map((event) => (
              <div key={event.event_id} className="event-item">
                <div className="event-icon">
                  {event.event_type === 'created' && '📄'}
                  {event.event_type === 'modified' && '✏️'}
                  {event.event_type === 'moved' && '🔀'}
                  {event.event_type === 'deleted' && '🗑️'}
                </div>
                <div className="event-content">
                  <div className="event-header">
                    <span className="event-type">{event.event_type.toUpperCase()}</span>
                    <span className="event-time">
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="event-message">
                    <strong>[Obsidian]</strong> File {event.event_type}: "{event.file_path}" → {event.action}
                  </p>
                  <span className={`event-status status-${normalizeStatus(event.status, STATUS_MAP)}`}>
                    {event.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};

export default AutomationDashboard;
