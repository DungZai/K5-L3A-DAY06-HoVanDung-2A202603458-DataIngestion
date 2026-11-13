# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

## Chạy bài làm

Bài làm sử dụng 45 mục nguồn tiếng Anh từ *Pro Git*, ấn bản 2, đã chuẩn hóa và lưu tại `data/corpus.jsonl`. [Manifest](data/manifest.json) ghi snapshot, URL, giấy phép và SHA-256 của từng mục. [Giấy phép corpus](data/LICENSE-ProGit.txt) áp dụng cho dữ liệu và các trích đoạn trong benchmark và trace. Các câu hỏi tiếng Anh được lưu sẵn trong [benchmark](benchmark/questions.json).

Từ thư mục gốc, với Python 3.14, chạy các lệnh PowerShell sau. Cần mạng lúc cài thư viện và tải model lần đầu. Qdrant chạy nhúng và lưu trên đĩa, ONNX Runtime chạy embedding trên CPU.

```powershell
python -m venv .venv
$labPython = ".\.venv\Scripts\python.exe"
& $labPython -m pip install -r starter/requirements.txt
& $labPython -m starter.src.embeddings
& $labPython -m starter.src.run --phase validate
& $labPython -m starter.src.run --phase dev
Get-Content results/selection.json
& $labPython -m starter.src.run --phase test
& $labPython -m starter.src.audit
```

Môi trường đã kiểm chứng là Windows với Python 3.14.8. Trên macOS/Linux có wheel ONNX Runtime tương thích, dùng `./.venv/bin/python` thay cho `& $labPython` và `cat` thay cho `Get-Content`. Khi cần tái tạo corpus từ snapshot đã ghi, chạy `python data/build_corpus.py` từ thư mục gốc.

- `validate` kiểm tra nội dung theo manifest, câu hỏi, gold evidence và các vị trí audit đã chốt.
- `dev` tạo hai index vật lý trong `.lab-cache/qdrant/`, kiểm tra nạp lại, truy xuất top-3 trên dev và ghi lựa chọn vào `results/selection.json`. B và C dùng chung index. C chỉ áp dụng filter `section` được cung cấp trong câu hỏi. Tiêu chí chọn trong [cấu hình](artifacts/strategies.json) ưu tiên Evidence Hit@3, sau đó Hit@1, rồi thứ tự A/B/C.
- `test` kiểm tra dữ liệu, code và runtime khớp lần chốt dev, sau đó đo cả ba cấu hình trên holdout. Sau một lượt dev mới, chạy tiếp test để cập nhật bộ kết quả. Bảng tổng hợp và trace dev/test nằm trong [results](results/).
- `audit` tổng hợp các nhãn định tính đã lưu. Nếu đổi cấu hình hoặc dữ liệu, hãy đọc lại các mẫu và cập nhật nhãn trước khi tổng hợp.

Kết quả, phân tích lỗi và các giới hạn được ghi trong [báo cáo cá nhân](report/individual/2A202603458_HoVanDung.md).

## Đề bài

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

### Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

### 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

### 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

### 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

### Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.
