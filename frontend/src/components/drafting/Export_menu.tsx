import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, Download, FileText, Loader2, Printer } from 'lucide-react';
import { cn } from '@/components/ui/button';

// Nút "Xuất văn bản": PDF (qua hộp thoại in của trình duyệt) hoặc Word (.docx).

interface ExportMenuProps {
  onPdf: () => Promise<void> | void;
  onDocx: () => Promise<void> | void;
}

export const Export_menu: React.FC<ExportMenuProps> = ({ onPdf, onDocx }) => {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<'pdf' | 'docx' | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const run = async (kind: 'pdf' | 'docx') => {
    setBusy(kind);
    setOpen(false);
    try {
      await (kind === 'pdf' ? onPdf() : onDocx());
    } finally {
      setBusy(null);
    }
  };

  const items = [
    { kind: 'pdf' as const, icon: Printer, title: 'PDF', hotkey: 'Ctrl P' },
    { kind: 'docx' as const, icon: FileText, title: 'Word (.docx)' },
  ];

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="inline-flex h-9 items-center gap-2 rounded-lg bg-[#0F172A] px-3.5 text-sm font-semibold text-white shadow-xs transition-colors hover:bg-[#1E3A8A] cursor-pointer"
      >
        {busy ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
        <span className="hidden sm:inline">Xuất văn bản</span>
        <ChevronDown className={cn('size-3.5 opacity-70 transition-transform duration-300', open && 'rotate-180')} />
      </button>

      {open && (
        <div role="menu" className="dp-pop absolute right-0 top-full z-50 mt-2 w-48 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl">
          {items.map(({ kind, icon: Icon, title, hotkey }) => (
            <button
              key={kind}
              type="button"
              role="menuitem"
              onClick={() => run(kind)}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm font-semibold text-[#0F172A] transition-colors hover:bg-slate-50 cursor-pointer"
            >
              <Icon className="size-4 shrink-0 text-slate-500" />
              <span className="flex-1">{title}</span>
              {hotkey && <kbd className="font-mono text-[11px] font-medium text-slate-400">{hotkey}</kbd>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
