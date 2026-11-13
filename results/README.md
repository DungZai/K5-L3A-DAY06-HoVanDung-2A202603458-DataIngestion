# Kết quả benchmark

- [selection.json](selection.json) ghi tiêu chí, số đo dev, cấu hình được chốt và fingerprint của dữ liệu cùng mã nguồn tại thời điểm chọn.
- [test_run.json](test_run.json) ghi số đo holdout và tham chiếu lần chốt dev.
- [retrieval_metrics.csv](retrieval_metrics.csv) tổng hợp Hit@1 và Evidence Hit@3 với tử số và tổng số câu của từng tập.
- [equivalent_evidence_review.csv](equivalent_evidence_review.csv) ghi các chunk đủ bằng chứng phát hiện khi đọc kết quả sau cả hai lượt. [reviewed_retrieval_metrics.csv](reviewed_retrieval_metrics.csv) cộng các nhãn này vào phép đo để kiểm tra độ nhạy với tiêu chí so khớp nguyên văn. Lượt chọn dev dùng số đo tự động đã chốt.
- [dev_traces.jsonl](dev_traces.jsonl) và [test_traces.jsonl](test_traces.jsonl) lưu câu hỏi, filter yêu cầu và filter thực sự áp dụng, đoạn gold, nội dung từng kết quả, score cosine và nhãn so khớp tự động.
- [index_stats.json](index_stats.json) ghi phiên bản runtime, phân bố độ dài chunk, thời gian ingest, chi phí API và kết quả kiểm tra nạp lại. B và C dùng chung index B.
- [coherence_samples.jsonl](coherence_samples.jsonl) lưu chunk được chọn cho 10 vị trí cố định trên mỗi cấu hình. Nhãn và lý do đọc mẫu nằm trong [coherence_audit.csv](coherence_audit.csv), [metadata_audit.csv](metadata_audit.csv) và [grounding_audit.csv](grounding_audit.csv). [audit_summary.json](audit_summary.json) tổng hợp các nhãn và tỷ lệ tuân thủ filter.
- [pipeline.log](pipeline.log) lưu các lượt kiểm tra và chạy. Lượt dev lúc 20:51 được dừng trong lúc nạp để cập nhật phần che thông tin minh họa và chuẩn hóa fingerprint giữa Windows và Linux. Lượt dev lúc 20:53 hoàn tất trên corpus đã chốt, trước khi truy xuất test.

Các trích đoạn sách trong các file trên thuộc *Pro Git*, ấn bản 2, và giữ giấy phép CC BY-NC-SA 3.0 Unported. [Ghi công và giấy phép](../data/LICENSE-ProGit.txt)
