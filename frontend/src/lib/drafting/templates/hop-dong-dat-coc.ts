import type { DraftTemplate } from '../types';
import { join, personParty, signedAt } from './parts';

// Hợp đồng đặt cọc — không có mẫu bắt buộc; điều khoản xử lý tiền cọc lấy nguyên khoản 2 Điều 328 BLDS 2015.

const opening = signedAt('chung');
const parties = join(
  personParty({ id: 'a', heading: 'BÊN ĐẶT CỌC (sau đây gọi là Bên A)', group: 'ben-a', role: 'Bên A', withPhone: true }),
  personParty({ id: 'b', heading: 'BÊN NHẬN ĐẶT CỌC (sau đây gọi là Bên B)', group: 'ben-b', role: 'Bên B', withPhone: true }),
);

export const hopDongDatCoc: DraftTemplate = {
  id: 'hop-dong-dat-coc',
  version: 1,
  title: 'Hợp đồng đặt cọc',
  category: 'Giao dịch dân sự',
  description: 'Đặt cọc một khoản tiền để bảo đảm sẽ ký kết hoặc thực hiện hợp đồng mua bán, thuê tài sản…',
  source: { kind: 'reference', basis: 'Điều 328 Bộ luật Dân sự 2015' },
  groups: [
    { id: 'chung', label: 'Thời gian & địa điểm' },
    { id: 'ben-a', label: 'Bên đặt cọc' },
    { id: 'ben-b', label: 'Bên nhận đặt cọc' },
    { id: 'tien-coc', label: 'Tiền đặt cọc' },
    { id: 'dieu-khoan', label: 'Điều khoản khác' },
  ],
  fields: [
    { id: 'so_hop_dong', label: 'Số hợp đồng', kind: 'text', group: 'chung', blank: 6, placeholder: '01' },
    ...opening.fields,
    ...parties.fields,
    {
      id: 'so_tien',
      label: 'Số tiền đặt cọc',
      kind: 'money',
      group: 'tien-coc',
      required: true,
      blank: 14,
      hint: 'Ghi bằng số; phần bằng chữ được tự điền theo số tiền.',
    },
    {
      id: 'muc_dich',
      label: 'Mục đích đặt cọc',
      kind: 'textarea',
      group: 'tien-coc',
      required: true,
      blank: 3,
      placeholder: 'Bảo đảm việc Bên A và Bên B ký hợp đồng mua bán …',
      hint: 'Mô tả hợp đồng được bảo đảm: loại hợp đồng, tài sản (địa chỉ nhà đất, số giấy chứng nhận, biển số xe…), giá dự kiến, thời điểm ký hợp đồng chính thức.',
    },
    { id: 'tu_ngay', label: 'Đặt cọc từ ngày', kind: 'date', group: 'tien-coc', required: true },
    { id: 'den_ngay', label: 'Đặt cọc đến ngày', kind: 'date', group: 'tien-coc', required: true },
    {
      id: 'phuong_thuc',
      label: 'Phương thức giao tiền',
      kind: 'text',
      group: 'tien-coc',
      required: true,
      blank: 30,
      placeholder: 'chuyển khoản vào tài khoản số … của Bên B',
    },
    {
      id: 'thoa_thuan_khac',
      label: 'Thỏa thuận khác',
      kind: 'textarea',
      group: 'dieu-khoan',
      blank: 2,
      hint: 'Thỏa thuận riêng về phạt cọc, sự kiện bất khả kháng… Thỏa thuận khác với khoản 2 Điều 328 BLDS sẽ được ưu tiên áp dụng. Không có thì để trống.',
    },
    { id: 'so_ban', label: 'Số bản', kind: 'text', group: 'dieu-khoan', required: true, blank: 4, placeholder: '02' },
  ],
  blocks: [
    { type: 'motto' },
    { type: 'title', text: 'HỢP ĐỒNG ĐẶT CỌC', sub: ['Số: ', { field: 'so_hop_dong' }, '/HĐĐC'] },
    { type: 'para', indent: true, italic: true, runs: ['- Căn cứ Bộ luật Dân sự số 91/2015/QH13 ngày 24 tháng 11 năm 2015;'] },
    { type: 'para', indent: true, italic: true, runs: ['- Căn cứ nhu cầu và khả năng thực tế của các bên.'] },
    ...opening.blocks,
    ...parties.blocks,
    { type: 'para', indent: true, gap: true, runs: ['Hai bên thống nhất ký kết hợp đồng đặt cọc với các thỏa thuận sau đây:'] },

    { type: 'para', bold: true, gap: true, runs: ['Điều 1. Tài sản đặt cọc'] },
    {
      type: 'para',
      indent: true,
      align: 'justify',
      runs: ['Bên A đặt cọc cho Bên B số tiền: ', { field: 'so_tien', bold: true }, ' đồng (Bằng chữ: ', { derived: 'money-words', from: 'so_tien' }, ').'],
    },

    { type: 'para', bold: true, gap: true, runs: ['Điều 2. Mục đích đặt cọc'] },
    { type: 'field', field: 'muc_dich', indent: true },

    { type: 'para', bold: true, gap: true, runs: ['Điều 3. Thời hạn đặt cọc'] },
    { type: 'para', indent: true, runs: ['Kể từ ', { field: 'tu_ngay' }, ' đến ', { field: 'den_ngay' }, '.'] },

    { type: 'para', bold: true, gap: true, runs: ['Điều 4. Phương thức giao nhận tiền đặt cọc'] },
    { type: 'para', indent: true, runs: ['Bên A giao tiền đặt cọc cho Bên B bằng hình thức: ', { field: 'phuong_thuc' }, '.'] },

    { type: 'para', bold: true, gap: true, runs: ['Điều 5. Xử lý tiền đặt cọc'] },
    {
      type: 'para',
      indent: true,
      align: 'justify',
      runs: ['1. Trường hợp hợp đồng được giao kết, thực hiện thì tiền đặt cọc được trả lại cho Bên A hoặc được trừ để thực hiện nghĩa vụ trả tiền.'],
    },
    {
      type: 'para',
      indent: true,
      align: 'justify',
      runs: ['2. Trường hợp Bên A từ chối việc giao kết, thực hiện hợp đồng thì tiền đặt cọc thuộc về Bên B.'],
    },
    {
      type: 'para',
      indent: true,
      align: 'justify',
      runs: ['3. Trường hợp Bên B từ chối việc giao kết, thực hiện hợp đồng thì Bên B phải trả cho Bên A tiền đặt cọc và một khoản tiền tương đương giá trị tiền đặt cọc, trừ trường hợp có thỏa thuận khác.'],
    },
    { type: 'para', indent: true, align: 'justify', omitIfEmpty: ['thoa_thuan_khac'], runs: ['4. Thỏa thuận khác:'] },
    { type: 'field', field: 'thoa_thuan_khac', indent: true, omitIfEmpty: true },

    { type: 'para', bold: true, gap: true, runs: ['Điều 6. Giải quyết tranh chấp'] },
    {
      type: 'para',
      indent: true,
      align: 'justify',
      runs: ['Trong quá trình thực hiện hợp đồng, nếu phát sinh tranh chấp, các bên cùng nhau thương lượng giải quyết; trường hợp không thương lượng được thì một trong các bên có quyền khởi kiện tại Tòa án có thẩm quyền theo quy định của pháp luật.'],
    },

    { type: 'para', bold: true, gap: true, runs: ['Điều 7. Điều khoản chung'] },
    {
      type: 'para',
      indent: true,
      align: 'justify',
      runs: ['Hai bên đã đọc lại, hiểu rõ và đồng ý toàn bộ nội dung hợp đồng. Hợp đồng có hiệu lực kể từ ngày ký, được lập thành ', { field: 'so_ban' }, ' bản có giá trị pháp lý như nhau, mỗi bên giữ một bản.'],
    },
    {
      type: 'signatures',
      parties: [
        { title: 'BÊN ĐẶT CỌC', caption: '(Ký, ghi rõ họ tên)', nameField: 'a_ho_ten' },
        { title: 'BÊN NHẬN ĐẶT CỌC', caption: '(Ký, ghi rõ họ tên)', nameField: 'b_ho_ten' },
      ],
    },
  ],
  aiSuggestions: [
    'Tôi đặt cọc 50 triệu để mua căn hộ của chị Lan, giá 2,1 tỷ, hẹn ký hợp đồng mua bán công chứng trong 30 ngày. Điền giúp mục đích đặt cọc và số tiền.',
    'Còn thiếu mục bắt buộc nào chưa điền?',
  ],
  draftTitle: (v) => {
    const a = typeof v.a_ho_ten === 'string' ? v.a_ho_ten.trim() : '';
    return a ? `Hợp đồng đặt cọc — ${a}` : undefined;
  },
};
