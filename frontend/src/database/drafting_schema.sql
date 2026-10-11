-- ==========================================
-- SOẠN THẢO VĂN BẢN - SUPABASE SCHEMA ("LegalRAG")
-- ==========================================
-- Chạy SAU supabase_schema.sql. Chạy lại nhiều lần vẫn an toàn (idempotent).
--
-- Mỗi dòng là một bản nháp của MỘT người dùng: chỉ chủ sở hữu được xem/sửa/xoá (RLS).
-- Biểu mẫu (ô cần điền, bố cục) KHÔNG nằm trong DB mà ở frontend/src/lib/drafting/templates —
-- bảng chỉ lưu template_id + giá trị đã điền, nên thêm/sửa biểu mẫu không phải sửa schema.
--
-- Mở rộng sau này:
--   * Chia sẻ bản nháp cho người khác: thêm bảng drafting_shares + policy SELECT theo bảng đó
--   * Lịch sử phiên bản đầy đủ: thêm bảng drafting_revisions (draft_id, field_values, created_at)

-- 1. BẢN NHÁP
CREATE TABLE IF NOT EXISTS "LegalRAG".drafting_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL DEFAULT auth.uid() REFERENCES "LegalRAG".profiles(id) ON DELETE CASCADE,
  template_id TEXT NOT NULL CHECK (template_id ~ '^[a-z0-9-]{1,80}$'),
  template_version INT NOT NULL DEFAULT 1,
  title TEXT NOT NULL CHECK (char_length(btrim(title)) BETWEEN 1 AND 200),
  -- { "<id ô>": "chuỗi" | ["dòng 1", "dòng 2"] }
  field_values JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(field_values) = 'object' AND pg_column_size(field_values) < 200000),
  -- Lịch sử trò chuyện với AI, mỗi tin của AI giữ cả giá trị trước/sau để hoàn tác được sau khi tải lại
  chat JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(chat) = 'array' AND pg_column_size(chat) < 1000000),
  -- % ô bắt buộc đã điền — để danh sách bản nháp không phải tải field_values
  progress SMALLINT NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS drafting_documents_owner_idx ON "LegalRAG".drafting_documents(owner_id, updated_at DESC);

-- updated_at do DB đặt, không tin đồng hồ máy khách
CREATE OR REPLACE FUNCTION "LegalRAG".drafting_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = '';

DROP TRIGGER IF EXISTS drafting_documents_touch ON "LegalRAG".drafting_documents;
CREATE TRIGGER drafting_documents_touch
  BEFORE UPDATE ON "LegalRAG".drafting_documents
  FOR EACH ROW EXECUTE FUNCTION "LegalRAG".drafting_touch_updated_at();

-- 2. RLS: chỉ chủ sở hữu
ALTER TABLE "LegalRAG".drafting_documents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Owners can view their drafts" ON "LegalRAG".drafting_documents;
CREATE POLICY "Owners can view their drafts"
  ON "LegalRAG".drafting_documents FOR SELECT TO authenticated
  USING (auth.uid() = owner_id);

DROP POLICY IF EXISTS "Owners can create drafts" ON "LegalRAG".drafting_documents;
CREATE POLICY "Owners can create drafts"
  ON "LegalRAG".drafting_documents FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = owner_id);

DROP POLICY IF EXISTS "Owners can update their drafts" ON "LegalRAG".drafting_documents;
CREATE POLICY "Owners can update their drafts"
  ON "LegalRAG".drafting_documents FOR UPDATE TO authenticated
  USING (auth.uid() = owner_id)
  WITH CHECK (auth.uid() = owner_id);

DROP POLICY IF EXISTS "Owners can delete their drafts" ON "LegalRAG".drafting_documents;
CREATE POLICY "Owners can delete their drafts"
  ON "LegalRAG".drafting_documents FOR DELETE TO authenticated
  USING (auth.uid() = owner_id);

-- 3. QUYỀN TỐI THIỂU
-- Schema LegalRAG có ALTER DEFAULT PRIVILEGES ... GRANT ALL cho anon/authenticated, nên bảng mới
-- tự nhận đủ mọi quyền. Thu hồi hết rồi cấp lại đúng phần cần dùng (RLS vẫn là lớp chặn chính).
-- Khách (anon) không có quyền gì: bản nháp là dữ liệu riêng tư.
REVOKE ALL ON "LegalRAG".drafting_documents FROM anon, authenticated;
GRANT SELECT, INSERT, DELETE ON "LegalRAG".drafting_documents TO authenticated;
-- Không cho đổi chủ sở hữu / ngày tạo qua API
GRANT UPDATE (template_version, title, field_values, chat, progress) ON "LegalRAG".drafting_documents TO authenticated;
GRANT ALL ON "LegalRAG".drafting_documents TO service_role;

REVOKE ALL ON FUNCTION "LegalRAG".drafting_touch_updated_at() FROM PUBLIC;
