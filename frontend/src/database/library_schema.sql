-- ==========================================
-- THƯ VIỆN PHÁP LUẬT - SUPABASE SCHEMA ("LegalRAG")
-- ==========================================
-- Chạy SAU supabase_schema.sql. Chạy lại nhiều lần vẫn an toàn (idempotent).
--
-- Ai ghi dữ liệu: CHỈ script backend/scripts/build_legal_library.py (dùng service_role,
-- bỏ qua RLS). Khách và người dùng đăng nhập chỉ được ĐỌC văn bản đã published.
--
-- Không dùng lại bảng legal_documents: bảng đó phẳng (một dòng một trích dẫn), không giữ
-- được cây Phần/Chương/Mục/Điều mà trang đọc cần.
--
-- Mở rộng sau này:
--   * Văn bản mới: không phải sửa schema, chỉ thêm vào manifest rồi chạy script
--   * Cấp cấu trúc mới (vd. "Tiết"): nằm trong JSON của cột toc, không phải sửa schema
--   * Tìm kiếm mạnh hơn: thay thân hàm library_search, client không đổi. Hiện quét tuần tự —
--     vài chục nghìn Điều vẫn chỉ vài ms; lớn hơn nữa thì thêm pg_trgm/full-text index ở đây

-- 1. VĂN BẢN (metadata + mục lục, KHÔNG có nội dung Điều)
CREATE TABLE IF NOT EXISTS "LegalRAG".library_documents (
  id TEXT PRIMARY KEY,                       -- slug, vd. 'bo-luat-dan-su-2015' (nằm trên URL)
  title TEXT NOT NULL,
  short_title TEXT,
  so_hieu TEXT,
  loai_van_ban TEXT,
  co_quan_ban_hanh TEXT,
  ngay_ban_hanh DATE,
  ngay_hieu_luc DATE,
  tinh_trang TEXT,
  linh_vuc TEXT,
  summary TEXT,
  version_note TEXT,
  aliases TEXT[] NOT NULL DEFAULT '{}',      -- doc_id của RAG, tên khác... để nối trích dẫn Chat
  stats JSONB NOT NULL DEFAULT '{}',         -- {articles, parts, chapters, sections, characters}
  first_article TEXT,
  last_article TEXT,
  preamble TEXT[] NOT NULL DEFAULT '{}',
  closing TEXT[] NOT NULL DEFAULT '{}',
  toc JSONB NOT NULL DEFAULT '[]',           -- cây cấu trúc; lá là {"type":"article","number":"328"}
  sort_order INT NOT NULL DEFAULT 0,
  published BOOLEAN NOT NULL DEFAULT false,  -- script tắt trong lúc nạp lại, bật khi xong
  schema_version INT NOT NULL DEFAULT 1,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. ĐIỀU
-- Bỏ dấu + chữ thường để tìm không dấu ("dat coc" khớp "Đặt cọc"). PHẢI cho kết quả giống
-- hàm fold() ở frontend/src/lib/library/text.ts — client fold từ khoá rồi so với cột sinh ra từ hàm này.
-- Tự viết thay cho extension unaccent vì cột GENERATED đòi hàm IMMUTABLE.
CREATE OR REPLACE FUNCTION "LegalRAG".library_fold(value TEXT)
RETURNS TEXT
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT SET search_path = ''
AS $$
  SELECT lower(translate(regexp_replace(normalize(value, NFD), U&'[\0300-\036F]', '', 'g'), 'Đđ', 'dd'));
$$;

-- array_to_string chỉ là STABLE nên phải bọc lại mới dùng được trong cột GENERATED
CREATE OR REPLACE FUNCTION "LegalRAG".library_fold(value TEXT[])
RETURNS TEXT
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT SET search_path = ''
AS $$
  SELECT "LegalRAG".library_fold(array_to_string(value, E'\n'));
$$;

CREATE TABLE IF NOT EXISTS "LegalRAG".library_articles (
  document_id TEXT NOT NULL REFERENCES "LegalRAG".library_documents(id) ON DELETE CASCADE,
  number TEXT NOT NULL,                      -- '328', '468a'
  ordinal INT NOT NULL,                      -- thứ tự trong văn bản
  title TEXT NOT NULL,
  paragraphs TEXT[] NOT NULL,
  path JSONB NOT NULL DEFAULT '[]',          -- [{type,label,title}] Phần/Chương/Mục chứa Điều (cho kết quả tìm kiếm)
  search_title TEXT GENERATED ALWAYS AS ("LegalRAG".library_fold(title)) STORED,
  search_body TEXT GENERATED ALWAYS AS ("LegalRAG".library_fold(paragraphs)) STORED,
  PRIMARY KEY (document_id, number)
);

CREATE INDEX IF NOT EXISTS library_articles_order_idx ON "LegalRAG".library_articles(document_id, ordinal);

-- 3. RLS: chỉ đọc, chỉ văn bản đã published
ALTER TABLE "LegalRAG".library_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE "LegalRAG".library_articles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Published library documents are viewable by everyone" ON "LegalRAG".library_documents;
CREATE POLICY "Published library documents are viewable by everyone"
  ON "LegalRAG".library_documents FOR SELECT USING (published);

DROP POLICY IF EXISTS "Articles of published documents are viewable by everyone" ON "LegalRAG".library_articles;
CREATE POLICY "Articles of published documents are viewable by everyone"
  ON "LegalRAG".library_articles FOR SELECT USING (
    EXISTS (SELECT 1 FROM "LegalRAG".library_documents d WHERE d.id = document_id AND d.published)
  );

-- 4. TÌM KIẾM TRÊN MỌI VĂN BẢN
-- terms: các từ khoá ĐÃ bỏ dấu + chữ thường (client tự fold, khớp library_fold sinh ra
-- search_title/search_body) → không cần extension unaccent. Mọi từ phải xuất hiện ở tiêu đề
-- hoặc nội dung; khớp nguyên cụm và khớp ở tiêu đề được xếp trên.
-- article_number khác NULL: tìm theo số Điều (đúng số lên đầu, rồi các số bắt đầu bằng nó).
CREATE OR REPLACE FUNCTION "LegalRAG".library_search(
  terms TEXT[] DEFAULT '{}',
  article_number TEXT DEFAULT NULL,
  only_document TEXT DEFAULT NULL,
  max_results INT DEFAULT 40
)
RETURNS TABLE (document_id TEXT, number TEXT, title TEXT, path JSONB, paragraphs TEXT[], score INT)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = ''
AS $$
  WITH q AS (
    SELECT array_to_string(terms, ' ') AS phrase
  )
  SELECT a.document_id, a.number, a.title, a.path, a.paragraphs,
    CASE
      WHEN article_number IS NOT NULL THEN CASE WHEN a.number = article_number THEN 1000 ELSE 500 END
      ELSE
        (CASE WHEN a.search_title = q.phrase THEN 200 WHEN strpos(a.search_title, q.phrase) > 0 THEN 100 ELSE 0 END)
        + (CASE WHEN strpos(a.search_body, q.phrase) > 0 THEN 40 ELSE 0 END)
        + (SELECT COALESCE(SUM((CASE WHEN strpos(a.search_title, t) > 0 THEN 10 ELSE 0 END)
                             + (CASE WHEN strpos(a.search_body, t) > 0 THEN 2 ELSE 0 END)), 0)::INT
           FROM unnest(terms) AS t)
    END AS score
  FROM "LegalRAG".library_articles a
  JOIN "LegalRAG".library_documents d ON d.id = a.document_id AND d.published
  CROSS JOIN q
  WHERE (only_document IS NULL OR a.document_id = only_document)
    AND CASE
      WHEN article_number IS NOT NULL THEN a.number LIKE article_number || '%'
      ELSE cardinality(terms) > 0 AND NOT EXISTS (
        SELECT 1 FROM unnest(terms) AS t
        WHERE strpos(a.search_title, t) = 0 AND strpos(a.search_body, t) = 0
      )
    END
  ORDER BY score DESC, length(a.number), a.document_id, a.ordinal
  LIMIT LEAST(GREATEST(max_results, 1), 100);
$$;

-- 5. QUYỀN TỐI THIỂU
-- Schema LegalRAG có ALTER DEFAULT PRIVILEGES ... GRANT ALL cho anon/authenticated, nên bảng mới
-- tự nhận đủ mọi quyền. Thu hồi hết rồi cấp lại đúng quyền đọc (RLS vẫn là lớp chặn chính).
REVOKE ALL ON "LegalRAG".library_documents, "LegalRAG".library_articles FROM anon, authenticated;
GRANT SELECT ON "LegalRAG".library_documents, "LegalRAG".library_articles TO anon, authenticated;
GRANT ALL ON "LegalRAG".library_documents, "LegalRAG".library_articles TO service_role;

REVOKE ALL ON FUNCTION "LegalRAG".library_search(TEXT[], TEXT, TEXT, INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION "LegalRAG".library_search(TEXT[], TEXT, TEXT, INT) TO anon, authenticated, service_role;
