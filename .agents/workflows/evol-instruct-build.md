---
description: Xây dựng Quy trình Evol-Instruct cho Dữ liệu Pháp luật Việt Nam trên Llama 3.1 8B GGUF
---

Trong kỷ nguyên của các mô hình ngôn ngữ lớn (LLM), chất lượng dữ liệu huấn luyện (fine-tuning) đóng vai trò quyết định hơn là số lượng đơn thuần. Tài liệu này hướng dẫn cách triển khai thuật toán Evol-Instruct—kế thừa từ nghiên cứu WizardLM—để tự động hóa việc tạo dữ liệu tổng hợp (Synthetic Data Generation) dựa trên kho tàng văn bản pháp quy Việt Nam. Mục tiêu là chuyển hóa các chỉ thị đơn giản thành các bài toán lập luận phức tạp theo cấu trúc pháp lý chuyên nghiệp IRAC (Issue, Rule, Application, Conclusion).

1. Thiết lập Môi trường Hệ thống và Cấu hình Local API

Việc sử dụng mô hình Llama 3.1 8B Instruct GGUF là một lựa chọn chiến lược cho các hệ thống nghiên cứu tại chỗ. Với kiến trúc Llama 3.1, mô hình 8B đạt được khả năng tuân thủ chỉ thị tương đương với các dòng 70B đời cũ nhưng yêu cầu tài nguyên phần cứng thấp hơn đáng kể.

Cấu hình Phần cứng & Phần mềm

* Mô hình: Meta-Llama-3.1-8B-Instruct-GGUF-Q4_K_M (Bản định lượng 4-bit Medium).
* Yêu cầu VRAM: Khoảng ~5.5GB cho trọng số mô hình và KV Cache. Khuyến nghị card đồ họa 8GB VRAM trở lên để đảm bảo tốc độ suy luận ổn định.
* Nền tảng: LM Studio (sử dụng backend llama.cpp).
* API Server: Kích hoạt Local Server tại Port 1234 để tương thích hoàn toàn với thư viện OpenAI Python SDK.

Tham số API tối ưu cho quy trình Evolution

