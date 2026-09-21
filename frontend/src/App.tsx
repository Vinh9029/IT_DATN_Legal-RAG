import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Index } from '@/pages/Index';
import { Assistant } from '@/pages/Assistant';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Index />} />
        <Route path="/tro-ly" element={<Assistant />} />
        <Route path="/tro-ly/:threadId" element={<Assistant />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
