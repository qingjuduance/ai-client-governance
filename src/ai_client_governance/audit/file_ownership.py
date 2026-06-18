#!/usr/bin/env python3
"""Audit host-project ownership for ``.ai-client`` files."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ai_client_governance.records import state_store


MANAGED_GITIGNORE_BEGIN = "# BEGIN AI Client Governance generated runtime"
MANAGED_GITIGNORE_END = "# END AI Client Governance generated runtime"

REQUIRED_GITIGNORE_PATTERNS = (
    ".ai-client/project/cache/",
    ".ai-client/project/tmp/",
    ".ai-client/project/logs/",
    ".ai-client/project/state/",
    ".ai-client/project/.worktree/",
    ".ai-client/project/doc-index/",
    ".ai-client/project/lifecycle/",
    ".ai-client/project/agents/comm/groups/",
    ".ai-client/project/agents/comm/locks.json",
    ".ai-client/project/agents/groups/",
)

FORBIDDEN_TRACKED_PREFIXES = (
    ".ai-client/project/cache/",
    ".ai-client/project/tmp/",
    ".ai-client/project/logs/",
    ".ai-client/project/state/",
    ".ai-client/project/.worktree/",
    ".ai-client/project/doc-index/",
    ".ai-client/project/lifecycle/",
    ".ai-client/project/agents/comm/groups/",
    ".ai-client/project/agents/groups/",
)

FORBIDDEN_TRACKED_FILES = {
    ".ai-client/project/agents/comm/locks.json",
}

ALLOWED_TRACKED_PREFIXES = (
    (".ai-client/project/rules/", "project-rules"),
    (".ai-client/project/skills/", "project-skills"),
    (".ai-client/project/tools/", "project-tools"),
    (".ai-client/project/records/task-tracking/", "project-human-records"),
    (".ai-client/project/records/pending-tasks/", "project-human-records"),
    (".ai-client/project/records/corrections/", "project-human-records"),
    (".ai-client/project/records/project-status/", "project-human-records"),
    (".ai-client/project/agents/briefs/", "project-agent-briefs"),
    (".ai-client/project/agents/comm/.references/", "project-agent-docs"),
)

ALLOWED_TRACKED_FILES = {
    ".ai-client/ai-client-governance-config.json": "governance-config",
    ".ai-client/project/agents/comm/README.md": "project-agent-docs",
}


@dataclass(frozen=True)
class Finding:
    level: str
    message: str
    path: str = ""
    category: str = ""


@dataclass(frozen=True)
class TrackedItem:
    mode: str
    object_id: str
    stage: str
    path: str
    category: str
    status: str
    reason: str


def normalized(value: str | Path) -> str:
    result = str(value).replace("\\", "/")
    while result.startswith("./"):
        result = result[2:]
    return result


def is_under(path: str, prefix: str) -> bool:
    clean_prefix = normalized(prefix).rstrip("/") + "/"
    return normalized(path).startswith(clean_prefix)


def git_output(root: Path, args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    command = ["git", "-c", "core.quotepath=false", "-C", str(root), *args]
    completed = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed: {completed.stderr.strip()}")
    return completed


def parse_ls_files_stage(output: str) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for raw_line in output.splitlines():
        if not raw_line.strip() or "\t" not in raw_line:
            continue
        meta, path = raw_line.split("\t", 1)
        parts = meta.split()
        if len(parts) < 3:
            continue
        rows.append((parts[0], parts[1], parts[2], normalized(path)))
    return rows


def classify_tracked(mode: str, path: str) -> tuple[str, str, str]:
    if path == ".ai-client/ai-client-governance":
        if mode == "160000":
            return "common-repo-gitlink", "ok", "host tracks only the embedded common repository commit"
        return "common-repo-normal-file", "error", "common repository must not be tracked as normal host files"
    if is_under(path, ".ai-client/ai-client-governance/"):
        return "common-repo-normal-file", "error", "common repository contents belong to the embedded Git repository"
    if path in FORBIDDEN_TRACKED_FILES:
        return "live-generated-state", "error", "generated runtime file must be local and ignored"
    for prefix in FORBIDDEN_TRACKED_PREFIXES:
        if is_under(path, prefix):
            return "live-generated-state", "error", "generated runtime directory must be local and ignored"
    if path in ALLOWED_TRACKED_FILES:
        return ALLOWED_TRACKED_FILES[path], "ok", "stable governance or project-owned file"
    for prefix, category in ALLOWED_TRACKED_PREFIXES:
        if is_under(path, prefix):
            return category, "ok", "stable project-owned governance asset"
    if is_under(path, ".ai-client/"):
        return "unknown-ai-client-tracked", "warning", "path is not covered by the ownership policy"
    return "outside-ai-client", "ok", "outside audit scope"


def gitignore_block() -> str:
    lines = [
        MANAGED_GITIGNORE_BEGIN,
        "# Local runtime state generated by ai-client-governance.",
        "# The host repository tracks stable adapters, project rules/tools/records,",
        "# and the embedded common repository gitlink, not live DBs or task worktrees.",
        *REQUIRED_GITIGNORE_PATTERNS,
        MANAGED_GITIGNORE_END,
    ]
    return "\n".join(lines)


def gitignore_status(root: Path) -> dict[str, object]:
    path = root / ".gitignore"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    begin = text.find(MANAGED_GITIGNORE_BEGIN)
    end = text.find(MANAGED_GITIGNORE_END)
    has_block = begin >= 0 and end >= begin
    block_text = text[begin : end + len(MANAGED_GITIGNORE_END)] if has_block else ""
    missing_patterns = [pattern for pattern in REQUIRED_GITIGNORE_PATTERNS if pattern not in block_text]
    return {
        "path": ".gitignore",
        "exists": path.exists(),
        "managed_block_present": has_block,
        "missing_patterns": missing_patterns,
        "status": "ok" if has_block and not missing_patterns else "missing" if not has_block else "outdated",
        "required_patterns": list(REQUIRED_GITIGNORE_PATTERNS),
    }


def ensure_gitignore_text(existing: str) -> tuple[str, str]:
    block = gitignore_block()
    pattern = re.compile(
        re.escape(MANAGED_GITIGNORE_BEGIN) + r"[\s\S]*?" + re.escape(MANAGED_GITIGNORE_END),
        re.MULTILINE,
    )
    if pattern.search(existing):
        updated = pattern.sub(block, existing, count=1)
        action = "unchanged" if updated == existing else "updated"
        return updated, action
    prefix = existing.rstrip()
    updated = f"{prefix}\n\n{block}\n" if prefix else f"{block}\n"
    return updated, "created"


def ensure_gitignore(root: Path, *, execute: bool) -> dict[str, object]:
    path = root / ".gitignore"
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    updated, action = ensure_gitignore_text(existing)
    changed = updated != existing
    if execute and changed:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return {
        "path": ".gitignore",
        "execute": execute,
        "changed": changed,
        "action": "unchanged" if not changed else action,
        "required_patterns": list(REQUIRED_GITIGNORE_PATTERNS),
    }


def ignored_status(root: Path) -> list[str]:
    completed = git_output(root, ["status", "--ignored", "--short", "--", ".ai-client", ".gitignore"])
    ignored: list[str] = []
    if completed.returncode != 0:
        return ignored
    for line in completed.stdout.splitlines():
        if line.startswith("!! "):
            ignored.append(normalized(line[3:].strip()))
    return ignored


def build_report(root: Path, *, max_samples: int = 20, record_state: bool = False, db: str | None = None) -> dict[str, object]:
    errors: list[Finding] = []
    warnings: list[Finding] = []
    notes: list[str] = []
    tracked_items: list[TrackedItem] = []
    category_counts: Counter[str] = Counter()
    category_samples: dict[str, list[str]] = defaultdict(list)

    top_level = git_output(root, ["rev-parse", "--show-toplevel"])
    if top_level.returncode != 0:
        errors.append(Finding("error", "root is not a Git worktree", root.as_posix(), "git"))
    else:
        detected = Path(top_level.stdout.strip()).resolve()
        if detected != root.resolve():
            warnings.append(
                Finding(
                    "warning",
                    "audit root is inside a nested Git worktree; pass the host project root explicitly",
                    detected.as_posix(),
                    "git",
                )
            )

    ls_files = git_output(root, ["ls-files", "--stage", "--", ".ai-client", ".gitignore", ".gitmodules"])
    if ls_files.returncode == 0:
        for mode, object_id, stage, path in parse_ls_files_stage(ls_files.stdout):
            category, status, reason = classify_tracked(mode, path)
            if category == "outside-ai-client":
                continue
            item = TrackedItem(mode, object_id, stage, path, category, status, reason)
            tracked_items.append(item)
            category_counts[category] += 1
            if len(category_samples[category]) < max_samples:
                category_samples[category].append(path)
            if status == "error":
                errors.append(Finding("error", reason, path, category))
            elif status == "warning":
                warnings.append(Finding("warning", reason, path, category))
    else:
        errors.append(Finding("error", "git ls-files failed", ".ai-client", "git"))

    ignore = gitignore_status(root)
    if ignore["status"] != "ok":
        errors.append(
            Finding(
                "error",
                "required .gitignore managed block is missing or outdated",
                ".gitignore",
                "gitignore",
            )
        )

    ignored_paths = ignored_status(root)
    for path in ignored_paths[:max_samples]:
        notes.append(f"ignored generated path: {path}")

    report: dict[str, object] = {
        "schema_version": 1,
        "root": root.as_posix(),
        "gitignore": ignore,
        "tracked_total": len(tracked_items),
        "tracked_category_counts": dict(sorted(category_counts.items())),
        "tracked_category_samples": {key: value for key, value in sorted(category_samples.items())},
        "ignored_untracked_count": len(ignored_paths),
        "ignored_untracked_samples": ignored_paths[:max_samples],
        "forbidden_tracked": [asdict(item) for item in tracked_items if item.status == "error"],
        "warnings": [asdict(item) for item in warnings],
        "errors": [asdict(item) for item in errors],
        "notes": notes,
        "policy": {
            "host_tracks": [
                ".ai-client/ai-client-governance gitlink only",
                ".ai-client/ai-client-governance-config.json",
                ".ai-client/project/rules/",
                ".ai-client/project/skills/",
                ".ai-client/project/tools/",
                ".ai-client/project/records/",
                ".ai-client/project/agents/briefs/",
            ],
            "host_ignores": list(REQUIRED_GITIGNORE_PATTERNS),
        },
    }
    if record_state:
        with state_store.connect(state_store.db_path(root, db), create=True) as con:
            state_store.upsert_state(
                con,
                state_type="file-ownership-audit",
                state_key="host-project",
                payload=report,
                source_command="ai_client_governance.py file-ownership audit --record-state",
                summary=(
                    f"tracked={len(tracked_items)} forbidden={len(report['forbidden_tracked'])} "
                    f"ignored={len(ignored_paths)} gitignore={ignore['status']}"
                ),
                event_type="file-ownership.audit",
            )
    return report


def render_audit_text(report: dict[str, object]) -> str:
    lines = [
        "AI Client Governance File Ownership Audit",
        f"Root: {report['root']}",
        f"Tracked .ai-client files: {report['tracked_total']}",
        f"Ignored generated paths: {report['ignored_untracked_count']}",
        f"Gitignore managed block: {report['gitignore']['status']}",
        "Tracked categories:",
    ]
    counts = report["tracked_category_counts"]
    if isinstance(counts, dict) and counts:
        for category, count in counts.items():
            lines.append(f"  - {category}: {count}")
    else:
        lines.append("  - none")
    errors = report["errors"]
    warnings = report["warnings"]
    lines.append(f"Errors: {len(errors)}")
    for item in errors:
        lines.append(f"  - {item['message']} [{item.get('path', '')}]")
    lines.append(f"Warnings: {len(warnings)}")
    for item in warnings:
        lines.append(f"  - {item['message']} [{item.get('path', '')}]")
    samples = report["tracked_category_samples"]
    if isinstance(samples, dict):
        for category, paths in samples.items():
            if not paths:
                continue
            lines.append(f"Sample {category}:")
            for path in paths[:5]:
                lines.append(f"  - {path}")
    return "\n".join(lines)


def render_ensure_text(report: dict[str, object]) -> str:
    mode = "executed" if report["execute"] else "planned"
    return "\n".join(
        [
            "AI Client Governance Gitignore Management",
            f"Path: {report['path']}",
            f"Mode: {mode}",
            f"Action: {report['action']}",
            f"Changed: {str(report['changed']).lower()}",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit .ai-client host-project file ownership.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="Audit tracked and ignored .ai-client paths.")
    audit.add_argument("--root", default=".", help="Host project root. Default: current directory.")
    audit.add_argument("--format", choices=("text", "json"), default="text")
    audit.add_argument("--strict", action="store_true", help="Exit non-zero on errors or warnings.")
    audit.add_argument("--max-samples", type=int, default=20)
    audit.add_argument("--record-state", action="store_true", help="Record the audit summary in aicg.db.")
    audit.add_argument("--db", help="SQLite state DB path. Default: <root>/.ai-client/project/state/aicg.db.")

    ensure = subparsers.add_parser("ensure-gitignore", help="Create or update the managed .gitignore block.")
    ensure.add_argument("--root", default=".", help="Host project root. Default: current directory.")
    ensure.add_argument("--execute", action="store_true", help="Write .gitignore. Without this flag, only plan.")
    ensure.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    if args.command == "audit":
        report = build_report(root, max_samples=args.max_samples, record_state=args.record_state, db=args.db)
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(render_audit_text(report))
        has_errors = bool(report["errors"])
        has_warnings = bool(report["warnings"])
        return 1 if has_errors or (args.strict and has_warnings) else 0
    if args.command == "ensure-gitignore":
        report = ensure_gitignore(root, execute=args.execute)
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(render_ensure_text(report))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
