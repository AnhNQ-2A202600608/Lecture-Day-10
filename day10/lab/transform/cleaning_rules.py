"""
Cleaning rules — raw export → cleaned rows + quarantine.

Baseline gồm các failure mode mở rộng (allowlist doc_id, parse ngày, HR stale version).
Sinh viên thêm ≥3 rule mới: mỗi rule phải ghi `metric_impact` (xem README — chống trivial).
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = ROOT / "contracts" / "data_contract.yaml"

def _load_contract() -> dict:
    if CONTRACT_PATH.is_file():
        try:
            with open(CONTRACT_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Failed to load data contract: {e}")
    return {}

_contract = _load_contract()

ALLOWED_DOC_IDS = frozenset(_contract.get("allowed_doc_ids", [
    "policy_refund_v4",
    "sla_p1_2026",
    "it_helpdesk_faq",
    "hr_leave_policy",
    "access_control_sop"
]))

_policy_versioning = _contract.get("policy_versioning", {})

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ]\d{2}:\d{2}:\d{2}.*$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_YMD_SLASH = re.compile(r"^(\d{4})/(\d{2})/(\d{2})$")
_DMY_DASH = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")

_DOC_CONTEXTS = {
    "policy_refund_v4": "Chính sách hoàn tiền (refund policy): ",
    "sla_p1_2026": "Quy định SLA xử lý sự cố ticket P1 (IT support SLA): ",
    "it_helpdesk_faq": "IT Helpdesk FAQ (hướng dẫn IT nội bộ): ",
    "hr_leave_policy": "Chính sách nghỉ phép nhân sự HR (HR leave policy): ",
    "access_control_sop": "Quy trình kiểm soát truy cập hệ thống (access control SOP): "
}


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_date, error_reason).
    iso_date rỗng nếu không parse được.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m_dt = _ISO_DATETIME.match(s)
    if m_dt:
        return m_dt.group(1), ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    m_ymd_slash = _YMD_SLASH.match(s)
    if m_ymd_slash:
        yyyy, mm, dd = m_ymd_slash.group(1), m_ymd_slash.group(2), m_ymd_slash.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    m_dmy_dash = _DMY_DASH.match(s)
    if m_dmy_dash:
        dd, mm, yyyy = m_dmy_dash.group(1), m_dmy_dash.group(2), m_dmy_dash.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Trả về (cleaned, quarantine).

    Các luật làm sạch & xử lý dữ liệu:
    1) Loại bỏ doc_id không nằm trong allowlist của data_contract.yaml.
    2) Chuẩn hóa effective_date thành định dạng ISO YYYY-MM-DD.
    3) Quarantine các tài liệu có ngày hiệu lực trước mốc cắt phiên bản cũ cấu hình trong data_contract.yaml (hỗ trợ ENV override).
    4) Làm sạch text:
       - Loại bỏ các chuỗi rác như "Nội dung không rõ ràng: ", "!!!".
       - Normalize khoảng trắng.
       - Normalize lặp từ "làm việc làm việc".
       - [Rule mới 1] internal_consecutive_sentence_deduplication: Khử trùng lặp câu trong cùng 1 chunk.
       - [Rule mới 2] phone_extension_standardization: Chuẩn hóa ext. <number> -> extension <number>.
       - [Rule mới 3] refund_exception_enrichment: Làm giàu từ khóa ngoại lệ không hoàn tiền cho policy_refund_v4.
    5) Quarantine nếu text trống sau khi làm sạch.
    6) Quarantine các tài liệu hr_leave_policy chứa text "10 ngày phép năm" (mâu thuẫn phiên bản).
    7) Loại bỏ trùng lặp nội dung chunk_text sau khi làm sạch (giữ bản đầu).
    8) Sửa lỗi stale refund window (14 -> 7 ngày làm việc).
    9) [Rule mới 4] export_timestamp_normalization: Chuẩn hóa exported_at sang định dạng ISO YYYY-MM-DDThh:mm:ss.
    10) Thêm Context Enrichment bằng cách chèn tiêu đề tài liệu làm tiền tố cho mỗi chunk.
    """
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        # 1) Kiểm tra allowlist
        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        # 2) Chuẩn hóa effective_date
        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw})
            continue

        # 3) Dynamic version cut check (với hỗ trợ ENV override tránh hard-code)
        min_date = os.environ.get(f"{doc_id.upper()}_CUTOFF_DATE") or _policy_versioning.get(doc_id)
        if min_date and eff_norm < min_date:
            quarantine.append(
                {
                    **raw,
                    "reason": f"stale_{doc_id}_effective_date",
                    "effective_date_normalized": eff_norm,
                    "min_effective_date": min_date,
                }
            )
            continue

        # 4) Clean text
        fixed_text = text or ""
        # Rule 1: Strip "Nội dung không rõ ràng: "
        if fixed_text.startswith("Nội dung không rõ ràng:"):
            fixed_text = fixed_text[len("Nội dung không rõ ràng:"):].strip()
        
        # Rule 1: Strip "!!!" và các ký tự rác khác ở đầu/cuối
        fixed_text = fixed_text.strip("! ")

        # Rule 2: Normalize duplicated phrases like "làm việc làm việc" -> "làm việc"
        fixed_text = re.sub(r"\b(làm việc\s+)+làm việc\b", "làm việc", fixed_text)

        # Rule 1: Normalize spaces
        fixed_text = " ".join(fixed_text.split())

        # [Rule mới 1] internal_consecutive_sentence_deduplication
        if fixed_text:
            sentences = re.split(r'(?<=[.!?])\s+', fixed_text)
            unique_sentences = []
            for s in sentences:
                s_clean = s.strip()
                if s_clean and s_clean not in unique_sentences:
                    unique_sentences.append(s_clean)
            fixed_text = " ".join(unique_sentences)

        # [Rule mới 2] phone_extension_standardization
        if fixed_text:
            fixed_text = re.sub(r'\bext\.\s*(\d+)\b', r'extension \1', fixed_text, flags=re.IGNORECASE)

        # [Rule mới 3] refund_exception_enrichment
        if doc_id == "policy_refund_v4" and "Ngoại lệ không được hoàn tiền" in fixed_text:
            fixed_text = fixed_text.replace(
                "Ngoại lệ không được hoàn tiền:",
                "Ngoại lệ (các loại sản phẩm bị loại khỏi điều kiện hoàn tiền):"
            )

        # 5) Kiểm tra chunk_text rỗng sau clean
        if not fixed_text:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        # 6) Quarantine stale HR policy text (10 ngày phép năm)
        if doc_id == "hr_leave_policy" and ("10 ngày phép năm" in fixed_text or "10 ngày làm việc phép năm" in fixed_text):
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_text",
                    "chunk_text_cleaned": fixed_text,
                }
            )
            continue

        # 7) Loại trùng lặp nội dung chunk_text sau clean
        key = _norm_text(fixed_text)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        # 8) Sửa stale refund window
        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ngày làm việc" in fixed_text:
                fixed_text = fixed_text.replace(
                    "14 ngày làm việc",
                    "7 ngày làm việc",
                )
                fixed_text += " [cleaned: stale_refund_window]"

        # [Rule mới 4] export_timestamp_normalization
        exp_raw = (raw.get("exported_at") or "").strip()
        exp_norm = exp_raw
        if "/" in exp_raw:
            exp_norm = exp_raw.replace("/", "-")

        # 9) Context Enrichment
        context_prefix = _DOC_CONTEXTS.get(doc_id, "")
        enriched_text = context_prefix + fixed_text

        seq += 1
        cleaned.append(
            {
                "chunk_id": _stable_chunk_id(doc_id, enriched_text, seq),
                "doc_id": doc_id,
                "chunk_text": enriched_text,
                "effective_date": eff_norm,
                "exported_at": exp_norm,
            }
        )

    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n", encoding="utf-8")
        return
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)
