import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight } from 'lucide-react';
import { Highlight } from './Highlight';
import { lawPath } from '@/lib/library/library-service';
import { formatDate } from '@/lib/library/text';
import type { LawSummary } from '@/lib/library/types';

interface Law_card_props {
  law: LawSummary;
  query?: string;
  style?: React.CSSProperties;
}

const lawYear = (law: LawSummary) => law.ngay_ban_hanh?.slice(0, 4);

/** Một dòng trong danh mục văn bản — đọc như mục lục của thư viện, không phải thẻ quảng cáo */
export const Law_card: React.FC<Law_card_props> = ({ law, query, style }) => {
  // Chỉ nhắc tình trạng khi văn bản KHÔNG còn hiệu lực — trường hợp bình thường thì im lặng
  const inactive = law.tinh_trang && !law.tinh_trang.toLowerCase().includes('còn hiệu lực');

  return (
    <Link
      to={lawPath(law.id)}
      style={style}
      className="community-rise group grid gap-x-8 gap-y-2 px-5 py-5 transition-colors hover:bg-slate-50 focus:outline-none focus-visible:bg-slate-50 md:grid-cols-[minmax(0,1fr)_auto] md:px-6"
    >
      <div className="min-w-0">
        <p className="font-mono text-xs uppercase tracking-wide text-slate-400">
          {[law.loai_van_ban, law.so_hieu].filter(Boolean).join(' · ')}
          {inactive && <span className="ml-2 font-sans font-semibold normal-case tracking-normal text-red-600">{law.tinh_trang}</span>}
        </p>
        <h3 className="mt-1.5 flex items-center gap-1.5 text-lg font-bold leading-snug text-[#0F172A] transition-colors group-hover:text-[#2563EB]">
          <span>
            <Highlight text={[law.title, lawYear(law)].filter(Boolean).join(' ')} query={query} />
          </span>
          <ArrowUpRight className="size-4 shrink-0 -translate-x-1 opacity-0 transition-all duration-200 group-hover:translate-x-0 group-hover:opacity-100" />
        </h3>
        {law.summary && <p className="mt-1.5 line-clamp-2 max-w-2xl text-sm leading-relaxed text-slate-600">{law.summary}</p>}
      </div>

      <dl className="flex gap-6 text-sm md:flex-col md:gap-1 md:text-right">
        {law.ngay_hieu_luc && (
          <div>
            <dt className="sr-only">Ngày hiệu lực</dt>
            <dd className="text-slate-500">Hiệu lực {formatDate(law.ngay_hieu_luc)}</dd>
          </div>
        )}
        <div>
          <dt className="sr-only">Số Điều</dt>
          <dd className="font-semibold text-[#0F172A]">{law.stats.articles} Điều</dd>
        </div>
      </dl>
    </Link>
  );
};
