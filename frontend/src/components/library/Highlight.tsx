import React, { memo } from 'react';
import { matchRanges } from '@/lib/library/text';

/** Tô sáng các từ của `query` trong `text`, không phân biệt dấu/hoa thường */
export const Highlight: React.FC<{ text: string; query?: string }> = memo(({ text, query }) => {
  if (!query?.trim()) return <>{text}</>;
  const ranges = matchRanges(text, query);
  if (!ranges.length) return <>{text}</>;

  const parts: React.ReactNode[] = [];
  let cursor = 0;
  ranges.forEach(([start, end], i) => {
    if (start > cursor) parts.push(text.slice(cursor, start));
    parts.push(
      <mark key={i} className="lib-mark">
        {text.slice(start, end)}
      </mark>,
    );
    cursor = end;
  });
  if (cursor < text.length) parts.push(text.slice(cursor));
  return <>{parts}</>;
});
Highlight.displayName = 'Highlight';
