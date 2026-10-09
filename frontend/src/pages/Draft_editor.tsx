import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AlertCircle, ArrowLeft, Check, CloudOff, FileQuestion, ListTree, Loader2, Redo2, RefreshCw, Sparkles, Undo2, X } from 'lucide-react';
import { Button, cn } from '@/components/ui/button';
import { Paper } from '@/components/drafting/Paper';
import { Field_outline } from '@/components/drafting/Field_outline';
import { Assistant_panel } from '@/components/drafting/Assistant_panel';
import { Export_menu } from '@/components/drafting/Export_menu';
import { getTemplate } from '@/lib/drafting/templates';
import { draftService, NEW_DRAFT_ID } from '@/lib/drafting/draft-service';
import { askAssistant, getAssistantStatus, type AssistantStatus } from '@/lib/drafting/ai-service';
import { exportFileName, resolveDocument } from '@/lib/drafting/document';
import { printDocument } from '@/lib/drafting/export-pdf';
import { useDraftState, editStatus } from '@/lib/drafting/use-draft-state';
import { asList, asText, emptyValue, isFilled, normalizeValues, progressOf, sameValue } from '@/lib/drafting/values';
import type { ChatMessage, Draft, DraftTemplate, FieldEdit, FieldValue } from '@/lib/drafting/types';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'missing' }
  // session: khoá của Workspace — giữ nguyên khi văn bản mới được tạo trong DB, để không mất lịch sử hoàn tác
  | { status: 'ready'; draft: Draft; template: DraftTemplate; session: string };

function blankDraft(template: DraftTemplate): Draft {
  const now = new Date().toISOString();
  return {
    id: '',
    template_id: template.id,
    template_version: template.version,
    title: template.title,
    field_values: normalizeValues(template, {}),
    chat: [],
    progress: 0,
    created_at: now,
    updated_at: now,
  };
}

