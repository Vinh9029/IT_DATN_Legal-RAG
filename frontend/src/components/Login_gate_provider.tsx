import React, { useCallback, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { LoginGateContext } from '@/lib/login-gate';
import { Auth_modal } from './Auth_modal';

export const Login_gate_provider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();
  const [open, setOpen] = useState(false);

  const requireLogin = useCallback(() => {
    if (user) return true;
    // Phiên đăng nhập còn đang khôi phục: chưa biết là khách hay không, đừng bật hộp đăng nhập
    if (!loading) setOpen(true);
    return false;
  }, [user, loading]);

  return (
    <LoginGateContext.Provider value={requireLogin}>
      {children}
      <Auth_modal isOpen={open && !user} onClose={() => setOpen(false)} />
    </LoginGateContext.Provider>
  );
};
