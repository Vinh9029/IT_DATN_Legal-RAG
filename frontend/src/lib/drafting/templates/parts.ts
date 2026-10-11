import type { Block, FieldDef } from '../types';

// Các khối lặp lại giữa nhiều biểu mẫu. Mỗi hàm trả về CẢ ô cần điền lẫn bố cục,
// nên một mẫu mới chỉ cần ghép các mảnh lại.

export interface Piece {
  fields: FieldDef[];
  blocks: Block[];
}

export const join = (...pieces: Piece[]): Piece => ({
  fields: pieces.flatMap((p) => p.fields),
  blocks: pieces.flatMap((p) => p.blocks),
});

/** Gợi ý nơi cư trú dùng chung — địa giới hành chính 2 cấp từ 01/7/2025 (bỏ cấp huyện) */
export const ADDRESS_EXAMPLE = 'số nhà, đường, phường/xã, tỉnh/thành phố';

/** Dòng "……(1), ngày … tháng … năm …" ở đầu đơn */
export function placeDate(group: string, note?: number): Piece {
  return {
    fields: [
      {
        id: 'noi_lam_don',
        label: 'Nơi làm đơn',
        kind: 'text',
        group,
        required: true,
        placeholder: 'Hà Nội',
        blank: 8,
        hint: 'Ghi địa điểm làm đơn, thường là tên tỉnh/thành phố (ví dụ: Hà Nội, TP. Hồ Chí Minh).',
      },
      {
        id: 'ngay_lam_don',
        label: 'Ngày làm đơn',
        kind: 'date',
        group,
        required: true,
        hint: 'Ngày, tháng, năm làm đơn.',
      },
    ],
    blocks: [{ type: 'para', align: 'right', italic: true, runs: [{ field: 'noi_lam_don', note }, ', ', { field: 'ngay_lam_don' }] }],
  };
}

interface CourtPartyOptions {
  /** Tiền tố id các ô, vd. "nkk" → nkk, nkk_dia_chi, nkk_dien_thoai… */
  id: string;
  label: string;
  group: string;
  nameNote?: number;
  addressNote?: number;
  nameHint: string;
  addressHint: string;
  required?: boolean;
  /** Mục "(nếu có)": bỏ cả khối khỏi bản in khi chưa điền tên */
  optional?: boolean;
  /** Dấu chấm câu cuối dòng thư điện tử (mẫu chính thức có chỗ kết thúc bằng ".") */
  endWithPeriod?: boolean;
}

/**
 * Một đương sự trong đơn gửi Tòa án theo các mẫu của NQ 01/2017/NQ-HĐTP:
 *   <Nhãn>: (n)……
 *   Địa chỉ: (n) ……
 *   Số điện thoại: ……(nếu có); số fax: ……(nếu có)
 *   Địa chỉ thư điện tử: ……(nếu có)
 */
export function courtParty(o: CourtPartyOptions): Piece {
  const ids = {
    name: o.id,
    address: `${o.id}_dia_chi`,
    phone: `${o.id}_dien_thoai`,
    fax: `${o.id}_fax`,
    email: `${o.id}_email`,
  };
  const omit = o.optional ? [ids.name, ids.address, ids.phone, ids.fax, ids.email] : undefined;
  const ifAny = (field: string) => ({ text: ' (nếu có)', whenEmpty: field });

  return {
    fields: [
      { id: ids.name, label: o.label, kind: 'text', group: o.group, required: o.required, hint: o.nameHint, blank: 40 },
      { id: ids.address, label: `Địa chỉ ${o.label.toLowerCase()}`, kind: 'text', group: o.group, required: o.required, hint: o.addressHint, placeholder: ADDRESS_EXAMPLE, blank: 45 },
      { id: ids.phone, label: 'Số điện thoại', kind: 'text', group: o.group, blank: 12 },
      { id: ids.fax, label: 'Số fax', kind: 'text', group: o.group, blank: 12 },
      { id: ids.email, label: 'Địa chỉ thư điện tử', kind: 'text', group: o.group, blank: 28 },
    ],
    blocks: [
      {
        type: 'para',
        indent: true,
        omitIfEmpty: omit,
        runs: [o.label, ...(o.optional ? [ifAny(ids.name)] : []), ': ', { field: ids.name, note: o.nameNote }],
      },
      { type: 'para', indent: true, omitIfEmpty: omit, runs: ['Địa chỉ: ', { field: ids.address, note: o.addressNote }] },
      {
        type: 'para',
        indent: true,
        omitIfEmpty: omit,
        runs: ['Số điện thoại: ', { field: ids.phone }, { text: '(nếu có)', whenEmpty: ids.phone }, '; số fax: ', { field: ids.fax }, { text: '(nếu có)', whenEmpty: ids.fax }],
      },
      {
        type: 'para',
        indent: true,
        omitIfEmpty: omit,
        runs: ['Địa chỉ thư điện tử: ', { field: ids.email }, { text: '(nếu có)', whenEmpty: ids.email }, ...(o.endWithPeriod ? ['.'] : [])],
      },
    ],
  };
}

