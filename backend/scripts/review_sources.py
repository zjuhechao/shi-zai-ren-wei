"""Offline content screening. Does not upload documents or expose credentials."""
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings
from app.document_loader import extract_text
from app.retrieval import LocalKnowledgeBase

PATTERNS = {
    "credential": r"sk-[A-Za-z0-9._-]{16,}|-----BEGIN .*PRIVATE KEY-----|(?i:api[_ -]?key\s*[:=]\s*\S+)",
    "identity_number": r"(?<!\d)[1-9]\d{5}(?:19|20)\d{9}[\dXx](?!\d)",
    "mobile": r"(?<!\d)1[3-9]\d{9}(?!\d)",
    "internal_personal": r"内部资料|不得外传|身份证|银行账号|开户账号|客户编号|户号|望月公寓|个人隐私|保密材料",
}

def main():
    settings = get_settings()
    rows = list(csv.DictReader(settings.knowledge_manifest.read_text(encoding="utf-8-sig").splitlines()))
    results = []
    for row in rows:
        item = {k: row[k] for k in ("document_id", "title", "source_url")}
        try:
            path = LocalKnowledgeBase._resolve_source(settings.knowledge_manifest, row["local_file"])
            text = extract_text(path)
            findings = {}
            for name, pattern in PATTERNS.items():
                matches = list(re.finditer(pattern, text))
                if matches:
                    findings[name] = [{"context": text[max(0,m.start()-45):m.start()] + "[MATCH REDACTED]" + text[m.end():m.end()+45]} for m in matches[:12]]
                    findings[name + "_count"] = len(matches)
            item.update(checksum=hashlib.sha256(path.read_bytes()).hexdigest(), characters=len(text), findings=findings,
                        beginning=text[:700], ending=text[-300:])
        except Exception as exc:
            item["blocked"] = str(exc)
        results.append(item)
    target = Path(__file__).resolve().parents[2] / "storage" / "source_content_screening.json"
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    # Source excerpts should not contain credentials even when screening detects one.
    output = json.dumps(results, ensure_ascii=False, indent=2)
    for pattern in list(PATTERNS.values())[:3]:
        output = re.sub(pattern, "[REDACTED]", output)
    print(output)

if __name__ == "__main__":
    main()
