import { supabase } from '@/lib/supabase';
import type { ChatMessage, Draft, DraftSummary, DraftTemplate, FieldValues } from './types';
import { normalizeValues, progressOf } from './values';

// UI chỉ nói chuyện với `draftService`. Hiện lưu ở Supabase (bảng drafting_documents,
// xem src/database/drafting_schema.sql); đổi nơi lưu = viết DraftSource khác rồi đổi dòng cuối file.

/** Đường dẫn mở một mẫu trống. Chưa ghi gì vào DB cho tới khi người dùng thực sự sửa. */
export const NEW_DRAFT_ID = 'moi';
export const newDraftPath = (templateId: string) => `/soan-thao/${NEW_DRAFT_ID}?mau=${encodeURIComponent(templateId)}`;

export interface DraftPatch {
  title?: string;
  field_values?: FieldValues;
  chat?: ChatMessage[];
}

export interface DraftSource {
  list(): Promise<DraftSummary[]>;
  get(id: string): Promise<Draft | null>;
  create(template: DraftTemplate, init?: { title?: string; field_values?: FieldValues; chat?: ChatMessage[] }): Promise<Draft>;
  update(id: string, template: DraftTemplate, patch: DraftPatch): Promise<{ updated_at: string }>;
  remove(id: string): Promise<void>;
}

const SUMMARY_COLUMNS = 'id,template_id,title,progress,created_at,updated_at';
// Lịch sử hiện ảnh thu nhỏ có nội dung đã điền nên cần field_values (vài KB/bản), không cần chat
const LIST_COLUMNS = `${SUMMARY_COLUMNS},field_values`;
const FULL_COLUMNS = `${SUMMARY_COLUMNS},template_version,field_values,chat`;

const fail = (what: string, error: { message: string; code?: string }) => {
  // PGRST205/42P01: bảng chưa được tạo — nhắc chạy SQL thay vì báo lỗi khó hiểu
  if (error.code === 'PGRST205' || error.code === '42P01') {
    return new Error('Chưa tạo bảng bản nháp trên Supabase (chạy src/database/drafting_schema.sql).');
  }
  return new Error(`Không ${what}: ${error.message}`);
};

const supabaseSource: DraftSource = {
  async list() {
    const { data, error } = await supabase.from('drafting_documents').select(LIST_COLUMNS).order('updated_at', { ascending: false }).limit(100);
    if (error) throw fail('tải được danh sách bản nháp', error);
    return data as DraftSummary[];
  },

  async get(id) {
    const { data, error } = await supabase.from('drafting_documents').select(FULL_COLUMNS).eq('id', id).maybeSingle();
    if (error) {
      // id không phải UUID hợp lệ → coi như không tồn tại
      if (error.code === '22P02') return null;
      throw fail('mở được bản nháp', error);
    }
    return (data as Draft | null) ?? null;
  },

  async create(template, init) {
    const values = normalizeValues(template, init?.field_values ?? {});
    const { data, error } = await supabase
      .from('drafting_documents')
      .insert({
        template_id: template.id,
        template_version: template.version,
        title: init?.title?.trim() || template.title,
        field_values: values,
        chat: init?.chat ?? [],
        progress: progressOf(template, values),
      })
      .select(FULL_COLUMNS)
      .single();
    if (error) throw fail('tạo được bản nháp', error);
    return data as Draft;
  },

  async update(id, template, patch) {
    const row: Record<string, unknown> = { template_version: template.version };
    if (patch.title !== undefined) row.title = patch.title.trim() || template.title;
    if (patch.chat !== undefined) row.chat = patch.chat;
    if (patch.field_values !== undefined) {
      row.field_values = patch.field_values;
      row.progress = progressOf(template, patch.field_values);
    }
    const { data, error } = await supabase.from('drafting_documents').update(row).eq('id', id).select('updated_at').single();
    if (error) throw fail('lưu được bản nháp', error);
    return data as { updated_at: string };
  },

  async remove(id) {
    const { error } = await supabase.from('drafting_documents').delete().eq('id', id);
    if (error) throw fail('xoá được bản nháp', error);
  },
};

export const draftService: DraftSource = supabaseSource;
