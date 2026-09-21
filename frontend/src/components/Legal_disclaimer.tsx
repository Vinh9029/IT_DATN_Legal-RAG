import React from 'react';
import { ShieldAlert } from 'lucide-react';

export const Legal_disclaimer: React.FC<{ className?: string; compact?: boolean }> = ({ 
  className = '',
  compact = false 
}) => {
  if (compact) {
    return (
      <div className={`flex items-center gap-2 border-t border-slate-200 bg-slate-50 px-4 py-2 text-xs text-slate-500 font-mono ${className}`}>
        <ShieldAlert className="size-4 shrink-0 text-[#2563EB]" />
        <span>Nội dung mang tính chất tham khảo định hướng, không thay thế ý kiến tư vấn pháp lý chính thức của Luật sư.</span>
      </div>
    );
  }

  return (
    <div className={`border-l-4 border-[#2563EB] bg-slate-50 p-4 rounded-r-lg shadow-xs ${className}`}>
      <div className="flex items-start gap-3">
        <ShieldAlert className="size-5 shrink-0 text-[#2563EB] mt-0.5" />
        <div>
          <h4 className="font-semibold text-sm text-[#0F172A]">Giới hạn tư vấn tham khảo</h4>
          <p className="mt-1 text-xs text-slate-600 leading-relaxed">
            Phản hồi từ Trợ lý AI và các nội dung hiển thị trên hệ thống LƯU HÀNH nhằm mục đích cung cấp thông tin pháp luật Việt Nam tham khảo. Do quy định pháp luật thay đổi theo thời gian và tính chất riêng của từng vụ việc, bạn nên tham vấn ý kiến trực tiếp của Luật sư trước khi ra các quyết định pháp lý quan trọng.
          </p>
        </div>
      </div>
    </div>
  );
};
