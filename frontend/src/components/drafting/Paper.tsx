import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/components/ui/button';
import { Editable, type EditableHandle } from './Editable';
import { blankFor, conditionHolds, derivedText, dots, inlineText, isOmitted } from '@/lib/drafting/document';
import { MOTTO, SLOGAN } from '@/lib/drafting/page-format';
import type { Block, DraftTemplate, FieldDef, FieldValue, FieldValues, Run } from '@/lib/drafting/types';
import { asList, asText, dateWords, formatMoney, moneyDigits, parseIsoDate, todayIso } from '@/lib/drafting/values';

// Trang giấy A4 dựng từ template. Có `onChange` → điền được ngay trên giấy; không có → chỉ xem
// (ảnh thu nhỏ ở trang chọn mẫu). Bản in/Word dựng từ cùng template qua lib/drafting/document.ts.

interface PaperProps {
  template: DraftTemplate;
  values: FieldValues;
  onChange?: (field: string, value: FieldValue) => void;
  activeField?: string | null;
  onFocusField?: (field: string | null) => void;
  /** Ô cần nháy sáng (AI vừa sửa / hoàn tác); đổi nonce để nháy lại */
  flash?: { fields: string[]; nonce: number };
  className?: string;
  style?: React.CSSProperties;
}

interface Ctx {
  fields: Map<string, FieldDef>;
  values: FieldValues;
  editable: boolean;
  activeField?: string | null;
  onChange: (field: string, value: FieldValue) => void;
  onFocusField: (field: string | null) => void;
}

const noop = () => {};

export const Paper = React.forwardRef<HTMLDivElement, PaperProps>(
  ({ template, values, onChange, activeField, onFocusField, flash, className, style }, ref) => {
    const rootRef = useRef<HTMLDivElement | null>(null);
    const ctx: Ctx = {
      fields: new Map(template.fields.map((f) => [f.id, f])),
      values,
      editable: !!onChange,
      activeField,
      onChange: onChange ?? noop,
      onFocusField: onFocusField ?? noop,
    };

    // Nháy sáng ô vừa đổi: gỡ class rồi gắn lại để animation chạy lại kể cả khi cùng một ô
    useEffect(() => {
      const root = rootRef.current;
      if (!root || !flash?.nonce) return;
      for (const id of flash.fields) {
        root.querySelectorAll<HTMLElement>(`[data-field="${CSS.escape(id)}"]`).forEach((el) => {
          el.classList.remove('dp-flash');
          void el.offsetWidth;
          el.classList.add('dp-flash');
        });
      }
    }, [flash?.nonce, flash?.fields]);

    return (
      <div
        ref={(el) => {
          rootRef.current = el;
          if (typeof ref === 'function') ref(el);
          else if (ref) ref.current = el;
        }}
        className={cn('dp-paper', className)}
        style={style}
        lang="vi"
      >
        {template.blocks.map((block, i) => (
          <Block_view key={i} block={block} ctx={ctx} />
        ))}
      </div>
    );
  },
);

Paper.displayName = 'Paper';

// ── Khối ─────────────────────────────────────────────────────────

const Block_view: React.FC<{ block: Block; ctx: Ctx }> = ({ block, ctx }) => {
  // Mục "nếu có" còn trống: vẫn điền được nhưng mờ đi, vì sẽ không có trong bản in
  const omitted = ctx.editable && isOmitted(block, ctx.values);
  const optionalTitle = omitted ? 'Mục không bắt buộc — để trống thì không in ra' : undefined;

  switch (block.type) {
    case 'form-code':
      return (
        <div className="mb-2 text-right italic" style={{ fontSize: '10pt', lineHeight: 1.3 }}>
          {block.lines.map((l, i) => (
            <div key={i}>{l}</div>
          ))}
        </div>
      );

    case 'motto':
      return (
        <div className="mb-1.5 text-center font-bold">
          <div style={{ fontSize: '13pt' }}>{MOTTO}</div>
          <div style={{ fontSize: '14pt' }}>
            <span className="inline-block border-b border-black pb-px">{SLOGAN}</span>
          </div>
        </div>
      );

    case 'title':
      return (
        <div className="mb-3 mt-5 text-center">
          <div className="font-bold" style={{ fontSize: '14pt' }}>
            {block.text}
          </div>
          {block.sub && <div>{block.sub.map((r, i) => <Run_view key={i} run={r} ctx={ctx} />)}</div>}
        </div>
      );

    case 'para':
      return (
        <p
          title={optionalTitle}
          className={cn(block.indent && 'dp-indent', block.gap && 'dp-gap', block.bold && 'font-bold', block.italic && 'italic', omitted && 'dp-optional')}
          style={{ textAlign: block.align ?? 'left' }}
        >
          {block.runs.map((r, i) => (
            <Run_view key={i} run={r} ctx={ctx} />
          ))}
        </p>
      );

    case 'field': {
      const field = ctx.fields.get(block.field);
      if (!field) return null;
      return (
        <div title={optionalTitle} className={cn(omitted && 'dp-optional')} style={block.indent ? { paddingLeft: '10mm' } : undefined}>
          {block.note && <Note n={block.note} field={field.id} ctx={ctx} />}
          {field.kind === 'list' ? <List_field field={field} ctx={ctx} /> : <Block_text_field field={field} ctx={ctx} />}
        </div>
      );
    }

    case 'signatures': {
      const cols = block.parties.length === 1 ? [null, block.parties[0]] : block.parties;
      return (
        <div className="mt-5 grid break-inside-avoid" style={{ gridTemplateColumns: `repeat(${cols.length}, minmax(0, 1fr))` }}>
          {cols.map((p, i) =>
            p ? (
              <div key={i} className="px-2 text-center">
                <div className="font-bold uppercase">
                  {p.title}
                  {p.note && <Note n={p.note} field={p.nameField} ctx={ctx} />}
                </div>
                {p.caption && <div className="italic">{p.caption}</div>}
                <div style={{ height: '22mm' }} />
                {p.nameField && ctx.fields.get(p.nameField) && (
                  <div className="font-bold">
                    <Inline_field field={ctx.fields.get(p.nameField)!} ctx={ctx} bold placeholder="Họ và tên" />
                  </div>
                )}
              </div>
            ) : (
              <div key={i} />
            ),
          )}
        </div>
      );
    }
  }
};

