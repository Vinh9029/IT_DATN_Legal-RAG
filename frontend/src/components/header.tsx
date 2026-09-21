import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Brand_mark } from './Brand_mark';
import { Button } from './ui/Button';
import { ArrowRight, BotMessageSquare } from 'lucide-react';

export const Header: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const handleNavClick = (e: React.MouseEvent<HTMLAnchorElement>, targetId: string) => {
    e.preventDefault();
    if (location.pathname !== '/') {
      navigate('/', { replace: false });
      setTimeout(() => {
        const el = document.getElementById(targetId);
        if (el) el.scrollIntoView({ behavior: 'smooth' });
      }, 100);
    } else {
      const el = document.getElementById(targetId);
      if (el) el.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-[#F8FAFC]/95 backdrop-blur-md shadow-xs">
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-5 md:px-10">
        <Brand_mark />

        <nav className="hidden items-center gap-8 font-mono text-xs uppercase tracking-wider text-slate-600 md:flex">
          <a 
            href="#linh-vuc" 
            onClick={(e) => handleNavClick(e, 'linh-vuc')}
            className="transition-colors hover:text-[#2563EB]"
          >
            Lĩnh vực
          </a>
          <a 
            href="#quy-trinh" 
            onClick={(e) => handleNavClick(e, 'quy-trinh')}
            className="transition-colors hover:text-[#2563EB]"
          >
            Cách tiếp cận
          </a>
          <a 
            href="#luu-y" 
            onClick={(e) => handleNavClick(e, 'luu-y')}
            className="transition-colors hover:text-[#2563EB]"
          >
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
