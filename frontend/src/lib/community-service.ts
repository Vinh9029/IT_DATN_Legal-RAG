import { supabase } from './supabase';

// Community lưu trên Supabase (schema "LegalRAG", xem database/community_schema.sql).
// Đọc qua 2 view community_post_feed / community_comment_feed (đã gộp tác giả + số đếm);
// ghi thẳng vào bảng gốc — quyền do RLS quyết định: ai cũng xem được, chỉ chủ mới xoá được.

export interface CommunityAuthor {
  id: string;
  name: string;
  avatar_url?: string | null;
}

export interface CommunityPost {
  id: number;
  author: CommunityAuthor;
  content: string;
  created_at: string;
  like_count: number;
  comment_count: number;
  liked_by_me: boolean;
}

export interface CommunityComment {
  id: number;
  post_id: number;
  author: CommunityAuthor;
  content: string;
  created_at: string;
  like_count: number;
  liked_by_me: boolean;
}

export interface Page<T> {
  items: T[];
  next_cursor: number | null;
}

// Thêm loại đối tượng thả cảm xúc được thì mở rộng ở đây (khớp TargetType bên backend)
export type ReactionTarget = 'post' | 'comment';

export interface ReactionState {
  target_type: ReactionTarget;
  target_id: number;
  liked: boolean;
  like_count: number;
}

export const POST_MAX_LENGTH = 3000;
export const COMMENT_MAX_LENGTH = 1000;

export class CommunityApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type DbError = { code?: string; message?: string } | null;

// Đổi lỗi PostgREST/Postgres sang thông báo tiếng Việt cho người dùng
function toApiError(error: DbError, fallback: string): CommunityApiError {
  const code = error?.code ?? '';
  if (code === 'PGRST106' || code === '42P01' || code === 'PGRST205') {
    return new CommunityApiError(503, 'Tính năng Cộng đồng chưa được cấu hình trên máy chủ.');
  }
  if (code === '42501') return new CommunityApiError(401, 'Bạn cần đăng nhập để thực hiện thao tác này.');
  if (code === '23514') return new CommunityApiError(422, 'Nội dung không hợp lệ hoặc quá dài.');
  if (code === '23503') return new CommunityApiError(404, 'Bài đăng không còn tồn tại.');
  if (/fetch|network/i.test(error?.message ?? '')) {
    return new CommunityApiError(0, 'Không kết nối được máy chủ. Vui lòng thử lại sau.');
  }
  return new CommunityApiError(500, fallback);
}

// ── Ánh xạ hàng của view (community_post_feed / community_comment_feed) ──
interface AuthorColumns {
  author_id: string;
  author_name: string | null;
  author_avatar: string | null;
}

const toAuthor = (row: AuthorColumns): CommunityAuthor => ({
  id: row.author_id,
  name: row.author_name || 'Người dùng',
  avatar_url: row.author_avatar,
});

type PostRow = AuthorColumns & Omit<CommunityPost, 'author'>;
type CommentRow = AuthorColumns & Omit<CommunityComment, 'author'>;

const toPost = ({ author_id, author_name, author_avatar, ...rest }: PostRow): CommunityPost => ({
  ...rest,
  author: toAuthor({ author_id, author_name, author_avatar }),
});

const toComment = ({ author_id, author_name, author_avatar, ...rest }: CommentRow): CommunityComment => ({
  ...rest,
  author: toAuthor({ author_id, author_name, author_avatar }),
});

const POST_COLUMNS = 'id, content, created_at, author_id, author_name, author_avatar, like_count, comment_count, liked_by_me';
const COMMENT_COLUMNS = 'id, post_id, content, created_at, author_id, author_name, author_avatar, like_count, liked_by_me';

// Lấy dư 1 hàng để biết còn trang sau không (phân trang theo id — keyset)
function toPage<R, T>(rows: R[], limit: number, map: (r: R) => T, idOf: (t: T) => number): Page<T> {
  const items = rows.slice(0, limit).map(map);
  return { items, next_cursor: rows.length > limit ? idOf(items[items.length - 1]) : null };
}

