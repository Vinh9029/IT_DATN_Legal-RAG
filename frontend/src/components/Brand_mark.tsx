import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

export const Brand_mark: React.FC<{ className?: string }> = ({ className = "" }) => {
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogoClick = (e: React.MouseEvent) => {
    e.preventDefault();
    if (location.pathname === '/') {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } else {
      navigate('/');
      setTimeout(() => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }, 50);
    }
  };

  return (
    <a 
      href="/" 
      onClick={handleLogoClick}
      className={`group flex items-center gap-3 decoration-none cursor-pointer ${className}`}
    >
      {/* Website Logo Image */}
      <div className="relative flex size-10 items-center justify-center overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs transition-transform duration-300 group-hover:scale-105 group-hover:border-[#2563EB]">
        <img 
          src="/logo.png" 
          alt="LƯU HÀNH Logo" 
          className="size-full object-contain p-0.5" 
        />
      </div>

      <div className="flex flex-col">
        <span className="font-display text-2xl tracking-wider text-[#0F172A] group-hover:text-[#2563EB] transition-colors leading-none">
          LƯU HÀNH
        </span>
        <span className="font-mono text-[9px] uppercase tracking-widest text-slate-500 mt-1">
          Thông tin pháp luật
        </span>
      </div>
    </a>
  );
};
