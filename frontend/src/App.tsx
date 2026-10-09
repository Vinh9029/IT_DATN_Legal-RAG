import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '@/lib/auth-context';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { Index } from '@/pages/Index';
import { Assistant } from '@/pages/Assistant';
import { Auth } from '@/pages/Auth';
import { Community } from '@/pages/Community';
import { Library } from '@/pages/Library';
import { Law_reader } from '@/pages/Law_reader';

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
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
