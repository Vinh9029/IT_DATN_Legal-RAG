import type { Align, Block, DraftTemplate, FieldDef, FieldValues, Run } from './types';
import { asList, asText, dateWords, formatMoney, isFilled, moneyWords } from './values';

// ── Văn bản đã ghép giá trị ─────────────────────────────────────
// Bản in (PDF) và file Word đều dựng từ DocBlock[] — một lớp trung gian đã bỏ hết khái niệm "ô",
// chỉ còn chữ + định dạng. Ô trống được thay bằng dấu chấm để in ra viết tay tiếp.

export interface DocRun {
  text: string;
  bold?: boolean;
  italic?: boolean;
}

export type DocBlock =
  | { kind: 'form-code'; lines: string[] }
  | { kind: 'motto' }
  | { kind: 'title'; text: string; sub?: DocRun[] }
  /** indent = thụt dòng đầu; inset = thụt cả đoạn (nội dung của ô khối) */
  | { kind: 'para'; runs: DocRun[]; align: Align; indent: boolean; gap: boolean; inset?: boolean }
  /** Các dòng chấm để viết tay (ô khối còn trống) */
  | { kind: 'blank-lines'; count: number; indent: boolean }
  | { kind: 'signatures'; parties: { title: string; caption?: string; name?: string }[] };

export const DOTS = '…';
export const dots = (n: number) => DOTS.repeat(Math.max(1, n));

/** Chữ hiển thị của một ô một dòng (dùng chung cho bản in và trình soạn thảo) */
export function inlineText(field: FieldDef, values: FieldValues): string | null {
  const raw = asText(values[field.id]).trim();
  if (!raw) return null;
  if (field.kind === 'date') return dateWords(raw) ?? raw;
  if (field.kind === 'money') return formatMoney(raw) || null;
  return raw.replace(/\s*\n\s*/g, ' ');
}

/** Ngày còn trống: in khung "ngày …… tháng …… năm ……" như mẫu giấy */
export const BLANK_DATE = `ngày ${dots(2)} tháng ${dots(2)} năm ${dots(3)}`;

/**
 * Chỗ trống của ô một dòng. `blank` tính theo số ký tự chữ thường; dấu "…" của Times New Roman
 * rộng cỡ 2,2 ký tự nên quy đổi lại để dòng in không tràn.
 */
export function blankFor(field: FieldDef): string {
  if (field.kind === 'date') return BLANK_DATE;
  return dots(Math.max(3, Math.round((field.blank ?? 15) * 0.45)));
}

export function derivedText(run: Extract<Run, { derived: string }>, values: FieldValues): string | null {
  if (run.derived === 'money-words') return moneyWords(asText(values[run.from]));
  return null;
}

/** Dòng có bị bỏ khỏi bản in không (mục "nếu có" còn trống) */
export function isOmitted(block: Block, values: FieldValues): boolean {
  if (block.type === 'para' && block.omitIfEmpty) return block.omitIfEmpty.every((id) => !isFilled(values[id]));
  if (block.type === 'field' && block.omitIfEmpty) return !isFilled(values[block.field]);
  return false;
}

/** Chữ điều kiện (whenEmpty/whenFilled) có hiện không */
export function conditionHolds(run: Extract<Run, { text: string }>, values: FieldValues): boolean {
  if (run.whenEmpty && isFilled(values[run.whenEmpty])) return false;
  if (run.whenFilled && !isFilled(values[run.whenFilled])) return false;
  return true;
}

export function resolveDocument(template: DraftTemplate, values: FieldValues): DocBlock[] {
  const fields = new Map(template.fields.map((f) => [f.id, f]));

  const runsOf = (runs: Run[], base: { bold?: boolean; italic?: boolean } = {}): DocRun[] => {
    const out: DocRun[] = [];
    for (const run of runs) {
      if (typeof run === 'string') out.push({ text: run, ...base });
      else if ('note' in run && !('field' in run)) continue;
      else if ('derived' in run) out.push({ text: derivedText(run, values) ?? dots(16), ...base });
      else if ('field' in run) {
        const field = fields.get(run.field);
        if (!field) continue;
        const text = inlineText(field, values);
        out.push(text ? { text, ...base, bold: base.bold || run.bold } : { text: blankFor(field), ...base });
      } else if (conditionHolds(run, values)) {
        out.push({ text: run.text, bold: base.bold || run.bold, italic: base.italic || run.italic });
      }
    }
    return out;
  };

  const blocks: DocBlock[] = [];
  for (const block of template.blocks) {
    if (isOmitted(block, values)) continue;
    switch (block.type) {
      case 'motto':
        blocks.push({ kind: 'motto' });
        break;
      case 'form-code':
        blocks.push({ kind: 'form-code', lines: block.lines });
        break;
      case 'title':
        blocks.push({ kind: 'title', text: block.text, sub: block.sub && runsOf(block.sub) });
        break;
      case 'para':
        blocks.push({
          kind: 'para',
          runs: runsOf(block.runs, { bold: block.bold, italic: block.italic }),
          align: block.align ?? 'left',
          indent: !!block.indent,
          gap: !!block.gap,
        });
        break;
      case 'field': {
        const field = fields.get(block.field);
        if (!field) break;
        const inset = !!block.indent;
        if (field.kind === 'list') {
          const items = asList(values[field.id]).map((s) => s.trim()).filter(Boolean);
          if (items.length) {
            items.forEach((item, i) => blocks.push({ kind: 'para', runs: [{ text: `${i + 1}. ${item}` }], align: 'justify', indent: false, inset, gap: false }));
          } else {
            // Mẫu giấy để sẵn "1. ……" "2. ……"
            for (let i = 0; i < (field.blank ?? 2); i++) {
              blocks.push({ kind: 'para', runs: [{ text: `${i + 1}. ` }, { text: dots(30) }], align: 'left', indent: false, inset, gap: false });
            }
          }
        } else {
          const lines = asText(values[field.id]).split('\n').map((s) => s.trim()).filter(Boolean);
          if (lines.length) lines.forEach((line) => blocks.push({ kind: 'para', runs: [{ text: line }], align: 'justify', indent: false, inset, gap: false }));
          else blocks.push({ kind: 'blank-lines', count: field.blank ?? 2, indent: inset });
        }
        break;
      }
      case 'signatures':
        blocks.push({
          kind: 'signatures',
          parties: block.parties.map((p) => ({
            title: p.title,
            caption: p.caption,
            name: p.nameField ? asText(values[p.nameField]).trim() || undefined : undefined,
          })),
        });
        break;
    }
  }
  return blocks;
}

/** Tên file xuất: bỏ dấu, ký tự lạ — tránh lỗi tên file trên Windows */
export function exportFileName(title: string, ext: string): string {
  const base = title
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .replace(/[^\w\s-]/g, ' ')
    .trim()
    .replace(/\s+/g, '_')
    .slice(0, 80);
  return `${base || 'van_ban'}.${ext}`;
}
