import type { DraftTemplate } from '../types';
import { courtParty, placeDate } from './parts';

// Mẫu số 54-DS — Đơn kháng cáo, ban hành kèm theo Nghị quyết 01/2017/NQ-HĐTP.
// Nội dung bắt buộc: Điều 272 BLTTDS 2015; thời hạn kháng cáo: Điều 273 (bản án 15 ngày, quyết định 07 ngày).

const head = placeDate('chung', 1);

const appellant = courtParty({
  id: 'nkc',
  label: 'Người kháng cáo',
  group: 'nguoi-khang-cao',
  nameNote: 3,
  addressNote: 4,
  required: true,
  nameHint:
    'Cá nhân tự kháng cáo: ghi họ tên. Kháng cáo qua người đại diện theo ủy quyền: ghi họ tên người đại diện và họ tên người được đại diện, kèm văn bản ủy quyền. Cơ quan, tổ chức: ghi tên và họ tên, chức vụ người đại diện theo pháp luật (Điều 272 BLTTDS).',
  addressHint: 'Ghi nơi cư trú (cá nhân) hoặc trụ sở (cơ quan, tổ chức) của người kháng cáo.',
});

export const donKhangCao: DraftTemplate = {
  id: 'don-khang-cao',
  version: 1,
  title: 'Đơn kháng cáo',
  category: 'Tố tụng dân sự',
  description: 'Không đồng ý với bản án, quyết định sơ thẩm và yêu cầu Tòa án cấp phúc thẩm xét xử lại.',
  source: { kind: 'official', code: 'Mẫu số 54-DS', issuedBy: 'Nghị quyết số 01/2017/NQ-HĐTP' },
  groups: [
    { id: 'chung', label: 'Nơi nhận & ngày làm đơn' },
    { id: 'nguoi-khang-cao', label: 'Người kháng cáo' },
    { id: 'noi-dung', label: 'Nội dung kháng cáo' },
    { id: 'ky-ten', label: 'Tài liệu & ký tên' },
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
      hint: 'Ghi tên Tòa án đã xét xử sơ thẩm — đơn kháng cáo nộp cho Tòa án cấp sơ thẩm đã ra bản án, quyết định bị kháng cáo (khoản 7 Điều 272 BLTTDS).',
    },
    ...appellant.fields,
    {
      id: 'tu_cach',
      label: 'Tư cách tố tụng',
      kind: 'text',
      group: 'noi-dung',
      required: true,
      blank: 45,
      placeholder: 'nguyên đơn trong vụ án tranh chấp hợp đồng vay tài sản',
      hint: 'Ghi tư cách tham gia tố tụng của người kháng cáo (ví dụ: là nguyên đơn (bị đơn) trong vụ án về tranh chấp hợp đồng mua bán nhà, hoặc người đại diện theo ủy quyền của nguyên đơn Nguyễn Văn A).',
    },
    {
      id: 'khang_cao',
      label: 'Phần bản án bị kháng cáo',
      kind: 'textarea',
      group: 'noi-dung',
      required: true,
      blank: 2,
      placeholder: 'Toàn bộ bản án dân sự sơ thẩm số …/20…/DS-ST ngày … của Tòa án nhân dân …',
      hint: 'Ghi cụ thể kháng cáo toàn bộ hay phần nào của bản án, quyết định sơ thẩm chưa có hiệu lực pháp luật (ví dụ: kháng cáo toàn bộ bản án sơ thẩm số 01/2017/DS-ST ngày 15-01-2017 của Tòa án nhân dân tỉnh H). Thời hạn: 15 ngày với bản án, 07 ngày với quyết định (Điều 273 BLTTDS).',
    },
    {
      id: 'ly_do',
      label: 'Lý do kháng cáo',
      kind: 'textarea',
      group: 'noi-dung',
      required: true,
      blank: 3,
      hint: 'Ghi lý do cụ thể của việc kháng cáo: phần nhận định, phán quyết nào chưa đúng và vì sao.',
    },
    {
      id: 'yeu_cau',
      label: 'Yêu cầu Tòa án cấp phúc thẩm',
      kind: 'textarea',
      group: 'noi-dung',
      required: true,
      blank: 2,
      hint: 'Nêu cụ thể từng vấn đề yêu cầu Tòa án cấp phúc thẩm giải quyết (ví dụ: sửa bản án sơ thẩm theo hướng…).',
    },
    {
      id: 'tai_lieu',
      label: 'Tài liệu, chứng cứ bổ sung',
      kind: 'list',
      group: 'ky-ten',
      blank: 2,
      hint: 'Nếu có tài liệu, chứng cứ bổ sung thì ghi đầy đủ tên từng tài liệu để chứng minh kháng cáo có căn cứ và hợp pháp. Không có thì để trống.',
    },
    {
      id: 'nguoi_ky',
      label: 'Họ tên người ký',
      kind: 'text',
      group: 'ky-ten',
      required: true,
      blank: 20,
      hint: 'Cá nhân ký tên hoặc điểm chỉ; người đại diện theo ủy quyền ký thay. Cơ quan, tổ chức: người đại diện theo pháp luật ký và đóng dấu.',
    },
  ],
  blocks: [
    { type: 'form-code', lines: ['Mẫu số 54-DS (Ban hành kèm theo Nghị quyết số 01/2017/NQ-HĐTP', 'ngày 13 tháng 01 năm 2017 của Hội đồng Thẩm phán Tòa án nhân dân tối cao)'] },
    { type: 'motto' },
    ...head.blocks,
    { type: 'title', text: 'ĐƠN KHÁNG CÁO' },
    { type: 'para', align: 'center', runs: [{ text: 'Kính gửi: ', bold: true }, 'Tòa án nhân dân ', { field: 'toa_an', note: 2 }] },
    ...appellant.blocks,
    { type: 'para', indent: true, runs: ['Là: ', { field: 'tu_cach', note: 5 }] },
    { type: 'para', indent: true, gap: true, runs: ['Kháng cáo: ', { note: 6 }] },
    { type: 'field', field: 'khang_cao', indent: true },
    { type: 'para', indent: true, gap: true, runs: ['Lý do của việc kháng cáo: ', { note: 7 }] },
    { type: 'field', field: 'ly_do', indent: true },
    { type: 'para', indent: true, gap: true, runs: ['Yêu cầu Tòa án cấp phúc thẩm giải quyết những việc sau đây: ', { note: 8 }] },
    { type: 'field', field: 'yeu_cau', indent: true },
    { type: 'para', indent: true, gap: true, runs: ['Những tài liệu, chứng cứ bổ sung kèm theo đơn kháng cáo gồm có: ', { note: 9 }] },
    { type: 'field', field: 'tai_lieu', indent: true },
    { type: 'signatures', parties: [{ title: 'Người kháng cáo', note: 10, nameField: 'nguoi_ky' }] },
  ],
  aiSuggestions: [
    'Tòa sơ thẩm buộc tôi bồi thường 80 triệu nhưng không xem xét biên bản thỏa thuận hai bên đã ký. Viết giúp phần lý do kháng cáo.',
    'Còn thiếu mục bắt buộc nào chưa điền?',
  ],
  draftTitle: (v) => (typeof v.nkc === 'string' && v.nkc.trim() ? `Đơn kháng cáo — ${v.nkc.trim()}` : undefined),
};
