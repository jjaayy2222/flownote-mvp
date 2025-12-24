// web_ui/src/components/SyncMonitor.js

import React, { useState, useEffect } from 'react';
import './SyncMonitor.css';

const SyncMonitor = () => {
  const [syncStatus, setSyncStatus] = useState(null);
  const [mcpStatus, setMcpStatus] = useState(null);
  const [conflicts, setConflicts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const API_BASE = 'http://localhost:8000';

  // Fetch sync status
  const fetchSyncStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/sync/status`);
      if (!response.ok) throw new Error('Failed to fetch sync status');
      const data = await response.json();
      setSyncStatus(data);
    } catch (err) {
      console.error('Sync status error:', err);
      setError(err.message);
    }
  };

  // Fetch MCP status
  const fetchMCPStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/sync/mcp/status`);
      if (!response.ok) throw new Error('Failed to fetch MCP status');
      const data = await response.json();
      setMcpStatus(data);
    } catch (err) {
      console.error('MCP status error:', err);
      setError(err.message);
    }
  };

  // Fetch conflicts
  const fetchConflicts = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/sync/conflicts?limit=10`);
      if (!response.ok) throw new Error('Failed to fetch conflicts');
      const data = await response.json();
      setConflicts(data);
    } catch (err) {
      console.error('Conflicts error:', err);
      setError(err.message);
    }
  };

  // Initial load
  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      await Promise.all([
        fetchSyncStatus(),
        fetchMCPStatus(),
        fetchConflicts()
      ]);
      setLoading(false);
    };

    loadAll();

    // Poll every 5 seconds
    const interval = setInterval(loadAll, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="sync-monitor loading">
        <div className="spinner"></div>
        <p>Loading sync status...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="sync-monitor error">
        <h2>⚠️ Error</h2>
        <p>{error}</p>
        <button onClick={() => window.location.reload()}>Retry</button>
      </div>
    );
  }

  return (
    <div className="sync-monitor">
      <h1>🔗 Sync Monitor</h1>

      {/* Obsidian Status */}
      <section className="status-card">
        <h2>📔 Obsidian Connection</h2>
        <div className="status-grid">
          <div className="status-item">
            <span className="label">Status:</span>
            <span className={`value ${syncStatus?.connected ? 'connected' : 'disconnected'}`}>
              {syncStatus?.connected ? '✅ Connected' : '❌ Disconnected'}
            </span>
          </div>
          <div className="status-item">
            <span className="label">Vault Path:</span>
            <span className="value">{syncStatus?.vault_path || 'N/A'}</span>
          </div>
          <div className="status-item">
            <span className="label">Last Sync:</span>
            <span className="value">
              {syncStatus?.last_sync 
                ? new Date(syncStatus.last_sync).toLocaleString()
                : 'Never'}
            </span>
          </div>
          <div className="status-item">
            <span className="label">File Count:</span>
            <span className="value">{syncStatus?.file_count || 0} files</span>
          </div>
          <div className="status-item">
            <span className="label">Sync Interval:</span>
            <span className="value">{syncStatus?.sync_interval || 0}s</span>
          </div>
          <div className="status-item">
            <span className="label">Enabled:</span>
            <span className={`value ${syncStatus?.enabled ? 'enabled' : 'disabled'}`}>
              {syncStatus?.enabled ? '✓ Yes' : '✗ No'}
            </span>
          </div>
        </div>
      </section>

      {/* MCP Server Status */}
      <section className="status-card">
        <h2>🤖 MCP Server</h2>
        <div className="status-grid">
          <div className="status-item">
            <span className="label">Status:</span>
            <span className={`value ${mcpStatus?.running ? 'running' : 'stopped'}`}>
              {mcpStatus?.running ? '▶ Running' : '⏸ Stopped'}
            </span>
          </div>
          <div className="status-item full-width">
            <span className="label">Active Clients:</span>
            <div className="client-list">
              {mcpStatus?.active_clients?.length > 0 ? (
                mcpStatus.active_clients.map((client, idx) => (
                  <span key={idx} className="client-badge">{client}</span>
                ))
              ) : (
                <span className="value muted">No active clients</span>
              )}
            </div>
          </div>
          <div className="status-item full-width">
            <span className="label">Registered Tools:</span>
            <div className="tool-list">
              {mcpStatus?.tools_registered?.map((tool, idx) => (
                <span key={idx} className="tool-badge">{tool}</span>
              ))}
            </div>
          </div>
          <div className="status-item full-width">
            <span className="label">Registered Resources:</span>
            <div className="resource-list">
              {mcpStatus?.resources_registered?.map((resource, idx) => (
                <code key={idx} className="resource-uri">{resource}</code>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Conflict Log Viewer */}
      <section className="status-card conflicts">
        <h2>⚠️ Conflict History</h2>
        {conflicts.length === 0 ? (
          <p className="empty-state">No conflicts detected. All syncs successful! 🎉</p>
        ) : (
          <div className="conflict-list">
            {conflicts.map((conflict) => (
              <div key={conflict.conflict_id} className="conflict-item">
                <div className="conflict-header">
                  <span className="conflict-id">{conflict.conflict_id}</span>
                  <span className={`conflict-status status-${conflict.status}`}>
                    {conflict.status}
                  </span>
                </div>
                <div className="conflict-body">
                  <p><strong>File:</strong> {conflict.file_path}</p>
                  <p><strong>Type:</strong> {conflict.conflict_type}</p>
                  <p><strong>Time:</strong> {new Date(conflict.timestamp).toLocaleString()}</p>
                  {conflict.resolution_method && (
                    <p><strong>Resolved:</strong> {conflict.resolution_method}</p>
                  )}
                  {conflict.notes && (
                    <p className="conflict-notes">{conflict.notes}</p>
                  )}
                </div>
                <div className="conflict-hashes">
                  <div><code>Local: {conflict.local_hash.substring(0, 8)}...</code></div>
                  <div><code>Remote: {conflict.remote_hash.substring(0, 8)}...</code></div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};

export default SyncMonitor;
