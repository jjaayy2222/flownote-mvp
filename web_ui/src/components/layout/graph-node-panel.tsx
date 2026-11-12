'use client';

import { FileText, Network, Tag } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Badge } from '@/components/ui/badge';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { NodeType } from '@/types/websocket';
import type { GraphNode } from '@/types/websocket';

interface GraphNodePanelProps {
  node: GraphNode | null;
  relatedNodes: GraphNode[];
  isOpen: boolean;
  onClose: () => void;
  onNodeSelect: (node: GraphNode) => void;
}

const NODE_TYPE_TRANSLATION_KEYS = {
  [NodeType.CATEGORY]: 'nodeTypes.category',
  [NodeType.NOTE]: 'nodeTypes.note',
  [NodeType.KEYWORD]: 'nodeTypes.keyword',
  [NodeType.TAG]: 'nodeTypes.tag',
} as const satisfies Record<NodeType, string>;

type NodeTypeTranslationKey =
  | (typeof NODE_TYPE_TRANSLATION_KEYS)[NodeType]
  | 'nodeTypes.unknown';

function getNodeTypeTranslationKey(nodeType: NodeType): NodeTypeTranslationKey {
  return NODE_TYPE_TRANSLATION_KEYS[nodeType] ?? 'nodeTypes.unknown';
}

export function GraphNodePanel({
  node,
  relatedNodes,
  isOpen,
  onClose,
  onNodeSelect,
}: GraphNodePanelProps) {
  const t = useTranslations('graph.nodePanel');
  const tSearch = useTranslations('search.filters');

  if (!node) return null;

  const paraCategory =
    node.properties !== null && typeof node.properties === 'object'
      ? node.properties.para_category
      : undefined;
  const category = typeof paraCategory === 'string' ? paraCategory : null;
  const categoryLabel =
    category && tSearch.has(`categories.${category}`)
      ? tSearch(`categories.${category}`)
      : category
        ? t('unknownCategory')
        : null;
  const nodeTypeLabel = t(getNodeTypeTranslationKey(node.node_type));

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        closeLabel={t('close')}
        className="flex w-full flex-col gap-0 border-l border-slate-200 bg-white p-0 sm:max-w-lg"
      >
        <SheetHeader className="border-b border-slate-100 bg-slate-50/80 px-6 py-5">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-100 text-blue-600">
              {node.node_type === NodeType.NOTE ? (
                <FileText aria-hidden="true" className="h-5 w-5" />
              ) : (
                <Network aria-hidden="true" className="h-5 w-5" />
              )}
            </div>
            <div className="min-w-0">
              <SheetTitle
                className="truncate text-base font-semibold text-slate-800"
              >
                {node.label}
              </SheetTitle>
              <SheetDescription
                className="mt-1 text-xs text-slate-500"
              >
                {t('description')}
              </SheetDescription>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge variant="secondary" className="gap-1">
              <Tag aria-hidden="true" className="h-3 w-3" />
              {nodeTypeLabel}
            </Badge>
            {categoryLabel && <Badge variant="outline">{categoryLabel}</Badge>}
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <section aria-labelledby="graph-node-related-title">
            <h3
              id="graph-node-related-title"
              className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400"
            >
              {t('relatedNodes')}
            </h3>
            {relatedNodes.length > 0 ? (
              <ul className="space-y-2">
                {relatedNodes.map((relatedNode) => (
                  <li key={relatedNode.id}>
                    <button
                      type="button"
                      onClick={() => onNodeSelect(relatedNode)}
                      className="flex w-full items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-left text-sm text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    >
                      <span className="truncate">{relatedNode.label}</span>
                      <span className="ml-3 shrink-0 text-xs text-slate-400">
                        {t(getNodeTypeTranslationKey(relatedNode.node_type))}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-500">{t('noRelatedNodes')}</p>
            )}
          </section>
        </div>

        <div className="border-t border-slate-100 bg-slate-50/50 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            {t('close')}
          </button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
