import { supabase } from './supabase';
import type { VerboseRAGInfo, LegalChunk } from './session-store';

export interface StreamCallbacks {
  onChunk: (chunk: string) => void;
  onVerboseInfo?: (info: VerboseRAGInfo) => void;
  onComplete: (fullText: string, verboseInfo?: VerboseRAGInfo) => void;
  onError: (error: Error) => void;
}

const RAG_BACKEND_URL = import.meta.env.VITE_RAG_BACKEND_URL || 'http://localhost:8000';
const LM_STUDIO_URL = import.meta.env.VITE_LM_STUDIO_URL || 'http://localhost:1234';

export interface SuggestedQuestion {
  category: string;
  title: string;
  prompt: string;
}

// 4 cau hoi goi y chuan theo yeu cau nguoi dung & thiet ke
export const SUGGESTED_QUESTIONS: SuggestedQuestion[] = [
  {
    category: 'Hợp đồng',
    title: 'Hiệu lực của Hợp đồng Đặt cọc',
    prompt: 'Hợp đồng đặt cọc mua bán nhà đất không công chứng có giá trị pháp lý không?'
  },
  {
    category: 'Lao động',
    title: 'Thời hạn Báo trước Nghỉ việc',
    prompt: 'Quy định về thời hạn báo trước khi đơn phương chấm dứt hợp đồng lao động là bao nhiêu ngày?'
  },
  {
    category: 'Bảo hiểm',
    title: 'Trợ cấp Thất nghiệp',
    prompt: 'Điều kiện và thủ tục để được hưởng trợ cấp thất nghiệp theo Luật Việc làm 2013?'
  },
  {
    category: 'Dân sự',
    title: 'Quyền và Nghĩa vụ Thuê nhà',
    prompt: 'Bên cho thuê nhà có quyền đơn phương lấy lại nhà trước thời hạn hợp đồng không?'
  }
];

// MOCK DATA

function getMockVerboseInfo(_prompt?: string): VerboseRAGInfo {

  const mockChunks: LegalChunk[] = [
    {
      chunk_id: 'blds-2015-dieu-328-001',
      doc_id: 'BLDS_2015',
      dieu: 'Dieu 328',
      content:
        'Dat coc la viec mot ben giao cho ben kia mot khoan tien hoac kim khi quy, da quy hoac vat co gia tri khac trong mot thoi han de bao dam giao ket hoac thuc hien hop dong.',
      score: 0.94,
      metadata: {
        law_name: 'Bo luat Dan su 2015',
        law_number: '91/2015/QH13',
        effective_date: '2017-01-01',
        status: 'Con hieu luc',
      },
    },
    {
      chunk_id: 'blds-2015-dieu-329-001',
      doc_id: 'BLDS_2015',
      dieu: 'Dieu 329',
      content:
        'Truong hop hop dong duoc giao ket, thuc hien thi tai san dat coc duoc tra lai cho ben dat coc hoac duoc tru de thuc hien nghia vu tra tien.',
      score: 0.87,
      metadata: {
        law_name: 'Bo luat Dan su 2015',
        law_number: '91/2015/QH13',
        effective_date: '2017-01-01',
        status: 'Con hieu luc',
      },
    },
  ];

  return {
    timeTaken: Math.random() * 1.5 + 0.5,
    topKDocs: mockChunks,
  };
}

