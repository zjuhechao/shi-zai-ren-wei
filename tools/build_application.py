"""Build an allowlisted, deterministic Windows source-type application ZIP.

This script never reads backend/.env, Git credentials, storage, or .venv.
Use it after regenerating release_files.sha256.json in the source checkout.
The ZIP contains runtime files plus user guides, not a bundled Python runtime.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


VERSION = "0.6.2"
FIXED_DATE = (2026, 10, 21, 0, 0, 0)
TOP_LEVEL = "shi-zai-ren-wei-app-v" + VERSION
MANIFEST_NAME = "application_manifest.sha256.json"

ROOT_ALLOWLIST = {
    ".gitignore",
    "app.js", "client-ui.js", "index.html", "styles.css",
    "charts.js", "ux.js", "ux.css",
    "启动演示.bat", "启动演示.ps1", "configure-keys.bat", "configure-keys.ps1",
    "backend/.env.example", "backend/run.py", "backend/requirements.txt",
    "backend/requirements-lock.windows-py312.txt",
    "backend/app/__init__.py", "backend/app/main.py", "backend/app/config.py",
    "backend/app/agent.py", "backend/app/calculators.py", "backend/app/schemas.py",
    "backend/app/retrieval.py", "backend/app/document_loader.py", "backend/app/knowledge_audit.py",
    "backend/app/knowledge_catalog.py", "backend/app/plan_service.py", "backend/app/plan_schemas.py",
    "backend/app/plan_pdf.py", "backend/app/safety.py", "backend/app/request_limits.py",
    "backend/scripts/check_dependencies.py", "backend/scripts/configure_secrets.py",
    "data/cases/wangyue_case.json", "data/cases/assumption_demo.json", "data/knowledge/reviewed_documents.json",
    "数据收集包/08_已整理结构化数据/knowledge_manifest.csv",
    "assets/reports/qinghe_plan_demo.pdf",
    "docs/API与平台操作清单.md", "docs/下载后运行与配置.md",
    "docs/技术架构_v0.6.2.svg", "docs/技术说明_v0.6.2.pdf",
    "docs/数据与材料收集清单.md",
}
PREFIX_ALLOWLIST = (
    "backend/app/", "backend/scripts/", "data/cases/",
    "data/knowledge/", "data/templates/", "数据收集包/",
)
WRAPPERS = ("start-app.bat", "start-app.ps1", "开始使用.txt", "开始使用.html")
BLOCKED_PARTS = {".git", ".venv", "storage", "__pycache__", "tests", "node_modules"}
KEY_PATTERN = re.compile(rb"sk-[A-Za-z0-9_.-]{16,}")


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def safe_relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (not name or name != path.as_posix() or path.is_absolute() or ".." in path.parts
            or "\\" in name or ":" in name or any(ord(char) < 32 for char in name)):
        raise ValueError("Unsafe relative path: " + name)
    if BLOCKED_PARTS.intersection(part.casefold() for part in path.parts) or path.name.casefold() == ".env":
        raise ValueError("Forbidden runtime/private path: " + name)
    for part in path.parts:
        if (part.endswith((".", " ")) or any(char in part for char in '<>"|?*')
                or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.IGNORECASE)):
            raise ValueError("Unsafe Windows path: " + name)
    return path


def build_application(source: Path, templates: Path, output: Path) -> dict:
    source = source.resolve(strict=True)
    templates = templates.resolve(strict=True)
    source_manifest = json.loads((source / "release_files.sha256.json").read_text(encoding="utf-8-sig"))
    if source_manifest.get("release_version") != VERSION:
        raise ValueError("Unexpected source release version")
    entries = source_manifest["files"]
    names = [entry["path"] for entry in entries]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate source manifest paths")
    if MANIFEST_NAME in names or any(name.startswith("downloads/") for name in names):
        # A repository may later track downloadable ZIPs. They are not runtime
        # input and must never be copied recursively into a newly built ZIP.
        names = [name for name in names if name != MANIFEST_NAME and not name.startswith("downloads/")]
    by_name = {entry["path"]: entry for entry in entries}
    selected = {
        name for name in names
        if name in ROOT_ALLOWLIST or any(name.startswith(prefix) for prefix in PREFIX_ALLOWLIST)
    }
    if ROOT_ALLOWLIST - selected:
        raise ValueError("Missing application files: " + ", ".join(sorted(ROOT_ALLOWLIST - selected)))
    contents: dict[str, bytes] = {}
    file_records = []
    for name in sorted(selected):
        relative = safe_relative(name)
        path = source.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source):
            raise ValueError("Missing or symlinked source file: " + name)
        data = path.read_bytes()
        expected = by_name[name]
        if len(data) != expected["bytes"] or sha256(data) != expected["sha256"]:
            raise ValueError("Source manifest mismatch: " + name)
        if KEY_PATTERN.search(data):
            raise ValueError("Credential-like content blocked: " + name)
        if relative.suffix == ".py":
            ast.parse(data.decode("utf-8-sig"), filename=name)
        contents[name] = data
        file_records.append({"path": name, "bytes": len(data), "sha256": sha256(data), "origin": "tracked_source"})
    for name in WRAPPERS:
        safe_relative(name)
        wrapper_path = templates / name
        if (wrapper_path.is_symlink() or not wrapper_path.is_file()
                or not wrapper_path.resolve().is_relative_to(templates)):
            raise ValueError("Missing or symlinked wrapper: " + name)
        data = wrapper_path.read_bytes()
        if KEY_PATTERN.search(data):
            raise ValueError("Credential-like wrapper content blocked")
        if name.endswith((".bat", ".ps1")) and not data.isascii():
            raise ValueError("New Windows entry-point wrappers must remain ASCII")
        contents[name] = data
        file_records.append({"path": name, "bytes": len(data), "sha256": sha256(data), "origin": "application_wrapper"})
    env = contents["backend/.env.example"].decode("utf-8-sig")
    for key in ("LLM_API_KEY", "EMBEDDING_API_KEY"):
        if not re.search(rf"^{key}=[ \t]*\r?$", env, flags=re.MULTILINE):
            raise ValueError("Key template must be blank: " + key)
    manifest = {
        "schema": "source-type-windows-application-sha256-v1",
        "application_version": VERSION,
        "package_revision": "r4",
        "package_date": "2026-10-21",
        "platform": "Windows x64; Python 3.12 tested release route",
        "package_type": "source-type local application; Python runtime and dependencies not bundled",
        "repository": "https://github.com/zjuhechao/shi-zai-ren-wei",
        # Hash only the selected unchanged-source records. Never embed a hash
        # of a repository manifest that might itself hash this generated ZIP.
        "source_selection_sha256": sha256(json.dumps(
            sorted(file_records[:len(selected)], key=lambda record: record["path"]),
            ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")),
        "source_file_count": len(selected),
        "wrapper_file_count": len(WRAPPERS),
        "hashed_file_count": len(file_records),
        "zip_file_count": len(file_records) + 1,
        "excluded_paths": [MANIFEST_NAME],
        "notice": "The manifest does not hash itself. API keys, Python runtime, installed dependencies, private material, original vector store, development tests and Git metadata are not included.",
        "files": sorted(file_records, key=lambda record: record["path"]),
    }
    contents[MANIFEST_NAME] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len({name.casefold() for name in contents}) != len(contents):
        raise ValueError("Case-insensitive application path collision")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing application ZIP: " + str(output))
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(contents):
            entry = ZipInfo(TOP_LEVEL + "/" + name, date_time=FIXED_DATE)
            entry.compress_type = ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, contents[name], compress_type=ZIP_DEFLATED, compresslevel=9)
    result = audit_zip(output)
    # External audit record can record the input manifest without making the
    # generated application archive recursively depend on its own hash.
    result["source_manifest_sha256"] = sha256((source / "release_files.sha256.json").read_bytes())
    result["source_selection_sha256"] = manifest["source_selection_sha256"]
    result["source_file_count"] = len(selected)
    result["wrapper_file_count"] = len(WRAPPERS)
    result["excluded_source_paths"] = sorted(set(by_name) - selected)
    return result


def audit_zip(path: Path) -> dict:
    checks = []
    with ZipFile(path) as archive:
        corrupt = archive.testzip()
        if corrupt:
            raise ValueError("Corrupt ZIP entry: " + corrupt)
        names = archive.namelist()
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError("Duplicate or case-insensitive ZIP entries")
        prefix = TOP_LEVEL + "/"
        for name in names:
            if not name.startswith(prefix):
                raise ValueError("ZIP has unexpected root")
            safe_relative(name[len(prefix):])
            if ((archive.getinfo(name).external_attr >> 16) & 0o170000) != 0o100000:
                raise ValueError("ZIP entries must be regular files")
        manifest = json.loads(archive.read(prefix + MANIFEST_NAME))
        if (manifest.get("application_version") != VERSION or manifest.get("package_revision") != "r4"
                or manifest.get("schema") != "source-type-windows-application-sha256-v1"):
            raise ValueError("Unexpected application manifest version or schema")
        manifest_names = [record["path"] for record in manifest["files"]]
        if len(set(manifest_names)) != len(manifest_names):
            raise ValueError("Duplicate application manifest paths")
        if (manifest.get("hashed_file_count") != len(manifest_names)
                or manifest.get("zip_file_count") != len(names)
                or manifest.get("source_file_count", 0) + manifest.get("wrapper_file_count", 0) != len(manifest_names)
                or manifest.get("excluded_paths") != [MANIFEST_NAME]):
            raise ValueError("Application manifest declarations are inconsistent")
        expected = {prefix + record["path"] for record in manifest["files"]} | {prefix + MANIFEST_NAME}
        if set(names) != expected:
            raise ValueError("Unexpected or missing ZIP files")
        for record in manifest["files"]:
            safe_relative(record["path"])
            data = archive.read(prefix + record["path"])
            if len(data) != record["bytes"] or sha256(data) != record["sha256"]:
                raise ValueError("Application manifest mismatch: " + record["path"])
            if KEY_PATTERN.search(data):
                raise ValueError("Credential-like content blocked: " + record["path"])
            if PurePosixPath(record["path"]).suffix.lower() == ".zip":
                raise ValueError("Nested archives are not application runtime files")
        checks.extend(["zip_crc", "single_root", "safe_paths", "regular_files_only", "no_private_runtime_paths",
                       "manifest_complete", "manifest_declarations_consistent", "all_sha256_match", "no_credential_patterns", "no_nested_archives"])
    return {
        "passed": True, "mode": "offline_file_packaging_no_cloud_calls",
        "application_version": VERSION, "zip_path": str(path.resolve()),
        "zip_file_count": len(names), "zip_bytes": path.stat().st_size,
        "zip_sha256": sha256(path.read_bytes()), "checks": checks,
        "not_tested": ["another_computer_installation", "new_dependency_download", "remote_API_connectivity", "new_RAG_ingestion", "public_deployment"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Clean source checkout with current release_files.sha256.json")
    parser.add_argument("--templates", type=Path, default=Path(__file__).resolve().parent / "templates")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--record", required=True, type=Path)
    args = parser.parse_args()
    result = build_application(args.source, args.templates, args.output)
    args.record.parent.mkdir(parents=True, exist_ok=True)
    args.record.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
