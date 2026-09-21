import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { IndexPage } from '@/pages/index-page';
import { AssistantPage } from '@/pages/assistant-page';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<IndexPage />} />
        <Route path="/tro-ly" element={<AssistantPage />} />
        <Route path="/tro-ly/:threadId" element={<AssistantPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