export const Draft_editor: React.FC = () => {
  const { draftId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const templateParam = searchParams.get('mau');
  const navigate = useNavigate();
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  // Mẫu mới: dựng bản trống ngay khi render (không qua effect, không gọi DB)
  const isNew = draftId === NEW_DRAFT_ID;
  const newKey = isNew ? `new:${templateParam}` : null;
  const [seenNewKey, setSeenNewKey] = useState<string | null>(null);
  if (isNew && newKey !== seenNewKey) {
    setSeenNewKey(newKey);
    const template = templateParam ? getTemplate(templateParam) : undefined;
    setState(template ? { status: 'ready', draft: blankDraft(template), template, session: crypto.randomUUID() } : { status: 'missing' });
  }

  // Văn bản vừa được tạo từ chính phiên này: URL đổi sang id thật nhưng giữ nguyên Workspace
  const handleCreated = (draft: Draft) => {
    setState((s) => (s.status === 'ready' ? { ...s, draft } : s));
    navigate(`/soan-thao/${draft.id}`, { replace: true });
  };

  const loadedId = state.status === 'ready' ? state.draft.id : null;
  useEffect(() => {
    if (isNew || loadedId === draftId) return;
    let alive = true;
    draftService.get(draftId).then(
      (draft) => {
        if (!alive) return;
        const template = draft && getTemplate(draft.template_id);
        setState(draft && template ? { status: 'ready', draft, template, session: draft.id } : { status: 'missing' });
      },
      (e: unknown) => alive && setState({ status: 'error', message: e instanceof Error ? e.message : 'Không mở được bản nháp.' }),
    );
    return () => {
      alive = false;
    };
  }, [draftId, isNew, loadedId, attempt]);

  if (state.status === 'ready') return <Workspace key={state.session} draft={state.draft} template={state.template} onCreated={handleCreated} />;

  return (
    <div className="flex h-dvh flex-col items-center justify-center bg-slate-100 px-6 text-center text-[#0F172A]">
      {state.status === 'loading' && (
        <div className="dp-fade flex flex-col items-center gap-3 text-slate-500">
          <Loader2 className="size-6 animate-spin text-[#2563EB]" />
          <p className="text-sm">Đang mở bản nháp…</p>
        </div>
      )}
      {state.status !== 'loading' && (
        <div className="community-rise flex max-w-sm flex-col items-center">
          {state.status === 'missing' ? <FileQuestion className="size-10 text-slate-400" strokeWidth={1.5} /> : <AlertCircle className="size-10 text-red-500" strokeWidth={1.5} />}
          <p className="mt-4 font-display text-xl uppercase">{state.status === 'missing' ? 'Không tìm thấy bản nháp' : 'Không mở được bản nháp'}</p>
          <p className="mt-2 text-sm text-slate-500">
            {state.status === 'missing' ? 'Bản nháp đã bị xoá, hoặc thuộc về tài khoản khác.' : state.message}
          </p>
          <div className="mt-6 flex gap-2">
            {state.status === 'error' && (
              <Button variant="secondary" size="sm" onClick={() => (setState({ status: 'loading' }), setAttempt((a) => a + 1))}>
                <RefreshCw className="size-4" />
                Thử lại
              </Button>
            )}
            <Button variant="primary" size="sm" onClick={() => navigate('/soan-thao')}>
              <ArrowLeft className="size-4" />
              Về trang Soạn thảo
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

// ── Không gian làm việc ──────────────────────────────────────────

type SaveState = 'saved' | 'dirty' | 'saving' | 'error';

const PAPER_PX = (210 * 96) / 25.4;
const SAVE_DELAY = 800;
const uid = () => crypto.randomUUID();
const nowIso = () => new Date().toISOString();

/** Thu nhỏ trang A4 cho vừa khung khi màn hình hẹp */
function useFitZoom(ref: React.RefObject<HTMLElement | null>) {
  const [zoom, setZoom] = useState(1);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const gutter = entry.contentRect.width < 640 ? 24 : 80;
      setZoom(Math.min(1, Math.max(0.3, (entry.contentRect.width - gutter) / PAPER_PX)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return zoom;
}

const Workspace: React.FC<{ draft: Draft; template: DraftTemplate; onCreated: (draft: Draft) => void }> = ({ draft, template, onCreated }) => {
  const navigate = useNavigate();
  const initialValues = useMemo(() => normalizeValues(template, draft.field_values), [template, draft.field_values]);
  const { values, flash, canUndo, canRedo, setField, applyEdits, undo, redo } = useDraftState(initialValues);

  const [title, setTitle] = useState(draft.title);
  const [chat, setChat] = useState<ChatMessage[]>(() => (Array.isArray(draft.chat) ? draft.chat : []));
  const [activeField, setActiveField] = useState<string | null>(null);
  const [aiOpen, setAiOpen] = useState(() => window.matchMedia('(min-width: 1024px)').matches);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const [aiStatus, setAiStatus] = useState<AssistantStatus | null>(null);
  const [pending, setPending] = useState(false);
  const [prefill, setPrefill] = useState<{ text: string; nonce: number } | null>(null);
  const [saveState, setSaveState] = useState<SaveState>('saved');
  const [toast, setToast] = useState<{ id: number; message: string } | null>(null);

  const paperRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const zoom = useFitZoom(viewportRef);

  // Bản mới nhất cho các callback chạy bất đồng bộ (gửi AI, lưu)
  const latest = useRef({ values, title, chat, activeField });
  useLayoutEffect(() => {
    latest.current = { values, title, chat, activeField };
  });

  const showError = useCallback((message: string) => setToast({ id: Date.now(), message }), []);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4500);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    const previous = document.title;
    document.title = `${title} · Soạn thảo · LƯU HÀNH`;
    return () => {
      document.title = previous;
    };
  }, [title]);

  // ── Trợ lý AI có dùng được không ──
  const recheckAi = useCallback(() => {
    setAiStatus(null);
    getAssistantStatus().then(setAiStatus);
  }, []);
  useEffect(() => {
    let alive = true;
    getAssistantStatus().then((s) => alive && setAiStatus(s));
    return () => {
      alive = false;
      abortRef.current?.abort();
    };
  }, []);

  // ── Tên bản nháp tự theo nội dung, cho tới khi người dùng tự đặt tên ──
  const autoTitle = template.draftTitle?.(values);
  const lastAutoTitle = useRef(template.draftTitle?.(initialValues));
  useEffect(() => {
    // Chụp tên tự đặt cũ ra biến: hàm cập nhật chạy trễ, lúc đó ref đã mang giá trị mới
    const previous = lastAutoTitle.current;
    if (autoTitle && autoTitle !== previous) {
      setTitle((t) => (t === template.title || t === previous ? autoTitle : t));
    }
    lastAutoTitle.current = autoTitle;
  }, [autoTitle, template.title]);

  // ── Tự động lưu ──
  // Rỗng = mẫu mới mở, chưa có trong DB
  const draftId = useRef(draft.id || null);
  const onCreatedRef = useRef(onCreated);
  useLayoutEffect(() => {
    onCreatedRef.current = onCreated;
  });
  const savedSnapshot = useRef(JSON.stringify({ values: initialValues, title: draft.title, chat: draft.chat ?? [] }));
  const saving = useRef(false);

  const flush = useCallback(async (): Promise<boolean> => {
    if (saving.current) return false;
    saving.current = true;
    try {
      // Có thay đổi mới trong lúc đang lưu thì lưu tiếp, tới khi DB khớp bản mới nhất
      for (;;) {
        const snap = latest.current;
        const key = JSON.stringify({ values: snap.values, title: snap.title, chat: snap.chat });
        if (key === savedSnapshot.current) {
          setSaveState('saved');
          return true;
        }
        setSaveState('saving');
        if (draftId.current) {
          await draftService.update(draftId.current, template, { title: snap.title, field_values: snap.values, chat: snap.chat });
        } else {
          // Lần sửa đầu tiên của mẫu mới mở: lúc này mới tạo văn bản trong lịch sử
          const created = await draftService.create(template, { title: snap.title, field_values: snap.values, chat: snap.chat });
          draftId.current = created.id;
          onCreatedRef.current(created);
        }
        savedSnapshot.current = key;
      }
    } catch (e) {
      setSaveState('error');
      showError(e instanceof Error ? e.message : 'Không lưu được bản nháp.');
      return false;
    } finally {
      saving.current = false;
    }
  }, [template, showError]);

  useEffect(() => {
    const key = JSON.stringify({ values, title, chat });
    if (key === savedSnapshot.current) return;
    setSaveState((s) => (s === 'error' ? s : 'dirty'));
    const t = setTimeout(flush, SAVE_DELAY);
    return () => clearTimeout(t);
  }, [values, title, chat, flush]);

  // Rời trang khi còn thay đổi chưa lưu: lưu nốt; đóng tab thì trình duyệt hỏi lại
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      const s = latest.current;
      if (JSON.stringify({ values: s.values, title: s.title, chat: s.chat }) !== savedSnapshot.current) e.preventDefault();
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload);
      void flush();
    };
  }, [flush]);

  // ── Điều hướng tới một ô ──
  const focusField = useCallback((id: string) => {
    setActiveField(id);
    setOutlineOpen(false);
    requestAnimationFrame(() => {
      const host = paperRef.current?.querySelector<HTMLElement>(`[data-field="${CSS.escape(id)}"]`);
      if (!host) return;
      host.scrollIntoView({ behavior: 'smooth', block: 'center' });
      const target = host.matches('[contenteditable], [role="button"]') ? host : host.querySelector<HTMLElement>('[contenteditable]');
      if (!target) return;
      target.focus({ preventScroll: true });
      if (target.isContentEditable) {
        const range = document.createRange();
        range.selectNodeContents(target);
        range.collapse(false);
        const sel = window.getSelection();
        sel?.removeAllRanges();
        sel?.addRange(range);
      }
    });
  }, []);

  // ── Trợ lý AI ──
  const send = useCallback(
    async (text: string) => {
      const { values: sentValues, chat: history, activeField: focus } = latest.current;
      setChat((c) => [...c, { id: uid(), role: 'user', content: text, created_at: nowIso(), focus_field: focus ?? undefined }]);
      setPending(true);
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        const res = await askAssistant({ template, values: sentValues, history, message: text, focusField: focus }, ctrl.signal);
        const current = latest.current.values;
        const dropped = [...(res.dropped ?? [])];
        const edits: FieldEdit[] = [];
        for (const e of res.edits) {
          const def = template.fields.find((f) => f.id === e.field);
          if (!def) continue;
          const after: FieldValue = def.kind === 'list' ? asList(e.value) : asText(e.value);
          // Người dùng gõ vào ô này trong lúc chờ → giữ chữ của người dùng
          if (!sameValue(current[e.field], sentValues[e.field])) {
            dropped.push({ field: e.field, reason: 'Bạn đã sửa ô này trong lúc trợ lý đang xử lý' });
            continue;
          }
          if (!sameValue(current[e.field], after)) edits.push({ field: e.field, before: current[e.field] ?? emptyValue(def), after });
        }
        applyEdits(edits, 'ai');
        setChat((c) => [
          ...c,
          { id: uid(), role: 'assistant', content: res.reply, created_at: nowIso(), edits: edits.length ? edits : undefined, dropped: dropped.length ? dropped : undefined },
        ]);
      } catch (e) {
        const content = ctrl.signal.aborted ? 'Đã dừng theo yêu cầu của bạn.' : e instanceof Error ? e.message : 'Trợ lý gặp lỗi.';
        setChat((c) => [...c, { id: uid(), role: 'assistant', content, created_at: nowIso(), error: true }]);
        if (!ctrl.signal.aborted) getAssistantStatus().then(setAiStatus);
      } finally {
        if (abortRef.current === ctrl) abortRef.current = null;
        setPending(false);
      }
    },
    [template, applyEdits],
  );

  const toggleEdits = useCallback(
    (messageId: string, fields: string[] | undefined, mode: 'revert' | 'reapply') => {
      const message = latest.current.chat.find((m) => m.id === messageId);
      if (!message?.edits) return;
      const current = latest.current.values;
      const from = mode === 'revert' ? 'applied' : 'reverted';
      const changes = message.edits
        .filter((e) => (!fields || fields.includes(e.field)) && editStatus(e, current) === from)
        .map((e) => (mode === 'revert' ? { field: e.field, before: e.after, after: e.before } : { field: e.field, before: e.before, after: e.after }));
      applyEdits(changes, 'ai');
    },
    [applyEdits],
  );

  const askAiForField = useCallback(
    (fieldId: string) => {
      const f = template.fields.find((x) => x.id === fieldId);
      if (!f) return;
      setAiOpen(true);
      setActiveField(fieldId);
      setPrefill({ text: `Viết giúp mục "${f.label}" dựa trên thông tin đã có. `, nonce: Date.now() });
    },
    [template],
  );

  // ── Xuất văn bản ──
  const exportPdf = useCallback(async () => {
    void flush();
    try {
      await printDocument(latest.current.title, resolveDocument(template, latest.current.values));
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Không mở được bản in.');
    }
  }, [flush, template, showError]);

  const exportDocx = useCallback(async () => {
    void flush();
    try {
      const { buildDocx, downloadBlob } = await import('@/lib/drafting/export-docx');
      const blob = await buildDocx(resolveDocument(template, latest.current.values));
      downloadBlob(blob, exportFileName(latest.current.title, 'docx'));
    } catch (e) {
      showError(e instanceof Error ? `Không tạo được file Word: ${e.message}` : 'Không tạo được file Word.');
    }
  }, [flush, template, showError]);

  // ── Phím tắt ──
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
      const key = e.key.toLowerCase();
      const target = e.target as HTMLElement;
      const inTextInput = target.tagName === 'TEXTAREA' || target.tagName === 'INPUT';
      if (key === 's') {
        e.preventDefault();
        void flush();
      } else if (key === 'p') {
        e.preventDefault();
        void exportPdf();
      } else if (!inTextInput && key === 'z') {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      } else if (!inTextInput && key === 'y') {
        e.preventDefault();
        redo();
      }
    };
    // Hoàn tác từ menu chuột phải của trình duyệt cũng phải đi qua lịch sử của biểu mẫu
    const onBeforeInput = (e: InputEvent) => {
      if (e.inputType === 'historyUndo' || e.inputType === 'historyRedo') {
        e.preventDefault();
        if (e.inputType === 'historyUndo') undo();
        else redo();
      }
    };
    const paper = paperRef.current;
    window.addEventListener('keydown', onKey);
    paper?.addEventListener('beforeinput', onBeforeInput);
    return () => {
      window.removeEventListener('keydown', onKey);
      paper?.removeEventListener('beforeinput', onBeforeInput);
    };
  }, [flush, exportPdf, undo, redo]);

  // ── Số liệu hiển thị ──
  const progress = progressOf(template, values);
  const missing = template.fields.filter((f) => f.required && !isFilled(values[f.id]));
  const sourceLine = template.source.kind === 'official' ? `${template.source.code} · ${template.source.issuedBy}` : `Mẫu tham khảo · ${template.source.basis}`;
  const aiUsable = !!aiStatus?.available;

  const outline = (
    <Field_outline template={template} values={values} activeField={activeField} onSelect={focusField} onAskAi={aiUsable ? askAiForField : undefined} />
  );

  const assistant = (onClose?: () => void) => (
    <Assistant_panel
      template={template}
      values={values}
      chat={chat}
      status={aiStatus}
      pending={pending}
      activeField={activeField}
      prefill={prefill}
      onSend={send}
      onStop={() => abortRef.current?.abort()}
      onRevert={(id, fields) => toggleEdits(id, fields, 'revert')}
      onReapply={(id, fields) => toggleEdits(id, fields, 'reapply')}
      onSelectField={focusField}
      onClearFocus={() => setActiveField(null)}
      onClearChat={() => setChat([])}
      onRecheck={recheckAi}
      onClose={onClose}
    />
  );

  return (
    <div className="flex h-dvh flex-col bg-slate-100 text-[#0F172A] selection:bg-[#2563EB]/20">
      {/* Thanh công cụ */}
      <header className="relative z-30 flex h-16 shrink-0 items-center gap-2 border-b border-slate-200 bg-white px-3 sm:gap-3 sm:px-4">
        <button
          type="button"
          onClick={() => navigate('/soan-thao')}
          aria-label="Về danh sách văn bản"
          className="flex size-9 shrink-0 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-[#0F172A] cursor-pointer"
        >
          <ArrowLeft className="size-5" />
        </button>

        <button
          type="button"
          onClick={() => setOutlineOpen(true)}
          aria-label="Mục cần điền"
          className="flex size-9 shrink-0 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-[#0F172A] lg:hidden cursor-pointer"
        >
          <ListTree className="size-5" />
        </button>

        <div className="min-w-0 flex-1">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value.slice(0, 200))}
            onBlur={() => !title.trim() && setTitle(template.title)}
            onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
            aria-label="Tên văn bản"
            className="w-full truncate rounded-md bg-transparent px-1.5 py-0.5 text-sm font-semibold text-[#0F172A] transition-colors hover:bg-slate-100 focus:bg-slate-100 focus:outline-none sm:text-base"
          />
          <p className="truncate px-1.5 text-xs text-slate-500">
            <span className="hidden sm:inline">{sourceLine}</span>
            {/* Mẫu vừa mở, chưa sửa gì: chưa có gì để báo "đã lưu" */}
            {(draft.id || saveState !== 'saved') && (
              <>
                <span className="hidden sm:inline"> · </span>
                <Save_status state={saveState} onRetry={() => void flush()} />
              </>
            )}
          </p>
        </div>

        <div className="hidden items-center sm:flex">
          <Icon_button label="Hoàn tác (Ctrl Z)" onClick={undo} disabled={!canUndo}>
            <Undo2 className="size-4" />
          </Icon_button>
          <Icon_button label="Làm lại (Ctrl Shift Z)" onClick={redo} disabled={!canRedo}>
            <Redo2 className="size-4" />
          </Icon_button>
        </div>

        <Progress_ring
          value={progress}
          title={missing.length ? `Còn ${missing.length} mục bắt buộc — bấm để tới mục tiếp theo` : 'Đã điền đủ các mục bắt buộc'}
          onClick={() => missing[0] && focusField(missing[0].id)}
        />

        <Export_menu onPdf={exportPdf} onDocx={exportDocx} />

        <button
          type="button"
          onClick={() => setAiOpen((o) => !o)}
          aria-pressed={aiOpen}
          aria-label="Trợ lý AI"
          className={cn(
            'inline-flex h-9 shrink-0 items-center gap-2 rounded-lg border px-2.5 text-sm font-semibold transition-all cursor-pointer',
            aiOpen ? 'border-[#2563EB] bg-[#2563EB]/10 text-[#2563EB]' : 'border-slate-200 bg-white text-slate-600 hover:border-[#2563EB] hover:text-[#2563EB]',
          )}
        >
          <Sparkles className="size-4" />
          <span className="hidden xl:inline">Trợ lý AI</span>
        </button>
      </header>

      <div className="relative flex min-h-0 flex-1">
        {/* Mục lục — màn hình rộng */}
        <aside className="hidden w-72 shrink-0 border-r border-slate-200 bg-white lg:block">{outline}</aside>

        {/* Trang giấy */}
        <main ref={viewportRef} className="lib-scroll min-w-0 flex-1 overflow-y-auto overflow-x-hidden">
          <div className="flex justify-center px-3 py-6 sm:px-10 sm:py-10">
            <div className="editorial-rise" style={{ zoom }}>
              <Paper ref={paperRef} template={template} values={values} onChange={setField} activeField={activeField} onFocusField={setActiveField} flash={flash} />
            </div>
          </div>
        </main>

        {/* Trợ lý — màn hình vừa trở lên: cột phải co giãn mượt */}
        <div className={cn('hidden shrink-0 overflow-hidden border-l bg-white transition-[width,border-color] duration-300 ease-out md:block', aiOpen ? 'w-[380px] border-slate-200' : 'w-0 border-transparent')}>
          <div className="h-full w-[380px]">{assistant()}</div>
        </div>
      </div>

      {/* Mục lục — màn hình hẹp: ngăn kéo trái */}
      {outlineOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="dp-fade absolute inset-0 bg-[#0F172A]/40" onClick={() => setOutlineOpen(false)} />
          <div className="dp-slide-left absolute inset-y-0 left-0 flex w-80 max-w-[85vw] flex-col bg-white shadow-2xl">
            <div className="flex h-14 items-center justify-between border-b border-slate-200 px-4">
              <p className="font-display text-sm uppercase">Mục cần điền</p>
              <button type="button" onClick={() => setOutlineOpen(false)} aria-label="Đóng" className="flex size-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-[#0F172A] cursor-pointer">
                <X className="size-4" />
              </button>
            </div>
            <div className="min-h-0 flex-1">{outline}</div>
          </div>
        </div>
      )}

      {/* Trợ lý — điện thoại: tấm trượt từ dưới lên */}
      {aiOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="dp-fade absolute inset-0 bg-[#0F172A]/40" onClick={() => setAiOpen(false)} />
          <div className="dp-sheet absolute inset-x-0 bottom-0 h-[82dvh] overflow-hidden rounded-t-2xl shadow-2xl">{assistant(() => setAiOpen(false))}</div>
        </div>
      )}

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

