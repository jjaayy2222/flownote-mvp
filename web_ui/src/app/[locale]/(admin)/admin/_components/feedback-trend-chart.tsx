'use client';

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { useTranslations } from 'next-intl';
import type { FeedbackTrend } from '../analytics/actions';

interface FeedbackTrendChartProps {
  data: FeedbackTrend[];
}

/**
 * [Client Component] 날짜별 AI 피드백 Up/Down 트렌드를 Area Chart로 시각화한다.
 * - recharts ResponsiveContainer로 반응형 적용
 * - CSS 변수(--chart-1, --chart-2)를 통해 다크모드 색상 토큰과 자동 동기화
 * - 데이터가 없을 경우 안내 메시지를 렌더링하는 Empty State 처리
 */
export function FeedbackTrendChart({ data }: FeedbackTrendChartProps) {
  const t = useTranslations('admin.analytics.trend_chart');

  if (!data || data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed">
        <p className="text-sm text-muted-foreground">{t('empty')}</p>
      </div>
    );
  }

  return (
    <div className="w-full">
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart
          data={data}
          margin={{ top: 10, right: 24, left: 0, bottom: 0 }}
        >
          <defs>
            {/* 긍정(Up) - chart-2 색상 토큰 (초록 계열) */}
            <linearGradient id="colorUp" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="5%"
                stopColor="var(--color-chart-2)"
                stopOpacity={0.3}
              />
              <stop
                offset="95%"
                stopColor="var(--color-chart-2)"
                stopOpacity={0}
              />
            </linearGradient>
            {/* 부정(Down) - chart-5 색상 토큰 (주황/적색 계열) */}
            <linearGradient id="colorDown" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="5%"
                stopColor="var(--color-chart-5)"
                stopOpacity={0.3}
              />
              <stop
                offset="95%"
                stopColor="var(--color-chart-5)"
                stopOpacity={0}
              />
            </linearGradient>
          </defs>

          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--color-border)"
            vertical={false}
          />

          <XAxis
            dataKey="date"
            tick={{ fontSize: 12, fill: 'var(--color-muted-foreground)' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(value: string) => {
              // "YYYY-MM-DD" → "MM/DD" 포맷으로 축약
              if (typeof value === 'string' && value.length === 10) {
                return value.slice(5).replace('-', '/');
              }
              return value;
            }}
          />

          <YAxis
            tick={{ fontSize: 12, fill: 'var(--color-muted-foreground)' }}
            axisLine={false}
            tickLine={false}
            allowDecimals={false}
            width={32}
          />

          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--color-card)',
              borderColor: 'var(--color-border)',
              borderRadius: '0.5rem',
              color: 'var(--color-card-foreground)',
              fontSize: '0.875rem',
            }}
            labelStyle={{ color: 'var(--color-muted-foreground)', marginBottom: '4px' }}
            itemStyle={{ color: 'var(--color-card-foreground)' }}
            formatter={(value: number | undefined, name: string | undefined) => {
              const labelMap: Record<string, string> = {
                up: t('up'),
                down: t('down'),
              };

              const label = (name && labelMap[name]) ?? name ?? '';
              return [value ?? 0, label];
            }}
          />

          <Legend
            formatter={(value: string) => {
              const labelMap: Record<string, string> = {
                up: t('up'),
                down: t('down'),
              };

              return labelMap[value] ?? value;
            }}
            wrapperStyle={{ fontSize: '0.875rem', paddingTop: '12px' }}
          />

          <Area
            type="monotone"
            dataKey="up"
            stroke="var(--color-chart-2)"
            strokeWidth={2}
            fill="url(#colorUp)"
            dot={false}
            activeDot={{ r: 5, strokeWidth: 0 }}
          />

          <Area
            type="monotone"
            dataKey="down"
            stroke="var(--color-chart-5)"
            strokeWidth={2}
            fill="url(#colorDown)"
            dot={false}
            activeDot={{ r: 5, strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
