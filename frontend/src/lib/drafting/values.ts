import type { DraftTemplate, FieldDef, FieldValue, FieldValues } from './types';

// ── Đọc / so sánh giá trị ô ──────────────────────────────────────

export const emptyValue = (field: FieldDef): FieldValue => (field.kind === 'list' ? [] : '');

export function isFilled(value: FieldValue | undefined): boolean {
  if (value == null) return false;
  if (Array.isArray(value)) return value.some((v) => v.trim() !== '');
  return value.trim() !== '';
}

export function sameValue(a: FieldValue | undefined, b: FieldValue | undefined): boolean {
  const na = a ?? '';
  const nb = b ?? '';
  if (Array.isArray(na) || Array.isArray(nb)) {
    const la = Array.isArray(na) ? na : na ? [na] : [];
    const lb = Array.isArray(nb) ? nb : nb ? [nb] : [];
    return la.length === lb.length && la.every((v, i) => v === lb[i]);
  }
  return na === nb;
}

export const asText = (value: FieldValue | undefined): string =>
  Array.isArray(value) ? value.join('\n') : (value ?? '');

export const asList = (value: FieldValue | undefined): string[] =>
  Array.isArray(value) ? value : value ? value.split('\n') : [];

/** Tỉ lệ ô bắt buộc đã điền, 0–100 */
export function progressOf(template: DraftTemplate, values: FieldValues): number {
  const required = template.fields.filter((f) => f.required);
  if (!required.length) return 100;
  const done = required.filter((f) => isFilled(values[f.id])).length;
  return Math.round((done / required.length) * 100);
}

// ── Ngày tháng ───────────────────────────────────────────────────

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

export function parseIsoDate(value: string): { d: string; m: string; y: string } | null {
  const m = ISO_DATE.exec(value.trim());
  if (!m) return null;
  return { y: m[1], m: m[2], d: m[3] };
}

export function todayIso(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** "ngày 09 tháng 10 năm 2026" — văn bản hành chính ghi ngày/tháng dưới 10 có số 0 phía trước (NĐ 30/2020) */
export function dateWords(value: string): string | null {
  const p = parseIsoDate(value);
  return p ? `ngày ${p.d} tháng ${p.m} năm ${p.y}` : null;
}

// ── Tiền ─────────────────────────────────────────────────────────

export const moneyDigits = (value: string): string => value.replace(/\D/g, '').replace(/^0+(?=\d)/, '');

/** "50000000" → "50.000.000" */
export function formatMoney(value: string): string {
  const digits = moneyDigits(value);
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

const DIGIT_WORDS = ['không', 'một', 'hai', 'ba', 'bốn', 'năm', 'sáu', 'bảy', 'tám', 'chín'];
const GROUP_UNITS = ['', 'nghìn', 'triệu', 'tỷ', 'nghìn tỷ', 'triệu tỷ'];

/** Đọc một nhóm 3 chữ số; `full` = có nhóm đứng trước nên phải đọc cả "không trăm", "linh" */
function readTriple(n: number, full: boolean): string[] {
  const h = Math.floor(n / 100);
  const t = Math.floor((n % 100) / 10);
  const u = n % 10;
  const out: string[] = [];
  if (full || h > 0) out.push(DIGIT_WORDS[h], 'trăm');
  if (t > 1) {
    out.push(DIGIT_WORDS[t], 'mươi');
    if (u === 1) out.push('mốt');
    else if (u === 5) out.push('lăm');
    else if (u > 0) out.push(DIGIT_WORDS[u]);
  } else if (t === 1) {
    out.push('mười');
    if (u === 5) out.push('lăm');
    else if (u > 0) out.push(DIGIT_WORDS[u]);
  } else if (u > 0) {
    if (full || h > 0) out.push('linh');
    out.push(DIGIT_WORDS[u]);
  }
  return out;
}

/** "1005000" → "Một triệu không trăm linh năm nghìn đồng"; trả null nếu không phải số hợp lệ */
export function moneyWords(value: string): string | null {
  const digits = moneyDigits(value);
  if (!digits || digits.length > 18) return null;
  if (/^0+$/.test(digits)) return 'Không đồng';

  const groups: number[] = [];
  for (let end = digits.length; end > 0; end -= 3) {
    groups.unshift(Number(digits.slice(Math.max(0, end - 3), end)));
  }

  const words: string[] = [];
  groups.forEach((g, i) => {
    if (g === 0) return;
    const unit = GROUP_UNITS[groups.length - 1 - i];
    words.push(...readTriple(g, words.length > 0));
    if (unit) words.push(unit);
  });

  const text = words.join(' ');
  return `${text.charAt(0).toUpperCase()}${text.slice(1)} đồng`;
}

// ── Chuẩn hoá giá trị khi nạp bản nháp ───────────────────────────

/** Giữ đúng kiểu cho từng ô (bản nháp cũ / dữ liệu lạ không làm vỡ trình soạn thảo) */
export function normalizeValues(template: DraftTemplate, raw: unknown): FieldValues {
  const src = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const out: FieldValues = {};
  for (const f of template.fields) {
    const v = src[f.id];
    if (f.kind === 'list') {
      out[f.id] = Array.isArray(v) ? v.map(String) : typeof v === 'string' && v ? v.split('\n') : [];
    } else {
      out[f.id] = Array.isArray(v) ? v.join('\n') : typeof v === 'string' ? v : '';
    }
  }
  return out;
}
