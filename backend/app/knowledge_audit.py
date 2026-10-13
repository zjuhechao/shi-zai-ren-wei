from __future__ import annotations

import csv
import hashlib
from datetime import date
from pathlib import Path

from .document_loader import chunk_text, extract_text
from .retrieval import LocalKnowledgeBase, _validity


def audit_manifest(manifest: Path) -> dict:
    records = []
    seen = set()
    with manifest.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        record = {"document_id": row.get("document_id", ""), "title": row.get("title", ""), "source_url": row.get("source_url", ""), "local_file": row.get("local_file", ""), "status": "blocked", "chunks": 0}
        try:
            for field in ("document_id", "title", "category", "region", "source_url", "local_file", "acquisition_date"):
                if not (row.get(field) or "").strip():
                    raise ValueError(f"必填字段为空：{field}")
            if row["document_id"] in seen:
                raise ValueError("document_id重复，请先去重")
            seen.add(row["document_id"])
            path = LocalKnowledgeBase._resolve_source(manifest, row["local_file"])
            if not path.is_file():
                raise ValueError("本地文件不存在")
            text = extract_text(path)
            chunks = chunk_text(text)
            if not chunks:
                raise ValueError("未提取到文本")
            record.update(status="parseable", chunks=len(chunks), characters=len(text), checksum=hashlib.sha256(path.read_bytes()).hexdigest(), date_status=_validity(row, date.today()))
        except Exception as exc:
            record["reason"] = str(exc)
        records.append(record)
    return {
        "mode": "offline_audit_no_api_calls",
        "notice": "可解析不等于已入库、有效期已核验或已获云端处理授权。此预检不生成向量、不调用模型。",
        "manifest_records": len(records),
        "parseable_documents": sum(record["status"] == "parseable" for record in records),
        "blocked_documents": sum(record["status"] == "blocked" for record in records),
        "planned_chunks": sum(record["chunks"] for record in records),
        "records": records,
    }
