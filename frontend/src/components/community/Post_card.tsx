import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { MessageCircle, MoreHorizontal, Trash2 } from 'lucide-react';
import { cn } from '@/components/ui/button';
import { useAuth } from '@/lib/auth-context';
import { formatRelativeTime, type CommunityPost } from '@/lib/community-service';
import { Comment_section } from './Comment_section';
import { Like_button } from './Like_button';
import { User_avatar } from './User_avatar';

interface PostCardProps {
  post: CommunityPost;
  onDelete: (postId: number) => void;
  onError: (message: string) => void;
  leaving?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

const COLLAPSED_MAX_HEIGHT = 168; // ~7 dòng

export const Post_card: React.FC<PostCardProps> = ({ post, onDelete, onError, leaving, className, style }) => {
  const { user } = useAuth();
  const isOwner = user?.id === post.author.id;

  const [commentCount, setCommentCount] = useState(post.comment_count);
  const [commentsOpen, setCommentsOpen] = useState(false);
  // Chỉ dựng phần bình luận (và gọi API) từ lần mở đầu tiên; đóng lại vẫn giữ để animation thu gọn mượt
  const [commentsMounted, setCommentsMounted] = useState(false);

  const [expanded, setExpanded] = useState(false);
  const [overflowing, setOverflowing] = useState(false);
  const [fullHeight, setFullHeight] = useState<number>();
  const contentRef = useRef<HTMLParagraphElement>(null);

  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const [syncedCount, setSyncedCount] = useState(post.comment_count);
  if (syncedCount !== post.comment_count) {
    setSyncedCount(post.comment_count);
    setCommentCount(post.comment_count);
  }

  useLayoutEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    // Đo lại khi đổi cỡ cửa sổ: số dòng thay đổi theo bề ngang
    const measure = () => {
      setFullHeight(el.scrollHeight);
      setOverflowing(el.scrollHeight > COLLAPSED_MAX_HEIGHT + 8);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [post.content]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) {
        setMenuOpen(false);
        setConfirmDelete(false);
      }
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [menuOpen]);

  const toggleComments = () => {
    setCommentsMounted(true);
    setCommentsOpen((o) => !o);
  };

  return (
    <article
      className={cn(
        'rounded-2xl border border-slate-200 bg-white shadow-xs transition-[box-shadow,border-color] duration-300 hover:border-slate-300 hover:shadow-md',
        leaving ? 'community-leave' : 'community-rise',
        className,
      )}
      style={style}
    >
      <div className="p-4 md:p-5">
        {/* Tác giả */}
        <header className="flex items-start gap-3">
          <User_avatar name={post.author.name} src={post.author.avatar_url} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className="truncate font-semibold text-[#0F172A]">{post.author.name}</p>
              {isOwner && (
                <span className="shrink-0 rounded-md bg-[#2563EB]/10 px-1.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-[#2563EB]">
                  Bạn
                </span>
              )}
            </div>
            <time
              dateTime={post.created_at}
              title={new Date(post.created_at).toLocaleString('vi-VN')}
              className="text-xs text-slate-400"
            >
              {formatRelativeTime(post.created_at)}
            </time>
          </div>

          {isOwner && (
            <div ref={menuRef} className="relative">
              <button
                type="button"
                onClick={() => {
                  setMenuOpen((o) => !o);
                  setConfirmDelete(false);
                }}
                aria-label="Tuỳ chọn bài đăng"
                className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 cursor-pointer"
              >
                <MoreHorizontal className="size-5" />
              </button>
              {menuOpen && (
                <div className="editorial-rise absolute right-0 z-20 mt-1 w-52 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl">
                  <button
                    type="button"
                    onClick={() => {
                      if (!confirmDelete) return setConfirmDelete(true);
                      setMenuOpen(false);
                      onDelete(post.id);
                    }}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors cursor-pointer',
                      confirmDelete ? 'bg-red-600 text-white hover:bg-red-700' : 'text-red-600 hover:bg-red-50',
                    )}
                  >
                    <Trash2 className="size-4" />
                    {confirmDelete ? 'Bấm lần nữa để xoá' : 'Xoá bài đăng'}
                  </button>
                </div>
              )}
            </div>
          )}
        </header>

        {/* Nội dung */}
        <div className="relative mt-3">
          <p
            ref={contentRef}
            className="overflow-hidden whitespace-pre-wrap break-words text-[15px] leading-relaxed text-slate-800 transition-[max-height] duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
            style={{ maxHeight: expanded || !overflowing ? fullHeight : COLLAPSED_MAX_HEIGHT }}
          >
            {post.content}
          </p>
          {overflowing && !expanded && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-white to-transparent" />
          )}
        </div>
        {overflowing && (
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="mt-1 text-sm font-semibold text-[#2563EB] hover:underline cursor-pointer"
          >
            {expanded ? 'Thu gọn' : 'Xem thêm'}
          </button>
        )}

        {/* Tương tác */}
        <div className="-mx-2 mt-3 flex items-center gap-1 border-t border-slate-100 pt-2">
          <Like_button target="post" targetId={post.id} liked={post.liked_by_me} count={post.like_count} onError={onError} />
          <button
            type="button"
            onClick={toggleComments}
            aria-expanded={commentsOpen}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold transition-colors cursor-pointer',
              commentsOpen ? 'bg-[#2563EB]/5 text-[#2563EB]' : 'text-slate-500 hover:bg-slate-100 hover:text-[#2563EB]',
            )}
          >
            <MessageCircle className="size-[18px]" />
            <span key={commentCount} className="count-tick tabular-nums">
              {commentCount > 0 ? `${commentCount} bình luận` : 'Bình luận'}
            </span>
          </button>
        </div>
      </div>

      <div className="collapse-grid" data-open={commentsOpen}>
        <div>
          {commentsMounted && (
            <Comment_section
              postId={post.id}
              onCountChange={(d) => setCommentCount((c) => Math.max(0, c + d))}
              onError={onError}
              autoFocus={commentsOpen}
            />
          )}
        </div>
      </div>
    </article>
  );
};
