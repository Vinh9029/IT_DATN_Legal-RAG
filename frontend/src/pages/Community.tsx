import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertCircle, ArrowRight, Bot, Loader2, MessagesSquare, RefreshCw, ShieldCheck, Users, X } from 'lucide-react';
import { Header } from '@/components/header';
import { Button } from '@/components/ui/button';
import { Post_card } from '@/components/community/Post_card';
import { Post_composer } from '@/components/community/Post_composer';
import { useAuth } from '@/lib/auth-context';
import { Login_gate_provider } from '@/components/Login_gate_provider';
import { communityService, type CommunityPost } from '@/lib/community-service';

const GUIDELINES = [
  'Mô tả tình huống rõ ràng: ai, khi nào, việc gì đã xảy ra.',
  'Không đăng thông tin cá nhân nhạy cảm (CCCD, số tài khoản, địa chỉ cụ thể).',
  'Tôn trọng người khác — tranh luận về vấn đề, không công kích cá nhân.',
  'Ý kiến trong cộng đồng chỉ mang tính tham khảo, không thay thế tư vấn của Luật sư.',
];

const PAGE_SIZE = 10;

const Feed_skeleton: React.FC = () => (
  <div className="space-y-4">
    {[0, 1, 2].map((i) => (
      <div key={i} className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex items-center gap-3">
          <div className="skeleton size-11 rounded-xl" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-3.5 w-36 rounded" />
            <div className="skeleton h-3 w-20 rounded" />
          </div>
        </div>
        <div className="mt-4 space-y-2">
          <div className="skeleton h-3.5 w-full rounded" />
          <div className="skeleton h-3.5 w-11/12 rounded" />
          <div className="skeleton h-3.5 rounded" style={{ width: `${55 + i * 12}%` }} />
        </div>
      </div>
    ))}
  </div>
);

