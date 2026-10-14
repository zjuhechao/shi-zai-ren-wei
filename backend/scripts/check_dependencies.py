"""Offline dependency integrity check used by the Windows startup script.

Only the selected public requirements file is read. No .env or cloud API is
used, and no packages are installed by this script.
"""
from __future__ import annotations

import argparse
import importlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import re

DIRECT_MODULES = ("fastapi", "uvicorn", "openai", "chromadb", "multipart", "dotenv",
                  "fitz", "docx", "reportlab", "httpx", "PIL")


def inspect_dependencies(requirements: Path, *, import_modules: bool = True) -> dict:
    records = []
    for line in requirements.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([A-Za-z0-9_.+!-]+)", line)
        if not match:
            raise ValueError("Expected a fully pinned requirements file")
        package, expected = match.groups()
        try:
            installed = version(package)
        except PackageNotFoundError:
            installed = None
        records.append({"package": package, "expected": expected, "installed": installed,
                        "passed": installed == expected})
    imports = []
    if records and all(record["passed"] for record in records) and import_modules:
        for module in DIRECT_MODULES:
            try:
                importlib.import_module(module)
                imports.append({"module": module, "passed": True})
            except Exception as exc:
                # Do not expose paths or configuration contents from exceptions.
                imports.append({"module": module, "passed": False, "error_type": type(exc).__name__})
    return {"mode": "offline_dependency_integrity_no_keys_no_api_calls",
            "passed": bool(records) and all(record["passed"] for record in records)
                      and all(record["passed"] for record in imports),
            "pinned_package_count": len(records), "packages": records, "imports": imports}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = inspect_dependencies(args.requirements)
    except Exception as exc:
        result = {"passed": False, "error_type": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)