function getMockLegalResponse(prompt: string): string {
  const lower = prompt.toLowerCase();

  if (lower.includes('dat coc') || lower.includes('\u0111\u1eb7t c\u1ecdc')) {
    return `### **Quy \u0111\u1ecbnh v\u1ec1 Hi\u1ec7u l\u1ef1c c\u1ee7a H\u1ee3p \u0111\u1ed3ng \u0110\u1eb7t c\u1ecdc**

---

#### 1. **Hi\u1ec7u l\u1ef1c c\u1ee7a H\u1ee3p \u0111\u1ed3ng \u0110\u1eb7t c\u1ecdc**
Theo **\u0110i\u1ec1u 328 B\u1ed9 lu\u1eadt D\u00e2n s\u1ef1 2015**, \u0111\u1eb7t c\u1ecdc l\u00e0 vi\u1ec7c m\u1ed9t b\u00ean giao cho b\u00ean kia m\u1ed9t kho\u1ea3n ti\u1ec1n ho\u1eb7c kim kh\u00ed qu\u00fd, \u0111\u00e1 qu\u00fd \u0111\u1ec3 b\u1ea3o \u0111\u1ea3m giao k\u1ebft ho\u1eb7c th\u1ef1c hi\u1ec7n h\u1ee3p \u0111\u1ed3ng.

*Status Badge: [C\u00f2n hi\u1ec7u l\u1ef1c]*
*Tr\u00edch d\u1eabn: **B\u1ed9 lu\u1eadt D\u00e2n s\u1ef1 2015 (Lu\u1eadt s\u1ed1 91/2015/QH13)***

> [!NOTE]
> **\u0110i\u1ec3m c\u1ea7n l\u01b0u \u00fd \u0111\u1eb7c bi\u1ec7t**: Ph\u00e1p lu\u1eadt *kh\u00f4ng b\u1eaft bu\u1ed9c* h\u1ee3p \u0111\u1ed3ng \u0111\u1eb7t c\u1ecdc ph\u1ea3i c\u00f4ng ch\u1ee9ng hay ch\u1ee9ng th\u1ef1c.

---

#### 2. **Tr\u00e1ch nhi\u1ec7m Ph\u1ea1t c\u1ecdc khi B\u00ean nh\u1eadn c\u1ecdc t\u1eeb ch\u1ed1i**
* N\u1ebfu b\u00ean nh\u1eadn c\u1ecdc t\u1eeb ch\u1ed1i giao k\u1ebft/th\u1ef1c hi\u1ec7n:
  1. Ph\u1ea3i **ho\u00e0n tr\u1ea3 t\u00e0i s\u1ea3n \u0111\u1eb7t c\u1ecdc** cho b\u00ean \u0111\u1eb7t c\u1ecdc.
  2. Ph\u1ea3i tr\u1ea3 th\u00eam m\u1ed9t kho\u1ea3n ti\u1ec1n t\u01b0\u01a1ng \u0111\u01b0\u01a1ng gi\u00e1 tr\u1ecb t\u00e0i s\u1ea3n \u0111\u1eb7t c\u1ecdc.

---

#### 3. **Kh\u00e2u ti\u1ebfp theo**
* L\u1eadp v\u0103n b\u1ea3n y\u00eau c\u1ea7u ho\u00e0n tr\u1ea3 ti\u1ec1n c\u1ecdc.
* N\u1ebfu c\u1ed1 t\u00ecnh kh\u00f4ng tr\u1ea3, c\u00f3 th\u1ec3 kh\u1edfi ki\u1ec7n t\u1ea1i T\u00f2a \u00e1n nh\u00e2n d\u00e2n c\u1ea5p huy\u1ec7n.`;
  }

  if (lower.includes('lao dong') || lower.includes('that nghiep') || lower.includes('lao \u0111\u1ed9ng') || lower.includes('th\u1ea5t nghi\u1ec7p')) {
    return `### **Quy \u0111\u1ecbnh v\u1ec1 \u0110\u01a1n ph\u01b0\u01a1ng Ch\u1ea5m d\u1ee9t H\u1ee3p \u0111\u1ed3ng & Tr\u1ee3 c\u1ea5p Th\u1ea5t nghi\u1ec7p**

---

#### 1. **Th\u1eddi h\u1ea1n b\u00e1o tr\u01b0\u1edbc khi \u0111\u01a1n ph\u01b0\u01a1ng ch\u1ea5m d\u1ee9t H\u0110L\u0110**
C\u0103n c\u1ee9 **\u0110i\u1ec1u 35 B\u1ed9 lu\u1eadt Lao \u0111\u1ed9ng 2019**:

* **\u00cdt nh\u1ea5t 45 ng\u00e0y**: H\u1ee3p \u0111\u1ed3ng *kh\u00f4ng x\u00e1c \u0111\u1ecbnh th\u1eddi h\u1ea1n*.
* **\u00cdt nh\u1ea5t 30 ng\u00e0y**: H\u1ee3p \u0111\u1ed3ng *x\u00e1c \u0111\u1ecbnh th\u1eddi h\u1ea1n* (12-36 th\u00e1ng).
* **\u00cdt nh\u1ea5t 03 ng\u00e0y l\u00e0m vi\u1ec7c**: H\u1ee3p \u0111\u1ed3ng *d\u01b0\u1edbi 12 th\u00e1ng*.

---

#### 2. **\u0110i\u1ec1u ki\u1ec7n h\u01b0\u1edfng Tr\u1ee3 c\u1ea5p Th\u1ea5t nghi\u1ec7p**
Theo **\u0110i\u1ec1u 49 Lu\u1eadt Vi\u1ec7c l\u00e0m 2013**:

> * \u0110\u00e3 \u0111\u00f3ng BHTN t\u1eeb \u0111\u1ee7 **12 th\u00e1ng tr\u1edf l\u00ean** trong 24 th\u00e1ng tr\u01b0\u1edbc khi ch\u1ea5m d\u1ee9t H\u0110L\u0110.
> * N\u1ed9p h\u1ed3 s\u01a1 t\u1ea1i **Trung t\u00e2m D\u1ecbch v\u1ee5 Vi\u1ec7c l\u00e0m** trong **03 th\u00e1ng** k\u1ec3 t\u1eeb ng\u00e0y ch\u1ea5m d\u1ee9t H\u0110L\u0110.`;
  }

  return `### **\u0110\u1ecbnh h\u01b0\u1edbng X\u1eed l\u00fd Y\u00eau c\u1ea7u Ph\u00e1p l\u00fd**

> [!IMPORTANT]
> **L\u01b0u \u00fd quan tr\u1ecdng**: Ph\u1ea3n h\u1ed3i n\u00e0y \u0111\u01b0\u1ee3c t\u1ed5ng h\u1ee3p t\u1ef1 \u0111\u1ed9ng nh\u1eb1m m\u1ee5c \u0111\u00edch tham kh\u1ea3o \u0111\u1ecbnh h\u01b0\u1edbng ban \u0111\u1ea7u, kh\u00f4ng thay th\u1ebf v\u0103n b\u1ea3n t\u01b0 v\u1ea5n ch\u00ednh th\u1ee9c t\u1eeb Lu\u1eadt s\u01b0.

Li\u00ean h\u1ec7 v\u1edbi **C\u01a1 quan nh\u00e0 n\u01b0\u1edbc c\u00f3 th\u1ea9m quy\u1ec1n** ho\u1eb7c **V\u0103n ph\u00f2ng Lu\u1eadt s\u01b0** \u0111\u1ec3 \u0111\u01b0\u1ee3c tr\u1ee3 gi\u00fap chi ti\u1ebft.`;
}

