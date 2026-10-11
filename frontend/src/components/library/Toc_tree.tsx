import React, { memo, useEffect, useRef, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/components/ui/button';
import { isArticle, structureKey } from '@/lib/library/library-service';
import { sentenceCase } from '@/lib/library/text';
import type { LawNode, StructureNode } from '@/lib/library/types';

interface Toc_tree_props {
  structure: LawNode[];
  activeArticle: string | null;
  /** Khoá (structureKey) của các node chứa Điều đang đọc — tự mở ra */
  activeAncestors: string[];
  onSelectArticle: (number: string) => void;
  onSelectHeading: (key: string) => void;
  /** Mục lục đang hiện (không bị lớp kết quả tìm kiếm che) — hiện lại thì cuộn tới Điều đang đọc */
  visible?: boolean;
}

const LEVEL_STYLE: Record<StructureNode['type'], string> = {
  part: 'text-[13px] font-bold uppercase tracking-wide text-[#0F172A]',
  chapter: 'text-sm font-semibold text-[#0F172A]',
  section: 'text-sm font-medium text-slate-700',
  subsection: 'text-[13px] font-medium text-slate-600',
};

export const Toc_tree: React.FC<Toc_tree_props> = memo(({ structure, activeArticle, activeAncestors, onSelectArticle, onSelectHeading, visible = true }) => {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(activeAncestors));
  const rootRef = useRef<HTMLDivElement>(null);

  // Đọc tới đâu thì mở mục lục tới đó (không tự đóng mục người dùng đã mở).
  // Điều chỉnh ngay lúc render khi nhánh đang đọc đổi, không cần effect.
  const ancestorsKey = activeAncestors.join('|');
  const [seenAncestors, setSeenAncestors] = useState(ancestorsKey);
  if (ancestorsKey !== seenAncestors) {
    setSeenAncestors(ancestorsKey);
    if (!activeAncestors.every((k) => expanded.has(k))) setExpanded(new Set([...expanded, ...activeAncestors]));
  }

  // Giữ mục đang đọc trong tầm nhìn của thanh mục lục. Không dùng scrollIntoView: nó cuộn
  // luôn cả trang, và nhánh vừa mở còn đang animation (cao 0) nên đo vị trí sẽ sai —
  // đợi animation mở (0.35s) xong rồi mới đo.
  useEffect(() => {
    if (!activeArticle || !visible) return;
    const t = setTimeout(() => {
      const container = rootRef.current?.closest<HTMLElement>('.lib-scroll');
      const el = rootRef.current?.querySelector<HTMLElement>(`[data-toc-article="${activeArticle}"]`);
      if (!container || !el) return;
      const c = container.getBoundingClientRect();
      const e = el.getBoundingClientRect();
      if (e.top < c.top + 24 || e.bottom > c.bottom - 24) {
        container.scrollTo({ top: container.scrollTop + e.top - c.top - c.height / 3 });
      }
    }, 380);
    return () => clearTimeout(t);
  }, [activeArticle, expanded, visible]);

  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div ref={rootRef} role="tree" aria-label="Mục lục">
      <Toc_level
        nodes={structure}
        parentKey=""
        depth={0}
        expanded={expanded}
        activeArticle={activeArticle}
        activeAncestors={activeAncestors}
        onToggle={toggle}
        onSelectArticle={onSelectArticle}
        onSelectHeading={onSelectHeading}
      />
    </div>
  );
});
Toc_tree.displayName = 'Toc_tree';

interface Toc_level_props {
  nodes: LawNode[];
  parentKey: string;
  depth: number;
  expanded: Set<string>;
  activeArticle: string | null;
  activeAncestors: string[];
  onToggle: (key: string) => void;
  onSelectArticle: (number: string) => void;
  onSelectHeading: (key: string) => void;
}

