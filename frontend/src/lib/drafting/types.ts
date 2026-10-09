// ── Mô hình biểu mẫu ─────────────────────────────────────────────
// Một biểu mẫu = danh sách Ô cần điền (fields) + bố cục trang giấy (blocks).
// Trình soạn thảo, bản in PDF và file Word đều dựng từ CÙNG một định nghĩa này,
// nên chữ in sẵn, thứ tự mục và chỗ trống luôn khớp nhau ở cả ba nơi.
// Thêm biểu mẫu mới = thêm một file trong ./templates rồi khai báo ở templates/index.ts.

/** Giá trị của một ô: danh sách (list) là mảng, còn lại là chuỗi */
export type FieldValue = string | string[];
export type FieldValues = Record<string, FieldValue>;

export type FieldKind =
  | 'text' // một dòng, nằm giữa câu chữ in sẵn
  | 'textarea' // đoạn văn nhiều dòng
  | 'list' // các dòng đánh số 1., 2., 3.
  | 'date' // lưu YYYY-MM-DD, in "ngày … tháng … năm …"
  | 'money'; // lưu chữ số, in "50.000.000"

export interface FieldDef {
  id: string;
  label: string;
  kind: FieldKind;
  /** Nhóm trong mục lục bên trái (FieldGroup.id) */
  group: string;
  required?: boolean;
  /** Hướng dẫn ghi — với mẫu chính thức là phần "Hướng dẫn sử dụng mẫu" */
  hint?: string;
  /** Chữ mờ khi ô còn trống trong trình soạn thảo */
  placeholder?: string;
  /** Số chấm "…" in ra khi ô để trống (để viết tay); textarea/list là số dòng chấm */
  blank?: number;
}

export interface FieldGroup {
  id: string;
  label: string;
}

/** Một đoạn chữ trong dòng */
export type Run =
  | string // chữ in sẵn
  | {
      text: string;
      bold?: boolean;
      italic?: boolean;
      /** Chỉ in khi ô này CÒN TRỐNG — vd. "(nếu có)" sau số điện thoại */
      whenEmpty?: string;
      /** Chỉ in khi ô này ĐÃ ĐIỀN */
      whenFilled?: string;
    }
  | {
      field: string;
      /** Số chú thích (1), (2)… của mẫu chính thức — chỉ hiện trong trình soạn thảo, không in ra */
      note?: number;
      bold?: boolean;
    }
  /** Chú thích đứng riêng (không gắn với ô nào) — chỉ hiện trong trình soạn thảo */
  | { note: number }
  | {
      /** Chữ tự sinh từ một ô khác, người dùng không gõ trực tiếp */
      derived: 'money-words';
      from: string;
    };

export type Align = 'left' | 'center' | 'right' | 'justify';

export type Block =
  /** Quốc hiệu + tiêu ngữ (có gạch dưới tiêu ngữ) */
  | { type: 'motto' }
  /** "Mẫu số 23-DS (Ban hành kèm theo …)" — góc phải, chữ nghiêng nhỏ */
  | { type: 'form-code'; lines: string[] }
  /** Tên văn bản: in hoa, đậm, căn giữa */
  | { type: 'title'; text: string; sub?: Run[] }
  | {
      type: 'para';
      runs: Run[];
      align?: Align;
      /** Thụt đầu dòng như văn bản hành chính */
      indent?: boolean;
      bold?: boolean;
      italic?: boolean;
      /** Khoảng cách phía trên lớn hơn bình thường (đầu một phần mới) */
      gap?: boolean;
      /** Bỏ hẳn dòng này khỏi bản in khi TẤT CẢ các ô này đều trống (mục "nếu có") */
      omitIfEmpty?: string[];
    }
  /** Ô dạng khối: textarea hoặc list chiếm trọn các dòng riêng */
  | { type: 'field'; field: string; note?: number; indent?: boolean; omitIfEmpty?: boolean }
  /** Chữ ký các bên, chia cột */
  | { type: 'signatures'; parties: SignatureParty[] };

export interface SignatureParty {
  title: string;
  note?: number;
  /** Dòng nghiêng dưới tiêu đề, vd. "(Ký, ghi rõ họ tên)" */
  caption?: string;
  /** Ô họ tên in dưới chỗ ký */
  nameField?: string;
}

export type TemplateSource =
  | { kind: 'official'; code: string; issuedBy: string }
  | { kind: 'reference'; basis: string };

export interface DraftTemplate {
  id: string;
  /** Tăng khi đổi ý nghĩa của ô cũ; bản nháp lưu lại số này */
  version: number;
  title: string;
  category: string;
  description: string;
  source: TemplateSource;
  groups: FieldGroup[];
  fields: FieldDef[];
  blocks: Block[];
  /** Câu gợi ý cho khung trợ lý AI khi chưa có tin nhắn nào */
  aiSuggestions?: string[];
  /** Tên mặc định của bản nháp theo nội dung đã điền */
  draftTitle?: (values: FieldValues) => string | undefined;
}

// ── Bản nháp & trò chuyện với AI ─────────────────────────────────

/** Một thay đổi AI đã áp vào biểu mẫu — giữ cả giá trị cũ để hoàn tác được kể cả sau khi tải lại trang */
export interface FieldEdit {
  field: string;
  before: FieldValue;
  after: FieldValue;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  /**
   * Chỉ có ở tin của AI có sửa biểu mẫu. Trạng thái "đã áp dụng / đã hoàn tác" KHÔNG lưu riêng mà
   * suy ra bằng cách so giá trị hiện tại với before/after — nên Ctrl+Z và nút hoàn tác luôn khớp nhau.
   */
  edits?: FieldEdit[];
  /** Đề xuất của AI bị backend loại (vd. chứa số liệu người dùng chưa cung cấp) */
  dropped?: { field: string; reason: string }[];
  /** Ô người dùng đang đứng khi gửi tin */
  focus_field?: string;
  error?: boolean;
}

export interface DraftSummary {
  id: string;
  template_id: string;
  title: string;
  progress: number;
  created_at: string;
  updated_at: string;
  /** Có trong danh sách lịch sử (để vẽ ảnh thu nhỏ) */
  field_values?: FieldValues;
}

export interface Draft extends DraftSummary {
  template_version: number;
  field_values: FieldValues;
  chat: ChatMessage[];
}
