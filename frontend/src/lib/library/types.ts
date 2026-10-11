// Dữ liệu do backend/scripts/build_legal_library.py nạp vào Supabase (cột schema_version).
// Đổi cấu trúc dữ liệu thì tăng SCHEMA_VERSION ở script và ở đây.

export const LIBRARY_SCHEMA_VERSION = 1;

/** Cấp cấu trúc của văn bản, từ ngoài vào trong. Văn bản thiếu cấp nào thì không có node cấp đó. */
export type StructureLevel = 'part' | 'chapter' | 'section' | 'subsection';

export interface LawMeta {
  id: string;
  title: string;
  short_title?: string;
  so_hieu?: string;
  loai_van_ban?: string;
  co_quan_ban_hanh?: string;
  ngay_ban_hanh?: string; // ISO yyyy-mm-dd
  ngay_hieu_luc?: string;
  tinh_trang?: string;
  linh_vuc?: string;
  summary?: string;
  version_note?: string;
  /** Tên/mã khác của văn bản (doc_id của RAG, tên đầy đủ...) — để nối trích dẫn của Chat về Thư viện */
  aliases?: string[];
}

export interface LawStats {
  articles: number;
  parts: number;
  chapters: number;
  sections: number;
  characters: number;
}

/** Một văn bản trong danh mục — đủ để hiện danh sách, không có nội dung */
export interface LawSummary extends LawMeta {
  stats: LawStats;
  first_article: string | null;
  last_article: string | null;
}

export interface ArticleNode {
  type: 'article';
  number: string; // "328", "468a"
  title: string;
  paragraphs: string[];
}

export interface StructureNode {
  type: StructureLevel;
  label: string; // "Chương XV"
  title: string; // "QUY ĐỊNH CHUNG"
  children: LawNode[];
}

export type LawNode = StructureNode | ArticleNode;

export interface LawDocument extends LawSummary {
  preamble: string[];
  structure: LawNode[];
  closing: string[];
}

/** Điều đã trải phẳng, kèm đường dẫn cấu trúc chứa nó (để hiện breadcrumb, tìm kiếm) */
export interface FlatArticle {
  lawId: string;
  article: ArticleNode;
  path: StructureNode[];
}

export interface ArticleHit extends FlatArticle {
  score: number;
  /** Đoạn trích quanh chỗ khớp; rỗng khi khớp tiêu đề/số Điều */
  snippet: string;
}