const Toc_level: React.FC<Toc_level_props> = (props) => {
  const { nodes, parentKey, depth, expanded, activeArticle, activeAncestors, onToggle, onSelectArticle, onSelectHeading } = props;

  return (
    <ul className={cn('space-y-0.5', depth > 0 && 'ml-3 border-l border-slate-200 pl-2')}>
      {nodes.map((node) => {
        if (isArticle(node)) {
          const active = node.number === activeArticle;
          return (
            <li key={`a-${node.number}`} role="treeitem" aria-selected={active}>
              <button
                type="button"
                data-toc-article={node.number}
                onClick={() => onSelectArticle(node.number)}
                className={cn(
                  'relative flex w-full gap-2 rounded-md px-2 py-1.5 text-left text-[13px] leading-snug transition-colors cursor-pointer',
                  active ? 'bg-[#2563EB]/10 text-[#2563EB]' : 'text-slate-600 hover:bg-slate-100 hover:text-[#0F172A]',
                )}
              >
                {/* Vạch đánh dấu Điều đang đọc */}
                <span
                  className={cn(
                    'absolute -left-[9px] top-1.5 bottom-1.5 w-0.5 rounded-full bg-[#2563EB] transition-transform duration-300',
                    active ? 'scale-y-100' : 'scale-y-0',
                  )}
                />
                <span className={cn('shrink-0 font-mono text-xs leading-5', active ? 'font-bold' : 'text-slate-400')}>{node.number}.</span>
                <span className="line-clamp-2">{node.title}</span>
              </button>
            </li>
          );
        }

        const key = structureKey(parentKey, node);
        const open = expanded.has(key);
        const containsActive = activeAncestors.includes(key);
        return (
          <Toc_branch
            key={key}
            node={node}
            nodeKey={key}
            open={open}
            containsActive={containsActive}
            onToggle={() => onToggle(key)}
            onSelect={() => {
              if (!open) onToggle(key);
              onSelectHeading(key);
            }}
          >
            <Toc_level {...props} nodes={node.children} parentKey={key} depth={depth + 1} />
          </Toc_branch>
        );
      })}
    </ul>
  );
};

interface Toc_branch_props {
  node: StructureNode;
  nodeKey: string;
  open: boolean;
  containsActive: boolean;
  onToggle: () => void;
  onSelect: () => void;
  children: React.ReactNode;
}

const Toc_branch: React.FC<Toc_branch_props> = ({ node, open, containsActive, onToggle, onSelect, children }) => {
  // Chỉ dựng cây con khi đã mở ít nhất một lần — bộ luật nghìn Điều mà dựng hết thì thanh bên ì
  const [mounted, setMounted] = useState(open);
  if (open && !mounted) setMounted(true);

  return (
    <li role="treeitem" aria-expanded={open}>
      <div className="group flex items-start gap-0.5">
        <button
          type="button"
          onClick={onToggle}
          aria-label={open ? `Thu gọn ${node.label}` : `Mở ${node.label}`}
          className="mt-1 flex size-6 shrink-0 items-center justify-center rounded text-slate-400 transition-colors hover:bg-slate-100 hover:text-[#0F172A] cursor-pointer"
        >
          <ChevronRight className={cn('size-3.5 transition-transform duration-300', open && 'rotate-90')} />
        </button>
        <button
          type="button"
          onClick={onSelect}
          className={cn(
            'min-w-0 flex-1 rounded-md px-1.5 py-1 text-left leading-snug transition-colors hover:bg-slate-100 cursor-pointer',
            LEVEL_STYLE[node.type],
            containsActive && !open && 'text-[#2563EB]',
          )}
        >
          <span className={cn('block text-[11px] font-semibold uppercase tracking-wider', containsActive ? 'text-[#2563EB]' : 'text-slate-400')}>
            {node.label}
          </span>
          <span className="line-clamp-2">{sentenceCase(node.title)}</span>
        </button>
      </div>
      <div className="collapse-grid" data-open={open}>
        <div>{mounted && <div className="pb-1 pt-0.5">{children}</div>}</div>
      </div>
    </li>
  );
};
