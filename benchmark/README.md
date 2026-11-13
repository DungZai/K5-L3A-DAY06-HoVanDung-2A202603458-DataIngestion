# Thiết kế benchmark

Bộ câu hỏi tiếng Anh khớp với ngôn ngữ của corpus Pro Git. [questions.json](questions.json) có 15 câu dev và 5 câu test, mỗi câu có đoạn trích xác minh trong đúng đơn vị nguồn sau chuẩn hóa. Tập test giữ riêng toàn bộ các mục `undoing`, `remote-branches`, `rerere`, `attributes` và `packfiles`. Mỗi câu dùng một mục nguồn khác nhau. Cả hai tập vẫn thuộc cùng một cuốn sách nên thuật ngữ và chủ đề có thể trùng nhau. Chốt câu hỏi, đoạn trích và tập chia trước khi chạy truy xuất.

Các câu q02, q06, q13 và q17 mô phỏng người đọc chọn phạm vi chương trước khi tìm kiếm. Trường `filter.section` ghi lựa chọn đó bằng slug chương có trong manifest. Các chương gồm nhiều mục nguồn để câu hỏi vẫn cần truy xuất đoạn bằng chứng trong phạm vi đã chọn. q17 thuộc tập test.

[coherence_anchors.json](coherence_anchors.json) lưu 10 vị trí thuộc các mục nguồn của tập dev. Mỗi vị trí có một đoạn trích ngắn xuất hiện duy nhất trên trang. Dùng cùng các vị trí này cho mọi cấu hình khi chấm mạch lạc.

Các đoạn trích thuộc *Pro Git, Second Edition* và giữ giấy phép CC BY-NC-SA 3.0 Unported. [Nguồn và giấy phép](../data/LICENSE-ProGit.txt)