async function deleteOwned(table: string, id: number, what: string): Promise<void> {
  // RLS chỉ cho xoá hàng của chính mình; xoá 0 hàng nghĩa là không có quyền hoặc đã bị xoá
  const { data, error } = await supabase.from(table).delete().eq('id', id).select('id');
  if (error) throw toApiError(error, `Không xoá được ${what}.`);
  if (!data?.length) throw new CommunityApiError(403, `Bạn chỉ có thể xoá ${what} của mình.`);
}

export const communityService = {
  async listPosts(cursor?: number | null, limit = 10): Promise<Page<CommunityPost>> {
    let q = supabase.from('community_post_feed').select(POST_COLUMNS).order('id', { ascending: false }).limit(limit + 1);
    if (cursor) q = q.lt('id', cursor);
    const { data, error } = await q;
    if (error) throw toApiError(error, 'Không tải được bảng tin.');
    return toPage(data as PostRow[], limit, toPost, (p) => p.id);
  },

  async createPost(content: string): Promise<CommunityPost> {
    const { data, error } = await supabase.from('community_posts').insert({ content }).select('id').single();
    if (error) throw toApiError(error, 'Không đăng được bài.');
    const { data: row, error: readError } = await supabase
      .from('community_post_feed').select(POST_COLUMNS).eq('id', data.id).single();
    if (readError) throw toApiError(readError, 'Không tải được bài vừa đăng.');
    return toPost(row as PostRow);
  },

  deletePost: (postId: number) => deleteOwned('community_posts', postId, 'bài đăng'),

  async listComments(postId: number, cursor?: number | null, limit = 20): Promise<Page<CommunityComment>> {
    // Bình luận đọc theo thứ tự cũ → mới
    let q = supabase.from('community_comment_feed').select(COMMENT_COLUMNS)
      .eq('post_id', postId).order('id', { ascending: true }).limit(limit + 1);
    if (cursor) q = q.gt('id', cursor);
    const { data, error } = await q;
    if (error) throw toApiError(error, 'Không tải được bình luận.');
    return toPage(data as CommentRow[], limit, toComment, (c) => c.id);
  },

  async createComment(postId: number, content: string): Promise<CommunityComment> {
    const { data, error } = await supabase.from('community_comments').insert({ post_id: postId, content }).select('id').single();
    if (error) throw toApiError(error, 'Không gửi được bình luận.');
    const { data: row, error: readError } = await supabase
      .from('community_comment_feed').select(COMMENT_COLUMNS).eq('id', data.id).single();
    if (readError) throw toApiError(readError, 'Không tải được bình luận vừa gửi.');
    return toComment(row as CommentRow);
  },

  deleteComment: (commentId: number) => deleteOwned('community_comments', commentId, 'bình luận'),

  // Idempotent: thích lại khi đã thích (trùng khoá 23505) hay bỏ thích khi chưa thích đều không lỗi
  async setLike(target: ReactionTarget, targetId: number, liked: boolean): Promise<ReactionState> {
    const { data: auth } = await supabase.auth.getUser();
    if (!auth.user) throw new CommunityApiError(401, 'Bạn cần đăng nhập để thực hiện thao tác này.');
    const key = { target_type: target, target_id: targetId, user_id: auth.user.id, kind: 'like' };

    const { error } = liked
      ? await supabase.from('community_reactions').insert(key)
      : await supabase.from('community_reactions').delete().match(key);
    if (error && error.code !== '23505') throw toApiError(error, 'Không thể cập nhật lượt thích.');

    const { count, error: countError } = await supabase
      .from('community_reactions')
      .select('*', { count: 'exact', head: true })
      .match({ target_type: target, target_id: targetId, kind: 'like' });
    if (countError) throw toApiError(countError, 'Không thể cập nhật lượt thích.');
    return { target_type: target, target_id: targetId, liked, like_count: count ?? 0 };
  },
};

export function formatRelativeTime(iso: string): string {
  const date = new Date(iso);
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return 'Vừa xong';
  if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} giờ trước`;
  if (diff < 7 * 86400) return `${Math.floor(diff / 86400)} ngày trước`;
  return date.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
}
