from __future__ import annotations

import csv
import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .config import PROJECT_ROOT, Settings, require_embedding_settings
from .document_loader import chunk_text, extract_text


def _batches(items: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _collection_name(settings: Settings) -> str:
    identity = f"{settings.embedding_provider}:{settings.embedding_base_url}:{settings.embedding_model}:{settings.embedding_dimensions or 'default'}"
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
    return f"low_carbon_knowledge_{suffix}"


def _validity(metadata: dict[str, Any], on_date: date) -> str:
    """Only assess the supplied dates; this is not a legal validity determination."""
    bounds = []
    for field in ("effective_from", "effective_to"):
        raw = str(metadata.get(field) or "").strip()
        try:
            bounds.append(date.fromisoformat(raw) if raw else None)
        except ValueError:
            return "unverified"
    start, end = bounds
    if start and end and start > end:
        return "unverified"
    if (start and on_date < start) or (end and on_date > end):
        return "outside_recorded_interval"
    return "within_recorded_interval" if start and end else "unverified"


def _region_matches(document_region: str, requested_region: str | None) -> bool:
    if not requested_region:
        return True
    parts = [part.strip() for part in re.split(r"[/、,，;；|]", document_region) if part.strip()]
    if not parts:
        return False
    return any(part in {"全国", "通用"} or part in requested_region or requested_region in part for part in parts)


class LocalKnowledgeBase:
    """本地 Chroma 持久化向量库；向量来自独立、可核验的嵌入服务。"""

    def __init__(self, settings: Settings):
        require_embedding_settings(settings)
        try:
            import chromadb
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("请先安装 backend/requirements.txt 中的依赖") from exc
        settings.chroma_path.mkdir(parents=True, exist_ok=True)
        self.settings = settings
        self.embedding_client = OpenAI(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            timeout=60,
            max_retries=1,
        )
        self.client = chromadb.PersistentClient(path=str(settings.chroma_path))
        self.collection = self.client.get_or_create_collection(
            name=_collection_name(settings),
            embedding_function=None,
            metadata={
                "hnsw:space": "cosine",
                "description": "既有建筑低碳改造知识库",
                "embedding_model": settings.embedding_model,
            },
        )

    def count(self) -> int:
        return int(self.collection.count())

    def _embed(self, texts: list[str]) -> list[list[float]]:
        kwargs: dict[str, Any] = {"model": self.settings.embedding_model, "input": texts, "encoding_format": "float"}
        if self.settings.embedding_dimensions:
            kwargs["dimensions"] = self.settings.embedding_dimensions
        response = self.embedding_client.embeddings.create(**kwargs)
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    @staticmethod
    def _resolve_source(manifest_path: Path, value: str) -> Path:
        source_path = Path(value.replace("\\", "/"))
        if source_path.is_absolute():
            return source_path
        candidates = [
            manifest_path.parent / source_path,
            manifest_path.parent.parent / source_path,
            PROJECT_ROOT / source_path,
        ]
        return next((candidate.resolve() for candidate in candidates if candidate.exists()), candidates[0].resolve())

    def ingest_manifest(self, manifest_path: Path | None = None, *, document_ids: set[str] | None = None, skip_unchanged: bool = False) -> dict[str, Any]:
        manifest_path = manifest_path or self.settings.knowledge_manifest
        if not manifest_path.exists():
            raise FileNotFoundError(f"知识库索引不存在：{manifest_path}")
        rows = list(csv.DictReader(manifest_path.read_text(encoding="utf-8-sig").splitlines()))
        required = {"document_id", "title", "category", "region", "source_url", "local_file", "acquisition_date"}
        missing_headers = sorted(required.difference(rows[0].keys() if rows else []))
        if missing_headers:
            raise ValueError(f"knowledge_manifest.csv缺少字段：{', '.join(missing_headers)}")

        if document_ids is not None:
            unknown = document_ids.difference(row["document_id"] for row in rows)
            if not document_ids or unknown:
                raise ValueError("请提供清单中存在的document_id；未发送任何文档")

        indexed_documents = 0
        indexed_chunks = 0
        unchanged_documents = 0
        skipped: list[dict[str, str]] = []
        for row_number, row in enumerate(rows, start=2):
            if document_ids is not None and row["document_id"] not in document_ids:
                continue
            missing = [key for key in required if not (row.get(key) or "").strip()]
            if missing:
                skipped.append({"row": str(row_number), "reason": f"字段为空：{', '.join(sorted(missing))}"})
                continue
            source_path = self._resolve_source(manifest_path, row["local_file"])
            if not source_path.exists():
                skipped.append({"row": str(row_number), "reason": f"文件不存在：{source_path}"})
                continue
            try:
                chunks = chunk_text(extract_text(source_path))
            except Exception as exc:
                skipped.append({"row": str(row_number), "reason": str(exc)})
                continue
            if not chunks:
                skipped.append({"row": str(row_number), "reason": "文档未提取到可用文本"})
                continue

            version = (row.get("version") or row.get("effective_from") or "未标注版本").strip()
            checksum = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if skip_unchanged:
                existing = self.collection.get(where={"document_id": row["document_id"]}, include=["metadatas"])
                if len(existing["ids"]) == len(chunks) and all(m.get("checksum") == checksum and m.get("version") == version for m in existing["metadatas"]):
                    unchanged_documents += 1
                    continue
            base_metadata = {
                "document_id": row["document_id"],
                "title": row["title"],
                "category": row["category"],
                "region": row["region"],
                "effective_from": row.get("effective_from", ""),
                "effective_to": row.get("effective_to", ""),
                "issuing_body": row.get("issuing_body", ""),
                "source_url": row["source_url"],
                "local_file": str(source_path),
                "version": version,
                "acquisition_date": row["acquisition_date"],
                "checksum": checksum,
            }
            for batch_start, batch in enumerate(_batches(chunks, self.settings.embedding_batch_size)):
                embeddings = self._embed(batch)
                ids = []
                metadatas = []
                for offset, _ in enumerate(batch):
                    chunk_index = batch_start * self.settings.embedding_batch_size + offset
                    stable = f"{row['document_id']}:{version}:{chunk_index}"
                    ids.append(hashlib.sha256(stable.encode("utf-8")).hexdigest())
                    metadatas.append({**base_metadata, "chunk_index": chunk_index})
                self.collection.upsert(ids=ids, embeddings=embeddings, documents=batch, metadatas=metadatas)
                indexed_chunks += len(batch)
            # Remove obsolete chunks for this document only after successful re-indexing.
            current_ids = {
                hashlib.sha256(f"{row['document_id']}:{version}:{index}".encode("utf-8")).hexdigest()
                for index in range(len(chunks))
            }
            previous = self.collection.get(where={"document_id": row["document_id"]}, include=[])
            obsolete = [item for item in previous["ids"] if item not in current_ids]
            if obsolete:
                self.collection.delete(ids=obsolete)
            indexed_documents += 1
        return {
            "indexed_documents": indexed_documents,
            "unchanged_documents": unchanged_documents,
            "indexed_chunks": indexed_chunks,
            "collection_count": self.count(),
            "skipped": skipped,
            "embedding_model": self.settings.embedding_model,
        }

    def search(self, query: str, *, region: str | None = None, category: str | None = None, top_k: int = 6) -> list[dict[str, Any]]:
        if not query.strip():
            raise ValueError("检索问题不能为空")
        if not isinstance(top_k, int) or not 1 <= top_k <= 10:
            raise ValueError("top_k必须为1至10的整数")
        if self.count() == 0:
            return []
        checked_on = date.today()
        normalized_category = {"政策": "policy", "标准": "standard", "电价": "tariff", "碳因子": "factor", "材料": "material", "报告": "report"}.get(category, category)
        eligible_documents = set()
        eligible_chunks = 0
        for metadata in self.collection.get(include=["metadatas"])["metadatas"]:
            if _validity(metadata, checked_on) == "outside_recorded_interval":
                continue
            if normalized_category and metadata.get("category") not in {normalized_category, "综合"}:
                continue
            if not _region_matches(str(metadata.get("region", "")), region):
                continue
            if metadata.get("document_id"):
                eligible_documents.add(metadata["document_id"])
                eligible_chunks += 1
        if not eligible_documents:
            return []
        embedding = self._embed([query])[0]
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, eligible_chunks),
            where={"document_id": {"$in": sorted(eligible_documents)}},
            include=["documents", "metadatas", "distances"],
        )
        candidates = []
        for document, metadata, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
            validity = _validity(metadata, checked_on)
            if validity == "outside_recorded_interval":
                continue
            if normalized_category and metadata.get("category") not in {normalized_category, "综合"}:
                continue
            doc_region = str(metadata.get("region", ""))
            if not _region_matches(doc_region, region):
                continue
            candidates.append(
                {
                    "content": re.sub(r"\s+", " ", document).strip(),
                    "score": round(1.0 - float(distance), 6),
                    "document_id": metadata.get("document_id"),
                    "title": metadata.get("title"),
                    "category": metadata.get("category"),
                    "region": metadata.get("region"),
                    "effective_from": metadata.get("effective_from"),
                    "effective_to": metadata.get("effective_to"),
                    "validity_status": validity,
                    "validity_checked_on": checked_on.isoformat(),
                    "issuing_body": metadata.get("issuing_body"),
                    "source_url": metadata.get("source_url"),
                    "version": metadata.get("version"),
                    "checksum": metadata.get("checksum"),
                    "chunk_index": metadata.get("chunk_index"),
                }
            )
            if len(candidates) >= top_k:
                break
        return candidates
