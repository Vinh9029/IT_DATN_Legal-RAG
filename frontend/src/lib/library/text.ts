// Tìm kiếm không phân biệt dấu/hoa thường: "dat coc" khớp "Đặt cọc".
// `fold` giữ NGUYÊN độ dài chuỗi (mỗi ký tự gốc → đúng một ký tự), nên vị trí
// tìm được trên chuỗi đã fold dùng thẳng được để tô sáng trên chuỗi gốc.

const foldCache = new Map<string, string>();

function foldChar(c: string): string {
  let f = foldCache.get(c);
  if (f === undefined) {
    f = c.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace('đ', 'd');
    if (f.length !== 1) f = c.toLowerCase().length === 1 ? c.toLowerCase() : c;
    foldCache.set(c, f);
  }
  return f;
}

export function fold(text: string): string {
  let out = '';
  for (let i = 0; i < text.length; i++) out += foldChar(text[i]);
  return out;
}

/** Tách truy vấn thành các từ đã fold, bỏ trùng */
export function queryTokens(query: string): string[] {
  return [...new Set(fold(query).split(/[\s,.;:!?()"'“”]+/).filter(Boolean))];
}

/** "Điều 328", "dieu 328", "đ.328", "328" → "328" */
export function parseArticleQuery(query: string): string | null {
  const m = fold(query.trim()).match(/^(?:dieu|d\.?)?\s*(\d{1,4}[a-z]?)$/);
  return m ? m[1] : null;
}

export type Range = [start: number, end: number];

/** Các khoảng cần tô sáng trong `text` cho truy vấn `query` (đã gộp khoảng chồng nhau) */
export function matchRanges(text: string, query: string): Range[] {
  const folded = fold(text);
  const tokens = queryTokens(query).filter((t) => t.length >= 2 || /\d/.test(t));
  const phrase = tokens.join(' ');
  const ranges: Range[] = [];

  // Từ ngắn ("di", "co") nằm trong rất nhiều chữ khác ("điểm", "cọc") — chỉ tô khi đứng riêng
  const isWordChar = (i: number) => i >= 0 && i < folded.length && /[a-z0-9]/.test(folded[i]);
  const collect = (needle: string) => {
    if (!needle) return;
    const wholeWord = needle.length <= 2;
    let from = 0;
    for (;;) {
      const at = folded.indexOf(needle, from);
      if (at < 0) break;
      if (!wholeWord || (!isWordChar(at - 1) && !isWordChar(at + needle.length))) ranges.push([at, at + needle.length]);
      from = at + needle.length;
    }
  };

  if (tokens.length > 1) collect(phrase);
  tokens.forEach(collect);
  if (!ranges.length) return ranges;

  ranges.sort((a, b) => a[0] - b[0]);
  const merged: Range[] = [ranges[0]];
  for (const r of ranges.slice(1)) {
    const last = merged[merged.length - 1];
    if (r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else merged.push([...r]);
  }
  return merged;
}

/** Đoạn trích ~`radius` ký tự quanh vị trí `at`, cắt ở ranh giới từ */
export function snippetAround(text: string, at: number, radius = 80): string {
  let start = Math.max(0, at - radius);
  let end = Math.min(text.length, at + radius * 1.6);
  if (start > 0) start = text.indexOf(' ', start) + 1 || start;
  if (end < text.length) end = text.lastIndexOf(' ', end) > at ? text.lastIndexOf(' ', end) : end;
  return `${start > 0 ? '… ' : ''}${text.slice(start, end).trim()}${end < text.length ? ' …' : ''}`;
}

/** Đoạn trích quanh chỗ khớp đầu tiên (ưu tiên khớp nguyên cụm) — `folded` = fold(text) */
export function snippetFor(text: string, folded: string, tokens: string[]): string {
  let at = folded.indexOf(tokens.join(' '));
  if (at < 0) at = tokens.map((t) => folded.indexOf(t)).find((i) => i >= 0) ?? 0;
  return snippetAround(text, at);
}

export function formatDate(iso?: string): string {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return d && m && y ? `${d}/${m}/${y}` : iso;
}

// Danh từ riêng/chức danh văn bản luật luôn viết hoa — hạ chữ thường cả câu thì phải dựng lại
const PROPER_NOUNS = [
  'Cộng hòa xã hội chủ nghĩa Việt Nam', 'Việt Nam', 'Nhà nước', 'Quốc hội', 'Chính phủ',
  'Tòa án', 'Viện kiểm sát', 'Chánh án', 'Viện trưởng', 'Thẩm phán', 'Hội thẩm', 'Kiểm sát viên',
  'Thư ký Tòa án', 'Thẩm tra viên', 'Bộ luật', 'Ủy ban', 'Hội đồng',
];
const PROPER_NOUN_RES = PROPER_NOUNS.map((n) => [new RegExp(n.toLocaleLowerCase('vi'), 'g'), n] as const);

/** "QUY ĐỊNH CHUNG" → "Quy định chung" — tiêu đề viết hoa toàn bộ khó đọc trong mục lục */
export function sentenceCase(text: string): string {
  if (text !== text.toUpperCase()) return text;
  let out = text.toLocaleLowerCase('vi');
  for (const [re, proper] of PROPER_NOUN_RES) out = out.replace(re, proper);
  return out.charAt(0).toLocaleUpperCase('vi') + out.slice(1);
}
