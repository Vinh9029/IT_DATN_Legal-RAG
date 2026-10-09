import type { DraftTemplate } from '../types';
import { courtParty, join, placeDate } from './parts';

// Mẫu số 23-DS — Đơn khởi kiện, ban hành kèm theo Nghị quyết 01/2017/NQ-HĐTP.
// Chữ in sẵn giữ nguyên như mẫu; các số (1)…(16) là chú thích của phần "Hướng dẫn sử dụng mẫu",
// nội dung từng chú thích nằm ở `hint` của ô tương ứng. Nội dung bắt buộc: Điều 189 BLTTDS 2015.

const SAME_AS_3 =
  'Cá nhân: ghi họ tên (người chưa thành niên, mất hoặc hạn chế năng lực hành vi dân sự thì ghi họ tên, địa chỉ của người đại diện hợp pháp). Cơ quan, tổ chức: ghi tên cơ quan, tổ chức và họ tên, chức vụ người đại diện hợp pháp.';
const SAME_AS_4 =
  'Cá nhân: ghi đầy đủ nơi cư trú tại thời điểm nộp đơn (ví dụ: trú tại số 12 đường B, phường C, thành phố H). Cơ quan, tổ chức: ghi địa chỉ trụ sở chính.';

const head = placeDate('chung', 1);

const parties = join(
  courtParty({
    id: 'nkk',
    label: 'Người khởi kiện',
    group: 'nguoi-khoi-kien',
    nameNote: 3,
    addressNote: 4,
    required: true,
    nameHint: SAME_AS_3,
    addressHint: SAME_AS_4,
  }),
  courtParty({
    id: 'nbk',
    label: 'Người bị kiện',
    group: 'nguoi-bi-kien',
    nameNote: 5,
    addressNote: 6,
    required: true,
    nameHint: SAME_AS_3,
    addressHint: `${SAME_AS_4} Không rõ nơi cư trú hiện tại thì ghi địa chỉ cuối cùng (Điều 189 BLTTDS).`,
  }),
  courtParty({
    id: 'nbv',
    label: 'Người có quyền, lợi ích được bảo vệ',
    group: 'nguoi-khac',
    nameNote: 7,
    addressNote: 8,
    optional: true,
    nameHint: `Chỉ ghi khi người khởi kiện khởi kiện để bảo vệ quyền, lợi ích của người khác. ${SAME_AS_3}`,
    addressHint: SAME_AS_4,
  }),
  courtParty({
    id: 'nlq',
    label: 'Người có quyền lợi, nghĩa vụ liên quan',
    group: 'nguoi-khac',
    nameNote: 9,
    addressNote: 10,
    optional: true,
    nameHint: `Người không khởi kiện, không bị kiện nhưng việc giải quyết vụ án có liên quan đến quyền lợi, nghĩa vụ của họ. ${SAME_AS_3}`,
    addressHint: SAME_AS_4,
  }),
);

const witness = courtParty({
  id: 'nlc',
  label: 'Người làm chứng',
  group: 'chung-cu',
  nameNote: 12,
  addressNote: 13,
  optional: true,
  endWithPeriod: true,
  nameHint: 'Họ tên người biết tình tiết liên quan đến vụ việc (nếu có).',
  addressHint: SAME_AS_4,
});

