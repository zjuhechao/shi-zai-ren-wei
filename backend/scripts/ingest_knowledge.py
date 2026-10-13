from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings  # noqa: E402
from app.retrieval import LocalKnowledgeBase  # noqa: E402
from app.knowledge_audit import audit_manifest  # noqa: E402
from app.knowledge_catalog import reviewed_ids  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-only", action="store_true", help="Parse local files only; no API calls or vector writes")
    parser.add_argument("--output", type=Path, help="Save the audit or ingestion report")
    parser.add_argument("--document-id", action="append", help="Ingest only the specified manifest document ID; repeat for multiple authorized documents")
    parser.add_argument("--reviewed", action="store_true", help="Require every selected document to match reviewed hashes and skip unchanged documents")
    args = parser.parse_args()
    settings = get_settings()
    if args.audit_only and args.document_id:
        parser.error("--document-id is for ingestion; --audit-only audits the full manifest")
    selected = set(args.document_id or [])
    if not args.audit_only:
        if not selected:
            parser.error("Ingestion requires an explicit --document-id allowlist; no documents sent")
        if args.reviewed and not selected.issubset(reviewed_ids(settings.knowledge_manifest)):
            parser.error("Selection includes documents outside the reviewed allowlist; no documents sent")
    result = audit_manifest(settings.knowledge_manifest) if args.audit_only else LocalKnowledgeBase(settings).ingest_manifest(document_ids=selected, skip_unchanged=args.reviewed)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
