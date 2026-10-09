import React, { useMemo, useState } from 'react';
import { ChevronRight, Sparkles } from 'lucide-react';
import { cn } from '@/components/ui/button';
import type { DraftTemplate, FieldValues } from '@/lib/drafting/types';
import { isFilled } from '@/lib/drafting/values';

// Cột trái của trình soạn thảo: mục lục các ô theo nhóm + hướng dẫn của ô đang chọn.

interface FieldOutlineProps {
  template: DraftTemplate;
  values: FieldValues;
  activeField: string | null;
  onSelect: (field: string) => void;
  /** Có = trợ lý AI dùng được → hiện nút "Nhờ AI viết mục này" */
  onAskAi?: (field: string) => void;
}

export const Field_outline: React.FC<FieldOutlineProps> = ({ template, values, activeField, onSelect, onAskAi }) => {
  const active = template.fields.find((f) => f.id === activeField) ?? null;
  const groups = useMemo(
    () =>
      template.groups.map((g) => {
        const fields = template.fields.filter((f) => f.group === g.id);
        const required = fields.filter((f) => f.required);
        return { ...g, fields, done: required.filter((f) => isFilled(values[f.id])).length, total: required.length };
      }),
    [template, values],
  );

  // Mở sẵn nhóm đầu tiên còn thiếu; nhóm của ô đang chọn luôn mở
  const [open, setOpen] = useState<Set<string>>(() => new Set([groups.find((g) => g.done < g.total)?.id ?? groups[0]?.id].filter(Boolean) as string[]));
  const [seenActive, setSeenActive] = useState(active?.id);
  if (active?.id !== seenActive) {
    setSeenActive(active?.id);
    if (active && !open.has(active.group)) setOpen(new Set(open).add(active.group));
  }

  const toggle = (id: string) =>
    setOpen((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="lib-scroll min-h-0 flex-1 overflow-y-auto px-3 py-4">
        <p className="px-2 text-xs font-semibold uppercase tracking-wider text-slate-400">Mục cần điền</p>
        <nav className="mt-2 space-y-0.5" aria-label="Các mục của biểu mẫu">
          {groups.map((g) => {
            const isOpen = open.has(g.id);
            const complete = g.total > 0 && g.done === g.total;
            return (
              <div key={g.id}>
                <button
                  type="button"
                  onClick={() => toggle(g.id)}
                  aria-expanded={isOpen}
                  className="group flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm font-semibold text-[#0F172A] transition-colors hover:bg-slate-100 cursor-pointer"
                >
                  <ChevronRight className={cn('size-3.5 shrink-0 text-slate-400 transition-transform duration-300', isOpen && 'rotate-90')} />
                  <span className="min-w-0 flex-1 truncate">{g.label}</span>
                  {g.total > 0 && (
                    <span className={cn('font-mono text-xs font-medium tabular-nums', complete ? 'text-[#2563EB]' : 'text-slate-400')}>
                      {g.done}/{g.total}
                    </span>
                  )}
                </button>
                <div className="collapse-grid" data-open={isOpen}>
                  <div>
                    <ul className="mb-1 ml-[15px] border-l border-slate-200 py-0.5">
                      {g.fields.map((f) => {
                        const filled = isFilled(values[f.id]);
                        const isActive = f.id === activeField;
                        return (
                          <li key={f.id}>
                            <button
                              type="button"
                              onClick={() => onSelect(f.id)}
                              className={cn(
                                '-ml-px flex w-full items-center gap-2.5 border-l-2 py-1.5 pl-3 pr-2 text-left text-sm transition-colors cursor-pointer',
                                isActive ? 'border-[#2563EB] bg-[#2563EB]/5 text-[#2563EB]' : 'border-transparent text-slate-600 hover:text-[#0F172A]',
                              )}
                            >
                              <span
                                aria-hidden
                                className={cn(
                                  'size-2 shrink-0 rounded-full transition-all duration-300',
                                  filled ? 'scale-100 bg-[#2563EB]' : f.required ? 'border-[1.5px] border-slate-400' : 'border border-dashed border-slate-300',
                                )}
                              />
                              <span className="min-w-0 flex-1 truncate">{f.label}</span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                </div>
              </div>
            );
          })}
        </nav>
      </div>

      {/* Hướng dẫn của ô đang chọn */}
      <div className="collapse-grid border-t border-slate-200" data-open={!!active}>
        <div>
          {active && (
            <div key={active.id} className="dp-fade px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Đang điền</p>
              <p className="mt-1 font-semibold text-[#0F172A]">{active.label}</p>
              {active.hint && <p className="lib-scroll mt-2 max-h-40 overflow-y-auto pr-1 text-sm leading-relaxed text-slate-600">{active.hint}</p>}
              {onAskAi && (active.kind === 'textarea' || active.kind === 'list') && (
                <button
                  type="button"
                  onClick={() => onAskAi(active.id)}
                  className="group mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-[#2563EB] transition-colors hover:text-[#1D4ED8] cursor-pointer"
                >
                  <Sparkles className="size-4 transition-transform duration-300 group-hover:rotate-12" />
                  Nhờ AI viết mục này
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
