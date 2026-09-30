-- ==========================================
-- LƯU HÀNH LEGAL RAG - SUPABASE DATABASE SCHEMA ("LegalRAG")
-- ==========================================

-- 1. KHỞI TẠO SCHEMA DÀNH RIÊNG CHO DỰ ÁN "LegalRAG"
CREATE SCHEMA IF NOT EXISTS "LegalRAG";

-- Gán quyền truy cập cho Schema mới
GRANT USAGE ON SCHEMA "LegalRAG" TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA "LegalRAG" TO anon, authenticated, service_role;
GRANT ALL ON ALL ROUTINES IN SCHEMA "LegalRAG" TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA "LegalRAG" TO anon, authenticated, service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA "LegalRAG" GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA "LegalRAG" GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA "LegalRAG" GRANT ALL ON ROUTINES TO anon, authenticated, service_role;

-- 2. BẢNG PROFILES (Lưu thông tin người dùng từ Auth)
CREATE TABLE IF NOT EXISTS "LegalRAG".profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT,
  full_name TEXT,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Bật Row Level Security (RLS) cho Profiles
ALTER TABLE "LegalRAG".profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public profiles are viewable by everyone" 
  ON "LegalRAG".profiles FOR SELECT USING (true);

CREATE POLICY "Users can insert their own profile" 
  ON "LegalRAG".profiles FOR INSERT WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can update their own profile" 
  ON "LegalRAG".profiles FOR UPDATE USING (auth.uid() = id);

-- Trigger tự động tạo Profile khi User Đăng ký mới
CREATE OR REPLACE FUNCTION "LegalRAG".handle_new_user() 
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO "LegalRAG".profiles (id, email, full_name, avatar_url)
  VALUES (
    new.id, 
    new.email, 
    COALESCE(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', new.email),
    COALESCE(new.raw_user_meta_data->>'avatar_url', new.raw_user_meta_data->>'picture')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION "LegalRAG".handle_new_user();

-- 3. BẢNG THREADS (Lưu danh sách cuộc trò chuyện chính của từng User)
CREATE TABLE IF NOT EXISTS "LegalRAG".threads (
  id TEXT PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT 'Cuộc trò chuyện mới',
  is_pinned BOOLEAN DEFAULT FALSE,
  theme_bg TEXT DEFAULT 'default',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE "LegalRAG".threads ENABLE ROW LEVEL SECURITY;

-- Policy chặt chẽ cho Threads: User chỉ xem và thao tác trên thread của chính mình
DROP POLICY IF EXISTS "Users can manage their own threads" ON "LegalRAG".threads;
CREATE POLICY "Users can manage their own threads" 
  ON "LegalRAG".threads FOR ALL 
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- 4. BẢNG MESSAGES (Lưu lịch sử tin nhắn - phân quyền riêng cho từng user và hỗ trợ Sub-thread / Branch)
CREATE TABLE IF NOT EXISTS "LegalRAG".messages (
  id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL REFERENCES "LegalRAG".threads(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  parent_message_id TEXT REFERENCES "LegalRAG".messages(id) ON DELETE CASCADE, -- ID tin nhắn cha nếu thuộc nhánh con (Sub-thread)
  sender TEXT NOT NULL CHECK (sender IN ('user', 'assistant')),
  content TEXT NOT NULL,
  verbose_info JSONB DEFAULT NULL,
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE "LegalRAG".messages ENABLE ROW LEVEL SECURITY;

-- Các Policy bảo mật RLS cho Messages: Đảm bảo User CHỈ xem, thêm, sửa, xóa tin nhắn của chính mình
DROP POLICY IF EXISTS "Users can view messages of their own threads" ON "LegalRAG".messages;
DROP POLICY IF EXISTS "Users can only select their own messages" ON "LegalRAG".messages;
DROP POLICY IF EXISTS "Users can only insert their own messages" ON "LegalRAG".messages;
DROP POLICY IF EXISTS "Users can only update their own messages" ON "LegalRAG".messages;
DROP POLICY IF EXISTS "Users can only delete their own messages" ON "LegalRAG".messages;

CREATE POLICY "Users can only select their own messages" 
  ON "LegalRAG".messages FOR SELECT 
  USING (auth.uid() = user_id);

CREATE POLICY "Users can only insert their own messages" 
  ON "LegalRAG".messages FOR INSERT 
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can only update their own messages" 
  ON "LegalRAG".messages FOR UPDATE 
  USING (auth.uid() = user_id);

CREATE POLICY "Users can only delete their own messages" 
  ON "LegalRAG".messages FOR DELETE 
  USING (auth.uid() = user_id);

-- 5. BẢNG SUB_THREADS (Quản lý các nhánh thảo luận phân tách từ phản hồi của Assistant)
CREATE TABLE IF NOT EXISTS "LegalRAG".sub_threads (
  id TEXT PRIMARY KEY,
  parent_message_id TEXT NOT NULL REFERENCES "LegalRAG".messages(id) ON DELETE CASCADE,
  thread_id TEXT NOT NULL REFERENCES "LegalRAG".threads(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL, -- Tiêu đề nhánh (lấy từ các dòng đầu của câu trả lời hoặc tóm tắt)
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE "LegalRAG".sub_threads ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can manage their own sub_threads" ON "LegalRAG".sub_threads;
CREATE POLICY "Users can manage their own sub_threads" 
  ON "LegalRAG".sub_threads FOR ALL 
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);


-- 5. BẢNG LƯU TRỮ VĂN BẢN PHÁP LUẬT (RAG LEGAL KNOWLEDGE)
CREATE TABLE IF NOT EXISTS "LegalRAG".legal_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,                  -- Tiêu đề văn bản (VD: Bộ luật Dân sự 2015)
  document_number TEXT,                 -- Số hiệu văn bản (Luật số 91/2015/QH13)
  article TEXT,                         -- Điều khoản (Điều 328)
  content TEXT NOT NULL,                -- Trích dẫn nội dung luật
  status TEXT DEFAULT 'Còn hiệu lực',   -- Tình trạng hiệu lực (Còn hiệu lực, Hết hiệu lực, Sửa đổi)
  created_at TIMESTAMPTZ DEFAULT NOW()
);
