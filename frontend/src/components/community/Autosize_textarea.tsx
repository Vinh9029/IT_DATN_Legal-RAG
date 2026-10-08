import React, { useImperativeHandle, useLayoutEffect, useRef } from 'react';
import { cn } from '@/components/ui/button';

interface AutosizeTextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  maxHeight?: number;
  /** Ctrl/⌘ + Enter để gửi */
  onSubmitShortcut?: () => void;
}

export const Autosize_textarea = React.forwardRef<HTMLTextAreaElement, AutosizeTextareaProps>(({
  maxHeight = 320,
  onSubmitShortcut,
  className,
  value,
  onKeyDown,
  ...props
}, ref) => {
  const innerRef = useRef<HTMLTextAreaElement | null>(null);
  useImperativeHandle(ref, () => innerRef.current as HTMLTextAreaElement);

  useLayoutEffect(() => {
    const el = innerRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }, [value, maxHeight]);

  return (
    <textarea
      ref={innerRef}
      rows={1}
      value={value}
      onKeyDown={(e) => {
        if (onSubmitShortcut && e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          onSubmitShortcut();
        }
        onKeyDown?.(e);
      }}
      className={cn('w-full resize-none bg-transparent outline-none placeholder:text-slate-400', className)}
      {...props}
    />
  );
});

Autosize_textarea.displayName = 'Autosize_textarea';
