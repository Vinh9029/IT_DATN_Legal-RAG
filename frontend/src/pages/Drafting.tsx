import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertCircle, LogIn, RefreshCw, Trash2, X } from 'lucide-react';
import { Header } from '@/components/header';
import { Button, cn } from '@/components/ui/button';
import { Paper } from '@/components/drafting/Paper';
import { Login_gate_provider } from '@/components/Login_gate_provider';
import { useAuth } from '@/lib/auth-context';
import { useRequireLogin } from '@/lib/login-gate';
import { formatRelativeTime } from '@/lib/community-service';
import { TEMPLATES, getTemplate } from '@/lib/drafting/templates';
import { draftService, newDraftPath } from '@/lib/drafting/draft-service';
import { isFilled, normalizeValues } from '@/lib/drafting/values';
import type { DraftSummary, DraftTemplate, FieldValues } from '@/lib/drafting/types';

const ALL = '__all__';
const RECENT_LIMIT = 8;
const EMPTY_VALUES: FieldValues = {};
const GRID = 'grid grid-cols-2 gap-x-5 gap-y-8 sm:grid-cols-3 lg:grid-cols-4';

const DraftingHome: React.FC = () => {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const requireLogin = useRequireLogin();

  const [category, setCategory] = useState(ALL);
  // Gắn với tài khoản đã tải: đổi tài khoản thì dữ liệu cũ tự thành "đang tải"
  const [loaded, setLoaded] = useState<{ userId: string; status: 'loading' | 'ready' | 'error'; items: DraftSummary[]; error?: string } | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [toast, setToast] = useState<{ id: number; message: string } | null>(null);

  useEffect(() => {
    const previous = document.title;
    document.title = 'Soạn thảo văn bản · LƯU HÀNH';
    return () => {
      document.title = previous;
    };
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4500);
    return () => clearTimeout(t);
  }, [toast]);

  const showError = useCallback((message: string) => setToast({ id: Date.now(), message }), []);

  const fetchDrafts = useCallback((userId: string) => {
    draftService.list().then(
      (items) => setLoaded({ userId, status: 'ready', items }),
      (e: unknown) => setLoaded({ userId, status: 'error', items: [], error: e instanceof Error ? e.message : 'Không tải được lịch sử soạn thảo.' }),
    );
  }, []);

  useEffect(() => {
    if (!authLoading && user) fetchDrafts(user.id);
  }, [authLoading, user, fetchDrafts]);

  const drafts = !user ? null : loaded?.userId === user.id ? loaded : { userId: user.id, status: 'loading' as const, items: [] as DraftSummary[], error: undefined };
  const retryDrafts = () => {
    if (!user) return;
    setLoaded({ userId: user.id, status: 'loading', items: [] });
    fetchDrafts(user.id);
  };

  const categories = useMemo(() => [...new Set(TEMPLATES.map((t) => t.category))], []);
  const visibleTemplates = TEMPLATES.filter((t) => category === ALL || t.category === category);

  // Chỉ mở trang soạn — văn bản vào lịch sử khi người dùng thực sự sửa (xem thử rồi thoát thì không lưu gì)
  const start = (template: DraftTemplate) => {
    if (requireLogin()) navigate(newDraftPath(template.id));
  };

  const remove = async (id: string) => {
    const removed = drafts?.items.find((x) => x.id === id);
    setLoaded((d) => d && { ...d, items: d.items.filter((x) => x.id !== id) });
    try {
      await draftService.remove(id);
    } catch (e) {
      if (removed) setLoaded((d) => d && { ...d, items: [...d.items, removed].sort((a, b) => b.updated_at.localeCompare(a.updated_at)) });
      showError(e instanceof Error ? e.message : 'Không xoá được văn bản.');
    }
  };

  const shownDrafts = !drafts ? [] : showAll ? drafts.items : drafts.items.slice(0, RECENT_LIMIT);

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] selection:bg-[#2563EB]/20 selection:text-[#2563EB]">
      <Header />

      <section className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-5 py-10 md:px-10 md:py-14">
          <div className="editorial-rise border-l-[3px] border-[#2563EB] pl-5">
            <p className="text-sm font-semibold uppercase tracking-wide text-[#2563EB]">Soạn thảo văn bản</p>
            <h1 className="mt-3 font-display text-3xl uppercase leading-[1.2] tracking-tight text-balance md:text-5xl">Soạn đơn từ & hợp đồng.</h1>
            <p className="mt-4 max-w-2xl text-base leading-relaxed text-slate-600 md:text-lg">
              Biểu mẫu giữ đúng bố cục bản giấy nộp Tòa án hay đem đi ký. Điền thẳng trên trang hoặc kể sự việc để trợ lý AI điền giúp, rồi xuất ra PDF, Word.
            </p>
          </div>
        </div>
      </section>

      <main className="mx-auto max-w-6xl space-y-14 px-5 py-10 md:px-10">
        {/* Biểu mẫu */}
        <section>
          <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
            <h2 className="font-display text-lg uppercase">Biểu mẫu</h2>
            {categories.length > 1 && (
              <div className="flex flex-wrap gap-2">
                {[ALL, ...categories].map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setCategory(c)}
                    className={cn(
                      'rounded-full border px-3.5 py-1.5 text-sm font-medium transition-all duration-200 cursor-pointer',
                      category === c ? 'border-[#0F172A] bg-[#0F172A] text-white shadow-sm' : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-[#0F172A]',
                    )}
                  >
                    {c === ALL ? 'Tất cả' : c}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className={GRID}>
            {visibleTemplates.map((t, i) => (
              <Template_card key={t.id} template={t} onStart={() => start(t)} style={{ animationDelay: `${i * 60}ms` }} />
            ))}
          </div>

          {!user && !authLoading && (
            <p className="community-rise mt-8 text-sm text-slate-500">
              <button type="button" onClick={() => requireLogin()} className="inline-flex items-center gap-1.5 font-semibold text-[#2563EB] hover:text-[#1D4ED8] cursor-pointer">
                <LogIn className="size-4" />
                Đăng nhập
              </button>{' '}
              để soạn và lưu văn bản vào tài khoản.
            </p>
          )}
        </section>

        {/* Lịch sử soạn thảo — chỉ hiện khi đã có văn bản */}
        {drafts && (drafts.status !== 'ready' || drafts.items.length > 0) && (
          <section className="community-rise">
            <div className="mb-5 flex items-baseline justify-between gap-4">
              <h2 className="font-display text-lg uppercase">Lịch sử soạn thảo</h2>
              {drafts.status === 'ready' && drafts.items.length > RECENT_LIMIT && (
                <button type="button" onClick={() => setShowAll((s) => !s)} className="text-sm font-semibold text-[#2563EB] hover:text-[#1D4ED8] cursor-pointer">
                  {showAll ? 'Thu gọn' : `Xem tất cả (${drafts.items.length})`}
                </button>
              )}
            </div>

            {drafts.status === 'loading' && (
              <div className={GRID}>
                {[0, 1, 2, 3].map((i) => (
                  <div key={i}>
                    <div className="skeleton h-56 rounded-xl" />
                    <div className="skeleton mt-3 h-4 w-3/4 rounded" />
                    <div className="skeleton mt-2 h-3 w-1/2 rounded" />
                  </div>
                ))}
              </div>
            )}

            {drafts.status === 'error' && (
              <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm">
                <AlertCircle className="size-4 shrink-0 text-red-500" />
                <span className="min-w-0 flex-1 text-slate-600">{drafts.error}</span>
                <Button variant="secondary" size="sm" onClick={retryDrafts}>
                  <RefreshCw className="size-4" />
                  Thử lại
                </Button>
              </div>
            )}

            {drafts.status === 'ready' && (
              <div className={GRID}>
                {shownDrafts.map((d, i) => (
                  <Draft_card key={d.id} draft={d} onOpen={() => navigate(`/soan-thao/${d.id}`)} onDelete={() => remove(d.id)} style={{ animationDelay: `${i * 50}ms` }} />
                ))}
              </div>
            )}
          </section>
        )}
      </main>

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

// Ảnh thu nhỏ: chính trang giấy của biểu mẫu (trống hoặc đã điền), cắt lấy nửa trên
const Thumbnail: React.FC<{ template: DraftTemplate; values: FieldValues; children?: React.ReactNode }> = ({ template, values, children }) => (
  <div className="dp-thumb relative h-56 overflow-hidden rounded-xl border border-slate-200 bg-slate-100 transition-colors duration-300 group-hover:border-[#2563EB]/40">
    <div className="flex justify-center pt-5" aria-hidden>
      <div style={{ zoom: 0.26 }} className="pointer-events-none shadow-md transition-all duration-300 ease-out group-hover:-translate-y-2 group-hover:shadow-xl">
        <Paper template={template} values={values} />
      </div>
    </div>
    {children}
  </div>
);

const Template_card: React.FC<{ template: DraftTemplate; onStart: () => void; style?: React.CSSProperties }> = ({ template, onStart, style }) => (
  <button type="button" onClick={onStart} title={template.description} style={style} className="community-rise group min-w-0 text-left cursor-pointer">
    <Thumbnail template={template} values={EMPTY_VALUES} />
    <h3 className="mt-3 truncate font-bold text-[#0F172A] transition-colors group-hover:text-[#2563EB]">{template.title}</h3>
    <p className="mt-0.5 truncate text-sm text-slate-500">{template.source.kind === 'official' ? template.source.code : 'Mẫu tham khảo'}</p>
  </button>
);

const Draft_card: React.FC<{ draft: DraftSummary; onOpen: () => void; onDelete: () => void; style?: React.CSSProperties }> = ({ draft, onOpen, onDelete, style }) => {
  const [confirming, setConfirming] = useState(false);
  const template = getTemplate(draft.template_id);
  const values = useMemo(() => (template ? normalizeValues(template, draft.field_values) : EMPTY_VALUES), [template, draft.field_values]);
  if (!template) return null;
  const missing = template.fields.filter((f) => f.required && !isFilled(values[f.id])).length;

  return (
    <div style={style} className="community-rise group relative min-w-0">
      <button type="button" onClick={onOpen} className="block w-full text-left cursor-pointer">
        <Thumbnail template={template} values={values} />
        <h3 className="mt-3 truncate font-bold text-[#0F172A] transition-colors group-hover:text-[#2563EB]">{draft.title}</h3>
        <p className="mt-0.5 truncate text-sm text-slate-500">
          {formatRelativeTime(draft.updated_at)} · {missing ? `còn ${missing} mục` : 'đã điền đủ'}
        </p>
      </button>

      {confirming ? (
        <div className="dp-fade absolute inset-x-0 top-0 flex h-56 flex-col items-center justify-center gap-3 rounded-xl bg-white/90 backdrop-blur-sm">
          <p className="text-sm font-semibold">Xoá văn bản này?</p>
          <div className="flex gap-2">
            <button type="button" onClick={onDelete} className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-red-700 cursor-pointer">
              Xoá
            </button>
            <button type="button" onClick={() => setConfirming(false)} className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 cursor-pointer">
              Huỷ
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          aria-label={`Xoá ${draft.title}`}
          className="absolute right-2 top-2 flex size-8 items-center justify-center rounded-lg bg-white/90 text-slate-500 shadow-sm transition-all hover:bg-white hover:text-red-600 sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100 cursor-pointer"
        >
          <Trash2 className="size-4" />
        </button>
      )}
    </div>
  );
};

export const Drafting: React.FC = () => (
  <Login_gate_provider>
    <DraftingHome />
  </Login_gate_provider>
);
