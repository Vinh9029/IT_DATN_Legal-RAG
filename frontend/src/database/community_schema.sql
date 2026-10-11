-- ==========================================
-- COMMUNITY (DIỄN ĐÀN) - SUPABASE SCHEMA ("LegalRAG")
-- ==========================================
-- Chạy SAU supabase_schema.sql (cần bảng "LegalRAG".profiles).
-- Chạy lại nhiều lần vẫn an toàn (idempotent).
--
-- Mở rộng sau này:
--   * Cảm xúc khác ("hữu ích", "cảm ơn"...): chỉ cần thêm giá trị vào CHECK của community_reactions.kind
--   * Thả cảm xúc cho đối tượng mới: thêm vào CHECK của target_type + trigger dọn reactions
--   * Trả lời lồng nhau: community_comments.parent_id đã có sẵn

-- 0. Bổ sung profile cho tài khoản tạo trước khi có trigger handle_new_user
INSERT INTO "LegalRAG".profiles (id, email, full_name, avatar_url)
SELECT u.id,
       u.email,
       COALESCE(u.raw_user_meta_data->>'full_name', u.raw_user_meta_data->>'name', u.email),
       COALESCE(u.raw_user_meta_data->>'avatar_url', u.raw_user_meta_data->>'picture')
FROM auth.users u
ON CONFLICT (id) DO NOTHING;

