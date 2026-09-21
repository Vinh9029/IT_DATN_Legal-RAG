import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Brand_mark } from './Brand_mark';
import { Button } from './ui/Button';
import { Auth_modal } from './Auth_modal';
import { useAuth } from '@/lib/auth-context';
import { ArrowRight, BotMessageSquare, LogIn, LogOut, User as UserIcon } from 'lucide-react';

export const Header: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, signOut } = useAuth();
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const userAvatar = user?.user_metadata?.avatar_url || user?.user_metadata?.picture;
  const userName = user?.user_metadata?.full_name || user?.user_metadata?.name || user?.email;

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
    <>
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
              <span>Hỏi đáp AI</span>
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
            </Button>

            {user ? (
              <div className="relative">
                <button
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-1 pr-3 shadow-xs hover:border-[#2563EB] transition-colors cursor-pointer"
                >
                  {userAvatar ? (
                    <img
                      src={userAvatar}
                      alt="User Avatar"
                      className="size-8 rounded-lg object-cover border border-slate-100"
                    />
                  ) : (
                    <div className="flex size-8 items-center justify-center rounded-lg bg-[#0F172A] text-white font-bold text-xs">
                      <UserIcon className="size-4" />
                    </div>
                  )}
                  <span className="max-w-[100px] truncate font-sans text-xs font-semibold text-[#0F172A]">
                    {userName}
                  </span>
                </button>

                {/* User Profile Dropdown Menu */}
                {userMenuOpen && (
                  <div className="absolute right-0 mt-2 w-56 rounded-xl border border-slate-200 bg-white p-2 shadow-xl font-sans text-xs z-50 editorial-rise">
                    <div className="px-3 py-2 border-b border-slate-100">
                      <p className="font-bold text-[#0F172A] truncate">{userName}</p>
                      <p className="font-mono text-[10px] text-slate-400 truncate mt-0.5">{user.email}</p>
                    </div>
                    <button
                      onClick={() => {
                        setUserMenuOpen(false);
                        signOut();
                      }}
                      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-red-600 hover:bg-red-50 transition-colors font-medium mt-1 cursor-pointer"
                    >
                      <LogOut className="size-4" />
                      <span>Đăng xuất</span>
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <Button
                variant="outline"
                size="md"
                onClick={() => setAuthModalOpen(true)}
                className="font-mono text-xs uppercase tracking-wider"
              >
                <LogIn className="size-4 text-[#2563EB]" />
                <span>Đăng nhập</span>
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* Auth Modal */}
      <Auth_modal
        isOpen={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
      />
    </>
  );
};
