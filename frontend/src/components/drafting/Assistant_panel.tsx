import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowUp, CornerUpLeft, RefreshCw, Redo2, Square, Trash2, Undo2, X } from 'lucide-react';
import { cn } from '@/components/ui/button';
import { Autosize_textarea } from '@/components/community/Autosize_textarea';
import { Thinking_indicator } from '@/components/Thinking_indicator';
import type { AssistantStatus } from '@/lib/drafting/ai-service';
import type { ChatMessage, DraftTemplate, FieldEdit, FieldValue, FieldValues } from '@/lib/drafting/types';
import { editStatus, type EditStatus } from '@/lib/drafting/use-draft-state';
import { inlineText } from '@/lib/drafting/document';

// Khung trò chuyện với trợ lý soạn thảo. AI sửa thẳng vào biểu mẫu; mỗi tin của AI kèm danh sách
// ô đã đổi (cũ → mới) để người dùng hoàn tác / áp dụng lại từng ô hoặc cả lượt.

const THINKING = ['Đang đọc biểu mẫu', 'Đang soạn nội dung', 'Đang đối chiếu thông tin bạn cung cấp'];

interface AssistantPanelProps {
  template: DraftTemplate;
  values: FieldValues;
  chat: ChatMessage[];
  status: AssistantStatus | null;
  pending: boolean;
  activeField: string | null;
  /** Nội dung đặt sẵn vào ô nhập (vd. bấm "Nhờ AI viết mục này") */
  prefill: { text: string; nonce: number } | null;
  onSend: (text: string) => void;
  onStop: () => void;
  onRevert: (messageId: string, fields?: string[]) => void;
  onReapply: (messageId: string, fields?: string[]) => void;
  onSelectField: (field: string) => void;
  onClearFocus: () => void;
  onClearChat: () => void;
  onRecheck: () => void;
  onClose?: () => void;
}

const MAX_PREVIEW = 140;

function preview(template: DraftTemplate, field: string, value: FieldValue): string {
  const def = template.fields.find((f) => f.id === field);
  const text = def ? (inlineText(def, { [field]: Array.isArray(value) ? value.join('; ') : value }) ?? '') : String(value);
  return text.length > MAX_PREVIEW ? `${text.slice(0, MAX_PREVIEW - 1)}…` : text;
}

const STATUS_LABEL: Record<EditStatus, string> = {
  applied: 'Đã áp dụng',
  reverted: 'Đã hoàn tác',
  changed: 'Bạn đã sửa tiếp',
};

