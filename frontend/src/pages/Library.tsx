import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AlertCircle, ArrowRight, Bot, Lightbulb, Loader2, RefreshCw, Search, SearchX, X } from 'lucide-react';
import { Header } from '@/components/header';
import { Button, cn } from '@/components/ui/button';
import { Law_card } from '@/components/library/Law_card';
import { Article_hit } from '@/components/library/Article_hit';
import { useLibraryIndex } from '@/lib/library/hooks';
import { lawPath, libraryService } from '@/lib/library/library-service';
import { fold, parseArticleQuery, queryTokens } from '@/lib/library/text';
import type { ArticleHit, LawSummary } from '@/lib/library/types';

// Chỉ nêu những thao tác người dùng KHÓ tự phát hiện — điều hiển nhiên (tìm không dấu...) thì không nhắc
const TIPS = [
  'Đã biết số Điều? Chỉ cần gõ số, ví dụ "328", rồi nhấn Enter là tới ngay.',
  'Khi đọc thấy "quy định tại Điều X", bạn nhấn phím / và gõ X để mở Điều đó mà không phải rời chỗ đang đọc.',
  'Muốn gửi một Điều cho người khác, bấm vào chữ "Điều …" ở đầu Điều đó để sao chép đường dẫn.',
  'Chưa rõ một Điều áp dụng vào trường hợp của mình ra sao? Bạn có thể hỏi trợ lý AI ngay tại Điều đang đọc.',
];

const ALL = '__all__';

const lawSearchText = (law: LawSummary) =>
  fold([law.title, law.short_title, law.so_hieu, law.loai_van_ban, law.linh_vuc, law.summary, ...(law.aliases ?? [])].filter(Boolean).join(' '));

const Catalog_skeleton: React.FC = () => (
  <div className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
    {[0, 1].map((i) => (
      <div key={i} className="space-y-2.5 px-6 py-5">
        <div className="skeleton h-3 w-32 rounded" />
        <div className="skeleton h-5 w-1/2 rounded" />
        <div className="skeleton h-3.5 w-4/5 rounded" />
      </div>
    ))}
  </div>
);

