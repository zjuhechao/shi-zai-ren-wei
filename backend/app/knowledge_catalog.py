"""Reviewed upload boundary and customer-facing inventory; never serves source files."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .config import PROJECT_ROOT
from .knowledge_audit import audit_manifest
from .retrieval import LocalKnowledgeBase

REVIEW_FILE = PROJECT_ROOT / "data" / "knowledge" / "reviewed_documents.json"


def reviewed_ids(manifest: Path, review_path: Path = REVIEW_FILE) -> set[str]:
    if not review_path.is_file():
        raise ValueError("尚无已核对的上传名单；请先核对资料与授权，不会发送文件")
    approved = json.loads(review_path.read_text(encoding="utf-8"))["documents"]
    rows = {r["document_id"]: r for r in csv.DictReader(manifest.read_text(encoding="utf-8-sig").splitlines())}
    ids = set()
    for record in approved:
        doc_id = record["document_id"]
        row = rows.get(doc_id)
        if not row or not row.get("local_file"):
            raise ValueError(f"已核对资料缺失：{doc_id}，请重新核对")
        path = LocalKnowledgeBase._resolve_source(manifest, row["local_file"])
        if not path.is_relative_to(PROJECT_ROOT / "数据收集包"):
            raise ValueError(f"资料不在指定数据收集目录：{doc_id}")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record["checksum"]:
            raise ValueError(f"资料已变更：{doc_id}，请重新核对后再上传")
        if row["source_url"] != record["source_url"]:
            raise ValueError(f"资料来源已变更：{doc_id}，请重新核对")
        ids.add(doc_id)
    if not ids:
        raise ValueError("已核对的上传名单为空")
    return ids


def build_catalog(manifest: Path, metadatas: list[dict], review_path: Path = REVIEW_FILE) -> dict:
    audit = audit_manifest(manifest)
    rows = {r["document_id"]: r for r in csv.DictReader(manifest.read_text(encoding="utf-8-sig").splitlines())}
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.is_file() else {}
    approved = {r["document_id"]: r for r in review.get("documents", [])}
    excluded = review.get("excluded", {})
    indexed = {}
    for meta in metadatas:
        indexed.setdefault(meta.get("document_id"), []).append(meta)
    records = []
    for item in audit["records"]:
        doc_id = item["document_id"]
        metadata = indexed.get(doc_id, [])
        match_count = sum(m.get("checksum") == item.get("checksum") for m in metadata)
        allowed = approved.get(doc_id, {})
        reviewed = bool(allowed and allowed.get("checksum") == item.get("checksum") and allowed.get("source_url") == item["source_url"])
        complete = item["status"] == "parseable" and match_count == item["chunks"] and match_count == len(metadata)
        status = "indexed" if complete else "pending" if reviewed else "review" if item["status"] == "parseable" else "blocked"
        reason = "已入库，可检索；适用性仍须核对" if complete else item.get("reason") or excluded.get(doc_id) or ("已核对，等待入库" if reviewed else "尚未完成上传前核对")
        records.append({"document_id": doc_id, "title": item["title"], "source_url": item["source_url"],
                        "category": rows[doc_id]["category"], "region": rows[doc_id]["region"],
                        "status": status, "reason": reason, "indexed_chunks": match_count,
                        "planned_chunks": item["chunks"], "date_status": item.get("date_status", "unverified"),
                        "source_note": allowed.get("note", ""), "upload_reviewed": reviewed})
    return {"records": records, "total": len(records), "indexed_documents": sum(r["status"] == "indexed" for r in records),
            "indexed_chunks": sum(r["indexed_chunks"] for r in records), "reviewed_documents": sum(r["upload_reviewed"] for r in records),
            "blocked_documents": sum(r["status"] in {"blocked", "review"} for r in records),
            "notice": "入库状态不代表法律效力或项目适用性已核验。政府公开文件与市场参考价不能替代本项目实测、报价及授权。"}
