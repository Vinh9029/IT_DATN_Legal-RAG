import { supabase } from '@/lib/supabase';
import type { LibrarySource } from './library-service';
import { fold, parseArticleQuery, queryTokens, snippetFor } from './text';
import { LIBRARY_SCHEMA_VERSION } from './types';
import type { ArticleHit, ArticleNode, LawDocument, LawNode, LawSummary, StructureNode } from './types';

// Bảng, RLS và hàm tìm kiếm: src/database/library_schema.sql
// Dữ liệu nạp bằng backend/scripts/build_legal_library.py

const SUMMARY_COLUMNS =
  'id,title,short_title,so_hieu,loai_van_ban,co_quan_ban_hanh,ngay_ban_hanh,ngay_hieu_luc,tinh_trang,linh_vuc,summary,version_note,aliases,stats,first_article,last_article';

// PostgREST của Supabase trả tối đa 1000 dòng mỗi lần ("Max rows") — bộ luật dài hơn phải tải nhiều trang
const PAGE_SIZE = 1000;

type TocNode = { type: 'article'; number: string } | (Omit<StructureNode, 'children'> & { children: TocNode[] });
type ArticleRow = { number: string; title: string; paragraphs: string[] };
type SearchRow = ArticleRow & { document_id: string; path: Omit<StructureNode, 'children'>[]; score: number };

const fail = (what: string, error: { message: string }) => new Error(`Không tải được ${what}: ${error.message}`);

/** Gắn nội dung Điều vào mục lục (lá của mục lục chỉ có số Điều) */
function assemble(toc: TocNode[], articles: Map<string, ArticleNode>): LawNode[] {
  const out: LawNode[] = [];
  for (const node of toc) {
    if (node.type === 'article') {
      const article = articles.get(node.number);
      if (article) out.push(article);
    } else {
      out.push({ ...node, children: assemble(node.children, articles) });
    }
  }
  return out;
}

export const supabaseSource: LibrarySource = {
  async loadIndex() {
    const { data, error } = await supabase
      .from('library_documents')
      .select(SUMMARY_COLUMNS)
      .order('sort_order')
      .order('title');
    if (error) throw fail('thư viện', error);
    return data as unknown as LawSummary[];
  },

  async loadLaw(id) {
    const { data: doc, error } = await supabase
      .from('library_documents')
      .select(`${SUMMARY_COLUMNS},preamble,closing,toc,schema_version`)
      .eq('id', id)
      .maybeSingle();
    if (error) throw fail('văn bản', error);
    if (!doc) return null;
    const { toc, schema_version, ...meta } = doc as unknown as LawSummary & { toc: TocNode[]; schema_version: number };
    if (schema_version !== LIBRARY_SCHEMA_VERSION) {
      console.warn(`[library] ${id}: schema_version ${schema_version} ≠ ${LIBRARY_SCHEMA_VERSION} — cần nạp lại dữ liệu`);
    }

    const total = meta.stats?.articles ?? 0;
    const pages = await Promise.all(
      Array.from({ length: Math.max(1, Math.ceil(total / PAGE_SIZE)) }, (_, i) =>
        supabase
          .from('library_articles')
          .select('number,title,paragraphs')
          .eq('document_id', id)
          .order('ordinal')
          .range(i * PAGE_SIZE, (i + 1) * PAGE_SIZE - 1),
      ),
    );
    const articles = new Map<string, ArticleNode>();
    for (const page of pages) {
      if (page.error) throw fail('nội dung văn bản', page.error);
      for (const row of page.data as ArticleRow[]) articles.set(row.number, { type: 'article', ...row });
    }

    return { ...(meta as Omit<LawDocument, 'structure'>), structure: assemble(toc, articles) };
  },

  async searchArticles(query, limit) {
    const number = parseArticleQuery(query);
    // Từ khoá gửi lên đã fold sẵn — khớp cột search_title/search_body do library_fold sinh ra
    const terms = number ? [] : queryTokens(query);
    if (!number && !terms.length) return [];

    const { data, error } = await supabase.rpc('library_search', {
      terms,
      article_number: number,
      max_results: limit,
    });
    if (error) throw fail('kết quả tìm kiếm', error);

    return (data as SearchRow[]).map((row): ArticleHit => {
      const text = row.paragraphs.join('\n');
      return {
        lawId: row.document_id,
        article: { type: 'article', number: row.number, title: row.title, paragraphs: row.paragraphs },
        path: row.path.map((p) => ({ ...p, children: [] })),
        score: row.score,
        snippet: number ? '' : snippetFor(text, fold(text), terms),
      };
    });
  },
};
