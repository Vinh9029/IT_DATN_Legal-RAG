import React from 'react';
import { CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';

export type LegalStatusType = 'valid' | 'invalid' | 'amended';

interface StatusBadgeProps {
  status: LegalStatusType | string;
  label?: string;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, className = '' }) => {
  const statusLower = typeof status === 'string' ? status.toLowerCase() : status;

  if (statusLower.includes('chồng') || statusLower.includes('còn hiệu lực') || statusLower === 'valid') {
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-md bg-[#DCFCE7] px-2.5 py-1 font-mono text-xs font-semibold text-[#16A34A] border border-[#16A34A]/20 ${className}`}>
        <CheckCircle2 className="size-3.5" />
        {label || 'Còn hiệu lực'}
      </span>
    );
  }

  if (statusLower.includes('hết hiệu lực') || statusLower === 'invalid') {
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-md bg-[#FEE2E2] px-2.5 py-1 font-mono text-xs font-semibold text-[#DC2626] border border-[#DC2626]/20 ${className}`}>
        <XCircle className="size-3.5" />
        {label || 'Hết hiệu lực'}
      </span>
    );
  }

  // Amended / Modifying
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md bg-[#FEF3C7] px-2.5 py-1 font-mono text-xs font-semibold text-[#D97706] border border-[#D97706]/20 ${className}`}>
      <AlertTriangle className="size-3.5" />
      {label || 'Sửa đổi / Bổ sung'}
    </span>
  );
};