-- Đồng bộ tên/ảnh đại diện khi người dùng đổi (vd. upload avatar ở Profile_modal)
CREATE OR REPLACE FUNCTION "LegalRAG".handle_user_updated()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE "LegalRAG".profiles SET
    email = new.email,
    full_name = COALESCE(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', full_name),
    avatar_url = COALESCE(new.raw_user_meta_data->>'avatar_url', new.raw_user_meta_data->>'picture', avatar_url),
    updated_at = NOW()
  WHERE id = new.id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

DROP TRIGGER IF EXISTS on_auth_user_updated ON auth.users;
CREATE TRIGGER on_auth_user_updated
  AFTER UPDATE OF email, raw_user_meta_data ON auth.users
  FOR EACH ROW EXECUTE FUNCTION "LegalRAG".handle_user_updated();


-- 1. BÀI ĐĂNG
CREATE TABLE IF NOT EXISTS "LegalRAG".community_posts (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  author_id UUID NOT NULL DEFAULT auth.uid() REFERENCES "LegalRAG".profiles(id) ON DELETE CASCADE,
  content TEXT NOT NULL CHECK (char_length(btrim(content)) BETWEEN 1 AND 3000),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS community_posts_author_idx ON "LegalRAG".community_posts(author_id);

ALTER TABLE "LegalRAG".community_posts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Community posts are viewable by everyone" ON "LegalRAG".community_posts;
CREATE POLICY "Community posts are viewable by everyone"
  ON "LegalRAG".community_posts FOR SELECT USING (true);

DROP POLICY IF EXISTS "Users can create their own posts" ON "LegalRAG".community_posts;
CREATE POLICY "Users can create their own posts"
  ON "LegalRAG".community_posts FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = author_id);

DROP POLICY IF EXISTS "Users can delete their own posts" ON "LegalRAG".community_posts;
CREATE POLICY "Users can delete their own posts"
  ON "LegalRAG".community_posts FOR DELETE TO authenticated
  USING (auth.uid() = author_id);


-- 2. BÌNH LUẬN
CREATE TABLE IF NOT EXISTS "LegalRAG".community_comments (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  post_id BIGINT NOT NULL REFERENCES "LegalRAG".community_posts(id) ON DELETE CASCADE,
  parent_id BIGINT REFERENCES "LegalRAG".community_comments(id) ON DELETE CASCADE,
  author_id UUID NOT NULL DEFAULT auth.uid() REFERENCES "LegalRAG".profiles(id) ON DELETE CASCADE,
  content TEXT NOT NULL CHECK (char_length(btrim(content)) BETWEEN 1 AND 1000),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS community_comments_post_idx ON "LegalRAG".community_comments(post_id, id);

ALTER TABLE "LegalRAG".community_comments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Community comments are viewable by everyone" ON "LegalRAG".community_comments;
CREATE POLICY "Community comments are viewable by everyone"
  ON "LegalRAG".community_comments FOR SELECT USING (true);

DROP POLICY IF EXISTS "Users can create their own comments" ON "LegalRAG".community_comments;
CREATE POLICY "Users can create their own comments"
  ON "LegalRAG".community_comments FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = author_id);

DROP POLICY IF EXISTS "Users can delete their own comments" ON "LegalRAG".community_comments;
CREATE POLICY "Users can delete their own comments"
  ON "LegalRAG".community_comments FOR DELETE TO authenticated
  USING (auth.uid() = author_id);


-- 3. CẢM XÚC (dùng chung cho mọi loại đối tượng)
CREATE TABLE IF NOT EXISTS "LegalRAG".community_reactions (
  target_type TEXT NOT NULL CHECK (target_type IN ('post', 'comment')),
  target_id BIGINT NOT NULL,
  user_id UUID NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'like' CHECK (kind IN ('like')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (target_type, target_id, user_id, kind)
);

CREATE INDEX IF NOT EXISTS community_reactions_target_idx
  ON "LegalRAG".community_reactions(target_type, target_id, kind);

ALTER TABLE "LegalRAG".community_reactions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Community reactions are viewable by everyone" ON "LegalRAG".community_reactions;
CREATE POLICY "Community reactions are viewable by everyone"
  ON "LegalRAG".community_reactions FOR SELECT USING (true);

DROP POLICY IF EXISTS "Users can add their own reactions" ON "LegalRAG".community_reactions;
CREATE POLICY "Users can add their own reactions"
  ON "LegalRAG".community_reactions FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can remove their own reactions" ON "LegalRAG".community_reactions;
CREATE POLICY "Users can remove their own reactions"
  ON "LegalRAG".community_reactions FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

-- target_id không có khoá ngoại (bảng dùng chung) → tự dọn khi bài/bình luận bị xoá
CREATE OR REPLACE FUNCTION "LegalRAG".community_cleanup_reactions()
RETURNS TRIGGER AS $$
BEGIN
  DELETE FROM "LegalRAG".community_reactions
  WHERE target_type = TG_ARGV[0] AND target_id = old.id;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

DROP TRIGGER IF EXISTS community_posts_cleanup_reactions ON "LegalRAG".community_posts;
CREATE TRIGGER community_posts_cleanup_reactions
  AFTER DELETE ON "LegalRAG".community_posts
  FOR EACH ROW EXECUTE FUNCTION "LegalRAG".community_cleanup_reactions('post');

DROP TRIGGER IF EXISTS community_comments_cleanup_reactions ON "LegalRAG".community_comments;
CREATE TRIGGER community_comments_cleanup_reactions
  AFTER DELETE ON "LegalRAG".community_comments
  FOR EACH ROW EXECUTE FUNCTION "LegalRAG".community_cleanup_reactions('comment');


-- 4. VIEW CHO FRONTEND: gộp tác giả + số đếm + "mình đã thích chưa" trong 1 truy vấn
-- security_invoker: view chạy với quyền của người gọi → RLS các bảng gốc vẫn áp dụng.
-- Không đọc cột email (để có thể khoá cột này với anon): full_name trùng email thì chỉ lấy phần trước @.
CREATE OR REPLACE VIEW "LegalRAG".community_post_feed
WITH (security_invoker = true) AS
SELECT
  p.id,
  p.content,
  p.created_at,
  p.author_id,
  CASE WHEN pr.full_name LIKE '%@%' THEN split_part(pr.full_name, '@', 1)
       ELSE COALESCE(NULLIF(btrim(pr.full_name), ''), 'Người dùng') END AS author_name,
  pr.avatar_url AS author_avatar,
  (SELECT COUNT(*) FROM "LegalRAG".community_reactions r
    WHERE r.target_type = 'post' AND r.target_id = p.id AND r.kind = 'like')::INT AS like_count,
  (SELECT COUNT(*) FROM "LegalRAG".community_comments c
    WHERE c.post_id = p.id)::INT AS comment_count,
  EXISTS (SELECT 1 FROM "LegalRAG".community_reactions r
    WHERE r.target_type = 'post' AND r.target_id = p.id AND r.kind = 'like'
      AND r.user_id = auth.uid()) AS liked_by_me
FROM "LegalRAG".community_posts p
JOIN "LegalRAG".profiles pr ON pr.id = p.author_id;

CREATE OR REPLACE VIEW "LegalRAG".community_comment_feed
WITH (security_invoker = true) AS
SELECT
  c.id,
  c.post_id,
  c.parent_id,
  c.content,
  c.created_at,
  c.author_id,
  CASE WHEN pr.full_name LIKE '%@%' THEN split_part(pr.full_name, '@', 1)
       ELSE COALESCE(NULLIF(btrim(pr.full_name), ''), 'Người dùng') END AS author_name,
  pr.avatar_url AS author_avatar,
  (SELECT COUNT(*) FROM "LegalRAG".community_reactions r
    WHERE r.target_type = 'comment' AND r.target_id = c.id AND r.kind = 'like')::INT AS like_count,
  EXISTS (SELECT 1 FROM "LegalRAG".community_reactions r
    WHERE r.target_type = 'comment' AND r.target_id = c.id AND r.kind = 'like'
      AND r.user_id = auth.uid()) AS liked_by_me
FROM "LegalRAG".community_comments c
JOIN "LegalRAG".profiles pr ON pr.id = c.author_id;

-- 5. QUYỀN TỐI THIỂU
-- Schema LegalRAG có ALTER DEFAULT PRIVILEGES ... GRANT ALL cho anon/authenticated, nên bảng mới
-- tự nhận đủ mọi quyền. Thu hồi hết rồi cấp lại đúng phần cần dùng (RLS vẫn là lớp chặn chính).
REVOKE ALL ON "LegalRAG".community_posts, "LegalRAG".community_comments, "LegalRAG".community_reactions,
              "LegalRAG".community_post_feed, "LegalRAG".community_comment_feed
  FROM anon, authenticated;

GRANT SELECT ON "LegalRAG".community_post_feed, "LegalRAG".community_comment_feed TO anon, authenticated;
GRANT SELECT ON "LegalRAG".community_posts, "LegalRAG".community_comments, "LegalRAG".community_reactions TO anon;
GRANT SELECT, INSERT, DELETE ON "LegalRAG".community_posts, "LegalRAG".community_comments, "LegalRAG".community_reactions TO authenticated;