export const Assistant_panel: React.FC<AssistantPanelProps> = ({
  template,
  values,
  chat,
  status,
  pending,
  activeField,
  prefill,
  onSend,
  onStop,
  onRevert,
  onReapply,
  onSelectField,
  onClearFocus,
  onClearChat,
  onRecheck,
  onClose,
}) => {
  const [input, setInput] = useState('');
  const [confirmClear, setConfirmClear] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const available = !!status?.available;
  const focus = template.fields.find((f) => f.id === activeField);

  // Nội dung đặt sẵn mới → thay vào ô nhập (điều chỉnh state ngay khi render, không qua effect)
  const [seenPrefill, setSeenPrefill] = useState(prefill);
  if (prefill !== seenPrefill) {
    setSeenPrefill(prefill);
    if (prefill) setInput(prefill.text);
  }

  useEffect(() => {
    if (!prefill) return;
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    });
  }, [prefill]);

  // Luôn cuộn xuống tin mới nhất
  useLayoutEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, [chat.length, pending]);

  const submit = (text = input) => {
    const t = text.trim();
    if (!t || pending || !available) return;
    onSend(t);
    setInput('');
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-white">
      {/* Đầu khung */}
      <div className="flex h-14 shrink-0 items-center gap-2 border-b border-slate-200 px-4">
        <div className="min-w-0 flex-1">
          <p className="font-display text-sm uppercase leading-none">Trợ lý soạn thảo</p>
          <p className="mt-1 flex items-center gap-1.5 text-xs text-slate-500">
            <span className={cn('size-1.5 rounded-full', status === null ? 'animate-pulse bg-slate-300' : available ? 'bg-emerald-500' : 'bg-slate-300')} />
            {status === null ? 'Đang kiểm tra…' : available ? 'Sẵn sàng' : 'Chưa kết nối'}
          </p>
        </div>
        {chat.length > 0 &&
          (confirmClear ? (
            <span className="dp-fade flex items-center gap-1 text-xs">
              <button type="button" onClick={() => {
                  onClearChat();
                  setConfirmClear(false);
                }} className="rounded-md px-2 py-1 font-semibold text-red-600 hover:bg-red-50 cursor-pointer">
                Xoá trò chuyện
              </button>
              <button type="button" onClick={() => setConfirmClear(false)} className="rounded-md px-2 py-1 text-slate-500 hover:bg-slate-100 cursor-pointer">
                Huỷ
              </button>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmClear(true)}
              aria-label="Xoá cuộc trò chuyện"
              title="Xoá cuộc trò chuyện (biểu mẫu giữ nguyên)"
              className="flex size-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-[#0F172A] cursor-pointer"
            >
              <Trash2 className="size-4" />
            </button>
          ))}
        {onClose && (
          <button type="button" onClick={onClose} aria-label="Đóng trợ lý" className="flex size-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-[#0F172A] cursor-pointer">
            <X className="size-4" />
          </button>
        )}
      </div>

      {/* Tin nhắn */}
      <div ref={listRef} className="lib-scroll min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-5">
        {chat.length === 0 && (
          <div className="dp-fade">
            <p className="text-sm leading-relaxed text-slate-600">Kể sự việc, trợ lý sẽ điền vào đúng ô trên biểu mẫu.</p>
            {available && template.aiSuggestions && (
              <div className="mt-5 space-y-2">
                {template.aiSuggestions.map((s, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => submit(s)}
                    style={{ animationDelay: `${120 + i * 70}ms` }}
                    className="community-rise block w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-left text-sm leading-relaxed text-slate-600 transition-all duration-200 hover:-translate-y-0.5 hover:border-[#2563EB]/40 hover:text-[#0F172A] hover:shadow-sm cursor-pointer"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {chat.map((m) =>
          m.role === 'user' ? (
            <div key={m.id} className="community-rise flex justify-end">
              <div className="max-w-[88%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-[#0F172A] px-3.5 py-2.5 text-sm leading-relaxed text-white">{m.content}</div>
            </div>
          ) : (
            <Assistant_message key={m.id} message={m} template={template} values={values} onRevert={onRevert} onReapply={onReapply} onSelectField={onSelectField} />
          ),
        )}

        {pending && <Thinking_indicator phrases={THINKING} interval={2600} className="text-sm" />}
      </div>

      {/* Ô nhập */}
      <div className="shrink-0 border-t border-slate-200 p-3">
        {!available && status !== null ? (
          <div className="dp-fade rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
            <p>Trợ lý cần backend và LM Studio đang chạy. Bạn vẫn điền và xuất văn bản bình thường.</p>
            <button type="button" onClick={onRecheck} className="mt-2 inline-flex items-center gap-1.5 font-semibold text-[#2563EB] hover:text-[#1D4ED8] cursor-pointer">
              <RefreshCw className="size-3.5" />
              Kiểm tra lại
            </button>
          </div>
        ) : (
          <>
            <div className="collapse-grid" data-open={!!focus}>
              <div>
                {focus && (
                  <div className="mb-2 flex items-center gap-1.5 text-xs text-slate-500">
                    <CornerUpLeft className="size-3.5 shrink-0" />
                    <span className="truncate">
                      Đang chọn: <button type="button" onClick={() => onSelectField(focus.id)} className="font-semibold text-[#0F172A] hover:text-[#2563EB] cursor-pointer">{focus.label}</button>
                    </span>
                    <button type="button" onClick={onClearFocus} aria-label="Bỏ chọn ô" className="rounded p-0.5 text-slate-400 hover:text-[#0F172A] cursor-pointer">
                      <X className="size-3" />
                    </button>
                  </div>
                )}
              </div>
            </div>
            <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 transition-all focus-within:border-[#2563EB] focus-within:ring-4 focus-within:ring-[#2563EB]/10">
              <Autosize_textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    submit();
                  }
                }}
                maxHeight={180}
                disabled={!available}
                placeholder={focus ? `Yêu cầu cho mục "${focus.label}"…` : 'Kể sự việc hoặc yêu cầu sửa…'}
                aria-label="Nhắn cho trợ lý soạn thảo"
                className="py-1.5 text-sm leading-relaxed"
              />
              {pending ? (
                <button type="button" onClick={onStop} aria-label="Dừng" className="mb-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-[#0F172A] transition-colors hover:bg-slate-200 cursor-pointer">
                  <Square className="size-3.5 fill-current" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => submit()}
                  disabled={!input.trim() || !available}
                  aria-label="Gửi"
                  className="mb-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-[#2563EB] text-white transition-all hover:bg-[#1D4ED8] disabled:bg-slate-200 disabled:text-slate-400 cursor-pointer disabled:cursor-default"
                >
                  <ArrowUp className="size-4" />
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

// ── Một tin của AI + các ô đã sửa ────────────────────────────────

const Assistant_message: React.FC<{
  message: ChatMessage;
  template: DraftTemplate;
  values: FieldValues;
  onRevert: AssistantPanelProps['onRevert'];
  onReapply: AssistantPanelProps['onReapply'];
  onSelectField: AssistantPanelProps['onSelectField'];
}> = ({ message, template, values, onRevert, onReapply, onSelectField }) => {
  const edits = message.edits ?? [];
  const statuses = edits.map((e) => editStatus(e, values));
  const anyApplied = statuses.includes('applied');
  const anyReverted = statuses.includes('reverted');
  const label = (field: string) => template.fields.find((f) => f.id === field)?.label ?? field;

  return (
    <div className="community-rise">
      <p className={cn('whitespace-pre-wrap text-sm leading-relaxed', message.error ? 'text-red-600' : 'text-[#0F172A]')}>{message.content}</p>

      {edits.length > 0 && (
        <div className="mt-3 overflow-hidden rounded-xl border border-slate-200">
          <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/70 px-3 py-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              {edits.length} mục đã sửa
            </span>
            <span className="flex items-center gap-1">
              {anyApplied && (
                <button type="button" onClick={() => onRevert(message.id)} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold text-[#0F172A] transition-colors hover:bg-white cursor-pointer">
                  <Undo2 className="size-3.5" />
                  Hoàn tác
                </button>
              )}
              {anyReverted && (
                <button type="button" onClick={() => onReapply(message.id)} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold text-[#2563EB] transition-colors hover:bg-white cursor-pointer">
                  <Redo2 className="size-3.5" />
                  Áp dụng lại
                </button>
              )}
            </span>
          </div>
          <ul className="divide-y divide-slate-100">
            {edits.map((e, i) => (
              <Edit_row
                key={e.field}
                edit={e}
                label={label(e.field)}
                status={statuses[i]}
                template={template}
                onOpen={() => onSelectField(e.field)}
                onToggle={() => (statuses[i] === 'applied' ? onRevert(message.id, [e.field]) : onReapply(message.id, [e.field]))}
              />
            ))}
          </ul>
        </div>
      )}

      {message.dropped && message.dropped.length > 0 && (
        <ul className="mt-2 space-y-1">
          {message.dropped.map((d, i) => (
            <li key={i} className="text-xs leading-relaxed text-slate-500">
              Không điền <span className="font-semibold text-slate-600">{label(d.field)}</span>: {d.reason.charAt(0).toLowerCase() + d.reason.slice(1)}.
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

const Edit_row: React.FC<{
  edit: FieldEdit;
  label: string;
  status: EditStatus;
  template: DraftTemplate;
  onOpen: () => void;
  onToggle: () => void;
}> = ({ edit, label, status, template, onOpen, onToggle }) => {
  const before = preview(template, edit.field, edit.before);
  const after = preview(template, edit.field, edit.after);
  return (
    <li className={cn('group px-3 py-2.5 transition-colors', status !== 'applied' && 'bg-slate-50/60')}>
      <div className="flex items-center gap-2">
        <button type="button" onClick={onOpen} className="min-w-0 flex-1 truncate text-left text-xs font-semibold text-[#0F172A] hover:text-[#2563EB] cursor-pointer">
          {label}
        </button>
        <span className={cn('text-xs', status === 'applied' ? 'text-slate-400' : status === 'reverted' ? 'text-amber-600' : 'text-slate-400 italic')}>{STATUS_LABEL[status]}</span>
        {status !== 'changed' && (
          <button
            type="button"
            onClick={onToggle}
            aria-label={status === 'applied' ? `Hoàn tác ${label}` : `Áp dụng lại ${label}`}
            title={status === 'applied' ? 'Hoàn tác mục này' : 'Áp dụng lại mục này'}
            className="flex size-6 items-center justify-center rounded-md text-slate-400 opacity-60 transition-all hover:bg-white hover:text-[#0F172A] group-hover:opacity-100 cursor-pointer"
          >
            {status === 'applied' ? <Undo2 className="size-3.5" /> : <Redo2 className="size-3.5" />}
          </button>
        )}
      </div>
      <div className={cn('mt-1 space-y-0.5 text-xs leading-relaxed transition-opacity', status === 'reverted' && 'opacity-60')}>
        {before && <p className="text-slate-400 line-through decoration-slate-300">{before}</p>}
        <p className={cn(status === 'applied' ? 'text-slate-700' : 'text-slate-500')}>{after || <span className="italic">(để trống)</span>}</p>
      </div>
    </li>
  );
};
