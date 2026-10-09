import React, { memo, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  ArrowLeft,
  ArrowUp,
  Bot,
  Check,
  ChevronRight,
  Link2,
  ListTree,
  RefreshCw,
  Search,
  SearchX,
  X,
} from 'lucide-react';
import { Header } from '@/components/header';
import { Button, cn } from '@/components/ui/button';
import { Toc_tree } from '@/components/library/Toc_tree';
import { Article_view, type ArticleAction } from '@/components/library/Article_view';
import { Article_hit } from '@/components/library/Article_hit';
import { useLaw } from '@/lib/library/hooks';
import {
  LawNotFoundError,
  articleAnchorId,
  flattenArticles,
  headingAnchorId,
  isArticle,
  lawPath,
  searchLaw,
  structureKey,
} from '@/lib/library/library-service';
import { formatDate, parseArticleQuery } from '@/lib/library/text';
import { smoothScrollTo } from '@/lib/smooth-scroll';
import type { ArticleNode, LawDocument, LawNode } from '@/lib/library/types';

// Header trang (80px) + thanh "đang đọc" dính bên dưới (~40px) + khoảng thở
const SCROLL_OFFSET = 136;

const lawYear = (law: LawDocument) => law.ngay_ban_hanh?.slice(0, 4) ?? '';
const lawFullName = (law: LawDocument) => [law.title, lawYear(law)].filter(Boolean).join(' ');

function scrollToElement(el: HTMLElement, smooth: boolean) {
  const target = el.getBoundingClientRect().top + window.scrollY - SCROLL_OFFSET;
  if (!smooth) {
    window.scrollTo(0, target);
    return;
  }
  // Nhảy xa (Điều 1 → Điều 600) mà cuộn mượt cả quãng thì chỉ thấy chữ nhoè:
  // dịch tức thì tới gần đích rồi mới cuộn mượt đoạn cuối.
  const near = window.innerHeight * 1.5;
  const distance = target - window.scrollY;
  if (Math.abs(distance) > near * 2) window.scrollTo(0, target - Math.sign(distance) * near);
  smoothScrollTo(target, 520);
}

function flash(el: HTMLElement) {
  el.classList.remove('lib-flash');
  void el.offsetWidth; // khởi động lại animation khi bấm cùng một Điều hai lần
  el.classList.add('lib-flash');
}

// ── Nội dung văn bản ─────────────────────────────────────────────

const HEADING_STYLE = {
  part: { wrap: 'mt-16 first:mt-0 border-t-[3px] border-[#0F172A] pt-6', label: 'text-sm text-[#2563EB]', title: 'text-2xl md:text-3xl' },
  chapter: { wrap: 'mt-12 first:mt-0 border-t border-slate-300 pt-6', label: 'text-xs text-[#2563EB]', title: 'text-xl md:text-2xl' },
  section: { wrap: 'mt-10 first:mt-0', label: 'text-xs text-slate-500', title: 'text-lg md:text-xl' },
  subsection: { wrap: 'mt-8 first:mt-0', label: 'text-xs text-slate-500', title: 'text-base md:text-lg' },
} as const;

interface Content_props {
  nodes: LawNode[];
  parentKey: string;
  highlight: string;
  hitSet: Set<string>;
  onAction: (action: ArticleAction, article: ArticleNode) => void;
}

const Law_content: React.FC<Content_props> = memo(({ nodes, parentKey, highlight, hitSet, onAction }) => (
  <>
    {nodes.map((node) => {
      if (isArticle(node)) {
        return (
          <Article_view
            key={node.number}
            article={node}
            highlight={hitSet.has(node.number) ? highlight : undefined}
            onAction={onAction}
          />
        );
      }
      const key = structureKey(parentKey, node);
      const style = HEADING_STYLE[node.type];
      return (
        <div key={key} className={style.wrap}>
          <header id={headingAnchorId(key)} className="mb-2 scroll-mt-24">
            <p className={cn('font-semibold uppercase tracking-[0.14em]', style.label)}>{node.label}</p>
            <h2 className={cn('mt-1.5 font-display uppercase leading-tight tracking-tight text-[#0F172A] text-balance', style.title)}>
              {node.title}
            </h2>
          </header>
          <Law_content nodes={node.children} parentKey={key} highlight={highlight} hitSet={hitSet} onAction={onAction} />
        </div>
      );
    })}
  </>
));
Law_content.displayName = 'Law_content';

