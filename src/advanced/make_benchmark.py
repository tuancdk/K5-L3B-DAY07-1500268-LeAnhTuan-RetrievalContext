"""Source of truth for the advanced benchmark -> advanced/benchmark.json (+ validation).

Every answer below was checked against the rendered ORIGINAL page (not the model description).
Schema per question:
  id, split, group (bang | anh_so_do | bieu_do | multi_hop | text | thieu_bang_chung), question,
  answerable, expected_answer, required (facts that must ALL appear for "đạt"),
  evidence: list of groups; each group = list of alternative locations (page = printed page,
            pdf_page, kind, locator, quote). A pass needs >= 1 cited location from EVERY group.
  calculation / unit (if any), note.
Unanswerable: expected_behavior, absence_reason, absent_terms, near_topic_pages.

    python -m src.advanced.make_benchmark          # write + validate
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf

from .extract import PDF, ROOT, halves

OUT = ROOT / "advanced" / "benchmark.json"


def E(page, kind, locator, quote):
    return {"page": page, "pdf_page": page // 2 + 1, "kind": kind, "locator": locator, "quote": quote}


def Q(id, split, group, question, answer, required, evidence, **kw):
    return {"id": id, "split": split, "group": group, "question": question, "answerable": True,
            "expected_answer": answer, "required": required, "evidence": evidence, **kw}


def U(id, split, question, reason, terms, near):
    return {"id": id, "split": split, "group": "thieu_bang_chung", "question": question, "answerable": False,
            "expected_behavior": "search_and_abstain", "absence_reason": reason, "absent_terms": terms,
            "near_topic_pages": near}


QUESTIONS = [
    # ============================== DEV ==============================
    # --- bảng
    Q("ad01", "dev", "bang", "Theo bảng chỉ tiêu kết quả hoạt động kinh doanh năm 2025, kế hoạch CIR là bao nhiêu và MB thực hiện được bao nhiêu?",
      "Kế hoạch CIR ≤30%; thực hiện 29,1% (Hoàn thành).", ["≤30%", "29,1%"],
      [[E(59, "table", "Bảng chỉ tiêu KQKD, dòng 9 CIR, cột Kế hoạch 2025 / Thực hiện 2025", "9 | CIR | ≤30% | 29,1% | - | Hoàn thành")]]),
    Q("ad02", "dev", "bang", "Theo lịch sử trả cổ tức bằng tiền mặt, cổ tức tiền mặt cho năm 2016 có tỷ lệ bao nhiêu và được thanh toán ngày nào?",
      "6%, thanh toán ngày 08/03/2017 (ngày GDKHQ 23/02/2017).", ["6%", "08/03/2017"],
      [[E(97, "table", "Lịch sử trả cổ tức bằng tiền mặt, dòng Năm 2016", "2016 | 6% | Tiền mặt | 23/02/2017 | 08/03/2017")]]),
    Q("ad03", "dev", "bang", "Theo bảng quản lý nước tiêu thụ, tổng lượng nước MB sử dụng năm 2025 là bao nhiêu và thay đổi thế nào so với 2024?",
      "28.664 (năm 2024: 29.711), giảm 4%.", ["28.664", "giảm 4%"],
      [[E(185, "table", "Quản lý nước tiêu thụ, dòng Tổng lượng nước sử dụng", "Tổng lượng nước sử dụng | 29.711 | 28.664 | (4%)")]],
      note="Bảng không ghi đơn vị cho dòng này (cường độ ghi m3/người); không yêu cầu đơn vị."),
    Q("ad04", "dev", "bang", "MB sở hữu bao nhiêu phần trăm Công ty Cổ phần Chứng khoán MB (MBS) và vốn điều lệ của MBS là bao nhiêu?",
      "MB sở hữu 66,76%; vốn điều lệ MBS 6.587,27 tỷ đồng.", ["66,76%", "6.587,27 tỷ"],
      [[E(80, "table", "Bảng thông tin cơ bản công ty con, dòng MBS", "Công ty Cổ phần Chứng khoán MB (MBS) | Công ty con | ... | 6.587,27 tỷ đồng | 66,76%")]]),
    # --- ảnh, sơ đồ
    Q("ad05", "dev", "anh_so_do", "Trong sơ đồ giá trị cốt lõi của MB, giá trị nào được diễn giải là \"Nhanh chóng – Chính xác – Sáng tạo\"?",
      "Thực thi.", ["Thực thi"],
      [[E(19, "diagram", "Sơ đồ Tầm nhìn, sứ mệnh và giá trị cốt lõi, nhánh dưới bên phải", "Thực thi – Nhanh chóng – Chính xác – Sáng tạo")]]),
    Q("ad06", "dev", "anh_so_do", "Theo dòng thời gian các mốc phát triển của MB, năm 2025 MB vinh dự đón nhận những huân chương nào?",
      "Huân chương Bảo vệ Tổ quốc hạng Nhất và Huân chương Lao động hạng Ba.", ["Bảo vệ Tổ quốc hạng Nhất", "Lao động hạng Ba"],
      [[E(21, "diagram", "Dòng thời gian, mốc 2025 (cột phải, cuối)", "MB vinh dự đón nhận Huân chương Bảo vệ Tổ quốc hạng Nhất và Huân chương Lao động hạng Ba.")]]),
    Q("ad07", "dev", "anh_so_do", "Trong sơ đồ quy trình quản lý rủi ro, nhóm \"Đánh giá rủi ro (2)\" gồm những bước nào?",
      "Nhận dạng (2.1), Đo lường (2.2) và Theo dõi (2.3).", ["Nhận dạng", "Đo lường", "Theo dõi"],
      [[E(41, "diagram", "Sơ đồ Quy trình Quản lý rủi ro, khung giữa 'Đánh giá rủi ro (2)'", "Nhận dạng (2.1) / Đo lường (2.2) / Theo dõi (2.3)")]]),
    # --- biểu đồ
    Q("ad08", "dev", "bieu_do", "Theo biểu đồ cho vay phân khúc KHCN, dư nợ cho vay KHCN năm 2025 là bao nhiêu?",
      "444.841 (năm 2024: 336.936; 2023: 277.720).", ["444.841"],
      [[E(64, "bar_chart", "Biểu đồ 'Cho vay phân khúc KHCN', cột 2025", "2023: 277.720; 2024: 336.936; 2025: 444.841")]]),
    Q("ad09", "dev", "bieu_do", "Theo biểu đồ phân loại nhân sự theo độ tuổi, năm 2025 MB có bao nhiêu nhân sự dưới 35 tuổi và tăng bao nhiêu so với 2024?",
      "9.182 người (2024: 8.671), tăng 6%.", ["9.182", "6%"],
      [[E(77, "bar_chart", "Biểu đồ 'Phân loại theo độ tuổi', nhóm Dưới 35 tuổi", "2024: 8.671; 2025: 9.182; ↑6% so với 2024"),
        E(188, "table", "Bảng Phát triển nguồn nhân lực, dòng Dưới 35 tuổi", "Dưới 35 tuổi | 8.671 | 9.182 | 6%")]]),
    Q("ad10", "dev", "bieu_do", "Theo biểu đồ mức độ biến động tỷ giá USD/VND, mức biến động năm 2025 là bao nhiêu và dự báo 2026 là bao nhiêu?",
      "2025: 3,2%; dự báo 2026: 3,4%.", ["3,2", "3,4"],
      [[E(102, "bar_chart", "Biểu đồ 'Mức độ biến động tỷ giá USD/VND (%)', cột 2025 và 2026F", "2025: 3,2; 2026F: 3,4")]]),
    Q("ad11", "dev", "bieu_do", "Theo biểu đồ so sánh tỷ lệ CASA các ngân hàng năm 2025, CASA của MBB là bao nhiêu và đứng thứ mấy?",
      "37,8%, cao nhất (thứ 1) trong nhóm so sánh; TCB thứ hai với 35,9%.", ["37,8", "thứ 1"],
      [[E(108, "combo_chart", "Biểu đồ 'Tỷ lệ CASA', cột MBB (ngoài cùng trái)", "MBB 37,8 | TCB 35,9 | VCB 35,4 | ...")]]),
    # --- multi-hop
    Q("ad12", "dev", "multi_hop", "CIR năm 2025 của MB có đạt kế hoạch không, và theo biểu đồ so sánh CIR các ngân hàng thì ngân hàng nào có CIR thấp nhất?",
      "Có: thực hiện 29,1% so với kế hoạch ≤30%. Ngân hàng có CIR thấp nhất trong biểu đồ là VPB (25,0%); MBB đứng thứ 2.",
      ["29,1%", "≤30%", "VPB", "25,0"],
      [[E(59, "table", "Bảng chỉ tiêu KQKD, dòng 9 CIR", "CIR | ≤30% | 29,1% | Hoàn thành")],
       [E(111, "combo_chart", "Biểu đồ 'Tỷ lệ chi phí trên thu nhập (CIR)', cột VPB", "VPB 25,0 | MBB 29,1 | CTG 30,4 ...")]]),
    Q("ad13", "dev", "multi_hop", "Trong năm MB niêm yết cổ phiếu MBB trên Sở giao dịch chứng khoán TP.HCM, MB chi trả cổ tức tiền mặt những đợt nào (tỷ lệ và ngày thanh toán)?",
      "Năm niêm yết là 2011; cổ tức tiền mặt năm 2011 có hai đợt: 12% (thanh toán 23/12/2011) và 3% (thanh toán 15/03/2012).",
      ["2011", "12%", "3%"],
      [[E(21, "diagram", "Dòng thời gian, mốc 2011", "2011 MB đã thực hiện thành công việc niêm yết cổ phiếu MBB trên Sở giao dịch chứng khoán TP.HCM.")],
       [E(97, "table", "Lịch sử trả cổ tức bằng tiền mặt, 2 dòng Năm 2011", "2011 | 12% | ... | 23/12/2011; 2011 | 3% | ... | 15/03/2012")]]),
    Q("ad14", "dev", "multi_hop", "Số lượng khách hàng MB thực hiện năm 2025 là bao nhiêu và theo biểu đồ kế hoạch của HĐQT, mục tiêu khách hàng năm 2026 cao hơn bao nhiêu?",
      "2025: 35 triệu khách hàng; mục tiêu 2026: 40 triệu, tức cao hơn 5 triệu khách hàng (~14,3%).",
      ["35 triệu", "40 triệu", "5 triệu"],
      [[E(59, "table", "Bảng chỉ tiêu KQKD, dòng 10 Số lượng khách hàng", "Số lượng khách hàng | 35 triệu | 35 triệu | 16,7% | Hoàn thành"),
        E(120, "table", "Bảng số liệu riêng ngân hàng, dòng Số lượng khách hàng", "Số lượng khách hàng | 35 triệu | 30,2 triệu")],
       [E(134, "bar_chart", "Kế hoạch và định hướng HĐQT 2026, ô 'Khách hàng (triệu KH)'", "2024: 30; 2025: 35; 2026: 40")]],
      calculation="40 − 35 = 5 triệu; 5/35 ≈ 14,3%"),
    # --- text
    Q("ad15", "dev", "text", "Năm 2025 MB tuyển mới bao nhiêu nhân sự?",
      "2.856 CBNV.", ["2.856"],
      [[E(77, "text", "Chính sách nhân sự trong năm 2025, gạch đầu dòng", "Số lượng nhân sự tuyển mới trong năm 2025: 2.856 CBNV")]]),
    Q("ad16", "dev", "text", "Với bài dự thi nào và tập trung vào giá trị cốt lõi nào, MB nhận giải \"Vietnam HR Excellence 2025\"? Ai trao giải?",
      "Bài dự thi \"Hành trình Niềm tin\", tập trung vào giá trị cốt lõi Tin cậy; hạng mục Văn hóa Doanh nghiệp, do Anphabe chứng nhận và trao tặng.",
      ["Hành trình Niềm tin", "Tin cậy", "Anphabe"],
      [[E(200, "text", "Giải thưởng Vietnam HR Excellence 2025", "Với bài dự thi “Hành trình Niềm tin”, tập trung vào giá trị cốt lõi Tin cậy ... do Anphabe chứng nhận và trao tặng")]]),
    Q("ad17", "dev", "text", "Bà Nguyễn Minh Châu được bổ nhiệm Phó Tổng Giám đốc ngày nào, và năm 2026 bà phụ trách những khối nào?",
      "Bổ nhiệm ngày 23/11/2009; năm 2026 phụ trách Khối Nguồn vốn và Kinh doanh tiền tệ, Khối FDI và Khách hàng chiến lược.",
      ["23/11/2009", "Nguồn vốn và Kinh doanh tiền tệ", "FDI và Khách hàng chiến lược"],
      [[E(72, "text", "Ban Điều hành, mục Bà NGUYỄN MINH CHÂU", "Ngày bổ nhiệm: 23/11/2009 ... Năm 2026, Bà Châu chịu trách nhiệm chỉ đạo và quản lý Khối Nguồn vốn và Kinh doanh tiền tệ, Khối FDI và Khách hàng chiến lược.")]]),
    # --- thiếu bằng chứng (dev)
    U("adn1", "dev", "Lãi suất cho vay bình quân của MB năm 2025 là bao nhiêu phần trăm?",
      "Báo cáo có tỷ suất tài sản sinh lời YEA (tr.110), chi phí vốn COF và NIM (tr.110–111) nhưng không công bố lãi suất cho vay bình quân.",
      ["lãi suất cho vay bình quân", "lãi suất cho vay trung bình"], [110, 111]),
    U("adn2", "dev", "Tỷ lệ nghỉ việc (turnover) của nhân viên MB năm 2025 là bao nhiêu?",
      "Bảng nguồn nhân lực (tr.188) và chính sách nhân sự (tr.77, 189) có số lao động, tuyển mới, lương, đào tạo; không có tỷ lệ nghỉ việc. 'nghỉ việc' chỉ xuất hiện ở tr.248 (danh sách người nội bộ).",
      ["tỷ lệ nghỉ việc", "tỷ lệ thôi việc", "biến động nhân sự", "turnover"], [77, 188, 189]),
    U("adn3", "dev", "Chi phí quảng cáo và marketing của MB năm 2025 là bao nhiêu tỷ đồng?",
      "Có chi phí hoạt động và chi cho nhân viên (tr.203) và giải 'Chiến dịch quảng cáo ngoài trời' (tr.116) nhưng không có số chi phí quảng cáo/marketing.",
      ["chi phí quảng cáo", "chi phí marketing", "chi phí tiếp thị"], [116, 203]),
    U("adn4", "dev", "Trong năm 2025 MB phát hành mới bao nhiêu thẻ tín dụng?",
      "'thẻ tín dụng' chỉ xuất hiện trong mô tả dịch vụ đại lý (tr.175) và định nghĩa cấp tín dụng (tr.295); không có số lượng thẻ phát hành.",
      ["số lượng thẻ tín dụng", "thẻ tín dụng phát hành mới", "số thẻ phát hành"], [175, 295]),

    # ============================== TEST ==============================
    # --- bảng (6)
    Q("at01", "test", "bang", "Theo bảng tình hình tài chính năm 2025, huy động vốn (bao gồm CCTG) thực hiện năm 2025 là bao nhiêu, tăng bao nhiêu % so với 2024 và đánh giá so với kế hoạch thế nào?",
      "1.062.198 tỷ VND (2024: 805.647), tăng 31,8%; vượt kế hoạch (kế hoạch tăng trưởng ~21,2%).",
      ["1.062.198", "31,8%", "Vượt kế hoạch"],
      [[E(85, "table", "Tình hình tài chính của MB năm 2025, dòng Huy động vốn (Bao gồm CCTG)", "Huy động vốn (Bao gồm CCTG) | 805.647 | Tăng trưởng ~21,2% | 1.062.198 | 31,8% | Vượt kế hoạch"),
        E(59, "table", "Bảng chỉ tiêu KQKD, dòng 2 Huy động vốn", "Huy động vốn | Tăng ~21,2% | 1.062.198 | 31,8% | Vượt kế hoạch")]], unit="tỷ VND"),
    Q("at02", "test", "bang", "Tại ngày 31/12/2025, cổ đông nào sở hữu tỷ lệ lớn thứ hai tại MB, với bao nhiêu cổ phần và tỷ lệ bao nhiêu?",
      "Tổng công ty đầu tư và kinh doanh vốn Nhà nước - Công ty TNHH (SCIC): 791.523.642 cổ phần, 9,83%.",
      ["Tổng công ty đầu tư và kinh doanh vốn Nhà nước", "791.523.642", "9,83%"],
      [[E(94, "table", "Danh sách tổ chức/cá nhân sở hữu từ 1% trở lên, dòng 2", "Tổng công ty đầu tư và kinh doanh vốn Nhà nước- Công ty TNHH | 791.523.642 | 9,83%")]]),
    Q("at03", "test", "bang", "Tại cuối năm 2025, MB có bao nhiêu cổ đông nước ngoài, tỷ lệ sở hữu nước ngoài là bao nhiêu và giới hạn sở hữu nước ngoài tối đa là bao nhiêu?",
      "1.049 cổ đông nước ngoài, sở hữu 21,24% (1.711.246.465 cổ phần); tỷ lệ sở hữu nước ngoài tối đa 30%.",
      ["1.049", "21,24%", "30%"],
      [[E(95, "table", "Cơ cấu cổ đông tại 31/12/2025, dòng Cổ đông nước ngoài và Tỷ lệ sở hữu nước ngoài tối đa", "Cổ đông nước ngoài | 1.711.246.465 | 21,24% | 1.049; Tỷ lệ sở hữu nước ngoài tối đa | - | 30%")]]),
    Q("at04", "test", "bang", "Theo bảng phát triển nguồn nhân lực, mức lương trung bình của người lao động MB năm 2025 là bao nhiêu và tăng bao nhiêu so với 2024?",
      "39,4 triệu đồng/người/tháng (2024: 37,4 triệu), tăng 5,3%.", ["39,4 triệu", "5,3%"],
      [[E(188, "table", "Phát triển nguồn nhân lực, dòng Mức lương trung bình", "Mức lương trung bình ... | 37,4 triệu đồng/ tháng | 39,4 triệu đồng/ tháng | 5,3%"),
        E(77, "infographic", "Ô 'Thu nhập bình quân tháng của CBNV'", "39,4 triệu/người/tháng ↑5,3%")]]),
    Q("at05", "test", "bang", "Tính riêng MB (không hợp nhất), chi phí dự phòng năm 2025 là bao nhiêu và tăng bao nhiêu % so với 2024?",
      "9.569 tỷ đồng (2024: 6.491 tỷ), tăng 47%.", ["9.569", "47%"],
      [[E(203, "table", "Bảng 'Riêng MB (Đơn vị: tỷ đồng)', dòng 3 Chi phí dự phòng", "3 | Chi phí dự phòng | 6.491 | 9.569 | 47%")]],
      note="Không nhầm với số toàn Tập đoàn (13.744 tỷ, +44%) ở bảng phía trên."),
    Q("at06", "test", "bang", "Giá cổ phiếu MBB tại thời điểm cuối năm 2025 và giá trị vốn hóa thị trường là bao nhiêu?",
      "Giá cuối năm 25.300 VND/cổ phiếu; vốn hóa 203.800.000.000.000 VND (~203,8 nghìn tỷ đồng).",
      ["25.300", "203.800"],
      [[E(94, "table", "Bảng Cổ phần, dòng Giá cổ phiếu tại thời điểm cuối năm và Giá trị vốn hóa thị trường", "Giá cổ phiếu tại thời điểm cuối năm | 25.300; Giá trị vốn hóa thị trường | 203.800.000.000.000")]]),
    # --- ảnh, sơ đồ (6)
    Q("at07", "test", "anh_so_do", "Theo bản đồ mạng lưới giao dịch năm 2025, MB có bao nhiêu điểm giao dịch trong nước và hiện diện ở những quốc gia nào khác ngoài Việt Nam?",
      "327 điểm giao dịch trong nước; ngoài ra có 01 địa điểm giao dịch tại Lào và 01 Ngân hàng đại chúng TNHH MB Campuchia (cùng 01 Hội sở chính).",
      ["327", "Lào", "Campuchia"],
      [[E(23, "map", "Bản đồ mạng lưới, cột chú thích bên trái", "Hội sở chính 01; Địa điểm giao dịch tại Lào 01; Ngân hàng đại chúng TNHH MB Campuchia 01; Điểm giao dịch trong nước 327")]]),
    Q("at08", "test", "anh_so_do", "Theo sơ đồ tổ chức nhân sự MB năm 2025, ba hội đồng được đánh số 1, 2, 3 là những hội đồng nào?",
      "(1) Hội đồng ALCO, (2) Hội đồng rủi ro, (3) Hội đồng quản lý vốn.",
      ["ALCO", "Hội đồng rủi ro", "Hội đồng quản lý vốn"],
      [[E(27, "org_chart", "Sơ đồ tổ chức, nhóm bên trái có đánh số 1-3", "1 Hội đồng ALCO; 2 Hội đồng rủi ro; 3 Hội đồng quản lý vốn")]]),
    Q("at09", "test", "anh_so_do", "Trong sơ đồ bộ máy quản lý của Ngân hàng, cơ quan nào được đặt ngay dưới Ban Kiểm soát?",
      "Cơ quan Kiểm toán nội bộ.", ["Kiểm toán nội bộ"],
      [[E(26, "diagram", "Sơ đồ bộ máy quản lý, khối dưới 'Ban Kiểm soát'", "BAN KIỂM SOÁT → CƠ QUAN KIỂM TOÁN NỘI BỘ")]]),
    Q("at10", "test", "anh_so_do", "Trong ảnh các giải thưởng năm 2025, giải \"The Best FX Bank in Vietnam\" do tổ chức nào trao tặng?",
      "The Asian Banker.", ["The Asian Banker"],
      [[E(15, "photo", "Ảnh tòa nhà MB với các biểu tượng vòng nguyệt quế, hàng thứ 3 bên trái", "The Best FX Bank in Vietnam – do The Asian Banker trao tặng")]]),
    Q("at11", "test", "anh_so_do", "Trong sơ đồ 7 giải pháp chủ đạo triển khai hoạt động kinh doanh năm 2026, giải pháp số 06 là gì?",
      "Quy hoạch hệ thống mạng lưới theo hướng đa kênh, thuận tiện, linh hoạt và hiệu quả; ưu tiên mở mới điểm giao dịch hiện đại và SmartBank tại các địa bàn trọng điểm, tiềm năng.",
      ["mạng lưới", "SmartBank"],
      [[E(119, "diagram", "Sơ đồ 'Một số giải pháp chủ đạo ... năm 2026', ô 06", "Quy hoạch hệ thống mạng lưới theo hướng đa kênh, thuận tiện, linh hoạt và hiệu quả ... Ưu tiên mở mới điểm giao dịch hiện đại và SmartBank tại các địa bàn trọng điểm, tiềm năng.")]]),
    Q("at12", "test", "anh_so_do", "Theo sơ đồ cơ cấu tổ chức phòng, chống tham nhũng, ai giữ vai trò Trưởng Ban Chỉ đạo tại Hội sở và ai là Trưởng Tiểu Ban Chỉ đạo tại Chi nhánh?",
      "Tại Hội sở: Bí thư Đảng ủy, Chủ tịch Hội đồng Quản trị MB. Tại Chi nhánh: Giám đốc Chi nhánh.",
      ["Chủ tịch Hội đồng Quản trị", "Giám đốc Chi nhánh"],
      [[E(166, "diagram", "Sơ đồ Cơ cấu tổ chức triển khai công tác Phòng, chống tham nhũng", "Trưởng Ban chỉ đạo: Bí thư Đảng ủy, Chủ tịch Hội đồng Quản trị MB; Trưởng Tiểu Ban Chỉ đạo: Giám đốc Chi nhánh")]]),
    # --- biểu đồ (6)
    Q("at13", "test", "bieu_do", "Theo biểu đồ tín dụng, tỷ trọng khách hàng cá nhân (KHCN) trong cơ cấu tín dụng năm 2024 là bao nhiêu và tổng tín dụng năm 2024 là bao nhiêu?",
      "KHCN 46% (KHDN 54%); tổng tín dụng 2024: 811 nghìn tỷ đồng.", ["46%", "811"],
      [[E(89, "combo_chart", "Biểu đồ 'Tín dụng (nghìn tỷ đồng)', cột 2024", "2024: 811; KHCN 46%; KHDN 54%")]]),
    Q("at14", "test", "bieu_do", "Theo biểu đồ cơ cấu doanh thu phí, mảng nào chiếm tỷ trọng lớn nhất và lớn thứ hai, mỗi mảng bao nhiêu %?",
      "Bảo hiểm 52%, Thanh toán và ngân quỹ 25%.", ["Bảo hiểm", "52%", "Thanh toán và ngân quỹ", "25%"],
      [[E(92, "pie_chart", "Biểu đồ tròn 'Cơ cấu doanh thu phí'", "Bảo hiểm 52%; Thanh toán và ngân quỹ 25%; Khác 10%; Dịch vụ tư vấn 6%; Môi giới chứng khoán 5%; Thu từ xử lý nợ 2%")]]),
    Q("at15", "test", "bieu_do", "Theo biểu đồ CIR năm 2025, CIR hợp nhất và CIR riêng lẻ chênh nhau bao nhiêu điểm phần trăm?",
      "Hợp nhất 29,1% và riêng lẻ 26,0%, chênh 3,1 điểm phần trăm.", ["29,1", "26,0", "3,1"],
      [[E(93, "line_chart", "Biểu đồ 'CIR (%)', điểm năm 2025 của hai đường Hợp nhất / Riêng lẻ", "2025: Hợp nhất 29,1; Riêng lẻ 26,0")]],
      calculation="29,1 − 26,0 = 3,1 điểm %"),
    Q("at16", "test", "bieu_do", "Theo biểu đồ so sánh tỷ lệ bao phủ nợ xấu (LLR) năm 2025, LLR của MBB là bao nhiêu và ngân hàng nào có LLR cao nhất?",
      "MBB 94%; cao nhất là VCB với 259%.", ["94", "VCB", "259"],
      [[E(113, "combo_chart", "Biểu đồ 'LLR', cột MBB và VCB", "VCB 259 | CTG 159 | TCB 128 | ACB 114 | BID 100 | MBB 94 | VPB 55 | STB 50")]]),
    Q("at17", "test", "bieu_do", "Theo biểu đồ tăng trưởng LNTT tập đoàn giai đoạn 2022 - 2026, LNTT kế hoạch năm 2026 là bao nhiêu và tốc độ tăng trưởng kép (CAGR) ghi trên biểu đồ là bao nhiêu?",
      "Kế hoạch 2026: 39.500 (tỷ đồng); CAGR 14,8%.", ["39.500", "14,8%"],
      [[E(118, "bar_chart", "Biểu đồ 'Tăng trưởng LNTT tập đoàn giai đoạn 2022 - 2026', cột Kế hoạch 2026 và nhãn CAGR", "22.729 | 26.306 | 28.829 | 34.268 | 39.500; CAGR 14,8%")]]),
    Q("at18", "test", "bieu_do", "Theo biểu đồ cơ cấu dư nợ xanh năm 2025, lĩnh vực nào chiếm tỷ trọng lớn nhất và bao nhiêu %?",
      "Lĩnh vực năng lượng tái tạo và năng lượng sạch, 62%.", ["năng lượng tái tạo", "62%"],
      [[E(169, "pie_chart", "Biểu đồ 'Cơ cấu dư nợ xanh'", "Năng lượng tái tạo và năng lượng sạch 62%; Nông, lâm nghiệp xanh 22%; Công nghiệp xanh 9%; Giao thông xanh 7%; Khác ~1%")]]),
    # --- multi-hop (4)
    Q("at19", "test", "multi_hop", "Bốn cổ đông lớn sở hữu từ 5% vốn cổ phần trở lên của MB là những ai, và tổng tỷ lệ sở hữu của nhóm cổ đông lớn này là bao nhiêu?",
      "Tập đoàn Công nghiệp - Viễn thông Quân đội (14,70%), Tổng công ty đầu tư và kinh doanh vốn Nhà nước (9,83%), Tổng Công ty trực thăng Việt Nam (8,43%), Tổng Công ty Tân Cảng Sài Gòn (7,09%); tổng 40,04% (3.225.575.405 cổ phần).",
      ["Viễn thông Quân đội", "đầu tư và kinh doanh vốn Nhà nước", "trực thăng", "Tân Cảng", "40,04%"],
      [[E(94, "table", "Danh sách sở hữu từ 1% trở lên, 4 dòng đầu (≥5%)", "14,70% | 9,83% | 8,43% | 7,09%")],
       [E(95, "table", "Cơ cấu cổ đông, dòng Cổ đông lớn (sở hữu từ 5% trở lên)", "Cổ đông lớn ... | 3.225.575.405 | 40,04% | 4")]],
      calculation="Tổng 4 dòng = 3.225.575.405 cổ phần, khớp bảng cơ cấu (40,04%; cộng các tỷ lệ làm tròn = 40,05%)"),
    Q("at20", "test", "multi_hop", "Từ vốn điều lệ cuối năm 2024 là 53.063 tỷ đồng, MB đã tăng vốn điều lệ lên bao nhiêu vào cuối 2025 và qua những đợt phát hành nào trong năm 2025 (tổng vốn huy động)?",
      "Vốn điều lệ cuối 2025: 80.550 tỷ đồng. Hai đợt trả cổ tức bằng cổ phiếu năm 2025: đợt 15% (kết thúc 8/1/2025, +7.959.486 triệu đồng) và đợt 32% (kết thúc 14/8/2025, +19.527.273 triệu đồng); tổng tăng 27.486.759 triệu đồng (~27.487 tỷ).",
      ["80.550", "15%", "32%", "27.48"],
      [[E(85, "table", "Tình hình tài chính 2025, dòng Vốn điều lệ", "Vốn điều lệ | 53.063 | 81.368 | 80.550 | 51,8%"),
        E(57, "table", "Một số chỉ tiêu kinh doanh chính, dòng Vốn điều lệ", "Vốn điều lệ | tỷ đồng | 52.141 | 53.063 | 80.550 | 51,8%")],
       [E(96, "table", "Tình hình thay đổi vốn đầu tư của chủ sở hữu, 2 dòng năm 2025", "8/1/2025 | ... (15%) | 53.063.241 | 7.959.486 | 61.022.727; 14/8/2025 | ... (32%) | 61.022.727 | 19.527.273 | 80.550.000")]],
      calculation="7.959.486 + 19.527.273 = 27.486.759 triệu đồng; 53.063.241 + 27.486.759 = 80.550.000 triệu đồng"),
    Q("at21", "test", "multi_hop", "Tính riêng MB, chi cho nhân viên năm 2025 bình quân trên mỗi nhân sự là khoảng bao nhiêu (dùng số lao động riêng MB cuối năm)?",
      "Khoảng 631,8 triệu đồng/người/năm (8.243 tỷ đồng chi cho nhân viên riêng MB ÷ 13.047 nhân sự riêng MB).",
      ["8.243", "13.047", "631"],
      [[E(203, "table", "Bảng 'Riêng MB', dòng 4.1 Chi cho nhân viên", "4.1 | Chi cho nhân viên | 7.018 | 8.243 | 17%")],
       [E(188, "table", "Phát triển nguồn nhân lực, dòng Số lượng lao động - tính riêng MB", "12.155 nhân sự | 13.047 nhân sự | 7%")]],
      calculation="8.243.000 triệu ÷ 13.047 ≈ 631,8 triệu đồng/người/năm", unit="triệu đồng/người/năm"),
    Q("at22", "test", "multi_hop", "Ngân hàng MBV trước đây có tên là gì, được chuyển giao bắt buộc cho MB từ ngày nào, và năm 2025 MBV có bao nhiêu lao động (suy từ bảng nhân lực toàn tập đoàn)?",
      "Trước đây là Ngân hàng Thương mại TNHH MTV Đại Dương (OceanBank); chuyển giao bắt buộc ngày 17/10/2024; số lao động MBV năm 2025 = 20.674 − 18.836 = 1.838 người.",
      ["Đại Dương", "17/10/2024", "1.838"],
      [[E(84, "text", "Mục Ngân hàng TNHH MTV Việt Nam Hiện Đại (MBV), Tình hình hoạt động", "Ngày 17/10/2024, Ngân hàng Thương mại TNHH một thành viên Đại Dương (nay là Ngân hàng Thương mại TNHH MTV Việt Nam Hiện đại) đã được NHNN phê duyệt quyết định về việc chuyển giao bắt buộc cho MB."),
        E(292, "text", "Thuyết minh BCTC: Công ty con", "Ngày 17 tháng 10 năm 2024, NHNNVN đã công bố quyết định chuyển giao bắt buộc Ngân hàng Thương mại TNHH MTV Đại Dương cho Ngân hàng")],
       [E(188, "table", "Phát triển nguồn nhân lực, 2 dòng Số lượng lao động toàn tập đoàn gồm / không gồm MBV", "gồm MBV | 20.674 nhân sự; không gồm MBV | 18.836 nhân sự")]],
      calculation="20.674 − 18.836 = 1.838"),
    # --- text (4)
    Q("at23", "test", "text", "Năm 2025 quy mô tín dụng của Khối CIB đạt bao nhiêu, tăng net bao nhiêu và tốc độ tăng trưởng so với 2024 là bao nhiêu?",
      "Hơn 362 nghìn tỷ đồng, tăng net 127 nghìn tỷ, tăng trưởng 54% so với 2024.", ["362", "127", "54%"],
      [[E(60, "text", "Hoạt động của các Khối – Khối CIB, gạch đầu dòng 'Dẫn đầu về tăng trưởng tín dụng'", "đạt quy mô hơn 362 nghìn tỷ, tăng net 127 nghìn tỷ, đạt tốc độ tăng trưởng 54% so với năm 2024")]]),
    Q("at24", "test", "text", "Năm 2025 dư nợ trung - dài hạn của Khối SME đạt bao nhiêu và tăng trưởng bao nhiêu so với 2024?",
      "88.868 tỷ đồng, tăng trưởng 50% so với 2024.", ["88.868", "50%"],
      [[E(62, "text", "Khối SME – Các thành tựu nổi bật năm 2025", "Dư nợ trung - dài hạn đạt 88.868 tỷ tăng trưởng 50% so với 2024")]]),
    Q("at25", "test", "text", "Sau khi hợp nhất dữ liệu tập đoàn, tổng số khách hàng hợp nhất thành công là bao nhiêu?",
      "36,7 triệu khách hàng.", ["36,7 triệu"],
      [[E(132, "text", "Hoạt động của Ban Điều hành – Đẩy mạnh công tác hiệp lực Tập đoàn", "Hợp nhất dữ liệu tập đoàn, tổng số lượng khách hàng hợp nhất thành công đạt 36,7 triệu khách hàng.")]]),
    Q("at26", "test", "text", "Trong định hướng tài chính xanh năm 2026, MB tích cực triển khai chương trình hỗ trợ lãi suất bao nhiêu %/năm và cho những loại dự án nào?",
      "Hỗ trợ lãi suất 2%/năm đối với các dự án xanh, kinh tế tuần hoàn và các dự án đáp ứng tiêu chuẩn ESG.",
      ["2%/năm", "dự án xanh", "kinh tế tuần hoàn", "ESG"],
      [[E(170, "text", "Tài chính xanh – Kế hoạch năm 2026", "chương trình hỗ trợ lãi suất 2%/năm đối với các dự án xanh, kinh tế tuần hoàn và các dự án đáp ứng tiêu chuẩn ESG")]]),
    # --- thiếu bằng chứng (test, 6)
    U("atn1", "test", "Lượng phát thải khí nhà kính phạm vi 3 (Scope 3) của MB năm 2025 là bao nhiêu tấn CO2e?",
      "MB chỉ kiểm kê khí nhà kính Phạm vi 1 và Phạm vi 2 (tr.177; dự án kiểm kê phạm vi 1, 2 ở tr.149–150); không có số liệu phạm vi 3.",
      ["phạm vi 3", "scope 3"], [149, 150, 177]),
    U("atn2", "test", "Lợi nhuận trước thuế năm 2025 của Mcredit (Công ty Tài chính TNHH MB Shinsei) là bao nhiêu?",
      "Mục Mcredit (tr.82) có chiến lược, xếp hạng Fitch B+; bảng công ty con (tr.80) có vốn điều lệ 1.600 tỷ và tỷ lệ sở hữu 50%; không có lợi nhuận của Mcredit.",
      ["lợi nhuận trước thuế của Mcredit", "LNTT Mcredit", "Mcredit đạt"], [80, 82]),
    U("atn3", "test", "Chi phí tín dụng (credit cost, % trên dư nợ bình quân) của MB năm 2025 là bao nhiêu?",
      "Có chi phí dự phòng tuyệt đối (tr.203) và tỷ lệ nợ xấu/bao phủ (tr.113) nhưng không công bố chỉ tiêu chi phí tín dụng.",
      ["chi phí tín dụng", "credit cost"], [113, 203]),
    U("atn4", "test", "Ngân hàng đại chúng TNHH MB Campuchia (MBCambodia) có bao nhiêu nhân sự vào cuối năm 2025?",
      "MBCambodia chỉ có trong bản đồ mạng lưới (tr.23), bảng công ty con (tr.80) và mục hoạt động (tr.83); không có số nhân sự riêng.",
      ["nhân sự của MBCambodia", "nhân viên MBCambodia", "MBCambodia có"], [23, 80, 83]),
    U("atn5", "test", "Giá cổ phiếu MBB cao nhất trong năm 2025 là bao nhiêu đồng?",
      "Chỉ có giá cuối năm 25.300 VND và vốn hóa (tr.94), biểu đồ tăng trưởng giá theo % (tr.104–105) và giá cao nhất tuần của chỉ số VNINDEX (tr.104); không có giá cao nhất của MBB.",
      ["giá cao nhất của MBB", "giá cổ phiếu cao nhất", "đỉnh giá"], [94, 104, 105]),
    U("atn6", "test", "Tỷ lệ cổ tức mà MB dự kiến chi trả trong năm 2026 cho kết quả kinh doanh năm 2025 là bao nhiêu?",
      "Chỉ có cổ tức đã chi trả năm 2025 cho kết quả năm 2024 (35% gồm 32% cổ phiếu và 3% tiền mặt, tr.59) và lịch sử cổ tức (tr.96–97); kế hoạch 2026 (tr.118, 134) không có cổ tức.",
      ["cổ tức năm 2026", "kế hoạch cổ tức", "phân phối lợi nhuận năm 2025"], [59, 97, 118, 134]),
]

MIN = {("dev", True): 15, ("dev", False): 3, ("test", True): 24, ("test", False): 6}
MIN_GROUP_TEST = {"bang": 6, "anh_so_do": 5, "bieu_do": 5, "multi_hop": 4, "text": 4}


def page_texts() -> dict[int, str]:
    doc = pymupdf.open(PDF)
    out = {}
    for i, page in enumerate(doc, 1):
        for side, pp, clip in halves(page, i):
            out[pp] = unicodedata.normalize("NFC", re.sub(r"\s+", " ", page.get_text(clip=clip)))
    return out


def validate(qs) -> list[str]:
    errs = []
    ids = [q["id"] for q in qs]
    if len(ids) != len(set(ids)):
        errs.append("duplicate ids")
    c = Counter((q["split"], q["answerable"]) for q in qs)
    errs += [f"{k}: {c[k]} < {v}" for k, v in MIN.items() if c[k] < v]
    g = Counter(q["group"] for q in qs if q["split"] == "test" and q["answerable"])
    errs += [f"test group {k}: {g[k]} < {v}" for k, v in MIN_GROUP_TEST.items() if g[k] < v]
    texts = page_texts()
    for q in qs:
        if q["answerable"]:
            if q["group"] == "multi_hop" and len(q["evidence"]) < 2:
                errs.append(f"{q['id']}: multi-hop needs >= 2 evidence groups")
            pages = {e["page"] for grp in q["evidence"] for e in grp}
            if q["group"] == "multi_hop" and len({e["page"] for grp in q["evidence"] for e in grp[:1]}) < 2:
                errs.append(f"{q['id']}: multi-hop evidence must span >= 2 pages")
            for p in pages:
                if p not in texts:
                    errs.append(f"{q['id']}: page {p} out of range")
        else:
            for t in q["absent_terms"]:
                rx = re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)", re.I)
                hit = [p for p, s in texts.items() if rx.search(s)]
                if hit:
                    errs.append(f"{q['id']}: absent term {t!r} found on pages {hit}")
    return errs


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(QUESTIONS, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    c = Counter((q["split"], q["group"]) for q in QUESTIONS)
    for s in ("dev", "test"):
        print(s, {g: c[(s, g)] for g in ("bang", "anh_so_do", "bieu_do", "multi_hop", "text", "thieu_bang_chung")},
              "total", sum(v for (sp, _), v in c.items() if sp == s))
    errs = validate(QUESTIONS)
    print("\n".join(errs) if errs else "OK: benchmark hợp lệ")
    if errs:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