const CommunityFeed: React.FC = () => {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();

  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [loadingMore, setLoadingMore] = useState(false);
  const [leaving, setLeaving] = useState<Set<number>>(new Set());
  const [toast, setToast] = useState<{ id: number; message: string } | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const showError = useCallback((message: string) => setToast({ id: Date.now(), message }), []);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const hasLoaded = useRef(false);

  // silent: đã có bảng tin thì làm mới tại chỗ, không chớp lại khung chờ
  const loadFirstPage = useCallback(async (silent = false) => {
    if (!silent) setStatus('loading');
    try {
      const page = await communityService.listPosts(null, PAGE_SIZE);
      setPosts(page.items);
      setCursor(page.next_cursor);
      setStatus('ready');
      hasLoaded.current = true;
    } catch {
      if (!silent) setStatus('error');
    }
  }, []);

  // Tải lại khi đăng nhập/đăng xuất để cập nhật trạng thái "đã thích" theo người xem
  useEffect(() => {
    if (!authLoading) loadFirstPage(hasLoaded.current);
  }, [authLoading, user?.id, loadFirstPage]);

  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await communityService.listPosts(cursor, PAGE_SIZE);
      setPosts((prev) => [...prev, ...page.items.filter((p) => !prev.some((x) => x.id === p.id))]);
      setCursor(page.next_cursor);
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Không tải thêm được bài đăng.');
    } finally {
      setLoadingMore(false);
    }
  }, [cursor, loadingMore, showError]);

  // Cuộn gần cuối danh sách thì tự tải trang tiếp
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !cursor) return;
    const io = new IntersectionObserver((entries) => entries[0].isIntersecting && loadMore(), { rootMargin: '400px' });
    io.observe(el);
    return () => io.disconnect();
  }, [cursor, loadMore]);

  const handleCreated = (post: CommunityPost) => setPosts((prev) => [post, ...prev]);

  const handleDelete = async (postId: number) => {
    setLeaving((s) => new Set(s).add(postId));
    try {
      await communityService.deletePost(postId);
      setTimeout(() => setPosts((prev) => prev.filter((p) => p.id !== postId)), 280);
    } catch (e) {
      setLeaving((s) => {
        const n = new Set(s);
        n.delete(postId);
        return n;
      });
      showError(e instanceof Error ? e.message : 'Không xoá được bài đăng.');
    }
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] selection:bg-[#2563EB]/20 selection:text-[#2563EB]">
      <Header />

      {/* Tiêu đề trang */}
      <section className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-5 py-10 md:px-10 md:py-14">
          <div className="editorial-rise border-l-[3px] border-[#2563EB] pl-5">
            <p className="text-sm font-semibold uppercase tracking-wide text-[#2563EB]">Cộng đồng LƯU HÀNH</p>
            <h1 className="mt-3 font-display text-3xl uppercase leading-[1.2] tracking-tight text-balance md:text-5xl">
              Hỏi, chia sẻ & thảo luận.
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-relaxed text-slate-600 md:text-lg">
              Nơi mọi người cùng đặt câu hỏi và trao đổi kinh nghiệm về các tình huống pháp lý thường ngày.
            </p>
          </div>
        </div>
      </section>

      <main className="mx-auto grid max-w-6xl gap-8 px-5 py-8 md:px-10 lg:grid-cols-[minmax(0,1fr)_320px]">
        {/* Bảng tin */}
        <div className="min-w-0 space-y-4">
          <Post_composer onCreated={handleCreated} onError={showError} />

          {status === 'loading' && <Feed_skeleton />}

          {status === 'error' && (
            <div className="community-rise flex flex-col items-center rounded-2xl border border-slate-200 bg-white px-6 py-12 text-center">
              <div className="flex size-12 items-center justify-center rounded-xl bg-red-50 text-red-500">
                <AlertCircle className="size-6" />
              </div>
              <p className="mt-4 font-semibold">Không tải được bảng tin</p>
              <p className="mt-1 text-sm text-slate-500">Máy chủ đang không phản hồi. Vui lòng thử lại sau ít phút.</p>
              <Button variant="secondary" size="sm" onClick={() => loadFirstPage()} className="mt-5">
                <RefreshCw className="size-4" />
                Thử lại
              </Button>
            </div>
          )}

          {status === 'ready' && posts.length === 0 && (
            <div className="community-rise flex flex-col items-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
              <div className="flex size-14 items-center justify-center rounded-2xl bg-[#2563EB]/10 text-[#2563EB]">
                <MessagesSquare className="size-7" strokeWidth={1.75} />
              </div>
              <p className="mt-4 font-display text-xl uppercase">Chưa có bài đăng nào</p>
              <p className="mt-1 max-w-sm text-sm text-slate-500">Hãy mở đầu cuộc thảo luận bằng câu hỏi pháp lý mà bạn đang quan tâm.</p>
            </div>
          )}

          {status === 'ready' &&
            posts.map((post, i) => (
              <Post_card
                key={post.id}
                post={post}
                onDelete={handleDelete}
                onError={showError}
                leaving={leaving.has(post.id)}
                // Xếp tầng cho trang đầu; bài tải thêm/bài mới hiện ngay
                style={{ animationDelay: i < PAGE_SIZE ? `${i * 60}ms` : undefined }}
              />
            ))}

          <div ref={sentinelRef} />
          {loadingMore && (
            <div className="flex justify-center py-4 text-slate-400">
              <Loader2 className="size-5 animate-spin" />
            </div>
          )}
          {status === 'ready' && posts.length > 0 && !cursor && (
            <p className="py-4 text-center text-sm text-slate-400">Bạn đã xem hết bài đăng.</p>
          )}
        </div>

        {/* Cột phụ */}
        <aside className="space-y-4 lg:sticky lg:top-28 lg:self-start">
          <div className="community-rise rounded-2xl border border-slate-200 bg-white p-5" style={{ animationDelay: '120ms' }}>
            <div className="flex items-center gap-2">
              <ShieldCheck className="size-5 text-[#2563EB]" />
              <h2 className="font-display text-base uppercase">Quy tắc cộng đồng</h2>
            </div>
            <ol className="mt-4 space-y-3">
              {GUIDELINES.map((g, i) => (
                <li key={i} className="flex gap-3 text-sm leading-relaxed text-slate-600">
                  <span className="font-mono text-xs font-bold leading-6 text-[#2563EB]">{String(i + 1).padStart(2, '0')}</span>
                  <span>{g}</span>
                </li>
              ))}
            </ol>
          </div>

          <div
            className="community-rise group relative overflow-hidden rounded-2xl bg-[#0F172A] p-5 text-white"
            style={{ animationDelay: '200ms' }}
          >
            <div className="absolute -right-6 -top-6 size-28 rounded-full bg-[#2563EB]/30 blur-2xl transition-transform duration-500 group-hover:scale-125" />
            <div className="relative">
              <div className="inline-flex items-center gap-2 rounded-md bg-[#2563EB]/20 px-2.5 py-1 text-xs font-semibold text-[#60A5FA]">
                <Bot className="size-3.5" />
                Cần câu trả lời ngay?
              </div>
              <p className="mt-3 text-sm leading-relaxed text-slate-300">
                Trợ lý AI tra cứu văn bản pháp luật và trả lời kèm căn cứ trích dẫn trong vài giây.
              </p>
              <Button variant="accent" size="sm" onClick={() => navigate('/tro-ly')} className="group/cta mt-4 w-full">
                Hỏi trợ lý AI
                <ArrowRight className="size-4 transition-transform group-hover/cta:translate-x-1" />
              </Button>
            </div>
          </div>

          {!user && !authLoading && (
            <div className="community-rise flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600" style={{ animationDelay: '280ms' }}>
              <Users className="mt-0.5 size-5 shrink-0 text-slate-400" />
              <p>Bạn đang xem với tư cách khách. Đăng nhập để đăng bài, bình luận và thả tim.</p>
            </div>
          )}
        </aside>
      </main>

      {/* Thông báo lỗi nổi */}
      {toast && (
        <div key={toast.id} className="fixed inset-x-0 bottom-6 z-50 flex justify-center px-4">
          <div role="alert" className="community-rise flex max-w-md items-center gap-3 rounded-xl bg-[#0F172A] px-4 py-3 text-sm text-white shadow-2xl">
            <AlertCircle className="size-4 shrink-0 text-red-400" />
            <span className="flex-1">{toast.message}</span>
            <button type="button" onClick={() => setToast(null)} aria-label="Đóng" className="rounded p-0.5 text-slate-400 hover:text-white cursor-pointer">
              <X className="size-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export const Community: React.FC = () => (
  <Login_gate_provider>
    <CommunityFeed />
  </Login_gate_provider>
);
