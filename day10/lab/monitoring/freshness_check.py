"""
Kiểm tra freshness từ manifest pipeline (SLA đơn giản theo giờ).

Sinh viên mở rộng: đọc watermark DB, so sánh với clock batch, v.v.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple


def parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        # Cho phép "2026-04-10T08:00:00" không có timezone
        if ts.endswith("Z"):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def check_manifest_freshness(
    manifest_path: Path,
    *,
    sla_hours: float = 24.0,  # Ingestion SLA
    publish_sla_hours: float = 1.0,  # Publish SLA
    now: datetime | None = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Xác định freshness tại 2 boundary (Bonus +1 | Distinction):
      1) Ingestion Boundary (latest_exported_at vs now)
      2) Publish Boundary (run_timestamp vs now)
    Trả về ("PASS" | "WARN" | "FAIL", detail dict).
    """
    import os
    now = now or datetime.now(timezone.utc)
    if not manifest_path.is_file():
        return "FAIL", {"reason": "manifest_missing", "path": str(manifest_path)}

    data: Dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    # Đọc cấu hình bổ sung từ env nếu có
    pub_sla = float(os.environ.get("PUBLISH_SLA_HOURS", str(publish_sla_hours)))
    
    # Boundary 1: Ingestion
    ts_ingest = data.get("latest_exported_at")
    dt_ingest = parse_iso(str(ts_ingest)) if ts_ingest else None
    
    # Boundary 2: Publish
    ts_publish = data.get("run_timestamp")
    dt_publish = parse_iso(str(ts_publish)) if ts_publish else None
    
    detail = {}
    ingest_status = "UNKNOWN"
    publish_status = "UNKNOWN"
    
    if dt_ingest:
        age_ingest = (now - dt_ingest).total_seconds() / 3600.0
        ingest_status = "PASS" if age_ingest <= sla_hours else "FAIL"
        detail["ingestion_boundary"] = {
            "latest_exported_at": ts_ingest,
            "age_hours": round(age_ingest, 3),
            "sla_hours": sla_hours,
            "status": ingest_status
        }
    else:
        detail["ingestion_boundary"] = {"status": "WARN", "reason": "no_ingest_timestamp"}
        ingest_status = "WARN"
        
    if dt_publish:
        age_publish = (now - dt_publish).total_seconds() / 3600.0
        publish_status = "PASS" if age_publish <= pub_sla else "FAIL"
        detail["publish_boundary"] = {
            "run_timestamp": ts_publish,
            "age_hours": round(age_publish, 3),
            "sla_hours": pub_sla,
            "status": publish_status
        }
    else:
        detail["publish_boundary"] = {"status": "WARN", "reason": "no_publish_timestamp"}
        publish_status = "WARN"
        
    # Tổng hợp trạng thái cuối cùng
    if "FAIL" in (ingest_status, publish_status):
        overall = "FAIL"
    elif "WARN" in (ingest_status, publish_status):
        overall = "WARN"
    else:
        overall = "PASS"
        
    return overall, detail
