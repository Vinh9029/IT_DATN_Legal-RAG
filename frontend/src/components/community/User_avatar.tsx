import React, { useState } from 'react';
import { cn } from '@/components/ui/button';

interface UserAvatarProps {
  name: string;
  src?: string | null;
  size?: 'sm' | 'md';
  className?: string;
}

const SIZES = {
  sm: 'size-8 rounded-lg text-xs',
  md: 'size-11 rounded-xl text-sm',
};

export const User_avatar: React.FC<UserAvatarProps> = ({ name, src, size = 'md', className }) => {
  const [broken, setBroken] = useState(false);
  const initial = name.trim().charAt(0).toUpperCase() || '?';

  if (src && !broken) {
    return (
      <img
        src={src}
        alt={name}
        onError={() => setBroken(true)}
        className={cn(SIZES[size], 'shrink-0 border border-slate-200 object-cover', className)}
      />
    );
  }
  return (
    <div
      aria-hidden
      className={cn(SIZES[size], 'flex shrink-0 items-center justify-center bg-[#0F172A] font-bold text-white', className)}
    >
      {initial}
    </div>
  );
};
