import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '@/lib/auth-context';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { Index } from '@/pages/Index';
import { Assistant } from '@/pages/Assistant';
import { Auth } from '@/pages/Auth';
import { Community } from '@/pages/Community';
import { Library } from '@/pages/Library';
import { Law_reader } from '@/pages/Law_reader';
import { Drafting } from '@/pages/Drafting';
import { Draft_editor } from '@/pages/Draft_editor';

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route 
            path="/tro-ly" 
            element={
              <ProtectedRoute>
                <Assistant />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/tro-ly/:threadId" 
            element={
              <ProtectedRoute>
                <Assistant />
              </ProtectedRoute>
            } 
          />
          <Route path="/auth" element={<Auth />} />
          {/* Công khai: xem không cần đăng nhập, tương tác thì mở hộp đăng nhập tại chỗ */}
          <Route path="/cong-dong" element={<Community />} />
          {/* Công khai: đọc văn bản không cần đăng nhập */}
          <Route path="/thu-vien" element={<Library />} />
          <Route path="/thu-vien/:lawId" element={<Law_reader />} />
          {/* Chọn mẫu xem công khai; mở/soạn bản nháp cần đăng nhập (bản nháp lưu theo tài khoản) */}
          <Route path="/soan-thao" element={<Drafting />} />
          <Route
            path="/soan-thao/:draftId"
            element={
              <ProtectedRoute>
                <Draft_editor />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
