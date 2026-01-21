// web_ui/src/components/dashboard/websocket-monitor.tsx

'use client';

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Activity, Radio, Database, Clock, TrendingUp } from 'lucide-react';

// API URL: Use environment variable or default to relative path for production safety
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE || '';

/**
 * Polling interval for metrics fetch (milliseconds)
 * Can be configured via NEXT_PUBLIC_METRICS_POLL_INTERVAL environment variable
 * Default: 5000ms (5 seconds)
 */
const METRICS_POLL_INTERVAL = parseInt(
  process.env.NEXT_PUBLIC_METRICS_POLL_INTERVAL || '5000',
  10
);

/**
 * Type guard to check if an error is an AbortError
 * Works for both Error instances and DOMException
 * @param err - Unknown error to check
 * @returns true if err is an AbortError with precise type narrowing
 */
function isAbortError(err: unknown): err is { name: 'AbortError' } {
  if (err === null || typeof err !== 'object') return false;
  
  const e = err as { name?: unknown };
  return typeof e.name === 'string' && e.name === 'AbortError';
}

// Maximum length for error messages to prevent UI overflow
const MAX_ERROR_LENGTH = 500;

/**
 * Truncate string to maximum length with ellipsis
 * @param str - String to truncate
 * @returns Truncated string if exceeds max length
 */
function truncateString(str: string): string {
  return str.length > MAX_ERROR_LENGTH
    ? str.substring(0, MAX_ERROR_LENGTH) + '...'
    : str;
}

/**
 * Extract meaningful error message from unknown error value
 * Preserves maximum debugging information while avoiding UI overflow
 * All return paths respect MAX_ERROR_LENGTH
 * @param err - Unknown error value
 * @returns Human-readable error message (≤ MAX_ERROR_LENGTH)
 */
function getErrorMessage(err: unknown): string {
  // Standard Error instance
  if (err instanceof Error) {
    return truncateString(err.message);
  }
  
  // Object with message property
  if (err && typeof err === 'object' && 'message' in err) {
    const messageValue = (err as { message: unknown }).message;
    
    // String message (most common case)
    if (typeof messageValue === 'string') {
      const trimmed = messageValue.trim();
      // Only use non-empty messages
      if (trimmed.length > 0) {
        return truncateString(trimmed);
      }
    }
    
    // Nested message object (e.g., { message: { detail: "..." } })
    if (messageValue && typeof messageValue === 'object') {
      try {
        const serialized = JSON.stringify(messageValue);
        if (serialized && serialized !== '{}') {
          return truncateString(serialized);
        }
      } catch {
        // JSON.stringify can fail
      }
    }
  }
  
  // Try to serialize entire object for debugging
  if (err && typeof err === 'object') {
    try {
      const serialized = JSON.stringify(err);
      // Avoid useless "{}" 
      if (serialized && serialized !== '{}') {
        return truncateString(serialized);
      }
    } catch {
      // JSON.stringify can fail for circular references or other reasons
    }
  }
  
  // Fall back to string conversion
  return truncateString(String(err));
}

// Strict typing for better type safety
type SystemStatus = 'healthy' | 'degraded' | 'down';

interface WebSocketMetrics {
  status: SystemStatus;
  connections: {
    active: number;
    peak: number;
  };
  performance: {
    window_seconds: number;
    broadcast_tps: number;
    message_tps: number;
    total_broadcasts: number;
    total_messages: number;
    total_data_bytes: number;
    total_data_mb: number;
  };
  redis: {
    connected: boolean;
    channel: string;
  };
  uptime_seconds: number;
}

