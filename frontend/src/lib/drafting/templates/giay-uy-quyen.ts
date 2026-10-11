import type { DraftTemplate } from '../types';
import { join, personParty, signedAt } from './parts';

// Giấy ủy quyền — không có mẫu bắt buộc; bố cục theo mẫu thông dụng, căn cứ Điều 562–569 BLDS 2015.

const opening = signedAt('chung');
const parties = join(
  personParty({ id: 'a', heading: 'I. BÊN ỦY QUYỀN (sau đây gọi là Bên A)', group: 'ben-a', role: 'Bên A', withPhone: true }),
  personParty({ id: 'b', heading: 'II. BÊN NHẬN ỦY QUYỀN (sau đây gọi là Bên B)', group: 'ben-b', role: 'Bên B', withPhone: true }),
);

export const giayUyQuyen: DraftTemplate = {
  id: 'giay-uy-quyen',
  version: 1,
  title: 'Giấy ủy quyền',
  category: 'Giao dịch dân sự',
  description: 'Ủy quyền cho người khác thay mình làm thủ tục, nhận giấy tờ, tham gia tố tụng…',
  source: { kind: 'reference', basis: 'Điều 562–569 Bộ luật Dân sự 2015' },
  groups: [
    { id: 'chung', label: 'Thời gian & địa điểm' },
    { id: 'ben-a', label: 'Bên ủy quyền' },
    { id: 'ben-b', label: 'Bên nhận ủy quyền' },
    { id: 'noi-dung', label: 'Nội dung ủy quyền' },
  ],
  fields: [
    ...opening.fields,
    ...parties.fields,
    {
      id: 'pham_vi',
      label: 'Phạm vi ủy quyền',
      kind: 'textarea',
      group: 'noi-dung',
      required: true,
      blank: 4,
      placeholder: 'Bên B được thay mặt Bên A …',
      hint: 'Ghi cụ thể từng công việc Bên B được làm thay (nộp, nhận hồ sơ; ký giấy tờ; tham gia tố tụng…). Ủy quyền mua bán, tặng cho bất động sản hoặc ủy quyền kháng cáo phải được công chứng, chứng thực (khoản 6 Điều 272 BLTTDS).',
    },
    {
      id: 'thoi_han',
      label: 'Thời hạn ủy quyền',
      kind: 'text',
      group: 'noi-dung',
      required: true,
      blank: 30,
      placeholder: 'kể từ ngày ký đến khi hoàn thành công việc',
      hint: 'Do các bên thỏa thuận; nếu không thỏa thuận và pháp luật không quy định thì ủy quyền có hiệu lực 01 năm kể từ ngày xác lập (Điều 563 BLDS).',
    },
    {
      id: 'thu_lao',
      label: 'Thù lao',
      kind: 'text',
      group: 'noi-dung',
      blank: 25,
      placeholder: 'Không có',
      hint: 'Bên ủy quyền chỉ phải trả thù lao nếu có thỏa thuận hoặc pháp luật quy định (Điều 562 BLDS). Không có thì ghi "Không có".',
    },
    { id: 'so_ban', label: 'Số bản', kind: 'text', group: 'noi-dung', required: true, blank: 4, placeholder: '02' },
  ],
  blocks: [
    { type: 'motto' },
    { type: 'title', text: 'GIẤY ỦY QUYỀN' },
    { type: 'para', indent: true, italic: true, runs: ['- Căn cứ Bộ luật Dân sự số 91/2015/QH13 ngày 24 tháng 11 năm 2015;'] },
    { type: 'para', indent: true, italic: true, runs: ['- Căn cứ nhu cầu của các bên.'] },
    ...opening.blocks,
    ...parties.blocks,
    { type: 'para', bold: true, gap: true, runs: ['III. NỘI DUNG ỦY QUYỀN'] },
    { type: 'para', indent: true, runs: ['1. Phạm vi ủy quyền: Bên A ủy quyền cho Bên B thực hiện các công việc sau:'] },
    { type: 'field', field: 'pham_vi', indent: true },
    { type: 'para', indent: true, runs: ['2. Thời hạn ủy quyền: ', { field: 'thoi_han' }, '.'] },
    { type: 'para', indent: true, runs: ['3. Thù lao: ', { field: 'thu_lao' }, '.'] },
    { type: 'para', bold: true, gap: true, runs: ['IV. CAM KẾT CỦA CÁC BÊN'] },
    {
      type: 'para',
      indent: true,
      align: 'justify',
      runs: ['1. Bên B thực hiện công việc trong phạm vi ủy quyền, báo cho Bên A về việc thực hiện công việc đó và giao lại cho Bên A tài sản, lợi ích đã nhận (Điều 565 Bộ luật Dân sự).'],
    },
    {
      type: 'para',
      indent: true,
      align: 'justify',
      runs: ['2. Bên A cung cấp thông tin, tài liệu và phương tiện cần thiết để Bên B thực hiện công việc, và chịu trách nhiệm về cam kết do Bên B thực hiện trong phạm vi ủy quyền (Điều 566 Bộ luật Dân sự).'],
    },
    {
      type: 'para',
      indent: true,
      align: 'justify',
      runs: ['3. Hai bên cam kết chịu trách nhiệm trước pháp luật về tính chính xác của các thông tin nêu trên.'],
    },
    {
      type: 'para',
      indent: true,
      gap: true,
      runs: ['Giấy ủy quyền này có hiệu lực kể từ ngày ký, được lập thành ', { field: 'so_ban' }, ' bản có giá trị pháp lý như nhau, mỗi bên giữ một bản.'],
    },
    {
      type: 'signatures',
      parties: [
        { title: 'BÊN ỦY QUYỀN', caption: '(Ký, ghi rõ họ tên)', nameField: 'a_ho_ten' },
        { title: 'BÊN NHẬN ỦY QUYỀN', caption: '(Ký, ghi rõ họ tên)', nameField: 'b_ho_ten' },
      ],
    },
  ],
  aiSuggestions: [
    'Tôi muốn ủy quyền cho em trai đi nộp và nhận hồ sơ cấp đổi sổ đỏ tại văn phòng đăng ký đất đai. Viết giúp phạm vi ủy quyền.',
    'Còn thiếu mục bắt buộc nào chưa điền?',
  ],
  draftTitle: (v) => {
    const a = typeof v.a_ho_ten === 'string' ? v.a_ho_ten.trim() : '';
    const b = typeof v.b_ho_ten === 'string' ? v.b_ho_ten.trim() : '';
    if (a && b) return `Giấy ủy quyền — ${a} cho ${b}`;
    return a ? `Giấy ủy quyền — ${a}` : undefined;
  },
};
