import React from 'react';
import { Link } from 'react-router-dom';

export const BrandMark: React.FC<{ className?: string }> = ({ className = "" }) => {
  return (
    <Link to="/" className={`group flex items-center gap-3 decoration-none ${className}`}>
      {/* Editorial Ink Letter "L" Icon with Electric Cyan AI Accent */}
      <div className="relative flex size-9 items-center justify-center border-2 border-[#0F172A] bg-[#0F172A] font-display text-xl font-bold text-white transition-all duration-300 group-hover:border-[#2563EB] group-hover:bg-[#1E3A8A]">
        <span>L</span>
        <span className="absolute -bottom-1 -right-1 size-2.5 rounded-full border-2 border-white bg-[#2563EB]" />
      </div>
      <div className="flex flex-col">
        <span className="font-display text-2xl tracking-wider text-[#0F172A] group-hover:text-[#2563EB] transition-colors">
          LƯU HÀNH
        </span>
        <span className="font-mono text-[9px] uppercase tracking-widest text-slate-500">
          Thông tin pháp luật
        </span>
      </div>
    </Link>
  );
};
