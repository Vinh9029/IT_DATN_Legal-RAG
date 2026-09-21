import { supabase } from './supabase';

export interface StreamCallbacks {
  onChunk: (chunk: string) => void;
  onComplete: (fullText: string) => void;
  onError: (error: Error) => void;
}

// 4 câu hỏi gợi ý chuẩn theo yêu cầu người dùng & thiết kế
export const SUGGESTED_QUESTIONS = [
  {
    category: "Hợp đồng & Dân sự",
    title: "Đặt cọc mua bán nhà đất không thành",
    prompt: "Hợp đồng đặt cọc mua bán nhà đất bằng giấy tay có hiệu lực pháp lý không? Bên nhận cọc hủy hợp đồng thì phạt cọc thế nào?",
    icon: "FileCheck2"
  },
  {
    category: "Lao động",
    title: "Trợ cấp thất nghiệp & Chấm dứt HĐLĐ",
    prompt: "Người lao động đơn phương chấm dứt hợp đồng lao động cần báo trước bao nhiêu ngày và thủ tục hưởng trợ cấp thất nghiệp ra sao?",
    icon: "BriefcaseBusiness"
  },
  {
    category: "Đất đai & Nhà ở",
    title: "Cấp Giấy chứng nhận QSDĐ lần đầu",
    prompt: "Điều kiện và thủ tục xin cấp Sổ đỏ (Giấy chứng nhận QSDĐ) lần đầu cho đất không có giấy tờ về quyền sử dụng đất?",
    icon: "Landmark"
  },
  {
    category: "Doanh nghiệp",
    title: "Thủ tục thay đổi người đại diện",
    prompt: "Hồ sơ và quy trình thay đổi Người đại diện theo pháp luật của Công ty TNHH 2 thành viên trở lên thực hiện thế nào?",
    icon: "Scale"
  }
];