// ── Đoạn chữ trong dòng ──────────────────────────────────────────

const Run_view: React.FC<{ run: Run; ctx: Ctx }> = ({ run, ctx }) => {
  if (typeof run === 'string') return <>{run}</>;
  if ('derived' in run) {
    const text = derivedText(run, ctx.values);
    return (
      <span title="Tự điền theo số tiền" className={cn(!text && 'text-slate-400')}>
        {text ?? dots(16)}
      </span>
    );
  }
  if ('field' in run) {
    const field = ctx.fields.get(run.field);
    if (!field) return null;
    return (
      <>
        {run.note && <Note n={run.note} field={field.id} ctx={ctx} />}
        {field.kind === 'date' ? <Date_field field={field} ctx={ctx} /> : <Inline_field field={field} ctx={ctx} bold={run.bold} />}
      </>
    );
  }
  if ('note' in run) return <Note n={run.note} ctx={ctx} />;
  if (!conditionHolds(run, ctx.values)) return null;
  return <span className={cn(run.bold && 'font-bold', run.italic && 'italic')}>{run.text}</span>;
};

/** Số chú thích (n) của mẫu chính thức: bấm vào để tới ô và xem hướng dẫn */
const Note: React.FC<{ n: number; field?: string; ctx: Ctx }> = ({ n, field, ctx }) => {
  if (!ctx.editable) return null;
  return (
    <span
      className="dp-note"
      title={field ? 'Xem hướng dẫn ghi mục này' : `Chú thích (${n}) của mẫu`}
      onMouseDown={(e) => {
        if (!field) return;
        e.preventDefault();
        ctx.onFocusField(field);
      }}
    >
      ({n})
    </span>
  );
};

// ── Ô điền ───────────────────────────────────────────────────────

const Static_value: React.FC<{ field: FieldDef; values: FieldValues; bold?: boolean }> = ({ field, values, bold }) => {
  const text = inlineText(field, values);
  return <span className={cn(bold && text && 'font-bold')}>{text ?? blankFor(field)}</span>;
};

const Inline_field: React.FC<{ field: FieldDef; ctx: Ctx; bold?: boolean; placeholder?: string }> = ({ field, ctx, bold, placeholder }) => {
  if (!ctx.editable) return <Static_value field={field} values={ctx.values} bold={bold} />;
  const raw = asText(ctx.values[field.id]);
  const money = field.kind === 'money';
  return (
    <Editable
      fieldId={field.id}
      label={field.label}
      value={raw}
      display={money ? formatMoney(raw) : raw}
      sanitize={money ? (t) => t.replace(/[^\d.\s]/g, '') : undefined}
      onChange={(t) => ctx.onChange(field.id, money ? moneyDigits(t) : t)}
      inputMode={money ? 'numeric' : undefined}
      placeholder={placeholder ?? field.placeholder ?? ''}
      minWidthEm={Math.min(18, Math.max(3, (field.blank ?? 12) * 0.5))}
      active={ctx.activeField === field.id}
      bold={bold}
      onFocus={() => ctx.onFocusField(field.id)}
    />
  );
};

const Block_text_field: React.FC<{ field: FieldDef; ctx: Ctx }> = ({ field, ctx }) => {
  const raw = asText(ctx.values[field.id]);
  if (!ctx.editable) {
    return raw.trim() ? <div className="whitespace-pre-wrap text-justify">{raw}</div> : <div>{dots(30)}</div>;
  }
  return (
    <Editable
      fieldId={field.id}
      label={field.label}
      value={raw}
      onChange={(t) => ctx.onChange(field.id, t)}
      multiline
      placeholder={field.placeholder ?? ''}
      active={ctx.activeField === field.id}
      className="text-justify"
      onFocus={() => ctx.onFocusField(field.id)}
    />
  );
};

