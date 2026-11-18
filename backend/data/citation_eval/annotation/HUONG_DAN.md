# Hướng dẫn gán nhãn trích dẫn (Citation Verification — D3)

Mỗi dòng là MỘT trích dẫn trong câu trả lời của hệ thống. Hai người gán nhãn ĐỘC LẬP
(mỗi người một file), không trao đổi trước khi xong.

Cột cần điền (Y / N / ?):

- `label_correct_document`: `resolved_document` có đúng là văn bản mà câu trả lời muốn trích không?
  `?` nếu câu trả lời không nói rõ văn bản.
- `label_article_exists`: Điều (và khoản, nếu có) được trích có tồn tại trong văn bản đó không?
  Đối chiếu `article_text`; nếu ghi "(không có trong KB)" thì tra văn bản gốc, không tra được thì `?`.
- `label_supports_claim`: nội dung `article_text` có hỗ trợ nhận định trong `sentence` không?
  `Y` = hỗ trợ trực tiếp; `N` = không hỗ trợ / nói chuyện khác; `?` = hỗ trợ một phần.

Không cần xét hiệu lực: hiệu lực lấy từ metadata, không phải phán đoán của người gán nhãn.