export const Library: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [indexState, retry] = useLibraryIndex();

  const [query, setQuery] = useState(() => searchParams.get('q') ?? '');
  const deferredQuery = useDeferredValue(query.trim());
  const [field, setField] = useState(ALL);
  // Kết quả gắn với truy vấn sinh ra nó: gõ tiếp thì kết quả cũ tự thành "đang tìm"
  const [articleResult, setArticleResult] = useState<{ query: string; hits: ArticleHit[]; error?: string } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const laws = useMemo(() => (indexState.status === 'ready' ? indexState.data : []), [indexState]);

  useEffect(() => {
    const previous = document.title;
    document.title = 'Thư viện pháp luật · LƯU HÀNH';
    return () => {
      document.title = previous;
    };
  }, []);

  // Giữ truy vấn trên URL: bấm quay lại từ trang đọc vẫn còn kết quả
  useEffect(() => {
    setSearchParams(deferredQuery ? { q: deferredQuery } : {}, { replace: true });
  }, [deferredQuery, setSearchParams]);

  const fields = useMemo(() => {
    const counts = new Map<string, number>();
    laws.forEach((l) => l.linh_vuc && counts.set(l.linh_vuc, (counts.get(l.linh_vuc) ?? 0) + 1));
    return [...counts.entries()];
  }, [laws]);

  const visibleLaws = useMemo(() => {
    const tokens = queryTokens(deferredQuery);
    return laws.filter((law) => {
      if (field !== ALL && law.linh_vuc !== field) return false;
      if (!tokens.length) return true;
      const text = lawSearchText(law);
      return tokens.every((t) => text.includes(t));
    });
  }, [laws, field, deferredQuery]);

  const totals = useMemo(() => ({ articles: laws.reduce((s, l) => s + l.stats.articles, 0) }), [laws]);

  // Tìm cấp Điều trên mọi văn bản (tải văn bản về khi cần, có cache)
  const searchingArticles = deferredQuery.length >= 2 || !!parseArticleQuery(deferredQuery);
  useEffect(() => {
    if (!searchingArticles || indexState.status !== 'ready') return;
    let alive = true;
    libraryService.searchAll(deferredQuery, 30).then(
      (hits) => alive && setArticleResult({ query: deferredQuery, hits }),
      (e: unknown) =>
        alive &&
        setArticleResult({ query: deferredQuery, hits: [], error: e instanceof Error ? e.message : 'Không tìm được trong nội dung văn bản.' }),
    );
    return () => {
      alive = false;
    };
  }, [deferredQuery, searchingArticles, indexState.status]);

  const lawById = useMemo(() => new Map(laws.map((l) => [l.id, l])), [laws]);
  const current = articleResult?.query === deferredQuery ? articleResult : null;
  const articleError = current?.error;
  const hitsReady = !!current && !articleError;
  const filteredHits = (current?.hits ?? []).filter((h) => field === ALL || lawById.get(h.lawId)?.linh_vuc === field);
  const highlightQuery = parseArticleQuery(deferredQuery) ? '' : deferredQuery;

  // Mở Điều kèm ?q= để trang đọc tô sáng đúng từ khoá vừa tìm
  const hitPath = (h: ArticleHit) => {
    const [path, hash] = lawPath(h.lawId, h.article.number).split('#');
    return `${path}${highlightQuery ? `?q=${encodeURIComponent(highlightQuery)}` : ''}#${hash}`;
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (filteredHits[0]) navigate(hitPath(filteredHits[0]));
    else if (visibleLaws.length === 1) navigate(lawPath(visibleLaws[0].id));
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] selection:bg-[#2563EB]/20 selection:text-[#2563EB]">
      <Header />

      {/* Tiêu đề + ô tìm kiếm */}
      <section className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-5 py-10 md:px-10 md:py-14">
          <div className="editorial-rise border-l-[3px] border-[#2563EB] pl-5">
            <p className="text-sm font-semibold uppercase tracking-wide text-[#2563EB]">Thư viện pháp luật</p>
            <h1 className="mt-3 font-display text-3xl uppercase leading-[1.2] tracking-tight text-balance md:text-5xl">Tra cứu & đọc văn bản gốc.</h1>
            <p className="mt-4 max-w-2xl text-base leading-relaxed text-slate-600 md:text-lg">
              Đọc trọn vẹn từng Điều luật mà trợ lý AI trích dẫn — từ khoản, điểm đến các Điều liên quan — và tra cứu nhanh mọi quy định trong các bộ luật.
            </p>
          </div>

          <form onSubmit={onSubmit} className="editorial-rise mt-8 max-w-3xl" style={{ animationDelay: '80ms' }} role="search">
            <div className="group relative">
              <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-[#2563EB]" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Escape' && setQuery('')}
                placeholder='Tìm văn bản hoặc nội dung, ví dụ "đặt cọc", "Điều 328"'
                aria-label="Tìm trong thư viện"
                className="h-14 w-full rounded-2xl border border-slate-200 bg-white pl-12 pr-12 text-base text-[#0F172A] shadow-sm placeholder:text-slate-400 transition-all focus:border-[#2563EB] focus:outline-none focus:ring-4 focus:ring-[#2563EB]/10"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => {
                    setQuery('');
                    inputRef.current?.focus();
                  }}
                  aria-label="Xoá tìm kiếm"
                  className="absolute right-3 top-1/2 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-[#0F172A] cursor-pointer"
                >
                  <X className="size-4" />
                </button>
              )}
            </div>
          </form>

          {indexState.status === 'ready' && laws.length > 0 && (
            <p className="editorial-rise mt-4 text-sm text-slate-500" style={{ animationDelay: '140ms' }}>
              {laws.length} văn bản · {totals.articles.toLocaleString('vi-VN')} Điều luật
            </p>
          )}
        </div>
      </section>

      <main className="mx-auto grid max-w-6xl gap-8 px-5 py-8 md:px-10 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0">
          {/* Lọc theo lĩnh vực — danh sách tự sinh từ dữ liệu */}
          {fields.length > 1 && (
            <div className="mb-5 flex flex-wrap gap-2">
              {[[ALL, laws.length] as const, ...fields].map(([value, count]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setField(value)}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-all duration-200 cursor-pointer',
                    field === value
                      ? 'border-[#0F172A] bg-[#0F172A] text-white shadow-sm'
                      : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-[#0F172A]',
                  )}
                >
                  {value === ALL ? 'Tất cả' : value}
                  <span className={cn('font-mono text-xs', field === value ? 'text-white/60' : 'text-slate-400')}>{count}</span>
                </button>
              ))}
            </div>
          )}

          {indexState.status === 'loading' && <Catalog_skeleton />}

          {indexState.status === 'error' && (
            <div className="community-rise flex flex-col items-center rounded-2xl border border-slate-200 bg-white px-6 py-12 text-center">
              <div className="flex size-12 items-center justify-center rounded-xl bg-red-50 text-red-500">
                <AlertCircle className="size-6" />
              </div>
              <p className="mt-4 font-semibold">Không tải được thư viện</p>
              <p className="mt-1 text-sm text-slate-500">{indexState.error.message}</p>
              <Button variant="secondary" size="sm" onClick={retry} className="mt-5">
                <RefreshCw className="size-4" />
                Thử lại
              </Button>
            </div>
          )}

          {indexState.status === 'ready' && (
            <>
              {(deferredQuery ? visibleLaws.length > 0 : true) && (
                <section>
                  {deferredQuery && <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Văn bản</h2>}
                  <div className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 bg-white">
                    {visibleLaws.map((law, i) => (
                      <Law_card key={law.id} law={law} query={deferredQuery} style={{ animationDelay: `${i * 60}ms` }} />
                    ))}
                  </div>
                </section>
              )}

              {searchingArticles && (
                <section className={cn(visibleLaws.length > 0 && 'mt-8')}>
                  <div className="mb-3 flex items-center gap-2">
                    <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Điều luật</h2>
                    {!hitsReady && !articleError && <Loader2 className="size-3.5 animate-spin text-slate-400" />}
                  </div>

                  {articleError && <p className="text-sm text-red-600">{articleError}</p>}

                  {hitsReady && filteredHits.length > 0 && (
                    <div className="space-y-2.5">
                      {filteredHits.map((hit, i) => (
                        <Article_hit
                          key={`${hit.lawId}-${hit.article.number}`}
                          hit={hit}
                          query={highlightQuery}
                          lawLabel={laws.length > 1 ? lawById.get(hit.lawId)?.short_title : undefined}
                          to={hitPath(hit)}
                          style={{ animationDelay: `${Math.min(i, 10) * 35}ms` }}
                        />
                      ))}
                    </div>
                  )}

                  {hitsReady && filteredHits.length === 0 && visibleLaws.length === 0 && (
                    <div className="community-rise flex flex-col items-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
                      <div className="flex size-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
                        <SearchX className="size-7" strokeWidth={1.75} />
                      </div>
                      <p className="mt-4 font-display text-xl uppercase">Không tìm thấy kết quả</p>
                      <p className="mt-1 max-w-sm text-sm text-slate-500">
                        Thử từ khoá khác, bỏ bớt từ, hoặc hỏi trợ lý AI để được gợi ý Điều luật liên quan.
                      </p>
                    </div>
                  )}
                  {hitsReady && filteredHits.length === 0 && visibleLaws.length > 0 && (
                    <p className="text-sm text-slate-500">Không có Điều nào chứa “{deferredQuery}”.</p>
                  )}
                </section>
              )}

              {!searchingArticles && deferredQuery && visibleLaws.length === 0 && (
                <p className="text-sm text-slate-500">Gõ thêm ít nhất 2 ký tự để tìm trong nội dung các Điều.</p>
              )}
            </>
          )}
        </div>

        {/* Cột phụ */}
        <aside className="space-y-4 lg:sticky lg:top-28 lg:self-start">
          <div className="community-rise rounded-2xl border border-slate-200 bg-white p-5" style={{ animationDelay: '120ms' }}>
            <div className="flex items-center gap-2">
              <Lightbulb className="size-5 text-[#2563EB]" />
              <h2 className="font-display text-base uppercase">Mẹo tra cứu</h2>
            </div>
            <ol className="mt-4 space-y-3">
              {TIPS.map((tip, i) => (
                <li key={i} className="flex gap-3 text-sm leading-relaxed text-slate-600">
                  <span className="font-mono text-xs font-bold leading-6 text-[#2563EB]">{String(i + 1).padStart(2, '0')}</span>
                  <span>{tip}</span>
                </li>
              ))}
            </ol>
          </div>

          <div className="community-rise group relative overflow-hidden rounded-2xl bg-[#0F172A] p-5 text-white" style={{ animationDelay: '200ms' }}>
            <div className="absolute -right-6 -top-6 size-28 rounded-full bg-[#2563EB]/30 blur-2xl transition-transform duration-500 group-hover:scale-125" />
            <div className="relative">
              <div className="inline-flex items-center gap-2 rounded-md bg-[#2563EB]/20 px-2.5 py-1 text-xs font-semibold text-[#60A5FA]">
                <Bot className="size-3.5" />
                Không biết bắt đầu từ Điều nào?
              </div>
              <p className="mt-3 text-sm leading-relaxed text-slate-300">
                Mô tả tình huống của bạn, trợ lý AI sẽ chỉ ra các Điều luật liên quan kèm trích dẫn để bạn đọc tiếp tại đây.
              </p>
              <Button variant="accent" size="sm" onClick={() => navigate('/tro-ly')} className="group/cta mt-4 w-full">
                Hỏi trợ lý AI
                <ArrowRight className="size-4 transition-transform group-hover/cta:translate-x-1" />
              </Button>
            </div>
          </div>

        </aside>
      </main>
    </div>
  );
};