export const donKhoiKien: DraftTemplate = {
  id: 'don-khoi-kien',
  version: 1,
  title: 'Đơn khởi kiện',
  category: 'Tố tụng dân sự',
  description: 'Yêu cầu Tòa án giải quyết tranh chấp dân sự: hợp đồng, đòi tài sản, bồi thường thiệt hại…',
  source: { kind: 'official', code: 'Mẫu số 23-DS', issuedBy: 'Nghị quyết số 01/2017/NQ-HĐTP' },
  groups: [
    { id: 'chung', label: 'Nơi nhận & ngày làm đơn' },
    { id: 'nguoi-khoi-kien', label: 'Người khởi kiện' },
    { id: 'nguoi-bi-kien', label: 'Người bị kiện' },
    { id: 'nguoi-khac', label: 'Người liên quan (nếu có)' },
    { id: 'yeu-cau', label: 'Yêu cầu Tòa án giải quyết' },
    { id: 'chung-cu', label: 'Chứng cứ & người làm chứng' },
    { id: 'ky-ten', label: 'Ký tên' },
  ],
  fields: [
    ...head.fields,
    {
      id: 'toa_an',
      label: 'Tòa án nhận đơn',
      kind: 'text',
      group: 'chung',
      required: true,
      blank: 40,
      placeholder: 'khu vực 1 - Hà Nội',
      hint: 'Ghi tên Tòa án có thẩm quyền giải quyết và địa chỉ của Tòa án đó. Từ 01/7/2025 cấp sơ thẩm gồm Tòa án nhân dân khu vực và Tòa án nhân dân tỉnh, thành phố (ví dụ: Tòa án nhân dân khu vực 1 - Hà Nội).',
    },
    ...parties.fields,
    {
      id: 'yeu_cau',
      label: 'Yêu cầu Tòa án giải quyết',
      kind: 'list',
      group: 'yeu-cau',
      required: true,
      blank: 2,
      placeholder: 'Buộc ông/bà … trả lại số tiền …',
      hint: 'Nêu cụ thể từng vấn đề yêu cầu Tòa án giải quyết đối với người bị kiện, người có quyền lợi, nghĩa vụ liên quan — mỗi yêu cầu một dòng.',
    },
    ...witness.fields,
    {
      id: 'tai_lieu',
      label: 'Tài liệu, chứng cứ kèm theo',
      kind: 'list',
      group: 'chung-cu',
      required: true,
      blank: 2,
      placeholder: 'Bản sao hợp đồng …',
      hint: 'Ghi rõ tên từng tài liệu kèm theo đơn và đánh số thứ tự (ví dụ: Bản sao hợp đồng mua bán nhà; Bản sao Giấy chứng nhận quyền sở hữu nhà…).',
    },
    {
      id: 'thong_tin_khac',
      label: 'Thông tin khác',
      kind: 'textarea',
      group: 'chung-cu',
      blank: 2,
      hint: 'Những thông tin người khởi kiện thấy cần thiết cho việc giải quyết vụ án (ví dụ: một đương sự đang ở nước ngoài…). Không có thì để trống.',
    },
    {
      id: 'nguoi_ky',
      label: 'Họ tên người ký',
      kind: 'text',
      group: 'ky-ten',
      required: true,
      blank: 20,
      hint: 'Cá nhân ký tên hoặc điểm chỉ. Cơ quan, tổ chức: người đại diện hợp pháp ký, ghi rõ họ tên, chức vụ và đóng dấu.',
    },
  ],
  blocks: [
    { type: 'form-code', lines: ['Mẫu số 23-DS (Ban hành kèm theo Nghị quyết số 01/2017/NQ-HĐTP', 'ngày 13 tháng 01 năm 2017 của Hội đồng Thẩm phán Tòa án nhân dân tối cao)'] },
    { type: 'motto' },
    ...head.blocks,
    { type: 'title', text: 'ĐƠN KHỞI KIỆN' },
    { type: 'para', align: 'center', runs: [{ text: 'Kính gửi: ', bold: true }, 'Tòa án nhân dân ', { field: 'toa_an', note: 2 }] },
    ...parties.blocks,
    { type: 'para', indent: true, gap: true, runs: ['Yêu cầu Tòa án giải quyết những vấn đề sau đây: ', { note: 11 }] },
    { type: 'field', field: 'yeu_cau', indent: true },
    ...witness.blocks,
    { type: 'para', indent: true, gap: true, runs: ['Danh mục tài liệu, chứng cứ kèm theo đơn khởi kiện gồm có: ', { note: 14 }] },
    { type: 'field', field: 'tai_lieu', indent: true },
    {
      type: 'para',
      indent: true,
      italic: true,
      gap: true,
      omitIfEmpty: ['thong_tin_khac'],
      runs: ['(Các thông tin khác mà người khởi kiện xét thấy cần thiết cho việc giải quyết vụ án) ', { note: 15 }],
    },
    { type: 'field', field: 'thong_tin_khac', indent: true, omitIfEmpty: true },
    { type: 'signatures', parties: [{ title: 'Người khởi kiện', note: 16, nameField: 'nguoi_ky' }] },
  ],
  aiSuggestions: [
    'Tôi cho anh Trần Văn Bình vay 200 triệu đồng từ tháng 3/2024, hẹn 6 tháng trả nhưng đến nay anh ấy không trả. Điền giúp tôi phần yêu cầu Tòa án giải quyết.',
    'Còn thiếu mục bắt buộc nào chưa điền?',
  ],
  draftTitle: (v) => (typeof v.nkk === 'string' && v.nkk.trim() ? `Đơn khởi kiện — ${v.nkk.trim()}` : undefined),
};