// Trả lời mẫu giàu định dạng Markdown (Status Badges, Highlights, Quotes, Bullet Points)
function getMockLegalResponse(prompt: string): string {
  const lower = prompt.toLowerCase();
  
  if (lower.includes("đặt cọc") || lower.includes("hợp đồng")) {
    return `### **Tư vấn Căn cứ Pháp lý về Đặt cọc & Hợp đồng Dân sự**

---

#### 1. **Hiệu lực của Hợp đồng Đặt cọc**
Theo **Điều 328 Bộ luật Dân sự 2015**, đặt cọc là việc một bên giao cho bên kia một khoản tiền hoặc kim khí quý, đá quý để bảo đảm tuyên bố giao kết hoặc thực hiện hợp đồng.

*Status Badge: [Còn hiệu lực]*  
*Trích dẫn: **Bộ luật Dân sự 2015 (Luật số 91/2015/QH13)***

> [!NOTE]
> **Điểm cần lưu ý đặc biệt**: Pháp luật *không bắt buộc* hợp đồng đặt cọc phải công chứng hay chứng thực. Tuy nhiên, lập hợp đồng bằng văn bản có chữ ký rõ ràng là căn cứ quan trọng nhất để giải quyết tranh chấp.

---

#### 2. **Trách nhiệm Phạt cọc khi Bên bán/Bên nhận cọc từ chối**
* **Trường hợp hợp đồng được giao kết**: Tài sản đặt cọc được trả lại cho bên đặt cọc hoặc được trừ để thực hiện nghĩa vụ trả tiền.
* **Nếu bên nhận cọc từ chối giao kết/thực hiện**:
  1. Phải **hoàn trả tài sản đặt cọc** cho bên đặt cọc.
  2. Phải trả thêm một khoản tiền tương đương giá trị tài sản đặt cọc (*trừ trường hợp có thỏa thuận khác*).

---

#### 3. **Khuyến nghị bước xử lý tiếp theo**
* Kiểm tra lại nội dung biên nhận/hợp đồng đặt cọc đã ký.
* Lập văn bản thông báo yêu cầu thực hiện nghĩa vụ hoặc hoàn trả tiền cọc.
* Trong trường hợp cố tình không trả, có thể khởi kiện tại **Tòa án nhân dân cấp huyện** nơi bị đơn cư trú.`;
  }

  if (lower.includes("lao động") || lower.includes("thất nghiệp")) {
    return `### **Quy định về Đơn phương Chấm dứt Hợp đồng & Trợ cấp Thất nghiệp**

---

#### 1. **Thời hạn báo trước khi đơn phương chấm dứt HĐLĐ**
Căn cứ **Điều 35 Bộ luật Lao động 2019**:

*Status Badge: [Còn hiệu lực]*  
*Trích dẫn: **Bộ luật Lao động 2019 (Luật số 45/2019/QH14)***

* **Ít nhất 45 ngày**: Đối với hợp đồng lao động *không xác định thời hạn*.
* **Ít nhất 30 ngày**: Đối với hợp đồng lao động *xác định thời hạn* (từ 12 đến 36 tháng).
* **Ít nhất 03 ngày làm việc**: Đối với hợp đồng lao động *xác định thời hạn dưới 12 tháng*.

---

#### 2. **Điều kiện & Thủ tục hưởng Trợ cấp Thất nghiệp**
Theo **Điều 49 Luật Việc làm 2013**:

> **Điều kiện nhận trợ cấp**:
> * Đã chấm dứt HĐLĐ đúng pháp luật (không vi phạm thời hạn báo trước).
> * Đã đóng BHTN từ đủ **12 tháng trở lên** trong thời gian 24 tháng trước khi chấm dứt HĐLĐ.
> * Đã nộp hồ sơ hưởng trợ cấp tại **Trung tâm Dịch vụ Việc làm** trong thời hạn **03 tháng** kể từ ngày chấm dứt HĐLĐ.

---

#### 3. **Hồ sơ cần chuẩn bị**
1. Đơn đề nghị hưởng trợ cấp thất nghiệp (theo mẫu).
2. Bản chính hoặc bản sao có chứng thực của **HĐLĐ hoặc Quyết định nghỉ việc**.
3. **Sổ Bảo hiểm xã hội** đã chốt bìa và tờ rời.`;
  }

  return `### **Định hướng Xử lý Yêu cầu Pháp lý**

---

#### 1. **Căn cứ Pháp luật liên quan**
Dựa trên thông tin bạn cung cấp, vấn đề này được điều chỉnh bởi hệ thống văn bản pháp luật hiện hành của Việt Nam.

*Status Badge: [Còn hiệu lực]*  
*Phạm vi tham chiếu: **Văn bản Quy phạm Pháp luật chuyên ngành***

> [!IMPORTANT]
> **Lưu ý quan trọng**: Phản hồi này được tổng hợp tự động nhằm mục đích tham khảo định hướng ban đầu, không thay thế văn bản tư vấn chính thức từ Luật sư hoặc Chuyên gia pháp lý.

---

#### 2. **Các điểm mấu chốt cần xác minh**
* **Chủ thể liên quan**: Cá nhân, Tổ chức hoặc Doanh nghiệp tham gia quan hệ pháp luật.
* **Thời hiệu & Mốc thời gian**: Các sự kiện pháp lý đã phát sinh và thời hạn còn hiệu lực.
* **Chứng cứ & Giấy tờ**: Giấy chứng nhận, văn bản thỏa thuận, hóa đơn, chứng từ giao dịch.

---

#### 3. **Hướng dẫn bước tiếp theo**
1. *Rà soát lại toàn bộ tài liệu*, giấy tờ giao dịch hiện có.
2. *Xác định rõ nguyện vọng* và kết quả pháp lý mong muốn đạt được.
3. Liên hệ với **Cơ quan nhà nước có thẩm quyền** hoặc **Văn phòng Luật sư** để được trợ giúp chi tiết.`;
}

/**
 * Gửi yêu cầu câu hỏi và streaming câu trả lời từng từ/chunk
 */
export async function streamLegalAnswer(
  prompt: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  try {
    // Thử gọi Supabase Edge Function nếu khả thi
    const { data, error } = await supabase.functions.invoke('rag-chat', {
      body: { prompt }
    }).catch(() => ({ data: null, error: true }));

    if (!error && data && data.text) {
      callbacks.onComplete(data.text);
      return;
    }

    // Fallback Streaming Simulation (hiệu ứng typing tự nhiên như AI thực thụ)
    const fullText = getMockLegalResponse(prompt);
    const words = fullText.split(' ');
    let currentText = '';

    for (let i = 0; i < words.length; i++) {
      if (signal?.aborted) {
        throw new Error('Yêu cầu đã bị hủy bởi người dùng.');
      }
      currentText += (i === 0 ? '' : ' ') + words[i];
      callbacks.onChunk(currentText);

      // Delay biến thiên nhẹ cho cảm giác gõ máy thực tế
      const delay = Math.floor(Math.random() * 25) + 15;
      await new Promise((res) => setTimeout(res, delay));
    }

    callbacks.onComplete(currentText);
  } catch (err: any) {
    if (err.name === 'AbortError' || err.message?.includes('hủy')) {
      console.log('Stream aborted');
    } else {
      callbacks.onError(err instanceof Error ? err : new Error('Có lỗi xảy ra khi kết nối máy chủ.'));
    }
  }
}
