import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '@/components/Header';
import { Auth_modal } from '@/components/Auth_modal';

export const Auth: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#F8FAFC]">
      <Header />
      <Auth_modal isOpen={true} onClose={() => navigate('/')} />
    </div>
  );
};
