import React from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/components/ui/button';
import { Highlight } from './Highlight';
import { sentenceCase } from '@/lib/library/text';
import type { ArticleHit } from '@/lib/library/types';

interface Article_hit_props {
  hit: ArticleHit;
  query: string;
  /** Tên ngắn của văn bản — chỉ hiện khi kết quả trộn nhiều văn bản */
  lawLabel?: string;
  to?: string;
  onSelect?: () => void;
  compact?: boolean;
  style?: React.CSSProperties;
}

/** Một kết quả tìm kiếm cấp Điều — dùng ở trang Thư viện (Link) và thanh bên trang đọc (nút) */
export const Article_hit: React.FC<Article_hit_props> = ({ hit, query, lawLabel, to, onSelect, compact, style }) => {
  const { article, path } = hit;
  const trail = path.map((p) => p.label).join(' › ');
  const lastTitle = path.length ? sentenceCase(path[path.length - 1].title) : '';

  const body = (
    <>
      <div className="flex items-start gap-2">
        <span className="mt-0.5 shrink-0 rounded-md bg-[#2563EB]/10 px-1.5 py-0.5 font-mono text-xs font-bold text-[#2563EB]">
          Đ.{article.number}
        </span>
        <p className={cn('min-w-0 flex-1 font-semibold text-[#0F172A]', compact ? 'text-sm leading-snug' : 'text-base leading-snug')}>
          <Highlight text={article.title} query={query} />
        </p>
        {!compact && <ChevronRight className="mt-1 size-4 shrink-0 text-slate-300 transition-all group-hover:translate-x-0.5 group-hover:text-[#2563EB]" />}
      </div>
      {hit.snippet && (
        <p className={cn('mt-1.5 text-slate-500', compact ? 'line-clamp-2 text-xs leading-relaxed' : 'line-clamp-3 text-sm leading-relaxed')}>
          <Highlight text={hit.snippet} query={query} />
        </p>
      )}
      <p className="mt-1.5 truncate text-xs text-slate-400">
        {lawLabel && <span className="font-semibold text-slate-500">{lawLabel} · </span>}
        {compact ? trail : [trail, lastTitle].filter(Boolean).join(' — ')}
      </p>
    </>
  );

  const className = cn(
    'group block w-full text-left transition-colors cursor-pointer',
    compact
      ? 'rounded-lg px-3 py-2.5 hover:bg-[#2563EB]/5 focus-visible:bg-[#2563EB]/5 focus:outline-none'
      : 'community-rise rounded-xl border border-slate-200 bg-white p-4 hover:border-[#2563EB]/50 hover:shadow-sm',
  );

  return to ? (
    <Link to={to} className={className} style={style}>
      {body}
    </Link>
  ) : (
    <button type="button" onClick={onSelect} className={className} style={style}>
      {body}
    </button>
  );
};
