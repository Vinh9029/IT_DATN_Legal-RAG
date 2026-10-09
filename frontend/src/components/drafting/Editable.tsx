import React, { useImperativeHandle, useLayoutEffect, useRef } from 'react';
import { cn } from '@/components/ui/button';

// Ô gõ chữ nằm ngay trong dòng văn bản (contentEditable) thay vì <input>: chữ dài tự xuống dòng
// như chữ viết trên giấy thật, nên trang soạn thảo trông giống hệt bản in.

export interface EditableHandle {
  focus: (at?: 'start' | 'end') => void;
  element: HTMLElement | null;
}

interface EditableProps {
  /** Giá trị chuẩn (đã lưu) */
  value: string;
  /** Chữ hiển thị khi KHÔNG đang gõ (vd. số tiền có dấu chấm); mặc định = value */
  display?: string;
  onChange: (value: string) => void;
  multiline?: boolean;
  placeholder?: string;
  /** Độ rộng tối thiểu khi trống, tính theo em */
  minWidthEm?: number;
  active?: boolean;
  bold?: boolean;
  label: string;
  inputMode?: React.HTMLAttributes<HTMLElement>['inputMode'];
  /** Lọc ký tự khi gõ (vd. chỉ cho số) */
  sanitize?: (text: string) => string;
  onFocus?: () => void;
  onBlur?: () => void;
  onKeyDown?: (e: React.KeyboardEvent<HTMLElement>) => void;
  className?: string;
  fieldId?: string;
}

const readText = (el: HTMLElement) => {
  const t = el.textContent ?? '';
  // Trình duyệt hay để lại một "\n" khi xoá hết chữ
  return t === '\n' ? '' : t;
};

function placeCaret(el: HTMLElement, at: 'start' | 'end') {
  const sel = window.getSelection();
  if (!sel) return;
  const range = document.createRange();
  range.selectNodeContents(el);
  range.collapse(at === 'start');
  sel.removeAllRanges();
  sel.addRange(range);
}

export const Editable = React.forwardRef<EditableHandle, EditableProps>(
  (
    { value, display, onChange, multiline, placeholder, minWidthEm, active, bold, label, inputMode, sanitize, onFocus, onBlur, onKeyDown, className, fieldId },
    ref,
  ) => {
    const elRef = useRef<HTMLSpanElement>(null);
    const focused = useRef(false);
    // Giá trị gần nhất do chính ô này phát ra — để phân biệt "mình vừa gõ" với "AI/hoàn tác đổi từ ngoài"
    const emitted = useRef<string | null>(null);
    const shown = display ?? value;

    useImperativeHandle(ref, () => ({
      focus: (at = 'end') => {
        const el = elRef.current;
        if (!el) return;
        el.focus({ preventScroll: true });
        placeCaret(el, at);
      },
      get element() {
        return elRef.current;
      },
    }));

    useLayoutEffect(() => {
      const el = elRef.current;
      if (!el) return;
      // Đang gõ và giá trị chính là cái vừa gõ → không đụng vào DOM (giữ nguyên con trỏ)
      if (focused.current && value === emitted.current) return;
      if (readText(el) !== shown) {
        el.textContent = shown;
        if (focused.current) placeCaret(el, 'end');
      }
    }, [shown, value]);

    const emit = (el: HTMLElement) => {
      let text = readText(el);
      if (!multiline && text.includes('\n')) text = text.replace(/\s*\n\s*/g, ' ');
      if (sanitize) text = sanitize(text);
      if (text !== readText(el)) {
        el.textContent = text;
        placeCaret(el, 'end');
      }
      emitted.current = text;
      onChange(text);
    };

    const empty = shown === '';

    return (
      <span
        ref={elRef}
        role="textbox"
        aria-label={label}
        aria-multiline={multiline || undefined}
        contentEditable="plaintext-only"
        suppressContentEditableWarning
        spellCheck={false}
        inputMode={inputMode}
        data-field={fieldId}
        data-empty={empty}
        data-block={multiline || undefined}
        data-active={active || undefined}
        data-placeholder={placeholder ?? ''}
        style={empty && minWidthEm ? { minWidth: `${minWidthEm}em` } : undefined}
        className={cn('dp-field', bold && 'font-bold', className)}
        onInput={(e) => emit(e.currentTarget)}
        onFocus={() => {
          focused.current = true;
          onFocus?.();
        }}
        onBlur={(e) => {
          focused.current = false;
          emitted.current = null;
          // Rời ô: hiện lại dạng đã định dạng (vd. 50000000 → 50.000.000)
          if (readText(e.currentTarget) !== shown) e.currentTarget.textContent = shown;
          onBlur?.();
        }}
        onKeyDown={(e) => {
          if (!multiline && e.key === 'Enter') e.preventDefault();
          onKeyDown?.(e);
        }}
        // Kéo thả chữ định dạng vào sẽ phá cấu trúc ô
        onDrop={(e) => e.preventDefault()}
      />
    );
  },
);

Editable.displayName = 'Editable';
