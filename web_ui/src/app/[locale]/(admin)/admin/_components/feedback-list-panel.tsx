'use client';

import { useState } from 'react';
import { useTranslations, useFormatter } from 'next-intl';
import { ThumbsUp, ThumbsDown, MessageSquareOff, ChevronLeft, ChevronRight } from 'lucide-react';
import type { FeedbackDetail } from '../analytics/actions';
import { clsx } from 'clsx';

interface FeedbackListPanelProps {
  feedbacks: FeedbackDetail[];
}

const ITEMS_PER_PAGE = 10;

export function FeedbackListPanel({ feedbacks }: FeedbackListPanelProps) {
  const t = useTranslations('admin.analytics.feed_list');
  const format = useFormatter();
  const [currentPage, setCurrentPage] = useState(1);

  // feedbacks 배열 변경에 따른 페이지 강제 보정 로직 (useEffect 대신 파생 상태 활용)
  const totalPages = Math.ceil((feedbacks?.length || 0) / ITEMS_PER_PAGE) || 1;
  const safeCurrentPage = Math.min(Math.max(1, currentPage), totalPages);

  if (!feedbacks || feedbacks.length === 0) {
    return (
      <div className="flex h-48 flex-col items-center justify-center rounded-lg border border-dashed text-slate-500">
        <MessageSquareOff className="mb-2 h-8 w-8 opacity-50" />
        <p className="text-sm">{t('empty')}</p>
      </div>
    );
  }

  const startIndex = (safeCurrentPage - 1) * ITEMS_PER_PAGE;
  const currentFeedbacks = feedbacks.slice(startIndex, startIndex + ITEMS_PER_PAGE);

  return (
    <div className="flex flex-col space-y-4">
      <div className="space-y-3">
        {currentFeedbacks.map((fb, idx) => {
          // Rating Badge 스타일 결정
          const isUp = fb.rating === 'up';
          const isDown = fb.rating === 'down';
          
          return (
            <div
              key={`${fb.message_id}-${idx}`}
              className="flex flex-col gap-2 rounded-lg border bg-card p-4 shadow-sm transition-colors hover:bg-slate-50/50 dark:hover:bg-slate-800/10"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className={clsx(
                      "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold",
                      isUp && "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400",
                      isDown && "bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-400",
                      !isUp && !isDown && "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                    )}
                  >
                    {isUp && <ThumbsUp className="h-3.5 w-3.5" />}
                    {isDown && <ThumbsDown className="h-3.5 w-3.5" />}
                    {!isUp && !isDown && <MessageSquareOff className="h-3.5 w-3.5" />}
                    
                    <span>
                      {isUp ? t('rating_up') : isDown ? t('rating_down') : t('rating_none')}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {format.dateTime(new Date(fb.timestamp), {
                      year: 'numeric',
                      month: '2-digit',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </span>
                </div>
              </div>

              {/* 사용자 입력 텍스트 */}
              <p className={clsx("text-sm", !fb.text && "italic text-muted-foreground/60")}>
                {fb.text ? fb.text : t('no_text')}
              </p>

              {/* 메타데이터 */}
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <div className="flex items-center gap-1">
                  <span className="font-medium">{t('meta_session')}:</span>
                  <span className="font-mono text-[10px]">{fb.session_id ? `${fb.session_id.split('-')[0]}...` : t('unknown')}</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="font-medium">{t('meta_message')}:</span>
                  <span className="font-mono text-[10px]">{fb.message_id ? `${fb.message_id.split('-')[0]}...` : t('unknown')}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <button
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={safeCurrentPage === 1}
            className="flex h-8 w-8 items-center justify-center rounded-md border text-slate-500 transition-colors hover:bg-slate-100 disabled:opacity-50 dark:hover:bg-slate-800"
            aria-label={t('prev_page')}
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-sm text-muted-foreground">
            {safeCurrentPage} / {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            disabled={safeCurrentPage === totalPages}
            className="flex h-8 w-8 items-center justify-center rounded-md border text-slate-500 transition-colors hover:bg-slate-100 disabled:opacity-50 dark:hover:bg-slate-800"
            aria-label={t('next_page')}
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
