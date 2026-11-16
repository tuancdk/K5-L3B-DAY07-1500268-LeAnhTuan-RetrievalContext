"""Draft manual labels for the dev agent runs (AI-drafted, confirmed by the student 2026-11-16).

Each label: answer_grade 0/1/2 (answerable), citation_support (one bool per citation, in trace order),
abstention_correct (unanswerable). Reasons cite what was checked in the chunk text.
Writes starter/results/agent/dev-<tag>/reviews.json.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OK = "Đúng và đủ so với đáp án; chunk được cite chứa evidence gold."
REVIEWER = "draft: Claude Code đọc câu trả lời + chunk được cite; học viên đã xác nhận 2026-11-16"

COMMON = {f"d{i:02d}": (2, OK) for i in range(1, 17)}
LABELS = {
    "dense": {**COMMON,
        "d01": (0, "Từ chối nhầm: 3 lượt search gần như cùng query, dense không lấy được tr.9."),
        "d02": (0, "Từ chối nhầm: query lặp lại, không lấy được tr.10."),
        "d08": (1, "Nhóm nợ xấu đúng, nhưng chỉ cite bảng phân loại dư nợ tr.31: bảng có số liệu từng nhóm "
                   "(số liệu đúng) nhưng không nói các nhóm này là nợ xấu -> thiếu evidence cho ý chính."),
        "d13": (0, "Không nêu tiêu chí (≤11% quyền biểu quyết, chưa niêm yết); chỉ liệt kê loại đầu tư và nói sai "
                   "521.748 là số 'đã trừ dự phòng' (tr.36: 521.748 là trước dự phòng, sau dự phòng 430.520)."),
        "d15": (0, "Từ chối nhầm: tìm 2 lần cùng query 'dự phòng chung mức lập', không thấy tr.15."),
    },
    "bm25": {**COMMON,
        "d13": (1, "Tiêu chí ≤11% và chưa niêm yết đúng, nhưng thêm ý sai: 521.748 'sau khi trừ dự phòng' "
                   "(tr.36: đó là số trước dự phòng)."),
    },
    "rerank": dict(COMMON),
    # --- improvement runs: học viên đã xác nhận 2026-11-16 ---
    "dense-v2": {**COMMON,
        "d01": (0, "Từ chối nhầm: query đã đổi nhưng dense vẫn không lấy được tr.9."),
        "d08": (1, "Liệt kê tiêu chí nợ nhóm 5 (tr.15) như thể đó là các 'nhóm nợ xấu'; không nêu nhóm 3, 4 và "
                   "không có evidence cho định nghĩa nợ xấu (p013 không được lấy)."),
        "d13": (1, "Số liệu đúng (521.748 trước dự phòng - đã sửa so với v1) nhưng vẫn không nêu tiêu chí ≤11%, chưa niêm yết."),
        "d15": (0, "Từ chối nhầm: dense không lấy được tr.15."),
    },
    "bm25-v2": dict(COMMON),
    "rerank-v2": dict(COMMON),
    "dense-v2fn": {**COMMON,
        "d01": (0, "Từ chối nhầm: dense không lấy được tr.9."),
        "d02": (0, "Từ chối nhầm (v2 không filter trả lời đúng): dense không lấy được tr.10 ở lần chạy này."),
        "d08": (1, "Nói nợ xấu là nhóm 3 trở lên, liệt kê tiêu chí nhóm 3 và 5 nhưng bỏ sót nhóm 4 trong phần 'cụ thể'; "
                   "chunk được cite (tr.14, tr.15) không nói các nhóm này là nợ xấu."),
        "d13": (1, "Như dense-v2: số liệu đúng, thiếu tiêu chí."),
        "d15": (0, "Từ chối nhầm dù đã lọc section chính sách kế toán: dense vẫn không xếp tr.15 vào top-3."),
    },
    "bm25-v2fn": dict(COMMON),
    "rerank-v2fn": dict(COMMON),
}
DRAFT_TAGS = {"dense-v2", "bm25-v2", "rerank-v2", "dense-v2fn", "bm25-v2fn", "rerank-v2fn"}
REVIEWER_DRAFT = "draft: Claude Code đọc câu trả lời + chunk được cite; học viên đã xác nhận 2026-11-16"
CITE_FALSE = {  # (tag, qid) -> indexes of citations that do NOT support the answer
    ("dense", "d08"): {0}, ("dense", "d13"): {0, 1}, ("bm25", "d13"): {1},
    ("dense-v2", "d08"): {0}, ("dense-v2", "d13"): {1},
    ("dense-v2fn", "d08"): {0, 1}, ("dense-v2fn", "d13"): {1},
    ("rerank-v2", "dn03"): {0},
}
CITE_NOTE = {
    ("dense", "d13"): "p036 không hỗ trợ ý 'đã trừ dự phòng'; p019 (định nghĩa) không được dùng trong câu trả lời.",
    ("bm25", "d13"): "p036 không hỗ trợ ý 'sau khi trừ dự phòng'.",
    ("bm25", "d06"): "Citation 2 (p015, dự phòng chung 0,75% trừ tiền gửi/cho vay TCTD) hỗ trợ ý không trích dự phòng chung.",
    ("rerank", "d08"): "Citation 2 (p015, tiêu chí nhóm 5) hỗ trợ các ví dụ nợ xấu bổ sung.",
    ("rerank", "d13"): "p036 hỗ trợ 521.748 trước dự phòng; p019 hỗ trợ tiêu chí.",
}
ABSTAIN = {
    ("rerank", "dn03"): (False, "status=answered (abstain=false). Nội dung nói báo cáo không có lãi suất tiết kiệm 12 tháng "
                                "rồi bổ sung lãi suất chứng chỉ tiền gửi 4,70-11,18% có cite tr.44 (đúng với tài liệu, "
                                "không bịa) - nhưng không gắn cờ từ chối nên không tính là abstention đúng."),
    ("rerank-v2", "dn03"): (False, "status=answered và khẳng định sai: 'lãi suất tiết kiệm 12 tháng nằm trong khoảng "
                                   "4,70-11,18%' - đó là lãi suất chứng chỉ tiền gửi (tr.44), không phải tiết kiệm. "
                                   "Prompt v2 (quy tắc 9) không sửa được, còn tệ hơn v1."),
    ("rerank", "dn02"): (True, "Từ chối; ý phụ 'có dư nợ cho vay và tiền gửi của cá nhân' đúng (tr.32, tr.43)."),
}

for tag, labels in LABELS.items():
    d = ROOT / "starter" / "results" / "agent" / f"dev-{tag}"
    traces = json.loads((d / "traces.json").read_text(encoding="utf-8"))
    reviews = []
    for t in traces:
        qid, cites = t["query_id"], t["citations"]
        bad = CITE_FALSE.get((tag, qid), set())
        r = {"query_id": qid, "citation_support": [i not in bad for i in range(len(cites))], "reviewer": REVIEWER_DRAFT if tag in DRAFT_TAGS else REVIEWER}
        if t["answerable"]:
            grade, reason = labels[qid]
            if t["status"] == "abstain":
                grade = 0
            r.update(answer_grade=grade, reason=reason)
        else:
            correct, reason = ABSTAIN.get((tag, qid), (t["status"] == "abstain",
                                          "Từ chối, nói rõ không đủ bằng chứng, không thêm khẳng định."))
            r.update(abstention_correct=correct, reason=reason)
        if (tag, qid) in CITE_NOTE:
            r["citation_note"] = CITE_NOTE[(tag, qid)]
        reviews.append(r)
    (d / "reviews.json").write_text(json.dumps(reviews, ensure_ascii=False, indent=1), encoding="utf-8")
    print(tag, "->", (d / "reviews.json").relative_to(ROOT))
