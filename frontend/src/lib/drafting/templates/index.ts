import type { DraftTemplate } from '../types';
import { donKhoiKien } from './don-khoi-kien';
import { donKhangCao } from './don-khang-cao';
import { giayUyQuyen } from './giay-uy-quyen';
import { hopDongDatCoc } from './hop-dong-dat-coc';

// Thêm biểu mẫu = viết một file cạnh đây (ghép từ parts.ts) rồi thêm vào danh sách.
// Thứ tự trong danh sách = thứ tự hiển thị trên trang chọn mẫu.
export const TEMPLATES: DraftTemplate[] = [donKhoiKien, donKhangCao, giayUyQuyen, hopDongDatCoc];

const byId = new Map(TEMPLATES.map((t) => [t.id, t]));

export const getTemplate = (id: string): DraftTemplate | undefined => byId.get(id);

// Lỗi khai báo (trùng id ô, block trỏ tới ô không tồn tại) lộ ra ngay lúc dev thay vì im lặng in sai
if (import.meta.env.DEV) {
  for (const t of TEMPLATES) {
    const ids = new Set<string>();
    for (const f of t.fields) {
      if (ids.has(f.id)) console.error(`[drafting] ${t.id}: trùng id ô "${f.id}"`);
      ids.add(f.id);
      if (!t.groups.some((g) => g.id === f.group)) console.error(`[drafting] ${t.id}: ô "${f.id}" thuộc nhóm lạ "${f.group}"`);
    }
    const check = (id: string) => ids.has(id) || console.error(`[drafting] ${t.id}: block trỏ tới ô không tồn tại "${id}"`);
    for (const b of t.blocks) {
      if (b.type === 'field') check(b.field);
      if (b.type === 'para') b.runs.forEach((r) => typeof r === 'object' && 'field' in r && check(r.field));
      if (b.type === 'signatures') b.parties.forEach((p) => p.nameField && check(p.nameField));
    }
  }
}
