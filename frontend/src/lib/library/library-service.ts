import type { ArticleHit, ArticleNode, FlatArticle, LawDocument, LawNode, LawSummary, StructureNode } from './types';
import { fold, parseArticleQuery, queryTokens, snippetFor } from './text';
import { supabaseSource } from './supabase-source';

// ── Nguồn dữ liệu ────────────────────────────────────────────────
// UI chỉ nói chuyện với `libraryService`; dữ liệu nằm ở đâu là việc của LibrarySource.
// Hiện tại: Supabase (bảng library_documents/library_articles, xem supabase-source.ts).
// Đổi nơi lưu = viết LibrarySource khác rồi đổi dòng cuối file — không component nào phải sửa.

export interface LibrarySource {
  /** Danh mục văn bản đã công bố — chỉ metadata, không có nội dung */
  loadIndex(): Promise<LawSummary[]>;
  /** Toàn văn một văn bản; trả null nếu không có (hoặc chưa công bố) */
  loadLaw(id: string): Promise<LawDocument | null>;
  /**
   * Tìm cấp Điều trên MỌI văn bản. Không bắt buộc: thiếu thì service tải hết các văn bản
   * về rồi tìm ở client — chỉ ổn khi thư viện còn nhỏ.
   */
  searchArticles?(query: string, limit: number): Promise<ArticleHit[]>;
}

// ── Duyệt cây ────────────────────────────────────────────────────

export const isArticle = (node: LawNode): node is ArticleNode => node.type === 'article';

const flatCache = new WeakMap<LawDocument, FlatArticle[]>();

/** Mọi Điều của văn bản theo thứ tự, kèm đường dẫn Phần/Chương/Mục chứa nó */
export function flattenArticles(law: LawDocument): FlatArticle[] {
  let flat = flatCache.get(law);
  if (flat) return flat;
  flat = [];
  const walk = (nodes: LawNode[], path: StructureNode[]) => {
    for (const node of nodes) {
      if (isArticle(node)) flat!.push({ lawId: law.id, article: node, path });
      else walk(node.children, [...path, node]);
    }
  };
  walk(law.structure, []);
  flatCache.set(law, flat);
  return flat;
}

// ── Tìm kiếm trong một văn bản ──────────────────────────────────

interface IndexedArticle extends FlatArticle {
  foldedTitle: string;
  text: string;
  foldedText: string;
}

const searchCache = new WeakMap<LawDocument, IndexedArticle[]>();

function searchIndex(law: LawDocument): IndexedArticle[] {
  let idx = searchCache.get(law);
  if (!idx) {
    idx = flattenArticles(law).map((a) => {
      const text = a.article.paragraphs.join('\n');
      return { ...a, foldedTitle: fold(a.article.title), text, foldedText: fold(text) };
    });
    searchCache.set(law, idx);
  }
  return idx;
}

export function searchLaw(law: LawDocument, query: string, limit = 60): ArticleHit[] {
  const q = query.trim();
  if (!q) return [];
  const items = searchIndex(law);

  // Gõ số Điều: khớp đúng số lên đầu, rồi các số bắt đầu bằng nó (gõ "32" thấy 32, 320-329)
  const number = parseArticleQuery(q);
  if (number) {
    return items
      .filter((a) => a.article.number === number || a.article.number.startsWith(number))
      .map((a) => ({ ...a, score: a.article.number === number ? 1000 : 500, snippet: '' }))
      .sort((a, b) => b.score - a.score || a.article.number.length - b.article.number.length)
      .slice(0, limit)
      .map(stripIndex);
  }

  const tokens = queryTokens(q);
  if (!tokens.length) return [];
  const phrase = tokens.join(' ');
  const hits: ArticleHit[] = [];

  for (const a of items) {
    // Mọi từ đều phải xuất hiện (ở tiêu đề hoặc nội dung)
    if (!tokens.every((t) => a.foldedTitle.includes(t) || a.foldedText.includes(t))) continue;

    let score = 0;
    if (a.foldedTitle.includes(phrase)) score += a.foldedTitle === phrase ? 200 : 100;
    if (a.foldedText.includes(phrase)) score += 40;
    for (const t of tokens) {
      if (a.foldedTitle.includes(t)) score += 10;
      if (a.foldedText.includes(t)) score += 2;
    }

    hits.push({ ...stripIndex(a), score, snippet: snippetFor(a.text, a.foldedText, tokens) });
  }

  return hits.sort((a, b) => b.score - a.score).slice(0, limit);
}

