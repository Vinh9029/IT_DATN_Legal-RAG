---
description: Xây dựng RAG nâng cao cho bài toán hỏi đáp Pháp Lý (Legal) ở Việt Nam
---

# Tổng quan sƠ ĐỒ KIẾN TRÚC HỆ THỐNG (PIPELINE ARCHITECTURE)
                            [LUỒNG NGOẠI TUYẾN - OFFLINE]
   ┌────────────────────────────────────────────────────────────────────────────┐
   │ 1.03M Relationships [7] ──► Xây dựng Đồ thị Tri thức Pháp luật (Neo4j)   │
   │ 171k Documents [7]  ──► Trích xuất thực thể (PhoBERT) [8] & Tạo Embeddings│
   │ WizardLM Evol-Instruct (Constraint) [1] ──► Tạo bộ 100k+ IRAC Instruct-Data│
   │ Fine-tuning LLM (ViAn/PhoGPT/LLaMA-3) ──► LLM Chuyên gia Pháp luật (IRAC)   │
   └────────────────────────────────────────────────────────────────────────────┘

                             [LUỒNG TRỰC TUYẾN - ONLINE]

                              [User Query (Câu hỏi thô)]
                                          │
                                          ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │ STAGE 1: PROMPT EVOLUTION & CONSTRAINT ADDITION                            │
   │ (Sử dụng LLM nhỏ làm Prompt Rewriter theo mẫu WizardLM Example 3.1)        │
   │  - Phân tích tình huống ngầm định từ câu hỏi thô.                           │
   │  - Ép buộc bộ khung lập luận pháp lý IRAC làm ràng buộc cứng.             │
   └────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                         [Evolved Query (IRAC-Structured)]
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
   ┌─────────────────────────────┐                 ┌─────────────────────────────┐
   │ STAGE 2A: Dense Search      │                 │ STAGE 2B: Sparse Search     │
   │ (Vector Embedding - PhoBERT)│                 │ (Từ khóa chính xác - BM25)  │
   │  - Tìm quan hệ ngữ nghĩa.   │                 │  - Tìm điều luật, số hiệu.  │
   └─────────────────────────────┘                 └─────────────────────────────┘
                  │                                               │
                  └───────────────────────┬───────────────────────┘
                                          ▼
                               [Rank Fusion (RRF)] ──► Top-K Documents
                                          │
                                          ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │ STAGE 3: LEGAL GRAPH EXPANSION (Khai thác bảng relationships) [9, 10]    │
   │  - Duyệt các đỉnh liên kết: Sửa đổi, bổ sung, hướng dẫn thi hành (Nghị định)│
   │  - Kiểm tra trạng thái hiệu lực từ Metadata (Còn/Hết hiệu lực) [11]        │
   └────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                             [Enriched Context Pool]
                                          │
                                          ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │ STAGE 4: CROSS-ENCODER RE-RANKING                                          │
   │  - Sắp xếp lại độ liên quan của toàn bộ các văn bản luật thu được.         │
   └────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                              [Final Context Window]
                                          │
                                          ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │ STAGE 5: GENERATOR (Fine-tuned Legal LLM)                                  │
   │  - Kết hợp Context + Evolved Query để sinh văn bản.                        │
   │  - Đầu ra bắt buộc trả lời chi tiết theo cấu trúc IRAC chuẩn mực.          │
   └────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                             [Ý KIẾN TƯ VẤN PHÁP LÝ (IRAC)]

---
# Phần thực hiện
## Cải tiến phần Prompt Instruction sử dụng Phương pháp Evol-Instruct của WizardLM (https://arxiv.org/pdf/2304.12244) tối ưu sức mạnh suy luận của LLM để tự động nâng cấp độ khó và đa dạng hóa tập câu lệnh. 

## Để tự động hóa quy trình này, xây dựng 4 thành phần cốt lõi sau:
1. Bộ câu hỏi gốc (Seed Prompts): Thu thập khoảng 100 - 1000 câu hỏi pháp lý đơn giản ban đầu bằng tiếng Việt. Bạn có thể tự viết hoặc trích lọc từ các tình huống pháp lý phổ biến trong tập dữ liệu vietnamese-legal-documents của Thịnh Ngô '''(from datasets import load_dataset
ds = load_dataset("th1nhng0/vietnamese-legal-documents", "content")'''

2. Bộ mẫu Prompt Tiến hóa (Evolution Templates) -sử dụng model meta-llama-3-8b-instruct trong LM Studio (http://127.0.0.1:1234): Dựng sẵn các template đóng vai trò Prompt Rewriter (để tiến hóa sâu) hoặc Prompt Creator (để tiến hóa rộng). Dựa trên nghiên cứu WizardLM, bạn cần cấu hình các prompt này để LLM thực hiện các tác vụ sau
   + Add Constraints: Bổ sung các ràng buộc thực tế(Ở đây bạn ép LLM thêm điều kiện: "Bắt buộc người trả lời phải lập luận chặt chẽ theo cấu trúc IRAC trong pháp ").
   + Deepening: Tăng chiều sâu của câu hỏi
   + Concretizing: Thay thế các khái niệm luật chung chung bằng các tình tiết giả định cụ thể
   + Increased Reasoning Steps: Đòi hỏi suy luận giải quyết vấn đề nhiều bước
   + Complicate Input: Chèn thêm dữ liệu phức tạp (như JSON, XML, bảng dữ liệu vụ việc)
   + In-Breadth Evolving (Mutation): Sinh ra câu hỏi hoàn toàn mới có độ hiếm cao (long-tailed) cùng lĩnh vực

3. Bộ lọc loại bỏ thất bại (Instruction Eliminator): Khi LLM tự viết lại prompt, sẽ có những trường hợp thất bại.Bạn cần viết code để tự động loại bỏ các prompt lỗi nếu rơi vào các trường hợp sau:
  + Prompt viết lại không mang lại thông tin mới so với prompt gốc
  + Mô hình từ chối trả lời (sinh ra phản hồi ngắn chứa từ khóa từ chối như "xin lỗi", "tôi không thể").
  + Mô hình sinh ra phản hồi chỉ chứa dấu câu hoặc stop words.
  + Mô hình bị lặp từ khóa lập trình (copy y nguyên các nhãn như #Given Prompt#, #Rewritten Prompt# vào trong nội dung câu hỏi mới)

4 Script Python điều khiển: Sử dụng thư viện requests để gọi API từ LM Studio, xử lý vòng lặp tiến hóa và lưu dữ liệu thu được dưới dạng file .jsonl chứa các cặp {"instruction": "...", "output": "..."} chuẩn chỉnh

## Fine-tuning LLM chuyên gia pháp luật (IRAC)
1. Unsloth LoRA để fine-tuning model meta-llama-3-8b-instructmeta-llama-3-8b-instruct.