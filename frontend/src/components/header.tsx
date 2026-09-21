import React from 'react';
import { useNavigate } from 'react-router-dom';
import { BrandMark } from './brand-mark';
import { Button } from './ui/button';
import { ArrowRight, BotMessageSquare } from 'lucide-react';

export const Header: React.FC = () => {
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-[#F8FAFC]/95 backdrop-blur-md">
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-5 md:px-10">
        <BrandMark />

        <nav className="hidden items-center gap-8 font-mono text-xs uppercase tracking-wider text-slate-600 md:flex">
          <a href="#linh-vuc" className="transition-colors hover:text-[#2563EB]">
            Lĩnh vực
          </a>
          <a href="#quy-trinh" className="transition-colors hover:text-[#2563EB]">
            Cách tiếp cận
          </a>
          <a href="#luu-y" className="transition-colors hover:text-[#2563EB]">
            Lưu ý pháp lý
          </a>
        </nav>

        <div className="flex items-center gap-3">
          <Button
            variant="accent"
            size="md"
            onClick={() => navigate('/tro-ly')}
            className="group font-mono text-xs uppercase tracking-wider shadow-sm"
          >
            <BotMessageSquare className="size-4" />
            <span>Hỏi trợ lý AI</span>
            <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
          </Button>
        </div>
      </div>
    </header>
  );
};