// ── Mảnh nhỏ của thanh công cụ ───────────────────────────────────

const Icon_button: React.FC<{ label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }> = ({ label, onClick, disabled, children }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    aria-label={label}
    title={label}
    className="flex size-9 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-[#0F172A] disabled:pointer-events-none disabled:opacity-35 cursor-pointer"
  >
    {children}
  </button>
);

const Save_status: React.FC<{ state: SaveState; onRetry: () => void }> = ({ state, onRetry }) => {
  if (state === 'error') {
    return (
      <button type="button" onClick={onRetry} className="inline-flex items-center gap-1 font-medium text-red-600 hover:underline cursor-pointer">
        <CloudOff className="size-3" />
        Chưa lưu được · Thử lại
      </button>
    );
  }
  return (
    <span key={state} className="dp-fade inline-flex items-center gap-1">
      {state === 'saving' && <Loader2 className="size-3 animate-spin" />}
      {state === 'saved' && <Check className="size-3" />}
      {state === 'saved' ? 'Đã lưu' : state === 'saving' ? 'Đang lưu…' : 'Chưa lưu'}
    </span>
  );
};

const Progress_ring: React.FC<{ value: number; title: string; onClick: () => void }> = ({ value, title, onClick }) => {
  const r = 13;
  const c = 2 * Math.PI * r;
  return (
    <button type="button" onClick={onClick} title={title} aria-label={title} className="relative hidden size-9 shrink-0 items-center justify-center rounded-full transition-transform hover:scale-105 sm:flex cursor-pointer">
      <svg viewBox="0 0 32 32" className="size-9 -rotate-90">
        <circle cx="16" cy="16" r={r} fill="none" stroke="#E2E8F0" strokeWidth="2.5" />
        <circle cx="16" cy="16" r={r} fill="none" stroke={value === 100 ? '#16A34A' : '#2563EB'} strokeWidth="2.5" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - value / 100)} className="dp-ring" />
      </svg>
      <span className="absolute font-mono text-[10px] font-semibold tabular-nums">{value === 100 ? <Check className="size-3.5 text-[#16A34A]" /> : value}</span>
    </button>
  );
};
