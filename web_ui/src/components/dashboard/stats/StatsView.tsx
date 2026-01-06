// web_ui/src/components/dashboard/stats/StatsView.tsx

'use client';

import React, { useEffect, useState } from 'react';
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  ScatterChart,
  Scatter,
  ZAxis
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

// Colors
const PARA_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#64748b']; // Proj, Area, Res, Arch
const HEATMAP_COLORS = ['#ebedf0', '#9be9a8', '#40c463', '#30a14e', '#216e39'];

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

interface StatsData {
  activity_heatmap: { date: string; count: number }[];
  weekly_trend: { name: string; value: number }[];
  para_distribution: { [key: string]: number };
}

export default function StatsView() {
  const [data, setData] = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchStats() {
      try {
        const res = await fetch(`${API_BASE_URL}/api/dashboard/stats`);
        if (res.ok) {
          const json = await res.json();
          setData(json);
        }
      } catch (error) {
        console.error("Failed to fetch stats", error);
      } finally {
        setLoading(false);
      }
    }
    fetchStats();
  }, []);

  if (loading) return <div className="p-4">Loading Statistics...</div>;
  if (!data) return <div className="p-4">No data available</div>;

  // Process PARA Data for Pie Chart
  const paraData = Object.keys(data.para_distribution).map((key) => ({
    name: key,
    value: data.para_distribution[key]
  })).filter(d => d.value > 0);

  // Process Heatmap Data for Scatter Chart (Week x Day)
  // We need to map dateStr to { x: week, y: day, z: count }
  const processedHeatmap = data.activity_heatmap.map(d => {
    const date = new Date(d.date);
    // Rough week calculation or just use index if sequential
    // For scatter, simple implementation:
    // x: ISO Week number (approx), y: Day (0-6)
    const day = date.getDay(); // 0 is Sunday
    // Week number hack
    const startOfYear = new Date(date.getFullYear(), 0, 1);
    const pastDaysYear = (date.getTime() - startOfYear.getTime()) / 86400000;
    const week = Math.ceil((pastDaysYear + startOfYear.getDay() + 1) / 7);
    
    return { x: week, y: day, z: d.count, date: d.date };
  });

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* 1. PARA Distribution Pie Chart */}
        <Card>
          <CardHeader>
            <CardTitle>PARA Distribution</CardTitle>
            <CardDescription>File count by category</CardDescription>
          </CardHeader>
          <CardContent className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={paraData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {paraData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={PARA_COLORS[index % PARA_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* 2. Weekly Trend Line Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Weekly Trends</CardTitle>
            <CardDescription>Files processed per week</CardDescription>
          </CardHeader>
          <CardContent className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.weekly_trend}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{fontSize: 12}} />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="value" stroke="#8884d8" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* 3. Activity Heatmap (using Scatter for grid simulation) */}
      <Card>
        <CardHeader>
          <CardTitle>Activity Heatmap</CardTitle>
          <CardDescription>File creation & modification frequency (Year View)</CardDescription>
        </CardHeader>
        <CardContent className="h-[300px]">
           {/* Note: True GitHub style requires complex D3 or dedicated lib. 
               ScatterChart is a "good enough" approximation for Recharts-only constraint. */}
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
              <CartesianGrid />
              <XAxis type="number" dataKey="x" name="Week" unit="w" domain={['auto', 'auto']} />
              <YAxis type="number" dataKey="y" name="Day" ticks={[0,1,2,3,4,5,6]} tickFormatter={(val) => ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][val]} />
              <ZAxis type="number" dataKey="z" range={[50, 400]} name="Count" />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} content={({ payload }) => {
                  if (payload && payload.length) {
                    const d = payload[0].payload;
                    return (
                        <div className="bg-white border p-2 rounded shadow text-xs">
                            <p className="font-bold">{d.date}</p>
                            <p>Activity: {d.z}</p>
                        </div>
                    );
                  }
                  return null;
              }} />
              <Scatter name="Activity" data={processedHeatmap} fill="#8884d8">
                  {processedHeatmap.map((entry, index) => {
                      // Color scale based on count
                      const intensity = Math.min(entry.z, 4); 
                      return <Cell key={`cell-${index}`} fill={HEATMAP_COLORS[intensity]} />;
                  })}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
