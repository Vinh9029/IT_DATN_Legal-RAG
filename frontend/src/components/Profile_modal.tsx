import React, { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { Button } from './ui/Button';
import { X, Upload, CheckCircle2, User as UserIcon, ShieldCheck } from 'lucide-react';

interface ProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const Profile_modal: React.FC<ProfileModalProps> = ({ isOpen, onClose }) => {
  const { user, uploadUserAvatar } = useAuth();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  if (!isOpen || !user) return null;

  const currentAvatar = user.user_metadata?.avatar_url || user.user_metadata?.picture;
  const userName = user.user_metadata?.full_name || user.user_metadata?.name || user.email;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setPreviewUrl(URL.createObjectURL(file));
      setStatusMsg(null);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setIsUploading(true);
    setStatusMsg(null);

    const { publicUrl, error } = await uploadUserAvatar(selectedFile);
    setIsUploading(false);

    if (error) {
      setStatusMsg({ type: 'error', text: 'Lỗi tải ảnh: ' + (error.message || 'Không thể upload.') });
    } else {
      setStatusMsg({ type: 'success', text: 'Cập nhật Avatar thành công trên Supabase Storage!' });
      setSelectedFile(null);
      if (publicUrl) setPreviewUrl(publicUrl);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
      <div className="relative w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl font-sans editorial-rise text-center">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
        >
          <X className="size-5" />
        </button>

        <h3 className="font-display text-2xl uppercase tracking-wider text-[#0F172A]">
          Hồ Sơ Nông Dân Legal
        </h3>
        <p className="mt-1 font-mono text-xs text-slate-400">
          Tài khoản Supabase Auth
        </p>

        {/* Current / Preview Avatar */}
        <div className="mt-6 flex flex-col items-center">
          <div className="relative size-24 overflow-hidden rounded-2xl border-2 border-[#2563EB] shadow-md bg-slate-100">
            {previewUrl || currentAvatar ? (
              <img 
                src={previewUrl || currentAvatar} 
                alt="Avatar Profile" 
                className="size-full object-cover" 
              />
            ) : (
              <div className="flex size-full items-center justify-center bg-[#0F172A] text-white">
                <UserIcon className="size-10" />
              </div>
            )}
          </div>

          <p className="mt-3 font-bold text-base text-[#0F172A] truncate max-w-[240px]">{userName}</p>
          <p className="font-mono text-xs text-slate-500 truncate max-w-[240px]">{user.email}</p>
        </div>

        {/* File Input & Upload */}
        <div className="mt-6 border-t border-slate-100 pt-4">
          <label className="block font-mono text-xs font-semibold uppercase text-slate-600 mb-2">
            Đổi ảnh đại diện (Supabase Storage)
          </label>

          <input
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            className="hidden"
            id="avatar-file-input"
          />

          <div className="flex flex-col gap-2">
            <label
              htmlFor="avatar-file-input"
              className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-2.5 text-xs font-semibold text-slate-700 hover:border-[#2563EB] hover:bg-slate-100 cursor-pointer transition-colors"
            >
              <Upload className="size-4 text-[#2563EB]" />
              <span>{selectedFile ? selectedFile.name : 'Chọn ảnh mới từ thiết bị'}</span>
            </label>

            {selectedFile && (
              <Button
                variant="accent"
                size="md"
                disabled={isUploading}
                onClick={handleUpload}
                className="w-full justify-center gap-2 font-mono text-xs uppercase"
              >
                {isUploading ? 'Đang tải lên Supabase...' : 'Lưu Avatar mới'}
              </Button>
            )}
          </div>

          {statusMsg && (
            <div className={`mt-3 rounded-lg p-2.5 text-xs font-medium flex items-center justify-center gap-1.5 ${
              statusMsg.type === 'success' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-red-50 text-red-700 border border-red-200'
            }`}>
              <CheckCircle2 className="size-4 shrink-0" />
              <span>{statusMsg.text}</span>
            </div>
          )}
        </div>

        <div className="mt-6 pt-3 border-t border-slate-100 font-mono text-[10px] text-slate-400 flex items-center justify-center gap-1">
          <ShieldCheck className="size-3.5 text-[#2563EB]" />
          <span>Lưu trữ bảo mật Supabase Storage Bucket</span>
        </div>
      </div>
    </div>
  );
};