Tham số	Giá trị	Vai trò
temperature	0.7 - 1.0	Khuyến nghị cho bước Evolution để tăng tính đa dạng sáng tạo.
max_tokens	2048	Đảm bảo đủ không gian cho các phân tích Application dài trong IRAC.
top_p	0.9	Lọc các phân phối xác suất đuôi dài, giữ tính mạch lạc.
stop	`<	eot_id

2. Xây dựng Bộ hạt giống (Seed Prompts) từ Kho tri thức Pháp luật

Dữ liệu nguồn được trích xuất từ tập th1nhng0/vietnamese-legal-documents. Tại đây, tính chính xác của metadata là chìa khóa để xây dựng ngữ cảnh hệ thống (System Prompt).
Code cài đặt dataset của Thịnh Ngô (from datasets import load_dataset
ds = load_dataset("th1nhng0/vietnamese-legal-documents", "content")from datasets import load_dataset
ds = load_dataset("th1nhng0/vietnamese-legal-documents", "content")

1. Tiền xử lý: Làm sạch trường content_html bằng thư viện BeautifulSoup, trích xuất văn bản thô (plain text).
2. Metadata Injection: Sử dụng các trường nganh (ngành) và linh_vuc (lĩnh vực) để làm tham số đầu vào cho System Prompt, giúp mô hình định vị đúng phạm vi điều chỉnh của luật.
3. Trích xuất thực thể (NER): Áp dụng mô hình PhoBERT để xác định các thực thể pháp lý trọng yếu:
  * Số hiệu luật/văn bản (vd: Luật Dân sự 2015).
  * Cơ quan ban hành (vd: Quốc hội, Chính phủ).
  * Nội dung điều luật cụ thể.

Logic tạo Seed Prompt: Từ các thực thể trích xuất, chúng ta tạo ra các chỉ thị đơn giản nhất. Ví dụ: "Dựa trên [Số hiệu luật], hãy cho biết thẩm quyền của [Cơ quan ban hành] trong việc [Nội dung điều luật]."

Các câu hỏi này đóng vai trò là "Seed" (hạt giống) ban đầu, nhưng chúng thiếu tính thực tiễn và chiều sâu lập luận cần thiết cho một trợ lý pháp lý cao cấp.

3. Thiết kế Prompt Tiến hóa (Evol-Instruct) chuyên biệt Pháp lý

Chúng ta sẽ sử dụng Llama 3.1 8B làm "Rewriter" để nâng cấp Seed Prompts. Điểm khác biệt ở đây là việc ép buộc cấu trúc IRAC theo đúng phương pháp luận của Giáo sư Ng (CSUN):

* Rule (Quy tắc): Phải là nguyên tắc chung, không chứa tên riêng hay tình tiết vụ việc.
* Application (Áp dụng): Phải phân tích tình tiết cụ thể dựa trên Rule.

In-Depth Evolving (5 Kỹ thuật nâng cao)

### 1. Constraint Addition (Thêm ràng buộc IRAC)
Mục tiêu của bạn là viết lại câu hỏi gốc sao cho phản hồi bắt buộc phải tuân thủ cấu trúc IRAC:
- Issue: Vấn đề pháp lý cụ thể dưới dạng câu hỏi.
- Rule: Trích dẫn nguyên tắc luật định chung (không dùng tên riêng).
- Application: Phân tích cách luật áp dụng vào tình huống thực tế.
- Conclusion: Kết luận ngắn gọn.

### 2. Deepening (Đi sâu vào ngoại lệ)
Hãy viết lại câu hỏi để yêu cầu người trả lời không chỉ nêu luật mà còn phải phân tích các trường hợp ngoại lệ (exceptions) hoặc các điều kiện loại trừ trách nhiệm dựa trên các tiền lệ tương tự Lewis v. State.

### 3. Concretizing (Cụ thể hóa tình huống - Case Study)
Hãy chuyển đổi chỉ thị lý thuyết thành một tình huống cụ thể. Sử dụng các thực thể như "Matthew (nhà thầu độc lập)" hoặc "Michelle và Jose (tranh chấp thuê nhà tại Tarrytown)" để mô phỏng các xung đột pháp lý thực tế.

### 4. Increased Reasoning Steps (Tăng bước lập luận)
Hãy yêu cầu mô hình giải thích logic từng bước, bắt đầu từ việc xác định sự kiện pháp lý, sau đó là sự tương tác giữa nhiều điều luật chồng chéo trước khi đưa ra phán quyết cuối cùng.

### 5. Complicating Input (Phức tạp hóa bằng dữ liệu cấu trúc)
Hãy viết lại câu hỏi bằng cách tích hợp thêm dữ liệu thực tế vào thẻ XML như sau:
<facts>
[Mô tả vụ việc mâu thuẫn giữa Hagan và Coca-Cola về dị vật trong đồ uống]
</facts>
Yêu cầu phân tích xem các tình tiết trên có cấu thành vi phạm hay không.


In-Breadth Evolving (1 Kỹ thuật mở rộng)

### 6. Mutation (Đột biến chủ đề ngách)
Dựa trên chủ đề pháp luật hiện tại, hãy tạo ra một câu hỏi hoàn toàn mới về một khía cạnh pháp lý ít phổ biến (long-tail topics) nhưng có cùng logic hệ thống, nhằm mở rộng phạm vi tri thức của bộ dữ liệu.


4. Xây dựng Bộ lọc Loại bỏ Lỗi (Instruction Eliminator)

Dữ liệu do LLM tự tạo thường chứa "nhiễu". Là một kiến trúc sư NLP, chúng ta không thể chỉ dựa vào độ dài văn bản mà phải sử dụng các độ đo ngữ nghĩa.

import re
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

def instruction_eliminator(original_p, evolved_p, response, threshold=0.95):
    # 1. Lọc rò rỉ thẻ kỹ thuật (Prompt Leakage)
    if any(tag in evolved_p for tag in ["#Rewritten Prompt#", "#Given Prompt#"]):
        return False

    # 2. Lọc từ chối (Refusal Filter) kèm RegEx
    refusal_patterns = [r"xin lỗi", r"không thể thực hiện", r"là một AI"]
    if any(re.search(p, response.lower()) for p in refusal_patterns) and len(response) < 100:
        return False

    # 3. Lọc trùng lặp ngữ nghĩa (Information Gain via Cosine Similarity)
    # Nếu Prompt mới quá giống Prompt cũ (>95%), nghĩa là không có sự tiến hóa
    vectorizer = TfidfVectorizer().fit_transform([original_p, evolved_p])
    similarity = cosine_similarity(vectorizer[0:1], vectorizer[1:2])[0][0]
    if similarity > threshold:
        return False

    # 4. Kiểm tra cấu trúc IRAC tối thiểu
    irac_tags = ["Vấn đề", "Quy tắc", "Áp dụng", "Kết luận"]
    if not all(tag in response for tag in irac_tags):
        return False

    return True


5. Mã Python Quy trình Tự động hóa Hoàn chỉnh (End-to-End Pipeline)

Sử dụng thư viện tenacity để xử lý cơ chế thử lại (Retry) khi API Local bị quá tải hoặc lỗi kết nối.

import openai
import json
import random
from tenacity import retry, stop_after_attempt, wait_exponential

client = openai.OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

class EvolPipeline:
    def __init__(self):
        self.techniques = [
            "Add Constraints", "Deepening", "Concretizing", 
            "Increased Reasoning", "Complicating Input", "Mutation"
        ]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def call_llm(self, messages, temp=0.7):
        response = client.chat.completions.create(
            model="meta-llama-3.1-8b-instruct",
            messages=messages,
            temperature=temp,
            stop=["<|eot_id|>"]
        )
        return response.choices[0].message.content

    def run_evolution(self, seed_dataset):
        for item in seed_dataset:
            tech = random.choice(self.techniques)
            # Bước 1: Tiến hóa Instruction
            evo_msg = [
                {"role": "system", "content": "Bạn là chuyên gia NLP Architect. Hãy viết lại chỉ thị sau."},
                {"role": "user", "content": f"Kỹ thuật: {tech}. Seed: {item['instruction']}"}
            ]
            evolved_p = self.call_llm(evo_msg, temp=0.8)

            # Bước 2: Sinh phản hồi chuẩn IRAC (Temperature thấp để tránh ảo tưởng)
            resp_msg = [
                {"role": "system", "content": "Bạn là Thẩm phán. Trả lời nghiêm ngặt theo IRAC (Issue, Rule, Application, Conclusion)."},
                {"role": "user", "content": evolved_p}
            ]
            final_resp = self.call_llm(resp_msg, temp=0.1)

            # Bước 3: Lọc và Lưu (Format Alpaca JSONL)
            if instruction_eliminator(item['instruction'], evolved_p, final_resp):
                self.save_data(evolved_p, final_resp)

    def save_data(self, instruction, output):
        record = {"instruction": instruction, "input": "", "output": output}
        with open("legal_evolved.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


6. Kinh nghiệm Tối ưu hóa và Xử lý Lỗi thực tế

Khi vận hành Evol-Instruct trên mô hình 8B, cần đặc biệt lưu ý các điểm sau để duy trì chất lượng:

* Instruction Drift (Trôi lệnh): Mô hình 8B có xu hướng "quên" định dạng XML hoặc IRAC nếu System Prompt quá dài. Giải pháp: Sử dụng Few-shot Prompting. Hãy cung cấp ví dụ về vụ án Lewis v. State (về định nghĩa "vận hành" xe khi say rượu) hoặc Hagan v. Coca-Cola (về "impact rule" trong tiêu thụ thực phẩm bẩn) ngay trong prompt để mô hình học theo mẫu lập luận.
* Temperature Strategy:
  * Evolution Phase: Dùng Temp cao (~0.9) để tạo ra các tình huống pháp lý lắt léo, mới lạ.
  * Answer Phase: Dùng Temp cực thấp (0.1) để đảm bảo mô hình không bịa đặt số hiệu điều luật hoặc nội dung pháp lý.
* Hallucination Pháp lý: Mô hình 8B có thể trích dẫn sai số hiệu văn bản luật Việt Nam. Quy trình kiểm tra chéo (Cross-check) bắt buộc phải được thực hiện bằng cách đối chiếu các số hiệu luật xuất hiện trong output với kho dữ liệu gốc vietnamese-legal-documents. Nếu không khớp, mẫu dữ liệu đó phải bị loại bỏ ngay lập tức.
* VRAM Management: Nếu gặp lỗi Out-of-Memory, hãy giới hạn context_length xuống 4096 hoặc 8192 thay vì sử dụng toàn bộ 128k context của Llama 3.1, vì các bài toán IRAC hiếm khi vượt quá ngưỡng này.

Việc áp dụng chặt chẽ quy trình này sẽ giúp xây dựng một bộ dữ liệu tinh hoa, sẵn sàng cho việc Fine-tuning mô hình ngôn ngữ chuyên biệt cho ngành luật tại Việt Nam.