interface PersonPartyOptions {
  id: string;
  /** "BÊN ĐẶT CỌC (sau đây gọi là Bên A)" */
  heading: string;
  group: string;
  /** Tên vai trò ngắn trong nhãn ô, vd. "Bên A" */
  role: string;
  withPhone?: boolean;
}

/** Thông tin nhân thân một bên của hợp đồng / giấy ủy quyền (cá nhân) */
export function personParty(o: PersonPartyOptions): Piece {
  const f = (suffix: string) => `${o.id}_${suffix}`;
  return {
    fields: [
      { id: f('ho_ten'), label: `Họ và tên ${o.role}`, kind: 'text', group: o.group, required: true, blank: 30, placeholder: 'NGUYỄN VĂN A' },
      { id: f('ngay_sinh'), label: 'Ngày sinh', kind: 'text', group: o.group, required: true, blank: 12, placeholder: '01/01/1990' },
      {
        id: f('cccd'),
        label: 'Số CCCD/Căn cước',
        kind: 'text',
        group: o.group,
        required: true,
        blank: 16,
        hint: 'Số định danh cá nhân trên thẻ Căn cước/Căn cước công dân (12 số). Người nước ngoài ghi số hộ chiếu.',
      },
      { id: f('ngay_cap'), label: 'Ngày cấp', kind: 'text', group: o.group, required: true, blank: 12, placeholder: '01/01/2021' },
      { id: f('noi_cap'), label: 'Nơi cấp', kind: 'text', group: o.group, required: true, blank: 30, placeholder: 'Bộ Công an' },
      { id: f('cu_tru'), label: 'Nơi cư trú', kind: 'text', group: o.group, required: true, blank: 50, placeholder: ADDRESS_EXAMPLE },
      ...(o.withPhone ? [{ id: f('dien_thoai'), label: 'Số điện thoại', kind: 'text' as const, group: o.group, blank: 14 }] : []),
    ],
    blocks: [
      { type: 'para', bold: true, gap: true, runs: [o.heading, ':'] },
      { type: 'para', indent: true, runs: ['Họ và tên: ', { field: f('ho_ten'), bold: true }, '; Ngày sinh: ', { field: f('ngay_sinh') }] },
      {
        type: 'para',
        indent: true,
        runs: ['Số CCCD/Căn cước: ', { field: f('cccd') }, ' cấp ngày ', { field: f('ngay_cap') }, ' tại ', { field: f('noi_cap') }],
      },
      { type: 'para', indent: true, runs: ['Nơi cư trú: ', { field: f('cu_tru') }] },
      ...(o.withPhone ? [{ type: 'para' as const, indent: true, runs: ['Số điện thoại: ', { field: f('dien_thoai') }] }] : []),
    ],
  };
}

/** Dòng "Hôm nay, ngày … tại …, chúng tôi gồm:" mở đầu hợp đồng */
export function signedAt(group: string): Piece {
  return {
    fields: [
      { id: 'ngay_lap', label: 'Ngày lập', kind: 'date', group, required: true },
      { id: 'noi_lap', label: 'Địa điểm lập', kind: 'text', group, required: true, blank: 30, placeholder: ADDRESS_EXAMPLE },
    ],
    blocks: [
      { type: 'para', indent: true, gap: true, runs: ['Hôm nay, ', { field: 'ngay_lap' }, ', tại ', { field: 'noi_lap' }, ', chúng tôi gồm:'] },
    ],
  };
}
