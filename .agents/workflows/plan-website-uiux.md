# Kế hoạch xây dựng LƯU HÀNH

## Mục tiêu
Xây dựng website thông tin pháp luật Việt Nam theo hướng **Editorial Ink**, gồm trang chính giới thiệu dịch vụ và một trang trợ lý pháp lý AI riêng. Trợ lý hỗ trợ nhiều cuộc trò chuyện trong phiên hiện tại nhưng không lưu sau khi tải lại hoặc đóng trang.

## Trang chính `/`
- Giữ bố cục biên tập đã chọn: thanh điều hướng, tiêu đề lớn “Pháp luật, đọc được rõ ràng.”, các lĩnh vực tư vấn, quy trình hỗ trợ, lưu ý pháp lý và chân trang tối giản.
- Các nút “Mở trợ lý pháp lý” và “Hỏi trợ lý pháp lý” dẫn sang trang chatbot riêng thay vì nhúng khung chat trên trang chính.
- Nội dung tập trung vào pháp luật Việt Nam, dùng ngôn ngữ rõ ràng và không đưa ra số liệu, giá hoặc thông tin luật sư chưa được cung cấp.
- Tối ưu hiển thị cho máy tính và điện thoại, với chuyển động xuất hiện tiết chế và hỗ trợ chế độ giảm chuyển động.

## Trang trợ lý `/tro-ly/:threadId`
- Tạo không gian chat riêng theo cùng hệ thống màu sắc và kiểu chữ Editorial Ink (hỗ trợ các giao diện Clean Slate, Dark Slate, Warm Ivory, Grid Pattern).
- Hiển thị danh sách các cuộc trò chuyện, hỗ trợ ghim (Pin), đổi tên trực tiếp, và phân biệt số lượng nhánh thảo luận con (Sub-thread Branch).
- **Phân tách dữ liệu người dùng (User Data Isolation)**: Tích hợp Supabase Auth với Row Level Security (RLS) trên bảng `threads` và `messages`, đảm bảo mỗi người dùng chỉ xem và thao tác trên lịch sử tin nhắn của chính mình.
- **Nút xóa nhanh từng tin nhắn (Quick Message Delete)**: Nút biểu tượng thùng rác ở góc trên bên phải mỗi card tin nhắn (cả User và AI) giúp người dùng xóa bỏ tin nhắn thừa trực tiếp mà không cần vào menu cài đặt.
- **Nhánh thảo luận con (Sub-thread / Deep Dive Branching)**:
  + Ở mỗi câu trả lời của AI có nút "Mở nhánh thảo luận" (hoặc hiển thị số phản hồi con đã có).
  + Khi bấm mở, kích hoạt **Right Panel (Tab nhánh phụ)** chiếm khoảng 1/3 màn hình ở phía bên phải.
  + **Tương tác kéo co giãn (Drag-to-resize)**: Cho phép người dùng kéo thả thanh điều khiển giữa hai màn hình để mở rộng độ rộng tab, hoặc bấm nút Maximize/Minimize để phóng to/thu nhỏ nhanh.
  + Right Panel hiển thị: Trích đoạn câu trả lời gốc làm ngữ cảnh, danh sách thảo luận sâu dạng Markdown, và ô nhập câu hỏi riêng biệt với hiệu ứng streaming mượt mà.
- Trạng thái trống với 4 nhóm câu hỏi mẫu định hướng pháp lý (hợp đồng, lao động, đất đai, doanh nghiệp).
- Hiển thị rõ cảnh báo rằng nội dung chỉ mang tính tham khảo, không thay thế tư vấn chính thức của luật sư.
- Tích hợp Modal Hồ sơ người dùng (Profile Modal) cho phép tải ảnh đại diện lên Supabase Storage và nút "Đăng xuất tài khoản" tiện lợi.

## Trợ lý AI & Backend Hybrid RAG
- Kết nối FastAPI Backend với kiến trúc Hybrid RAG: Dense Retrieval (Qdrant), Sparse Retrieval (BM25), Knowledge Graph Expansion (Neo4j) và Cross-Encoder Reranker (bge-reranker-large).
- Stage 1 Query Evolution hỗ trợ viết lại câu hỏi theo chuẩn pháp lý trước khi tra cứu.
- Hỗ trợ kết nối linh hoạt mô hình ngôn ngữ lớn cục bộ qua LM Studio / Ollama (ví dụ: `meta-llama-3.1-8b-instruct`, `Qwen2.5-VL-3B-Instruct-GGUF`) thông qua cấu hình `backend/.env`.
- Developer Verbose Mode: Cho phép mở xem chi tiết Top-K tài liệu pháp lý trích dẫn, điểm số rerank, số hiệu điều luật và thời gian thực thi từng giai đoạn của pipeline.

## Giao diện và nền tảng kỹ thuật
- Áp dụng chính xác bảng màu, Anton/Inter/JetBrains Mono, nhịp lưới, đường kẻ và nút nhấn của phương án Editorial Ink.
- Hỗ trợ giao diện sáng / tối (Night Mode) và các theme thẩm mỹ cao.
- Thiết kế bố cục 3 cột linh hoạt: Sidebar trái (Danh sách hội thoại) — Main Panel (Cuộc trò chuyện chính) — Right Panel (Nhánh thảo luận sâu resizable).
- Tạo dấu hiệu nhận diện chữ “L” riêng cho LƯU HÀNH.

## Kiểm tra hoàn thiện
- Kiểm tra kết nối API backend không bị chặn CORS giữa Frontend Vite (port 5173) và Backend FastAPI (port 8000).
- Kiểm tra tính năng kéo co giãn thanh trượt Right Panel mượt mà, không giật lag.
- Kiểm tra tính năng xóa tin nhắn trên từng card hoạt động tức thì.
- Kiểm tra phân quyền RLS Supabase: chuyển đổi tài khoản người dùng đảm bảo không thấy tin nhắn của tài khoản khác.
- Kiểm tra đăng xuất tài khoản từ Profile Modal chuyển hướng an toàn về trang chủ.