// LM STUDIO INTEGRATION

async function streamFromLMStudio(
  prompt: string,
  context: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<boolean> {
  try {
    const systemPrompt = `Ban la tro ly phap ly AI chuyen ve phap luat Viet Nam. Hay tra loi dua tren cac van ban phap luat duoc cung cap. Su dung dinh dang Markdown voi cac tieu de ro rang. Luon trich dan dieu khoan va ten van ban phap luat cu the.`;

    const userMessage = context
      ? `Cau hoi: ${prompt}\n\nNgu canh tu co so du lieu phap luat:\n${context}`
      : prompt;

    const res = await fetch(`${LM_STUDIO_URL}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'local-model',
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userMessage },
        ],
        stream: true,
        temperature: 0.3,
        max_tokens: 2048,
      }),
      signal,
    });

    if (!res.ok || !res.body) return false;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let fullText = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split('\n').filter((l) => l.startsWith('data: '));

      for (const line of lines) {
        const jsonStr = line.replace('data: ', '').trim();
        if (jsonStr === '[DONE]') continue;
        try {
          const parsed = JSON.parse(jsonStr);
          const delta = parsed.choices?.[0]?.delta?.content;
          if (delta) {
            fullText += delta;
            callbacks.onChunk(fullText);
          }
        } catch {
          // ignore malformed JSON chunks
        }
      }
    }

    if (fullText) {
      callbacks.onComplete(trimRepeatedBlocks(fullText));
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

// HELPERS

const MIN_LOOP_PARAGRAPH_CHARS = 40;

/**
 * Cat khoi lap: model nho doi khi lap nguyen mot khoi den het max_tokens.
 * Chi tinh la lap khi >= 2 doan dai lien tiep trung nguyen van va dung thu tu voi
 * mot khoi truoc do (cung logic voi find_loop_cut o backend/src/retrieval/generator.py).
 */
export function trimRepeatedBlocks(text: string): string {
  const keys: string[] = [];
  const starts: number[] = [];
  let pos = 0;
  for (const para of text.split('\n')) {
    const key = para.split(/\s+/).join(' ').trim().replace(/^[•*\-– ]+|[•*\-– ]+$/g, '').toLowerCase();
    if (key.length >= MIN_LOOP_PARAGRAPH_CHARS) {
      keys.push(key);
      starts.push(pos);
    }
    pos += para.length + 1;
  }
  for (let i = 1; i < keys.length - 1; i++) {
    for (let j = 0; j < i; j++) {
      if (keys[j] === keys[i] && keys[j + 1] === keys[i + 1]) {
        return text.slice(0, starts[i]).trimEnd();
      }
    }
  }
  return text;
}

/**
 * Mo phong streaming tung tu cho mock/fallback response.
 */
async function simulateStreaming(
  fullText: string,
  callbacks: StreamCallbacks,
  signal: AbortSignal | undefined,
  verboseInfo: VerboseRAGInfo
): Promise<void> {
  const words = fullText.split(' ');
  let currentText = '';

  for (let i = 0; i < words.length; i++) {
    if (signal?.aborted) {
      throw new Error('Yeu cau da bi huy boi nguoi dung.');
    }
    currentText += (i === 0 ? '' : ' ') + words[i];
    callbacks.onChunk(currentText);

    const delay = Math.floor(Math.random() * 25) + 15;
    await new Promise((res) => setTimeout(res, delay));
  }

  callbacks.onComplete(currentText, verboseInfo);
}

/**
 * Gui yeu cau cau hoi va streaming cau tra loi tung tu/chunk.
 *
 * Thu tu uu tien:
 *   1. FastAPI RAG Backend (/api/query) -> lay context + goi LM Studio streaming
 *   2. LM Studio truc tiep (neu backend offline nhung LM Studio online)
 *   3. Supabase Edge Function (fallback cloud)
 *   4. Mock response (offline hoan toan)
 */
export async function streamLegalAnswer(
  prompt: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  try {
    // BUOC 1: Goi FastAPI RAG Backend de lay context
    let ragResponse: any = null;
    try {
      const res = await fetch(`${RAG_BACKEND_URL}/api/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: prompt, top_k: 5, enable_graph: true }),
        signal,
      });
      if (res.ok) {
        ragResponse = await res.json();
      }
    } catch {
      // Backend offline -> tiep tuc fallback
    }

    // Xay dung VerboseInfo tu RAG results
    let verboseInfo: VerboseRAGInfo;
    if (ragResponse?.results) {
      verboseInfo = {
        timeTaken: ragResponse.time_taken,
        topKDocs: ragResponse.results.map((r: any) => ({
          chunk_id: r.chunk_id,
          doc_id: r.doc_id,
          dieu: r.dieu,
          content: r.content,
          score: r.score,
          metadata: r.metadata,
        })),
      };
    } else {
      verboseInfo = getMockVerboseInfo(prompt);
    }

    // Gui VerboseInfo ve UI som (hien thi sources trong khi LLM dang stream)
    callbacks.onVerboseInfo?.(verboseInfo);

    // BUOC 2: Backend da sinh san cau tra loi (Stage 5) -> dung luon, khong goi LM Studio lan nua
    // (trinh duyet goi thang LM Studio bi chan CORS, va context o day thieu so hieu van ban)
    if (ragResponse?.llm_answer) {
      await simulateStreaming(trimRepeatedBlocks(ragResponse.llm_answer), callbacks, signal, verboseInfo);
      return;
    }

    // BUOC 3: Thu LM Studio truc tiep (khong co RAG context)
    const lmDirectOk = await streamFromLMStudio(prompt, '', callbacks, signal);
    if (lmDirectOk) return;

    // BUOC 4: Thu Supabase Edge Function
    const { data, error } = await supabase.functions
      .invoke('rag-chat', { body: { prompt } })
      .catch(() => ({ data: null, error: true }));

    if (!error && data?.text) {
      callbacks.onComplete(data.text, verboseInfo);
      return;
    }

    // BUOC 5: Mock fallback (offline hoan toan)
    const mockText = getMockLegalResponse(prompt);
    await simulateStreaming(mockText, callbacks, signal, verboseInfo);
  } catch (err: any) {
    if (err.name === 'AbortError' || err.message?.includes('huy')) {
      console.log('Stream aborted by user');
    } else {
      callbacks.onError(
        err instanceof Error ? err : new Error('Co loi xay ra khi ket noi may chu.')
      );
    }
  }
}