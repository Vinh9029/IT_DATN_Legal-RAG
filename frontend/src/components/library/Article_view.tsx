import React, { memo } from 'react';
import { Bot, Copy, Link2 } from 'lucide-react';
import { cn } from '@/components/ui/button';
import { Highlight } from './Highlight';
import { articleAnchorId } from '@/lib/library/library-service';
import type { ArticleNode } from '@/lib/library/types';

export type ArticleAction = 'link' | 'copy' | 'ask';

interface Article_view_props {
  article: ArticleNode;
  highlight?: string;
  onAction: (action: ArticleAction, article: ArticleNode) => void;
}

// Khoản "1.", điểm "a)", gạch đầu dòng "-" — mỗi loại một mức thụt
const CLAUSE_RE = /^(\d+[a-z]?\.)\s+/;
const POINT_RE = /^([a-zđ]\))\s*/;
const DASH_RE = /^([-–—•])\s+/;

const Paragraph: React.FC<{ text: string; highlight?: string }> = ({ text, highlight }) => {
  const clause = text.match(CLAUSE_RE);
  const point = !clause && text.match(POINT_RE);
  const dash = !clause && !point && text.match(DASH_RE);
  const marker = clause || point || dash;
  const rest = marker ? text.slice(marker[0].length) : text;

  return (
    <p className={cn('text-[1.0625rem] leading-[1.8] text-slate-700', point && 'pl-6', dash && 'pl-10')}>
      {marker && <span className={cn('mr-1.5 font-semibold', clause ? 'text-[#0F172A]' : 'text-slate-500')}>{marker[1]}</span>}
      <Highlight text={rest} query={highlight} />
    </p>
  );
};

const ACTIONS: { action: ArticleAction; label: string; icon: React.ElementType }[] = [
  { action: 'link', label: 'Sao chép liên kết', icon: Link2 },
  { action: 'copy', label: 'Sao chép nội dung', icon: Copy },
  { action: 'ask', label: 'Hỏi trợ lý AI về Điều này', icon: Bot },
];

export const Article_view: React.FC<Article_view_props> = memo(({ article, highlight, onAction }) => (
  <section
    id={articleAnchorId(article.number)}
    data-article={article.number}
    className="lib-article group/article relative -mx-4 rounded-xl px-4 py-5 md:-mx-6 md:px-6"
  >
    <div className="flex items-start gap-3">
      <h3 className="min-w-0 flex-1 text-lg font-bold leading-snug text-[#0F172A] md:text-xl">
        <a
          href={`#${articleAnchorId(article.number)}`}
          onClick={(e) => {
            e.preventDefault();
            onAction('link', article);
          }}
          className="mr-2 whitespace-nowrap text-[#2563EB] hover:underline underline-offset-4"
          title="Sao chép liên kết tới Điều này"
        >
          Điều {article.number}.
        </a>
        <Highlight text={article.title} query={highlight} />
      </h3>

      {/* Thao tác: hiện khi rê chuột (máy tính), luôn hiện mờ trên màn hình cảm ứng */}
      <div className="flex shrink-0 items-center gap-0.5 opacity-60 transition-opacity duration-200 md:opacity-0 md:group-hover/article:opacity-100 md:group-focus-within/article:opacity-100">
        {ACTIONS.map(({ action, label, icon: Icon }) => (
          <button
            key={action}
            type="button"
            onClick={() => onAction(action, article)}
            title={label}
            aria-label={label}
            className={cn(
              'flex size-8 items-center justify-center rounded-lg text-slate-400 transition-colors cursor-pointer',
              action === 'ask' ? 'hover:bg-[#2563EB] hover:text-white' : 'hover:bg-slate-100 hover:text-[#0F172A]',
            )}
          >
            <Icon className="size-4" />
          </button>
        ))}
      </div>
    </div>

    <div className="mt-3 space-y-2.5">
      {article.paragraphs.map((p, i) => (
        <Paragraph key={i} text={p} highlight={highlight} />
      ))}
    </div>
  </section>
));
Article_view.displayName = 'Article_view';
