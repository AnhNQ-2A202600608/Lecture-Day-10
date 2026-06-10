"""
Expectation suite đơn giản (không bắt buộc Great Expectations).

Sinh viên có thể thay bằng GE / pydantic / custom — miễn là có halt có kiểm soát.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []

    # E1: có ít nhất 1 dòng sau clean
    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    # E2: không doc_id rỗng
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    ok2 = len(bad_doc) == 0
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            ok2,
            "halt",
            f"empty_doc_id_count={len(bad_doc)}",
        )
    )

    # E3: policy refund không được chứa cửa sổ sai 14 ngày (sau khi đã fix)
    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    ok3 = len(bad_refund) == 0
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            ok3,
            "halt",
            f"violations={len(bad_refund)}",
        )
    )

    # E4: chunk_text đủ dài
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    ok4 = len(short) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            ok4,
            "warn",
            f"short_chunks={len(short)}",
        )
    )

    # E5: effective_date đúng định dạng ISO sau clean (phát hiện parser lỏng)
    iso_bad = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    ok5 = len(iso_bad) == 0
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            ok5,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    # E6: không còn marker phép năm cũ 10 ngày trên doc HR (conflict version sau clean)
    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    ok6 = len(bad_hr_annual) == 0
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            ok6,
            "halt",
            f"violations={len(bad_hr_annual)}",
        )
    )

    # E7: Đảm bảo mỗi doc_id trong allowlist có ít nhất 1 dòng được cleaned
    from transform.cleaning_rules import ALLOWED_DOC_IDS
    missing_doc_ids = []
    cleaned_doc_ids = {r.get("doc_id") for r in cleaned_rows if r.get("doc_id")}
    for allowed_id in ALLOWED_DOC_IDS:
        if allowed_id not in cleaned_doc_ids:
            missing_doc_ids.append(allowed_id)
    ok7 = len(missing_doc_ids) == 0
    results.append(
        ExpectationResult(
            "min_records_per_doc_id",
            ok7,
            "halt",
            f"missing_doc_ids={missing_doc_ids}",
        )
    )

    # E8: Đảm bảo không còn ký tự rác (!!!), tiền tố rác, hoặc trùng lặp từ trong cleaned_rows
    bad_symbols = []
    for r in cleaned_rows:
        text = r.get("chunk_text") or ""
        if "!!!" in text or "Nội dung không rõ ràng:" in text or "làm việc làm việc" in text:
            bad_symbols.append(r.get("chunk_id"))
    ok8 = len(bad_symbols) == 0
    results.append(
        ExpectationResult(
            "no_corrupted_symbols",
            ok8,
            "halt",
            f"corrupted_chunks={len(bad_symbols)}",
        )
    )

    # E9: Validate schema qua Pydantic model thật (Bonus +2 | Distinction)
    pydantic_ok, pydantic_errs = validate_rows_pydantic(cleaned_rows)
    results.append(
        ExpectationResult(
            "pydantic_schema_validation",
            pydantic_ok,
            "halt",
            f"validation_errors={len(pydantic_errs)} :: details: {pydantic_errs[:2]}",
        )
    )

    # E10: Đảm bảo exported_at đúng định dạng ISO YYYY-MM-DDThh:mm:ss sau clean
    bad_exported = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}$", (r.get("exported_at") or "").strip())
    ]
    ok10 = len(bad_exported) == 0
    results.append(
        ExpectationResult(
            "exported_at_iso_format",
            ok10,
            "halt",
            f"non_iso_exported_rows={len(bad_exported)}",
        )
    )

    # E11: Đảm bảo chunk_text không quá dài (> 1000 ký tự) để tối ưu hoá vector (Warn)
    long_chunks = [r for r in cleaned_rows if len(r.get("chunk_text") or "") > 1000]
    ok11 = len(long_chunks) == 0
    results.append(
        ExpectationResult(
            "chunk_max_length_1000",
            ok11,
            "warn",
            f"long_chunks={len(long_chunks)}",
        )
    )

    # E12: Đảm bảo không trùng lặp chunk_id trong cleaned data
    chunk_ids = [r.get("chunk_id") for r in cleaned_rows if r.get("chunk_id")]
    ok12 = len(chunk_ids) == len(set(chunk_ids))
    results.append(
        ExpectationResult(
            "no_duplicate_chunk_ids",
            ok12,
            "halt",
            f"duplicate_count={len(chunk_ids) - len(set(chunk_ids))}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt


def validate_rows_pydantic(cleaned_rows: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """
    Sử dụng Pydantic Model để xác thực cấu trúc schema và kiểu dữ liệu (Bonus +2).
    """
    try:
        from pydantic import BaseModel, Field, ValidationError
        from datetime import date, datetime
        
        class CleanedRow(BaseModel):
            chunk_id: str = Field(..., min_length=1)
            doc_id: str = Field(..., min_length=1)
            chunk_text: str = Field(..., min_length=8)
            effective_date: date
            exported_at: datetime
            
        errors = []
        for i, r in enumerate(cleaned_rows):
            try:
                CleanedRow(
                    chunk_id=r.get("chunk_id", ""),
                    doc_id=r.get("doc_id", ""),
                    chunk_text=r.get("chunk_text", ""),
                    effective_date=r.get("effective_date", ""),
                    exported_at=r.get("exported_at", "")
                )
            except ValidationError as e:
                errors.append(f"Row {i} (chunk_id={r.get('chunk_id')}): {e.errors()}")
        return len(errors) == 0, errors
    except Exception as e:
        return False, [f"Pydantic validation error: {e}"]

