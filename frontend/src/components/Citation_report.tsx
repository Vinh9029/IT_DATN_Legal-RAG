import React, { useMemo, useState } from 'react';
import { ShieldCheck, AlertTriangle, XCircle, HelpCircle, ChevronDown, Wrench } from 'lucide-react';
import type { CitationCheck, CitationReport } from '@/lib/session-store';

/**
 * Stage 6 — hiển thị kết quả kiểm chứng trích dẫn dưới câu trả lời.
 * Gộp các lần trích cùng một Điều; trạng thái xấu nhất đại diện cho cả nhóm.
 */

type Status = CitationCheck['status'];

const STATUS_META: Record<Status, { label: string; icon: React.ElementType; cls: string; rank: number }> = {
  invalid: { label: 'Không hợp lệ', icon: XCircle, rank: 0,
    cls: 'bg-[#FEE2E2] text-[#DC2626] border-[#DC2626]/20 dark:bg-red-950/40 dark:text-red-300' },
  unverifiable: { label: 'Không kiểm chứng được', icon: HelpCircle, rank: 1,
    cls: 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600' },
  warning: { label: 'Lưu ý', icon: AlertTriangle, rank: 2,
    cls: 'bg-[#FEF3C7] text-[#B45309] border-[#D97706]/20 dark:bg-amber-950/40 dark:text-amber-300' },
  valid: { label: 'Hợp lệ', icon: ShieldCheck, rank: 3,
    cls: 'bg-[#DCFCE7] text-[#16A34A] border-[#16A34A]/20 dark:bg-green-950/40 dark:text-green-300' },
};

function citationLabel(c: CitationCheck): string {
  const parts = [c.diem && `điểm ${c.diem}`, c.khoan && `khoản ${c.khoan}`, `Điều ${c.dieu}`].filter(Boolean);
  const doc = [c.loai, c.so_hieu].filter(Boolean).join(' ');
  return `${parts.join(' ')}${doc ? ` · ${doc}` : ''}`;
}

interface Props {
  report: CitationReport;
  isDark?: boolean;
}

export const Citation_report: React.FC<Props> = ({ report, isDark = false }) => {
  const [open, setOpen] = useState(false);

  const groups = useMemo(() => {
    const map = new Map<string, { item: CitationCheck; reasons: Set<string>; n: number }>();
    for (const c of report.citations || []) {
      const key = `${c.doc_id || c.text}|${c.dieu}|${c.khoan || ''}`;
      const g = map.get(key);
      if (!g) {
        map.set(key, { item: c, reasons: new Set(c.reason_texts || []), n: 1 });
      } else {
        g.n += 1;
        (c.reason_texts || []).forEach((r) => g.reasons.add(r));
        if (STATUS_META[c.status].rank < STATUS_META[g.item.status].rank) g.item = c;
      }
    }
    return [...map.values()].sort((a, b) => STATUS_META[a.item.status].rank - STATUS_META[b.item.status].rank);
  }, [report]);

  if (!report || report.n_citations === 0) return null;

  const counts = report.counts || {};
  const repaired = report.repair?.accepted;

  return (
    <div className={`mt-4 rounded-xl border text-sm ${isDark ? 'border-slate-800 bg-slate-950/40' : 'border-slate-200 bg-slate-50/70'}`}>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 cursor-pointer"
        aria-expanded={open}
      >
        <span className="flex flex-wrap items-center gap-1.5 font-semibold">
          <ShieldCheck className="size-4 text-[#2563EB]" />
          <span className={isDark ? 'text-slate-200' : 'text-slate-700'}>Kiểm chứng trích dẫn</span>
          {(['valid', 'warning', 'invalid', 'unverifiable'] as Status[]).map((s) =>
            counts[s] ? (
              <span key={s} className={`rounded-md border px-1.5 py-0.5 text-[11px] font-semibold ${STATUS_META[s].cls}`}>
                {counts[s]} {STATUS_META[s].label.toLowerCase()}
              </span>
            ) : null
          )}
        </span>
        <ChevronDown className={`size-4 shrink-0 transition-transform ${open ? 'rotate-180' : ''} ${isDark ? 'text-slate-400' : 'text-slate-500'}`} />
      </button>

      {repaired && (
        <p className={`flex items-center gap-1.5 px-3 pb-2 text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
          <Wrench className="size-3.5" />
          Câu trả lời đã được tự động viết lại để sửa {report.repair?.invalid_before} trích dẫn không hợp lệ.
        </p>
      )}

      {open && (
        <ul className={`space-y-1.5 border-t px-3 py-2 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
          {groups.map(({ item, reasons, n }) => {
            const meta = STATUS_META[item.status];
            const Icon = meta.icon;
            return (
              <li key={`${item.doc_id}-${item.dieu}-${item.khoan}-${item.start}`} className="flex items-start gap-2">
                <span className={`mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-semibold ${meta.cls}`}>
                  <Icon className="size-3" />
                  {meta.label}
                </span>
                <div className="min-w-0">
                  <p className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>
                    {citationLabel(item)}
                    {n > 1 && <span className="ml-1 text-xs text-slate-400">×{n}</span>}
                  </p>
                  {item.title && (
                    <p className="truncate text-xs text-slate-500" title={item.title}>{item.title}</p>
                  )}
                  {reasons.size > 0 && (
                    <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>{[...reasons].join(' · ')}</p>
                  )}
                </div>
              </li>
            );
          })}
          <li className="pt-1 text-[11px] text-slate-400">
            Đối chiếu với cơ sở dữ liệu văn bản của hệ thống; “không kiểm chứng được” không có nghĩa là trích dẫn sai.
          </li>
        </ul>
      )}
    </div>
  );
};
