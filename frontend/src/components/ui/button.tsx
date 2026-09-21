import React from 'react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'accent' | 'outline' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', children, ...props }, ref) => {
    const baseStyles = 'inline-flex items-center justify-center font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[#2563EB]/40 disabled:opacity-50 disabled:pointer-events-none cursor-pointer rounded-lg';
    
    const variants = {
      primary: 'bg-[#0F172A] text-white hover:bg-[#1E3A8A] active:bg-[#0F172A] shadow-xs',
      secondary: 'bg-[#F1F5F9] text-[#0F172A] hover:bg-slate-200 border border-slate-200',
      accent: 'bg-[#2563EB] text-white hover:bg-[#1D4ED8] shadow-sm',
      outline: 'border-2 border-[#0F172A] text-[#0F172A] hover:bg-[#0F172A] hover:text-white',
      ghost: 'text-slate-600 hover:text-[#0F172A] hover:bg-slate-100',
    };

    const sizes = {
      sm: 'h-8 px-3 text-xs gap-1.5 font-mono uppercase tracking-wider',
      md: 'h-10 px-4 text-sm gap-2',
      lg: 'h-12 px-6 text-base gap-2.5 font-medium',
    };

    return (
      <button
        ref={ref}
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        {...props}
      >
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';