// ── Thanh bên: tìm kiếm + mục lục ────────────────────────────────

interface Sidebar_props {
  law: LawDocument;
  query: string;
  onQueryChange: (q: string) => void;
  hits: ReturnType<typeof searchLaw>;
  searching: boolean;
  activeArticle: string | null;
  activeAncestors: string[];
  onSelectArticle: (number: string) => void;
  onSelectHeading: (key: string) => void;
  inputRef?: React.Ref<HTMLInputElement>;
}

const Reader_sidebar: React.FC<Sidebar_props> = ({
  law,
  query,
  onQueryChange,
  hits,
  searching,
  activeArticle,
  activeAncestors,
  onSelectArticle,
  onSelectHeading,
  inputRef,
}) => {
  const isNumber = !!parseArticleQuery(query);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="relative shrink-0">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onQueryChange('');
            if (e.key === 'Enter' && hits[0]) onSelectArticle(hits[0].article.number);
          }}
          placeholder="Số Điều hoặc từ khoá…"
          aria-label={`Tìm trong ${law.title}`}
          className="h-11 w-full rounded-xl border border-slate-200 bg-white pl-9 pr-16 text-sm text-[#0F172A] placeholder:text-slate-400 transition-all focus:border-[#2563EB] focus:outline-none focus:ring-4 focus:ring-[#2563EB]/10"
        />
        {query ? (
          <button
            type="button"
            onClick={() => onQueryChange('')}
            aria-label="Xoá tìm kiếm"
            className="absolute right-2 top-1/2 flex size-7 -translate-y-1/2 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-[#0F172A] cursor-pointer"
          >
            <X className="size-4" />
          </button>
        ) : (
          <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border border-slate-200 bg-slate-50 px-1.5 font-mono text-[11px] text-slate-400 lg:block">
            /
          </kbd>
        )}
      </div>

      <div className="relative mt-3 min-h-0 flex-1">
        {/* Hai lớp chồng lên nhau, đổi qua lại bằng mờ dần thay vì giật cục */}
        <div
          className={cn(
            'lib-scroll absolute inset-0 overflow-y-auto pr-1 transition-all duration-300',
            searching ? 'pointer-events-none -translate-x-2 opacity-0' : 'opacity-100',
          )}
          inert={searching}
        >
          <p className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Mục lục</p>
          <Toc_tree
            structure={law.structure}
            activeArticle={activeArticle}
            activeAncestors={activeAncestors}
            onSelectArticle={onSelectArticle}
            onSelectHeading={onSelectHeading}
            visible={!searching}
          />
        </div>

        <div
          className={cn(
            'lib-scroll absolute inset-0 overflow-y-auto pr-1 transition-all duration-300',
            searching ? 'opacity-100' : 'pointer-events-none translate-x-2 opacity-0',
          )}
          inert={!searching}
        >
          {searching && (
            <>
              <p className="mb-1 px-1 text-xs text-slate-500" aria-live="polite">
                {hits.length ? (
                  <>
                    <span className="font-semibold text-[#0F172A]">{hits.length >= 60 ? '60+' : hits.length}</span> Điều khớp
                    {!isNumber && <span className="text-slate-400"> · Enter để mở kết quả đầu</span>}
                  </>
                ) : null}
              </p>
              {hits.length ? (
                <div className="space-y-0.5">
                  {hits.map((hit) => (
                    <Article_hit
                      key={hit.article.number}
                      hit={hit}
                      query={isNumber ? '' : query}
                      compact
                      onSelect={() => onSelectArticle(hit.article.number)}
                    />
                  ))}
                </div>
              ) : (
                <div className="community-rise flex flex-col items-center px-4 py-10 text-center">
                  <SearchX className="size-8 text-slate-300" strokeWidth={1.5} />
                  <p className="mt-3 text-sm font-semibold text-[#0F172A]">Không có Điều nào khớp</p>
                  <p className="mt-1 text-xs text-slate-500">Thử từ khoá ngắn hơn, hoặc gõ số Điều (ví dụ: 328).</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

// ── Khung chờ / lỗi ──────────────────────────────────────────────

const Reader_skeleton: React.FC = () => (
  <div className="mx-auto max-w-7xl px-5 py-10 md:px-10">
    <div className="skeleton h-3 w-40 rounded" />
    <div className="skeleton mt-5 h-10 w-2/3 max-w-xl rounded-lg" />
    <div className="skeleton mt-3 h-4 w-48 rounded" />
    <div className="mt-10 grid gap-10 lg:grid-cols-[300px_minmax(0,1fr)]">
      <div className="hidden space-y-3 lg:block">
        <div className="skeleton h-11 rounded-xl" />
        {[70, 85, 60, 90, 75, 65].map((w, i) => (
          <div key={i} className="skeleton h-4 rounded" style={{ width: `${w}%` }} />
        ))}
      </div>
      <div className="space-y-8">
        {[0, 1, 2].map((i) => (
          <div key={i} className="space-y-3">
            <div className="skeleton h-6 w-1/2 rounded" />
            <div className="skeleton h-4 rounded" />
            <div className="skeleton h-4 w-11/12 rounded" />
            <div className="skeleton h-4 w-4/5 rounded" />
          </div>
        ))}
      </div>
    </div>
  </div>
);

// ── Trang ────────────────────────────────────────────────────────

export const Law_reader: React.FC = () => {
  const { lawId } = useParams<{ lawId: string }>();
  const [lawState, retry] = useLaw(lawId);

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] selection:bg-[#2563EB]/20 selection:text-[#2563EB]">
      <Header />
      {lawState.status === 'loading' && <Reader_skeleton />}
      {lawState.status === 'error' && (
        <div className="mx-auto flex max-w-lg flex-col items-center px-5 py-24 text-center">
          <div className="community-rise flex size-14 items-center justify-center rounded-2xl bg-red-50 text-red-500">
            <AlertCircle className="size-7" />
          </div>
          <p className="community-rise mt-5 font-display text-2xl uppercase">
            {lawState.error instanceof LawNotFoundError ? 'Không tìm thấy văn bản' : 'Không tải được văn bản'}
          </p>
          <p className="community-rise mt-2 text-sm text-slate-500">{lawState.error.message}</p>
          <div className="community-rise mt-6 flex gap-3">
            <Link to="/thu-vien">
              <Button variant="secondary" size="sm">
                <ArrowLeft className="size-4" />
                Về Thư viện
              </Button>
            </Link>
            {!(lawState.error instanceof LawNotFoundError) && (
              <Button variant="accent" size="sm" onClick={retry}>
                <RefreshCw className="size-4" />
                Thử lại
              </Button>
            )}
          </div>
        </div>
      )}
      {lawState.status === 'ready' && <Reader key={lawState.data.id} law={lawState.data} />}
    </div>
  );
};

const Reader: React.FC<{ law: LawDocument }> = ({ law }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const [query, setQuery] = useState(() => searchParams.get('q') ?? '');
  const deferredQuery = useDeferredValue(query);
  const [activeArticle, setActiveArticle] = useState<string | null>(law.first_article);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [showTop, setShowTop] = useState(false);
  const [toast, setToast] = useState<{ id: number; message: string } | null>(null);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);
  const spyLockUntil = useRef(0);

  const articles = useMemo(() => flattenArticles(law), [law]);

  // Điều → khoá các node cấu trúc chứa nó (để mục lục tự mở đúng nhánh)
  const ancestorsByArticle = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const { article, path } of articles) {
      const keys: string[] = [];
      path.reduce((parent, node) => {
        const key = structureKey(parent, node);
        keys.push(key);
        return key;
      }, '');
      map.set(article.number, keys);
    }
    return map;
  }, [articles]);

  const searching = deferredQuery.trim().length > 0;
  const hits = useMemo(() => (searching ? searchLaw(law, deferredQuery) : []), [law, deferredQuery, searching]);
  // Chỉ tô sáng Điều nằm trong kết quả — Điều khác không phải render lại khi gõ
  const highlight = parseArticleQuery(deferredQuery) ? '' : deferredQuery;
  const hitSet = useMemo(() => new Set(highlight ? hits.map((h) => h.article.number) : []), [hits, highlight]);

  useEffect(() => {
    const previous = document.title;
    document.title = `${law.short_title || law.title} · Thư viện pháp luật`;
    return () => {
      document.title = previous;
    };
  }, [law]);

  // Ghi truy vấn lên URL (replace) để copy link là giữ được kết quả tìm
  useEffect(() => {
    const url = new URL(window.location.href);
    if (deferredQuery.trim()) url.searchParams.set('q', deferredQuery.trim());
    else url.searchParams.delete('q');
    window.history.replaceState(window.history.state, '', url);
  }, [deferredQuery]);

  const showToast = useCallback((message: string) => setToast({ id: Date.now(), message }), []);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2200);
    return () => clearTimeout(t);
  }, [toast]);

  const setHash = (hash: string) => {
    const url = new URL(window.location.href);
    url.hash = hash;
    window.history.replaceState(window.history.state, '', url);
  };

  const goToArticle = useCallback((number: string, smooth = true) => {
    const el = document.getElementById(articleAnchorId(number));
    if (!el) return;
    spyLockUntil.current = performance.now() + (smooth ? 900 : 300);
    setActiveArticle(number);
    setDrawerOpen(false);
    setHash(articleAnchorId(number));
    scrollToElement(el, smooth);
    flash(el);
  }, []);

  const goToHeading = useCallback((key: string) => {
    const el = document.getElementById(headingAnchorId(key));
    if (!el) return;
    spyLockUntil.current = performance.now() + 900;
    setDrawerOpen(false);
    setHash(headingAnchorId(key));
    scrollToElement(el, true);
  }, []);

  // Mở trang bằng liên kết có #dieu-N (từ Chat, từ kết quả tìm kiếm, link được chia sẻ)
  useEffect(() => {
    const hash = decodeURIComponent(location.hash.slice(1));
    if (!hash) return;
    const id = requestAnimationFrame(() => {
      const el = document.getElementById(hash);
      if (!el) return;
      const number = el.dataset.article;
      if (number) goToArticle(number, false);
      else scrollToElement(el, false);
    });
    return () => cancelAnimationFrame(id);
    // Chỉ khi đổi hash qua router; goToArticle tự ghi hash bằng replaceState nên không lặp
  }, [location.key, location.hash, goToArticle]);

  // Theo dõi Điều đang đọc: Điều trên cùng nằm trong dải phía trên màn hình
  useEffect(() => {
    const order = new Map(articles.map((a, i) => [a.article.number, i]));
    const visible = new Set<string>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          const n = (e.target as HTMLElement).dataset.article!;
          if (e.isIntersecting) visible.add(n);
          else visible.delete(n);
        }
        if (!visible.size || performance.now() < spyLockUntil.current) return;
        // Chạm đáy trang thì các Điều cuối không bao giờ cuộn lên được tới dải theo dõi —
        // lấy Điều thấp nhất đang hiện thay vì Điều cao nhất
        const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
        let pick: string | null = null;
        for (const n of visible) {
          if (pick === null || (atBottom ? order.get(n)! > order.get(pick)! : order.get(n)! < order.get(pick)!)) pick = n;
        }
        setActiveArticle(pick);
      },
      { rootMargin: `-${SCROLL_OFFSET}px 0px -65% 0px` },
    );
    document.querySelectorAll<HTMLElement>('[data-article]').forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [articles]);

  // Thanh tiến độ đọc + nút lên đầu trang (cập nhật thẳng DOM, không render lại cả trang)
  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const ratio = max > 0 ? Math.min(1, window.scrollY / max) : 0;
      if (progressRef.current) progressRef.current.style.transform = `scaleX(${ratio})`;
      setShowTop(window.scrollY > 900);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, []);

  // "/" để tìm như các trang tài liệu; Esc đóng ngăn mục lục
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && (e.target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName));
      if (e.key === '/' && !typing) {
        e.preventDefault();
        if (window.innerWidth < 1024) setDrawerOpen(true);
        requestAnimationFrame(() => searchInputRef.current?.focus());
      }
      if (e.key === 'Escape') setDrawerOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Khoá cuộn trang khi ngăn mục lục (mobile) đang mở
  useEffect(() => {
    if (!drawerOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [drawerOpen]);

  const askAI = useCallback(
    (prefill: string) => navigate('/tro-ly', { state: { prefill } }),
    [navigate],
  );

  const copy = useCallback(
    async (text: string, message: string) => {
      try {
        await navigator.clipboard.writeText(text);
        showToast(message);
      } catch {
        showToast('Trình duyệt không cho phép sao chép.');
      }
    },
    [showToast],
  );

  const handleArticleAction = useCallback(
    (action: ArticleAction, article: ArticleNode) => {
      const name = lawFullName(law);
      if (action === 'link') {
        copy(`${window.location.origin}${lawPath(law.id, article.number)}`, `Đã sao chép liên kết tới Điều ${article.number}`);
        setHash(articleAnchorId(article.number));
      } else if (action === 'copy') {
        const source = [name, law.so_hieu && `số ${law.so_hieu}`].filter(Boolean).join(', ');
        copy(`Điều ${article.number}. ${article.title}\n${article.paragraphs.join('\n')}\n\n(${source})`, `Đã sao chép nội dung Điều ${article.number}`);
      } else {
        askAI(`Theo Điều ${article.number} ${name} (${article.title}), `);
      }
    },
    [law, copy, askAI],
  );

  // Chỉ nhắc tình trạng khi văn bản KHÔNG còn hiệu lực
  const inactive = law.tinh_trang && !law.tinh_trang.toLowerCase().includes('còn hiệu lực');

  const activeAncestors = (activeArticle && ancestorsByArticle.get(activeArticle)) || [];
  const activeTrail = activeAncestors.length ? articles.find((a) => a.article.number === activeArticle)?.path ?? [] : [];

  const sidebarProps: Sidebar_props = {
    law,
    query,
    onQueryChange: setQuery,
    hits,
    searching,
    activeArticle,
    activeAncestors,
    onSelectArticle: goToArticle,
    onSelectHeading: goToHeading,
  };

  return (
    <>
      {/* Tiến độ đọc, bám ngay dưới header */}
      <div className="fixed inset-x-0 top-20 z-30 h-0.5 bg-transparent">
        <div ref={progressRef} className="h-full origin-left bg-[#2563EB] transition-transform duration-150 ease-out" style={{ transform: 'scaleX(0)' }} />
      </div>

      {/* Đầu trang văn bản */}
      <section className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-7xl px-5 py-8 md:px-10 md:py-12">
          <nav aria-label="Breadcrumb" className="editorial-rise flex items-center gap-1.5 text-sm text-slate-500">
            <Link to="/thu-vien" className="font-medium transition-colors hover:text-[#2563EB]">
              Thư viện
            </Link>
            <ChevronRight className="size-3.5 text-slate-300" />
            <span className="truncate font-medium text-[#0F172A]">{law.short_title || law.title}</span>
          </nav>

          <div className="editorial-rise mt-6 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between" style={{ animationDelay: '60ms' }}>
            <div className="min-w-0">
              <p className="font-mono text-xs uppercase tracking-wide text-slate-400">
                {[law.loai_van_ban, law.so_hieu && `Số ${law.so_hieu}`].filter(Boolean).join(' · ')}
                {inactive && <span className="ml-2 font-sans font-semibold normal-case tracking-normal text-red-600">{law.tinh_trang}</span>}
              </p>
              <h1 className="mt-2 font-display text-3xl uppercase leading-[1.15] tracking-tight text-balance md:text-5xl">{lawFullName(law)}</h1>
              <p className="mt-3 text-sm text-slate-500">
                {[
                  law.co_quan_ban_hanh && law.ngay_ban_hanh && `${law.co_quan_ban_hanh} ban hành ${formatDate(law.ngay_ban_hanh)}`,
                  law.ngay_hieu_luc && `Hiệu lực ${formatDate(law.ngay_hieu_luc)}`,
                  `${law.stats.articles} Điều`,
                ]
                  .filter(Boolean)
                  .join(' · ')}
                {/* Ghi chú phiên bản để dạng chữ phụ, không phải hộp cảnh báo */}
                {law.version_note && <span className="block text-xs text-slate-400">{law.version_note}</span>}
              </p>
            </div>

            <div className="flex shrink-0 flex-wrap gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => copy(`${window.location.origin}${lawPath(law.id)}`, 'Đã sao chép liên kết văn bản')}
              >
                <Link2 className="size-4" />
                Sao chép liên kết
              </Button>
              <Button variant="primary" size="sm" onClick={() => askAI(`Theo ${lawFullName(law)}, `)}>
                <Bot className="size-4" />
                Hỏi AI về văn bản này
              </Button>
            </div>
          </div>
        </div>
      </section>

      <div className="mx-auto grid max-w-7xl gap-10 px-5 py-8 md:px-10 lg:grid-cols-[300px_minmax(0,1fr)]">
        {/* Thanh bên (máy tính) */}
        <aside className="hidden lg:block">
          <div className="sticky top-24 h-[calc(100vh-7.5rem)]">
            <Reader_sidebar {...sidebarProps} inputRef={searchInputRef} />
          </div>
        </aside>

        {/* Nội dung */}
        <article className="min-w-0 max-w-3xl">
          {/* Vị trí đang đọc */}
          <div className="sticky top-20 z-20 -mx-5 mb-4 border-b border-slate-200/70 bg-[#F8FAFC]/90 px-5 py-2.5 backdrop-blur-md md:-mx-6 md:px-6">
            <p className="flex min-w-0 items-center gap-1.5 truncate text-xs text-slate-500">
              {activeTrail.length ? (
                activeTrail.map((node, i) => (
                  <React.Fragment key={node.label}>
                    {i > 0 && <ChevronRight className="size-3 shrink-0 text-slate-300" />}
                    <span className={cn('truncate', i === activeTrail.length - 1 && 'font-semibold text-[#0F172A]')}>{node.label}</span>
                  </React.Fragment>
                ))
              ) : (
                <span>{law.short_title || law.title}</span>
              )}
              {activeArticle && (
                <>
                  <ChevronRight className="size-3 shrink-0 text-slate-300" />
                  <span className="shrink-0 font-mono font-semibold text-[#2563EB]">Điều {activeArticle}</span>
                </>
              )}
            </p>
          </div>

          {law.preamble.length > 0 && (
            <div className="mb-10 space-y-1.5 rounded-xl border-l-2 border-slate-300 py-1 pl-5 text-[1.0625rem] italic leading-relaxed text-slate-600">
              {law.preamble.map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
          )}

          <Law_content nodes={law.structure} parentKey="" highlight={highlight} hitSet={hitSet} onAction={handleArticleAction} />

          {law.closing.length > 0 && (
            <footer className="mt-14 border-t border-slate-200 pt-8">
              <p className="text-[1.0625rem] italic leading-relaxed text-slate-600">{law.closing[0]}</p>
              {law.closing.length > 1 && (
                <div className="mt-8 ml-auto w-fit text-center">
                  {law.closing.slice(1).map((p, i) => (
                    <p key={i} className={i === 0 ? 'font-bold uppercase tracking-wide text-[#0F172A]' : 'mt-10 font-semibold text-[#0F172A]'}>
                      {p}
                    </p>
                  ))}
                </div>
              )}
            </footer>
          )}
        </article>
      </div>

      {/* Nút nổi: mục lục (mobile) + lên đầu trang */}
      <div className="fixed bottom-6 right-5 z-30 flex flex-col items-end gap-3">
        <button
          type="button"
          onClick={() => window.scrollY > 0 && smoothScrollTo(0, 600)}
          aria-label="Lên đầu trang"
          className={cn(
            'flex size-11 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-lg transition-all duration-300 hover:border-[#2563EB] hover:text-[#2563EB] cursor-pointer',
            showTop ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-3 opacity-0',
          )}
        >
          <ArrowUp className="size-5" />
        </button>
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          className="flex h-12 items-center gap-2 rounded-full bg-[#0F172A] px-5 text-sm font-semibold text-white shadow-xl transition-transform hover:scale-[1.03] active:scale-95 cursor-pointer lg:hidden"
        >
          <ListTree className="size-4" />
          Mục lục
        </button>
      </div>

      {/* Ngăn mục lục (mobile) */}
      <div className={cn('fixed inset-0 z-50 lg:hidden', !drawerOpen && 'pointer-events-none')} aria-hidden={!drawerOpen} inert={!drawerOpen}>
        <div
          onClick={() => setDrawerOpen(false)}
          className={cn('absolute inset-0 bg-[#0F172A]/40 backdrop-blur-sm transition-opacity duration-300', drawerOpen ? 'opacity-100' : 'opacity-0')}
        />
        <div
          role="dialog"
          aria-label="Mục lục"
          className={cn(
            'absolute inset-y-0 left-0 flex w-[86vw] max-w-sm flex-col bg-[#F8FAFC] p-4 shadow-2xl transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]',
            drawerOpen ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <div className="mb-3 flex items-center justify-between">
            <p className="font-display text-base uppercase">{law.short_title || law.title}</p>
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              aria-label="Đóng"
              className="flex size-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-200/60 cursor-pointer"
            >
              <X className="size-5" />
            </button>
          </div>
          <div className="min-h-0 flex-1">
            <Reader_sidebar {...sidebarProps} />
          </div>
        </div>
      </div>

      {toast && (
        <div key={toast.id} className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center px-4">
          <div role="status" className="community-rise flex items-center gap-2.5 rounded-xl bg-[#0F172A] px-4 py-3 text-sm text-white shadow-2xl">
            <Check className="size-4 text-emerald-400" />
            {toast.message}
          </div>
        </div>
      )}
    </>
  );
};
