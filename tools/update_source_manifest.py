"""Mechanically refresh hashes for Git-tracked release files, never local secrets."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

MANIFEST = "release_files.sha256.json"
BLOCKED = {".git", ".venv", "storage", "__pycache__", "node_modules"}


def refresh(source: Path, date: str, revision: str) -> dict:
    source = source.resolve(strict=True)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or not re.fullmatch(r"r\d+", revision):
        raise ValueError("Use ISO date and r-number revision")
    result = subprocess.run(["git", "-C", str(source), "ls-files", "-z"], check=True, stdout=subprocess.PIPE)
    names = sorted(part.decode("utf-8") for part in result.stdout.split(b"\0") if part)
    if MANIFEST not in names:
        raise ValueError("Release manifest must be Git-tracked")
    records = []
    for name in names:
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
            raise ValueError("Unsafe tracked path")
        if BLOCKED.intersection(relative.parts) or relative.name == ".env":
            raise ValueError("Private/runtime file tracked: " + name)
        if relative.suffix.lower() == ".zip" and name != "downloads/app-windows-v0.6.1.zip":
            raise ValueError("Only the approved application ZIP may be tracked")
        if name == MANIFEST:
            continue
        path = source.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source):
            raise ValueError("Missing or symbolic-link file: " + name)
        content = path.read_bytes()
        records.append({"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    payload = {
        "schema": "tracked-source-release-sha256-v2", "release_version": "0.6.1",
        "release_date": date, "materials_revision": revision,
        "tracked_file_count": len(names), "hashed_file_count": len(records),
        "excluded_paths": [MANIFEST],
        "exclusion_reason": "Manifest does not hash itself; Git HEAD and archive hashes remain in an external verification record to avoid circular references.",
        "files": records,
    }
    (source / MANIFEST).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"tracked_files": len(names), "hashed_files": len(records), "local_secrets_read": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("."))
    parser.add_argument("--date", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    print(json.dumps(refresh(args.source, args.date, args.revision)))
