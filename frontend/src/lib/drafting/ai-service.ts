import type { ChatMessage, DraftTemplate, FieldValue, FieldValues } from './types';

// Gọi trợ lý soạn thảo ở backend (backend/src/api/routers/drafting.py). Trình duyệt không gọi thẳng
// LM Studio được (bị chặn CORS), nên mọi yêu cầu đi qua FastAPI.

const RAG_BACKEND_URL = import.meta.env.VITE_RAG_BACKEND_URL || 'http://localhost:8000';

export interface AssistResult {
  reply: string;
  edits: { field: string; value: FieldValue }[];
  dropped: { field: string; reason: string }[];
}

export interface AssistantStatus {
  available: boolean;
  model?: string;
}

export async function getAssistantStatus(signal?: AbortSignal): Promise<AssistantStatus> {
  try {
    const res = await fetch(`${RAG_BACKEND_URL}/api/drafting/status`, { signal });
    if (!res.ok) return { available: false };
    return (await res.json()) as AssistantStatus;
  } catch {
    return { available: false };
  }
}

export async function askAssistant(
  args: {
    template: DraftTemplate;
    values: FieldValues;
    history: ChatMessage[];
    message: string;
    focusField?: string | null;
  },
  signal?: AbortSignal,
): Promise<AssistResult> {
  const { template, values, history, message, focusField } = args;
  const body = {
    template_title: template.title,
    fields: template.fields.map((f) => ({
      id: f.id,
      label: f.label,
      kind: f.kind,
      group: template.groups.find((g) => g.id === f.group)?.label,
      hint: f.hint,
      required: !!f.required,
    })),
    values,
    // Tin lỗi không gửi lại cho model
    history: history.filter((m) => !m.error).map((m) => ({ role: m.role, content: m.content })),
    message,
    focus_field: focusField ?? null,
  };

  let res: Response;
  try {
    res = await fetch(`${RAG_BACKEND_URL}/api/drafting/assist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new Error('Không kết nối được máy chủ trợ lý. Kiểm tra backend đã chạy chưa.', { cause: e });
  }

  if (!res.ok) {
    const detail = await res
      .json()
      .then((d: { detail?: unknown }) => (typeof d.detail === 'string' ? d.detail : null))
      .catch(() => null);
    throw new Error(detail ?? `Trợ lý gặp lỗi (${res.status}).`);
  }
  return (await res.json()) as AssistResult;
}
