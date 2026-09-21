# Kế hoạch xây dựng LƯU HÀNH

## Mục tiêu
Xây dựng website thông tin pháp luật Việt Nam theo hướng **Editorial Ink**, gồm trang chính giới thiệu dịch vụ và một trang trợ lý pháp lý AI riêng. Trợ lý hỗ trợ nhiều cuộc trò chuyện trong phiên hiện tại nhưng không lưu sau khi tải lại hoặc đóng trang.

## Trang chính `/`
- Giữ bố cục biên tập đã chọn: thanh điều hướng, tiêu đề lớn “Pháp luật, đọc được rõ ràng.”, các lĩnh vực tư vấn, quy trình hỗ trợ, lưu ý pháp lý và chân trang tối giản.
- Các nút “Mở trợ lý pháp lý” và “Hỏi trợ lý pháp lý” dẫn sang trang chatbot riêng thay vì nhúng khung chat trên trang chính.
- Nội dung tập trung vào pháp luật Việt Nam, dùng ngôn ngữ rõ ràng và không đưa ra số liệu, giá hoặc thông tin luật sư chưa được cung cấp.
- Tối ưu hiển thị cho máy tính và điện thoại, với chuyển động xuất hiện tiết chế và hỗ trợ chế độ giảm chuyển động.

## Trang trợ lý `/tro-ly/:threadId`
- Tạo không gian chat riêng theo cùng hệ thống màu sắc và kiểu chữ Editorial Ink.
- Hiển thị danh sách các cuộc trò chuyện tạm thời, nút tạo cuộc trò chuyện mới và địa chỉ riêng cho từng cuộc trò chuyện.
- Cho phép chuyển qua lại giữa các cuộc trò chuyện trong phiên; tải lại trang sẽ xóa nội dung nhưng giữ đúng mã cuộc trò chuyện đang mở để bắt đầu lại.
- Có trạng thái trống với câu hỏi gợi ý theo các nhóm: hợp đồng, lao động, đất đai và doanh nghiệp.
- Giữ ô nhập luôn sẵn sàng, hiển thị tin nhắn người dùng ngay khi gửi, trạng thái “Đang suy nghĩ…”, phản hồi dạng Markdown và nút dừng khi AI đang trả lời.
- Hiển thị rõ cảnh báo rằng nội dung chỉ mang tính tham khảo, không thay thế tư vấn chính thức của luật sư.

## Trợ lý AI
- Kích hoạt Lovable Cloud để chạy phần xử lý AI an toàn phía máy chủ; không tạo cơ sở dữ liệu hoặc đăng nhập vì lịch sử không được lưu.
- Dùng Lovable AI với mô hình mặc định `openai/gpt-6-astra`, trả lời dạng streaming bằng tiếng Việt.
- Gửi đầy đủ nội dung của cuộc trò chuyện hiện tại trong mỗi yêu cầu để AI giữ đúng ngữ cảnh.
- Thiết lập hướng dẫn hệ thống: ưu tiên pháp luật Việt Nam, nêu giới hạn thông tin, không bịa điều luật, khuyến nghị gặp luật sư khi tình huống có rủi ro cao hoặc thiếu dữ kiện.
- Hiển thị thông báo lỗi cụ thể cho thiếu cấu hình, hết tín dụng, giới hạn tốc độ hoặc lỗi dịch vụ; không tự động gửi lại các lỗi không thể thử lại.

## Giao diện và nền tảng kỹ thuật
- Áp dụng chính xác bảng màu, Anton/Inter/JetBrains Mono, nhịp lưới, đường kẻ và nút nhấn đỏ của phương án Editorial Ink bằng các biến giao diện dùng chung.
- Dùng các thành phần AI Elements cho danh sách tin nhắn, nội dung Markdown, trạng thái tải và khung nhập; chỉ tùy biến lớp trình bày để khớp thiết kế đã chọn.
- Tạo dấu hiệu nhận diện chữ “L” riêng cho LƯU HÀNH, không dùng biểu tượng AI chung chung.
- Thêm tiêu đề, mô tả và metadata chia sẻ riêng cho trang chính và trang trợ lý.

## Kiểm tra hoàn thiện
- Kiểm tra trang chính và luồng: mở trợ lý → tạo hai cuộc trò chuyện → gửi câu hỏi trong từng cuộc → chuyển đổi không lẫn nội dung.
- Kiểm tra tải lại sẽ xóa lịch sử đúng như yêu cầu và khởi tạo lại cuộc trò chuyện theo địa chỉ đang mở.
- Kiểm tra phản hồi AI thật, trạng thái đang tải/dừng, Markdown, cảnh báo pháp lý và thông báo lỗi.
- Kiểm tra giao diện ở kích thước máy tính và điện thoại, bảo đảm chữ, nút và danh sách hội thoại không chồng lấn.
