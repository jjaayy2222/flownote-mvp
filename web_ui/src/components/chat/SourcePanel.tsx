'use client';

import React from 'react';
import { FileText, X, Hash, BarChart2 } from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { type SourceItem } from '@/types/chat';

interface SourcePanelProps {
  source: SourceItem | null;
  isOpen: boolean;
  onClose: () => void;
}

export function SourcePanel({ source, isOpen, onClose }: SourcePanelProps) {
  if (!source) return null;

  const scorePercent = source.score != null ? (source.score * 100).toFixed(1) : null;

  // source.id에서 파일명만 추출 (경로가 있을 경우)
  const displayName = source.title
    || (source.id ? source.id.split('/').pop() || source.id : '참조 문서');

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-lg flex flex-col gap-0 p-0 border-l border-slate-200 bg-white"
        aria-labelledby="source-panel-title"
        aria-describedby="source-panel-description"
      >
        {/* 헤더 */}
        <SheetHeader className="px-6 py-4 border-b border-slate-100 bg-slate-50/80">
          <div className="flex items-center gap-3">
            <div className="flex-shrink-0 w-9 h-9 rounded-lg bg-blue-100 flex items-center justify-center">
              <FileText className="w-5 h-5 text-blue-600" />
            </div>
            <div className="flex-1 min-w-0">
              <SheetTitle
                id="source-panel-title"
                className="text-base font-semibold text-slate-800 truncate leading-tight"
              >
                {displayName}
              </SheetTitle>
              <SheetDescription
                id="source-panel-description"
                className="text-xs text-slate-500 mt-0.5"
              >
                RAG 검색 참조 문서
              </SheetDescription>
            </div>
          </div>

          {/* 메타데이터 뱃지 영역 */}
          <div className="flex flex-wrap gap-2 mt-3">
            {scorePercent && (
              <Badge variant="secondary" className="text-xs gap-1 bg-emerald-50 text-emerald-700 border-emerald-200 border">
                <BarChart2 className="w-3 h-3" />
                관련도 {scorePercent}%
              </Badge>
            )}
            {source.id && (
              <Badge variant="outline" className="text-xs gap-1 font-mono text-slate-500 max-w-[180px] truncate">
                <Hash className="w-3 h-3 flex-shrink-0" />
                <span className="truncate">{source.id}</span>
              </Badge>
            )}
            {source.source && (
              <Badge variant="outline" className="text-xs text-slate-500 max-w-[200px] truncate">
                📂 {source.source}
              </Badge>
            )}
          </div>
        </SheetHeader>

        {/* 본문 */}
        <ScrollArea className="flex-1 px-6 py-5">
          {source.page_content ? (
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                문서 내용
              </p>
              <div className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap bg-slate-50 rounded-xl p-4 border border-slate-100 font-mono">
                {source.page_content}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full py-16 text-center">
              <FileText className="w-10 h-10 text-slate-200 mb-3" />
              <p className="text-sm text-slate-400">
                이 문서의 상세 내용을 불러올 수 없습니다.
              </p>
            </div>
          )}

          {/* 추가 메타데이터 (id/score/page_content/source/title 제외한 나머지) */}
          {(() => {
            const extraKeys = Object.keys(source).filter(
              (k) => !['id', 'score', 'page_content', 'source', 'title'].includes(k)
            );
            if (extraKeys.length === 0) return null;
            return (
              <div className="mt-6">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                  추가 정보
                </p>
                <div className="space-y-2">
                  {extraKeys.map((key) => (
                    <div key={key} className="flex items-start gap-2 text-xs">
                      <span className="text-slate-400 font-mono w-24 flex-shrink-0 pt-0.5">{key}</span>
                      <span className="text-slate-600 break-all">
                        {JSON.stringify(source[key])}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}
        </ScrollArea>

        {/* 닫기 버튼 (푸터) */}
        <div className="px-6 py-4 border-t border-slate-100 bg-slate-50/50">
          <button
            onClick={onClose}
            className="w-full flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 transition-colors"
          >
            <X className="w-4 h-4" />
            닫기
          </button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