export default function WebSocketMonitor() {
  const [metrics, setMetrics] = useState<WebSocketMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // AbortController to cancel fetch on unmount
    const abortController = new AbortController();
    
    async function fetchMetrics() {
      try {
        const endpoint = API_BASE_URL ? `${API_BASE_URL}/health/metrics` : '/health/metrics';
        
        const res = await fetch(endpoint, {
          signal: abortController.signal,
        });
        
        if (res.ok) {
          const json = await res.json();
          setMetrics(json);
          setError(null);
        } else {
          setError(`Failed to fetch metrics: ${res.status}`);
        }
      } catch (err: unknown) {
        // Ignore AbortError from cleanup
        if (isAbortError(err)) {
          return;
        }
        // Extract meaningful error message for debugging
        setError(getErrorMessage(err));
        console.error("Failed to fetch WebSocket metrics", err);
      } finally {
        setLoading(false);
      }
    }

    // Initial fetch
    fetchMetrics();

    // Poll at configured interval (default: 5 seconds)
    const interval = setInterval(fetchMetrics, METRICS_POLL_INTERVAL);

    return () => {
      clearInterval(interval);
      abortController.abort(); // Cancel any pending fetch on unmount
    };
  }, []);

  const formatUptime = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return `${hours}h ${minutes}m ${secs}s`;
  };

  if (loading) {
    return (
      <div className="p-4 text-center text-muted-foreground">
        Loading WebSocket metrics...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-destructive">Error</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{error}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!metrics) {
    return (
      <div className="p-4 text-center text-muted-foreground">
        No metrics available
      </div>
    );
  }

  const getStatusVariant = (status: SystemStatus): "default" | "destructive" | "secondary" => {
    switch (status) {
      case 'healthy':
        return 'default';
      case 'degraded':
        return 'secondary';
      case 'down':
        return 'destructive';
      default:
        // Exhaustive check: this should never be reached if all cases are handled
        const _exhaustiveCheck: never = status;
        return _exhaustiveCheck;
    }
  };

  return (
    <div className="space-y-6">
      {/* System Status */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>WebSocket System Status</CardTitle>
            <Badge variant={getStatusVariant(metrics.status)}>
              {metrics.status}
            </Badge>
          </div>
          <CardDescription>
            Real-time monitoring of WebSocket infrastructure
          </CardDescription>
        </CardHeader>
      </Card>

      {/* Key Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Active Connections */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Active Connections
            </CardTitle>
            <Radio className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.connections.active}</div>
            <p className="text-xs text-muted-foreground">
              Peak: {metrics.connections.peak}
            </p>
          </CardContent>
        </Card>

        {/* Broadcast TPS */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Broadcast TPS
            </CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metrics.performance.broadcast_tps.toFixed(2)}
            </div>
            <p className="text-xs text-muted-foreground">
              Events/sec ({metrics.performance.window_seconds}s window)
            </p>
          </CardContent>
        </Card>

        {/* Message TPS */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Message TPS
            </CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metrics.performance.message_tps.toFixed(2)}
            </div>
            <p className="text-xs text-muted-foreground">
              Messages/sec (per recipient)
            </p>
          </CardContent>
        </Card>

        {/* Data Transferred */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Data Transferred
            </CardTitle>
            <Database className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metrics.performance.total_data_mb.toFixed(2)} MB
            </div>
            <p className="text-xs text-muted-foreground">
              {metrics.performance.total_data_bytes.toLocaleString()} bytes
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Detailed Performance Stats */}
      <Card>
        <CardHeader>
          <CardTitle>Performance Details</CardTitle>
          <CardDescription>Cumulative statistics since system start</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div>
              <div className="text-sm font-medium text-muted-foreground">Total Broadcasts</div>
              <div className="text-2xl font-bold">{metrics.performance.total_broadcasts.toLocaleString()}</div>
            </div>
            <div>
              <div className="text-sm font-medium text-muted-foreground">Total Messages</div>
              <div className="text-2xl font-bold">{metrics.performance.total_messages.toLocaleString()}</div>
            </div>
            <div>
              <div className="text-sm font-medium text-muted-foreground">Uptime</div>
              <div className="text-2xl font-bold">
                <div className="flex items-center gap-2">
                  <Clock className="h-5 w-5 text-muted-foreground" />
                  <span className="text-lg">{formatUptime(metrics.uptime_seconds)}</span>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Redis Status */}
      <Card>
        <CardHeader>
          <CardTitle>Redis Pub/Sub Status</CardTitle>
          <CardDescription>Backend message broker connectivity</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">Connection Status</div>
              <div className="text-xs text-muted-foreground mt-1">
                Channel: <code className="text-xs bg-muted px-1 py-0.5 rounded">{metrics.redis.channel}</code>
              </div>
            </div>
            <Badge variant={metrics.redis.connected ? "default" : "destructive"}>
              {metrics.redis.connected ? "Connected" : "Disconnected"}
            </Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
