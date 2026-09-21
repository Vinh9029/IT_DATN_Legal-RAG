import React, { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { Button } from './ui/Button';
import { X, Mail, Lock, ShieldCheck } from 'lucide-react';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const Auth_modal: React.FC<AuthModalProps> = ({ isOpen, onClose }) => {
  const { signInWithGoogle, signInWithEmail, signUpWithEmail } = useAuth();
  const [tab, setTab] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');
    setLoading(true);

    try {
      if (tab === 'login') {
        const { error } = await signInWithEmail(email, password);
        if (error) {
          setErrorMsg(error.message || 'Đăng nhập không thành công.');
        } else {
          onClose();
        }
      } else {
        const { error } = await signUpWithEmail(email, password);
        if (error) {
          setErrorMsg(error.message || 'Đăng ký không thành công.');
        } else {
          setSuccessMsg('Đăng ký thành công! Vui lòng kiểm tra email xác nhận.');
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Đã xảy ra lỗi.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
      <div className="relative w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 md:p-8 shadow-2xl font-sans editorial-rise">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
        >
          <X className="size-5" />
        </button>

        {/* Brand Header */}
        <div className="text-center">
          <div className="mx-auto flex size-12 items-center justify-center rounded-xl bg-white border border-slate-200 p-1 shadow-xs">
            <img src="/logo.png" alt="Logo" className="size-full object-contain" />
          </div>
          <h3 className="mt-3 font-display text-2xl uppercase tracking-wider text-[#0F172A]">
            Tài Khoản LƯU HÀNH
          </h3>
          {/* <p className="mt-1 font-mono text-xs text-slate-500">
            Tích hợp Supabase Engine & Google OAuth
          </p> */}
        </div>

        {/* Google OAuth Login Button */}
        <div className="mt-6">
          <Button
            variant="secondary"
            size="lg"
            onClick={signInWithGoogle}
            className="w-full justify-center gap-3 border-2 border-slate-200 bg-white hover:bg-slate-50 text-[#0F172A] font-semibold"
          >
            <svg className="size-5" viewBox="0 0 24 24">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
              />
            </svg>
            <span>Tiếp tục với Google</span>
          </Button>
        </div>

        <div className="my-5 flex items-center gap-3">
          <div className="h-px flex-1 bg-slate-200" />
          <span className="font-mono text-[10px] uppercase text-slate-400">hoặc dùng Email</span>
          <div className="h-px flex-1 bg-slate-200" />
        </div>

        {/* Tab Selection */}
        <div className="flex rounded-lg bg-slate-100 p-1 font-mono text-xs">
          <button
            onClick={() => { setTab('login'); setErrorMsg(''); setSuccessMsg(''); }}
            className={`flex-1 rounded-md py-1.5 font-semibold transition-all ${tab === 'login' ? 'bg-white text-[#0F172A] shadow-xs' : 'text-slate-500 hover:text-slate-900'
              }`}
          >
            Đăng nhập
          </button>
          <button
            onClick={() => { setTab('register'); setErrorMsg(''); setSuccessMsg(''); }}
            className={`flex-1 rounded-md py-1.5 font-semibold transition-all ${tab === 'register' ? 'bg-white text-[#0F172A] shadow-xs' : 'text-slate-500 hover:text-slate-900'
              }`}
          >
            Đăng ký
          </button>
        </div>

        {/* Messages */}
        {errorMsg && (
          <div className="mt-4 rounded-lg bg-red-50 p-3 text-xs font-medium text-red-600 border border-red-200">
            {errorMsg}
          </div>
        )}
        {successMsg && (
          <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-xs font-medium text-emerald-600 border border-emerald-200">
            {successMsg}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <div>
            <label className="block font-mono text-[11px] uppercase font-semibold text-slate-600 mb-1">
              Email
            </label>
            <div className="relative flex items-center">
              <Mail className="absolute left-3 size-4 text-slate-400" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@example.com"
                className="w-full rounded-lg border border-slate-300 bg-white pl-9 pr-3 py-2 text-sm text-[#0F172A] focus:border-[#2563EB] focus:outline-none focus:ring-2 focus:ring-[#2563EB]/20"
              />
            </div>
          </div>

          <div>
            <label className="block font-mono text-[11px] uppercase font-semibold text-slate-600 mb-1">
              Mật khẩu
            </label>
            <div className="relative flex items-center">
              <Lock className="absolute left-3 size-4 text-slate-400" />
              <input
                type="password"
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-lg border border-slate-300 bg-white pl-9 pr-3 py-2 text-sm text-[#0F172A] focus:border-[#2563EB] focus:outline-none focus:ring-2 focus:ring-[#2563EB]/20"
              />
            </div>
          </div>

          <Button
            type="submit"
            variant="accent"
            size="lg"
            disabled={loading}
            className="w-full font-mono text-xs uppercase tracking-wider mt-2"
          >
            {loading ? 'Đang xử lý...' : tab === 'login' ? 'Đăng nhập' : 'Đăng ký tài khoản'}
          </Button>
        </form>

        <div className="mt-5 text-center font-mono text-[10px] text-slate-400 flex items-center justify-center gap-1">
          <ShieldCheck className="size-3.5 text-[#2563EB]" />
          <span>Bảo mật Supabase Authentication & SSL 256-bit</span>
        </div>
      </div>
    </div>
  );
};
