import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, Loader2, SendHorizontal } from 'lucide-react';
import { cn } from '@/components/ui/button';
import { useAuth } from '@/lib/auth-context';
import { useRequireLogin } from '@/lib/login-gate';
import {
  COMMENT_MAX_LENGTH,
  communityService,
  formatRelativeTime,
  type CommunityComment,
} from '@/lib/community-service';
import { Autosize_textarea } from './Autosize_textarea';
import { Like_button } from './Like_button';
import { User_avatar } from './User_avatar';

interface CommentSectionProps {
  postId: number;
  /** Báo cho bài đăng cập nhật số bình luận (+1 khi thêm, -1 khi xoá) */
  onCountChange: (delta: number) => void;
  onError: (message: string) => void;
  autoFocus?: boolean;
}

export const Comment_section: React.FC<CommentSectionProps> = ({ postId, onCountChange, onError, autoFocus }) => {
  const { user } = useAuth();
  const requireLogin = useRequireLogin();
  const [comments, setComments] = useState<CommunityComment[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [leaving, setLeaving] = useState<Set<number>>(new Set());
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Tải lại khi đổi tài khoản để cập nhật trạng thái "đã thích"
  useEffect(() => {
    let cancelled = false;
    communityService
      .listComments(postId)
      .then((page) => {
        if (cancelled) return;
        setComments(page.items);
        setCursor(page.next_cursor);
      })
      .catch((e) => !cancelled && onError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // onError là callback của cha, không cần tải lại khi nó đổi
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [postId, user?.id]);

  useEffect(() => {
    if (autoFocus && user) inputRef.current?.focus({ preventScroll: true });
  }, [autoFocus, user]);

  const loadMore = async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await communityService.listComments(postId, cursor);
      // Bỏ những bình luận đã có sẵn (vừa tự gửi lên trước khi tải tới trang này)
      setComments((prev) =>
        [...prev, ...page.items.filter((c) => !prev.some((p) => p.id === c.id))].sort((a, b) => a.id - b.id),
      );
      setCursor(page.next_cursor);
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Không tải được bình luận.');
    } finally {
      setLoadingMore(false);
    }
  };

  const trimmed = draft.trim();
  const overLimit = draft.length > COMMENT_MAX_LENGTH;

  const send = async () => {
    if (!trimmed || overLimit || sending || !requireLogin()) return;
    setSending(true);
    try {
      const comment = await communityService.createComment(postId, trimmed);
      setComments((prev) => [...prev, comment]);
      setDraft('');
      onCountChange(1);
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Không gửi được bình luận.');
    } finally {
      setSending(false);
    }
  };

  const remove = async (id: number) => {
    setLeaving((s) => new Set(s).add(id));
    try {
      await communityService.deleteComment(id);
      setTimeout(() => {
        setComments((prev) => prev.filter((c) => c.id !== id));
        onCountChange(-1);
      }, 280);
    } catch (e) {
      setLeaving((s) => {
        const n = new Set(s);
        n.delete(id);
        return n;
      });
      onError(e instanceof Error ? e.message : 'Không xoá được bình luận.');
    }
  };

  const userName = user?.user_metadata?.full_name || user?.user_metadata?.name || user?.email || '';
  const userAvatar = user?.user_metadata?.avatar_url || user?.user_metadata?.picture;

  return (
    <div className="border-t border-slate-100 px-4 pb-4 pt-3 md:px-5">
      {loading ? (
        <div className="space-y-3 py-1">
          {[0, 1].map((i) => (
            <div key={i} className="flex gap-2.5">
              <div className="skeleton size-8 shrink-0 rounded-lg" />
              <div className="skeleton h-14 flex-1 rounded-2xl" style={{ maxWidth: i ? '55%' : '80%' }} />
            </div>
          ))}
        </div>
      ) : (
        <>
          {comments.length === 0 && (
            <p className="community-rise py-2 text-center text-sm text-slate-400">Chưa có bình luận nào. Hãy là người đầu tiên!</p>
          )}

          <ul className="space-y-3">
            {comments.map((c, i) => (
              <li
                key={c.id}
                className={cn('flex gap-2.5', leaving.has(c.id) ? 'community-leave' : 'community-rise')}
                style={{ animationDelay: leaving.has(c.id) ? undefined : `${Math.min(i, 6) * 40}ms` }}
              >
                <User_avatar name={c.author.name} src={c.author.avatar_url} size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="inline-block max-w-full rounded-2xl rounded-tl-md bg-slate-100/80 px-3.5 py-2">
                    <p className="text-sm font-semibold text-[#0F172A]">{c.author.name}</p>
                    <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-700">{c.content}</p>
                  </div>
                  <div className="mt-0.5 flex items-center gap-1 pl-2 text-xs text-slate-400">
                    <time dateTime={c.created_at} title={new Date(c.created_at).toLocaleString('vi-VN')}>
                      {formatRelativeTime(c.created_at)}
                    </time>
                    <span aria-hidden>·</span>
                    <Like_button target="comment" targetId={c.id} liked={c.liked_by_me} count={c.like_count} size="sm" onError={onError} />
                    {user?.id === c.author.id && (
                      <>
                        <span aria-hidden>·</span>
                        <button
                          type="button"
                          onClick={() => remove(c.id)}
                          className="rounded px-1 py-0.5 font-semibold transition-colors hover:text-red-600 cursor-pointer"
                        >
                          Xoá
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>

          {cursor && (
            <button
              type="button"
              onClick={loadMore}
              disabled={loadingMore}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-semibold text-[#2563EB] transition-colors hover:bg-[#2563EB]/5 cursor-pointer"
            >
              {loadingMore ? <Loader2 className="size-4 animate-spin" /> : <ChevronDown className="size-4" />}
              Xem thêm bình luận
            </button>
          )}
        </>
      )}

      {/* Ô bình luận */}
      {user ? (
        <div className="mt-3 flex items-end gap-2.5">
          <User_avatar name={userName} src={userAvatar} size="sm" />
          <div
            className={cn(
              'flex flex-1 items-end gap-1 rounded-2xl border bg-white pl-3.5 pr-1.5 transition-all duration-200',
              'border-slate-200 focus-within:border-[#2563EB]/60 focus-within:ring-4 focus-within:ring-[#2563EB]/5',
            )}
          >
            <Autosize_textarea
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                // Enter gửi, Shift+Enter xuống dòng — giống ô chat quen thuộc
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send();
                }
              }}
              maxHeight={160}
              placeholder="Viết bình luận…"
              aria-label="Nội dung bình luận"
              className="py-2 text-sm leading-relaxed text-[#0F172A]"
            />
            <button
              type="button"
              onClick={send}
              disabled={!trimmed || overLimit || sending}
              aria-label="Gửi bình luận"
              className="mb-1 flex size-8 shrink-0 items-center justify-center rounded-xl text-[#2563EB] transition-all hover:bg-[#2563EB] hover:text-white disabled:pointer-events-none disabled:opacity-40 cursor-pointer"
            >
              {sending ? <Loader2 className="size-4 animate-spin" /> : <SendHorizontal className="size-4" />}
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={requireLogin}
          className="mt-3 w-full rounded-2xl border border-dashed border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-500 transition-colors hover:border-[#2563EB] hover:bg-[#2563EB]/5 hover:text-[#2563EB] cursor-pointer"
        >
          Đăng nhập để bình luận
        </button>
      )}
      {overLimit && (
        <p className="mt-1 pl-11 text-xs font-medium text-red-600">
          Bình luận tối đa {COMMENT_MAX_LENGTH} ký tự ({draft.length}/{COMMENT_MAX_LENGTH}).
        </p>
      )}
    </div>
  );
};
