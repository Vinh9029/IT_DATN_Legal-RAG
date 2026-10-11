import React, { useState } from 'react';
import { Loader2, LogIn, Send } from 'lucide-react';
import { Button, cn } from '@/components/ui/button';
import { useAuth } from '@/lib/auth-context';
import { useRequireLogin } from '@/lib/login-gate';
import { communityService, POST_MAX_LENGTH, type CommunityPost } from '@/lib/community-service';
import { Autosize_textarea } from './Autosize_textarea';
import { User_avatar } from './User_avatar';

interface PostComposerProps {
  onCreated: (post: CommunityPost) => void;
  onError: (message: string) => void;
}

export const Post_composer: React.FC<PostComposerProps> = ({ onCreated, onError }) => {
  const { user, loading: authLoading } = useAuth();
  const requireLogin = useRequireLogin();
  const [content, setContent] = useState('');
  const [focused, setFocused] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const userName = user?.user_metadata?.full_name || user?.user_metadata?.name || user?.email || '';
  const userAvatar = user?.user_metadata?.avatar_url || user?.user_metadata?.picture;

  const trimmed = content.trim();
  const overLimit = content.length > POST_MAX_LENGTH;
  const expanded = focused || content.length > 0;

  const submit = async () => {
    if (!trimmed || overLimit || submitting || !requireLogin()) return;
    setSubmitting(true);
    try {
      const post = await communityService.createPost(trimmed);
      setContent('');
      onCreated(post);
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Không đăng được bài.');
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading) {
    return (
      <div className="flex items-center gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
        <div className="skeleton size-11 shrink-0 rounded-xl" />
        <div className="skeleton h-4 w-2/3 rounded" />
      </div>
    );
  }

  if (!user) {
    return (
      <button
        type="button"
        onClick={requireLogin}
        className="group flex w-full items-center gap-4 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-xs transition-all duration-300 hover:-translate-y-0.5 hover:border-[#2563EB] hover:shadow-lg cursor-pointer"
      >
        <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-400 transition-colors group-hover:bg-[#2563EB] group-hover:text-white">
          <LogIn className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-[#0F172A]">Bạn đang băn khoăn vấn đề pháp lý nào?</p>
          <p className="text-sm text-slate-500">Đăng nhập để đặt câu hỏi, bình luận và thả tim.</p>
        </div>
        <span className="hidden shrink-0 text-sm font-semibold text-[#2563EB] sm:inline">Đăng nhập</span>
      </button>
    );
  }

  return (
    <div
      className={cn(
        'rounded-2xl border bg-white p-4 shadow-xs transition-all duration-300',
        expanded ? 'border-[#2563EB]/60 shadow-lg ring-4 ring-[#2563EB]/5' : 'border-slate-200',
      )}
    >
      <div className="flex gap-3">
        <User_avatar name={userName} src={userAvatar} />
        <Autosize_textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onSubmitShortcut={submit}
          placeholder="Chia sẻ tình huống hoặc đặt câu hỏi pháp lý của bạn…"
          aria-label="Nội dung bài đăng"
          className="min-h-11 py-2.5 text-base leading-relaxed text-[#0F172A]"
        />
      </div>

      <div className="collapse-grid" data-open={expanded}>
        <div>
          <div className="mt-3 flex items-center justify-between gap-3 border-t border-slate-100 pt-3 pl-14">
            <span className="hidden text-xs text-slate-400 sm:inline">Ctrl + Enter để đăng nhanh</span>
            <div className="ml-auto flex items-center gap-3">
              <span
                className={cn(
                  'text-xs tabular-nums transition-colors',
                  overLimit ? 'font-semibold text-red-600' : content.length > POST_MAX_LENGTH * 0.9 ? 'text-amber-600' : 'text-slate-400',
                )}
              >
                {content.length}/{POST_MAX_LENGTH}
              </span>
              <Button
                variant="accent"
                size="sm"
                // Giữ focus ở textarea để khung không bị thu lại giữa chừng khi bấm
                onMouseDown={(e) => e.preventDefault()}
                onClick={submit}
                disabled={!trimmed || overLimit || submitting}
                className="group px-4"
              >
                {submitting ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />}
                <span>Đăng bài</span>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