const List_field: React.FC<{ field: FieldDef; ctx: Ctx }> = ({ field, ctx }) => {
  const stored = asList(ctx.values[field.id]);
  const items = stored.length ? stored : [''];
  const refs = useRef<(EditableHandle | null)[]>([]);
  // Thêm/xoá dòng: chờ danh sách vẽ lại rồi mới đặt con trỏ vào dòng mới
  const pendingFocus = useRef<{ index: number; at: 'start' | 'end' } | null>(null);

  useLayoutEffect(() => {
    const p = pendingFocus.current;
    if (!p) return;
    pendingFocus.current = null;
    refs.current[p.index]?.focus(p.at);
  }, [items.length]);

  if (!ctx.editable) {
    const filled = stored.filter((s) => s.trim());
    return (
      <>
        {(filled.length ? filled : Array.from({ length: field.blank ?? 2 }, () => '')).map((item, i) => (
          <p key={i}>
            {i + 1}. {item || dots(30)}
          </p>
        ))}
      </>
    );
  }

  const commit = (next: string[]) => ctx.onChange(field.id, next.length === 1 && next[0] === '' ? [] : next);

  return (
    <div data-field={field.id}>
      {items.map((item, i) => (
        <p key={i} className="flex gap-[0.35em]">
          <span className="shrink-0 select-none">{i + 1}.</span>
          <Editable
            ref={(h) => {
              refs.current[i] = h;
            }}
            fieldId={i === 0 ? field.id : undefined}
            label={`${field.label} — dòng ${i + 1}`}
            value={item}
            onChange={(t) => {
              const next = [...items];
              next[i] = t;
              commit(next);
            }}
            placeholder={i === 0 ? (field.placeholder ?? '') : ''}
            active={ctx.activeField === field.id}
            className="min-w-0 flex-1"
            onFocus={() => ctx.onFocusField(field.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                // Enter = thêm mục mới ngay dưới
                const next = [...items];
                next.splice(i + 1, 0, '');
                pendingFocus.current = { index: i + 1, at: 'start' };
                ctx.onChange(field.id, next);
              } else if (e.key === 'Backspace' && item === '' && items.length > 1) {
                e.preventDefault();
                pendingFocus.current = { index: Math.max(0, i - 1), at: 'end' };
                commit(items.filter((_, j) => j !== i));
              } else if (e.key === 'ArrowUp' && i > 0) {
                e.preventDefault();
                refs.current[i - 1]?.focus('end');
              } else if (e.key === 'ArrowDown' && i < items.length - 1) {
                e.preventDefault();
                refs.current[i + 1]?.focus('end');
              }
            }}
          />
        </p>
      ))}
    </div>
  );
};

const Date_field: React.FC<{ field: FieldDef; ctx: Ctx }> = ({ field, ctx }) => {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLSpanElement>(null);
  const value = asText(ctx.values[field.id]);
  const words = dateWords(value);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !wrapRef.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  if (!ctx.editable) return <Static_value field={field} values={ctx.values} />;

  const set = (v: string) => ctx.onChange(field.id, v);

  return (
    <span ref={wrapRef} className="relative">
      <span
        role="button"
        tabIndex={0}
        aria-label={`${field.label}: ${words ?? 'chưa chọn'}`}
        aria-expanded={open}
        data-field={field.id}
        data-active={ctx.activeField === field.id || undefined}
        className="dp-field cursor-pointer"
        onFocus={() => ctx.onFocusField(field.id)}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setOpen((o) => !o);
          } else if (e.key === 'Escape') setOpen(false);
        }}
      >
        {words ?? <span className="text-slate-400">{blankFor(field)}</span>}
      </span>
      {open && (
        <span
          className="dp-pop absolute left-0 top-full z-30 mt-2 flex w-60 flex-col gap-2 rounded-xl border border-slate-200 bg-white p-3 font-sans text-sm not-italic text-[#0F172A] shadow-xl"
          style={{ textIndent: 0, fontWeight: 400, transformOrigin: 'top left' }}
          onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}
        >
          <input
            type="date"
            autoFocus
            value={parseIsoDate(value) ? value : ''}
            onChange={(e) => set(e.target.value)}
            className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm focus:border-[#2563EB] focus:outline-none focus:ring-4 focus:ring-[#2563EB]/10"
          />
          <span className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                set(todayIso());
                setOpen(false);
              }}
              className="flex-1 rounded-lg bg-[#0F172A] px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-[#1E3A8A] cursor-pointer"
            >
              Hôm nay
            </button>
            {value && (
              <button
                type="button"
                onClick={() => {
                  set('');
                  setOpen(false);
                }}
                className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-[#0F172A] cursor-pointer"
              >
                <X className="size-3.5" />
                Để trống
              </button>
            )}
          </span>
        </span>
      )}
    </span>
  );
};