function stripIndex(a: IndexedArticle & { score?: number; snippet?: string }): ArticleHit {
  return { lawId: a.lawId, article: a.article, path: a.path, score: a.score ?? 0, snippet: a.snippet ?? '' };
}

// ── Nối trích dẫn của Chat về Thư viện ──────────────────────────

/** "91/2015/QH13", "BLDS_2015", "Bộ luật Dân sự 2015" → khoá so khớp chung */
const refKey = (s: string) => fold(s).replace(/[^a-z0-9]/g, '');

/** "Dieu 328", "Điều 328.", "328" → "328" */
export function normalizeArticleNumber(raw?: string | number | null): string | null {
  if (raw == null) return null;
  const m = fold(String(raw)).match(/(\d{1,4}[a-z]?)/);
  return m ? m[1] : null;
}

/** Khoá duy nhất của một node cấu trúc trong văn bản: "Phần thứ nhất/Chương I" */
export const structureKey = (parentKey: string, node: StructureNode) => (parentKey ? `${parentKey}/${node.label}` : node.label);

export const articleAnchorId = (number: string) => `dieu-${number}`;

/** "Phần thứ nhất/Chương I" → "muc-phan-thu-nhat-chuong-i" */
export const headingAnchorId = (structureKey: string) => `muc-${fold(structureKey).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}`;

export function lawPath(lawId: string, articleNumber?: string | null): string {
  return `/thu-vien/${encodeURIComponent(lawId)}${articleNumber ? `#${articleAnchorId(articleNumber)}` : ''}`;
}

// ── Service ──────────────────────────────────────────────────────

export function createLibraryService(source: LibrarySource) {
  let indexPromise: Promise<LawSummary[]> | null = null;
  const lawPromises = new Map<string, Promise<LawDocument>>();

  // Lỗi mạng không được "dính" vào cache, nếu không bấm Thử lại cũng vô ích
  const remember = <T>(p: Promise<T>, forget: () => void) => {
    p.catch(forget);
    return p;
  };

  const getIndex = () => {
    indexPromise ??= remember(source.loadIndex(), () => (indexPromise = null));
    return indexPromise;
  };

  const getLaw = (id: string): Promise<LawDocument> => {
    let p = lawPromises.get(id);
    if (!p) {
      p = remember(
        source.loadLaw(id).then((law) => {
          if (!law) throw new LawNotFoundError(id);
          return law;
        }),
        () => lawPromises.delete(id),
      );
      lawPromises.set(id, p);
    }
    return p;
  };

  return {
    getIndex,
    getLaw,

    /** Đã tải văn bản này chưa (để biết có cần hiện khung chờ không) */
    isLawCached: (id: string) => lawPromises.has(id),

    async searchAll(query: string, limit = 40): Promise<ArticleHit[]> {
      if (source.searchArticles) return source.searchArticles(query, limit);
      const laws = await Promise.all((await getIndex()).map((l) => getLaw(l.id)));
      return laws
        .flatMap((law) => searchLaw(law, query, limit))
        .sort((a, b) => b.score - a.score)
        .slice(0, limit);
    },

    /** Tìm văn bản trong thư viện ứng với một trích dẫn (số hiệu, doc_id, tên) */
    resolveReference(laws: LawSummary[], ...refs: (string | undefined | null)[]): LawSummary | undefined {
      const keys = refs.filter((r): r is string => !!r).map(refKey).filter(Boolean);
      if (!keys.length) return undefined;
      return laws.find((law) => {
        const own = [law.id, law.so_hieu, law.short_title, ...(law.aliases ?? [])]
          .filter((x): x is string => !!x)
          .map(refKey);
        return keys.some((k) => own.includes(k));
      });
    },
  };
}

export class LawNotFoundError extends Error {
  constructor(id: string) {
    super(`Không tìm thấy văn bản "${id}" trong thư viện.`);
    this.name = 'LawNotFoundError';
  }
}

export const libraryService = createLibraryService(supabaseSource);
