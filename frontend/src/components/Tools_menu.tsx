import React, { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, ChevronDown, FilePen, LayoutGrid, Library, Users } from 'lucide-react';
import { cn } from './ui/button';

// Các trang tiện ích (không phải mục cuộn của trang chủ), gom vào một menu để header không quá chật.
// Thêm trang mới = thêm một dòng.
const TOOL_LINKS = [
  { to: '/cong-dong', label: 'Cộng đồng', description: 'Hỏi đáp, chia sẻ tình huống pháp lý', icon: Users },
  { to: '/thu-vien', label: 'Thư viện', description: 'Đọc và tra cứu văn bản luật gốc', icon: Library },
  { to: '/soan-thao', label: 'Soạn thảo văn bản', description: 'Điền đơn theo mẫu, xuất PDF hoặc Word', icon: FilePen },
] as const;

const CLOSE_DELAY = 160;

/** `nav`: chữ "Tiện ích" trên thanh điều hướng (màn hình rộng). `icon`: nút biểu tượng (màn hình hẹp). */
export const Tools_menu: React.FC<{ variant: 'nav' | 'icon'; className?: string }> = ({ variant, className }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeTo = TOOL_LINKS.find((l) => location.pathname.startsWith(l.to))?.to;

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

  useEffect(() => () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
  }, []);

  // Rê chuột: mở ngay, đóng trễ một chút để kịp đưa chuột từ nút xuống menu
  const hover =
    variant === 'nav'
      ? {
          onMouseEnter: () => {
            if (closeTimer.current) clearTimeout(closeTimer.current);
            setOpen(true);
          },
          onMouseLeave: () => {
            closeTimer.current = setTimeout(() => setOpen(false), CLOSE_DELAY);
          },
        }
      : {};

  const go = (to: string) => {
    setOpen(false);
    navigate(to);
  };

  return (
    <div ref={ref} className={cn('relative', className)} {...hover}>
      {variant === 'nav' ? (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-haspopup="menu"
          className={cn(
            'relative flex items-center gap-1 font-semibold uppercase tracking-wide transition-colors hover:text-[#2563EB] cursor-pointer',
            'after:absolute after:-bottom-1.5 after:left-0 after:h-0.5 after:w-full after:origin-left after:rounded-full after:bg-[#2563EB] after:transition-transform after:duration-300',
            activeTo ? 'text-[#2563EB] after:scale-x-100' : 'after:scale-x-0',
          )}
        >
          Tiện ích
          <ChevronDown className={cn('size-4 transition-transform duration-300', open && 'rotate-180')} />
        </button>
      ) : (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-haspopup="menu"
          aria-label="Tiện ích"
          className={cn(
            'flex size-10 shrink-0 items-center justify-center rounded-lg border transition-colors cursor-pointer',
            activeTo || open ? 'border-[#2563EB] bg-[#2563EB]/10 text-[#2563EB]' : 'border-slate-200 bg-white text-slate-600 hover:border-[#2563EB] hover:text-[#2563EB]',
          )}
        >
          <LayoutGrid className="size-5" />
        </button>
      )}

      {open && (
        // pt-3 thay cho margin: vùng đệm vẫn thuộc menu nên rê chuột xuống không bị đóng
        <div className={cn('absolute top-full z-50 pt-3', variant === 'nav' ? '-left-6' : 'right-0')}>
          <div role="menu" className="dp-pop w-80 rounded-2xl border border-slate-200 bg-white p-2 normal-case tracking-normal shadow-xl" style={{ transformOrigin: variant === 'nav' ? 'top left' : 'top right' }}>
            {TOOL_LINKS.map(({ to, label, description, icon: Icon }, i) => {
              const active = to === activeTo;
              return (
                <a
                  key={to}
                  href={to}
                  role="menuitem"
                  onClick={(e) => {
                    e.preventDefault();
                    go(to);
                  }}
                  aria-current={active ? 'page' : undefined}
                  style={{ animationDelay: `${40 + i * 40}ms` }}
                  className={cn('community-rise group flex items-start gap-3 rounded-xl px-3 py-3 transition-colors', active ? 'bg-[#2563EB]/5' : 'hover:bg-slate-50')}
                >
                  <Icon className={cn('mt-0.5 size-5 shrink-0 transition-colors', active ? 'text-[#2563EB]' : 'text-slate-400 group-hover:text-[#2563EB]')} strokeWidth={1.75} />
                  <span className="min-w-0 flex-1">
                    <span className={cn('block text-sm font-semibold', active ? 'text-[#2563EB]' : 'text-[#0F172A]')}>{label}</span>
                    <span className="mt-0.5 block text-xs font-normal leading-relaxed text-slate-500">{description}</span>
                  </span>
                  <ArrowRight className="mt-0.5 size-4 shrink-0 -translate-x-1 text-[#2563EB] opacity-0 transition-all duration-200 group-hover:translate-x-0 group-hover:opacity-100" />
                </a>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
