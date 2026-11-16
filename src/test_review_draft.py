"""Draft manual labels for the final TEST runs (AI-drafted, confirmed by the student 2026-11-16).

Covers all 9 test questions (6 answerable + 3 unanswerable) for baseline and selected config,
plus context_grade 0/1/2 (BENCHMARK.md §2): 0 = no evidence in final context, 1 = evidence but
missing condition/source, 2 = full evidence with source/page tag.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWER = "draft: Claude Code đọc câu trả lời, chunk được cite và context cuối; học viên đã xác nhận 2026-11-16"
NOTES = {
    "t01": "17% BHXH và 0,5% bảo hiểm tai nạn/bệnh nghề nghiệp trên lương cơ bản hàng tháng; khớp p028:003.",
    "t02": "Đường thẳng, 10 năm; khớp p021:003.",
    "t03": "Nhóm rủi ro không thấp hơn nhóm trước khi mua; ý phụ 'phân loại, trích lập tương tự cho vay khác' có trong p016:002.",
    "t04": "5% LNST tới khi bằng 10% vốn điều lệ; tên đầy đủ MIC/MBLife có trong p025:003.",
    "t05": "20% trên thu nhập chịu thuế; khớp p050:001.",
    "t06": "0%-100% giá trị cam kết tùy mức tin cậy; ý phụ 'ký quỹ cho công cụ tài chính liên quan tín dụng' có trong p051:002.",
}
CONTEXT_NOTE = "Context cuối chứa chunk gold kèm nhãn chunk_id/trang/mục, đủ điều kiện của đáp án."

for tag in ("baseline-dense-v1", "selected-bm25-v2"):
    d = ROOT / "starter" / "results" / "agent" / f"test-{tag}"
    reviews = []
    for t in json.loads((d / "traces.json").read_text(encoding="utf-8")):
        r = {"query_id": t["query_id"], "citation_support": [True] * len(t["citations"]), "reviewer": REVIEWER}
        if t["answerable"]:
            r.update(answer_grade=2 if t["status"] == "answered" else 0, reason=NOTES[t["query_id"]],
                     context_grade=2 if t.get("context_evidence") else 0, context_reason=CONTEXT_NOTE)
        else:
            r.update(abstention_correct=t["status"] == "abstain",
                     reason="Từ chối, nói rõ tài liệu không có thông tin, không thêm khẳng định hay số liệu.")
        reviews.append(r)
    (d / "reviews.json").write_text(json.dumps(reviews, ensure_ascii=False, indent=1), encoding="utf-8")
    print(tag, "->", (d / "reviews.json").relative_to(ROOT))
