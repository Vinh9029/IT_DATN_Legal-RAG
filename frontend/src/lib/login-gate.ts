import { createContext, useContext } from 'react';

// Trang công khai (xem không cần đăng nhập) gọi `requireLogin()` trước mỗi thao tác:
// đã đăng nhập → trả true để làm tiếp; chưa → mở hộp đăng nhập ngay tại chỗ và trả false.
// Provider nằm ở components/Login_gate_provider.tsx.
export type RequireLogin = () => boolean;

export const LoginGateContext = createContext<RequireLogin | undefined>(undefined);

export const useRequireLogin = () => {
  const ctx = useContext(LoginGateContext);
  if (!ctx) throw new Error('useRequireLogin must be used within a Login_gate_provider');
  return ctx;
};
