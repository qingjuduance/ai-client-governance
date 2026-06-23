#!/usr/bin/env python3
"""Compact session bootstrap for rule entry and sync facts.

This command is the default safe replacement for dumping long AGENTS.md files
into the terminal at session start. It verifies the rule entry files, reports
bounded metadata and headings, and runs sync-check without pull or push.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ai_client_governance.common.paths import (
    COMMON_REPO_PATH,
    PROJECT_RULES_ENTRY,
    ai_client_governance_root,
    host_project_root,
)
from ai_client_governance.io.context_extract import HEADING_RE
from ai_client_governance.sync import check as sync_check


@dataclass(frozen=True)
class HeadingSummary:
    line: int
    level: int
    title: str


@dataclass(frozen=True)
class RuleFileSummary:
    role: str
    path: str
    exists: bool
    line_count: int = 0
    byte_count: int = 0
    sha256: str = ""
    heading_count: int = 0
    headings: list[HeadingSummary] | None = None
    warning: str = ""


@dataclass(frozen=True)
class BootstrapReport:
    status: str
    requested_root: str
    project_root: str
    governance_root: str
    rule_files: list[RuleFileSummary]
    read_policy: list[str]
    sync_check: dict[str, Any]
    warnings: list[str]
    next_commands: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print compact session-start rule and sync facts without dumping long rule files.",
    )
    parser.add_argument("--root", default=".", help="Project or embedded governance root. Default: current directory.")
    parser.add_argument("--root-entry", help="Override native/root AGENTS.md path.")
    parser.add_argument("--governance-entry", help="Override embedded governance AGENTS.md path.")
    parser.add_argument("--project-entry", help="Override project AGENTS.md path.")
    parser.add_argument("--db", help="SQLite DB path forwarded to sync-check.")
    parser.add_argument("--max-headings", type=int, default=12, help="Maximum headings per file in output.")
    parser.add_argument("--no-headings", action="store_true", help="Only show metadata, not heading indexes.")
    parser.add_argument("--no-sync-check", action="store_true", help="Skip sync-check and only summarize rule files.")
    parser.add_argument("--no-fetch", action="store_true", help="Forward --no-fetch to sync-check.")
    parser.add_argument("--force-fetch", action="store_true", help="Forward --force-fetch to sync-check.")
    parser.add_argument("--fail-on-warning", action="store_true", help="Exit non-zero when warnings are present.")
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    return parser.parse_args()


def resolve_relative(root: Path, value: str | None, default: Path) -> Path:
    if not value:
        return default.resolve()
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def resolve_governance_root(requested_root: Path, project_root: Path) -> Path:
    embedded = (project_root / COMMON_REPO_PATH).resolve()
    if (embedded / "AGENTS.md").exists():
        return embedded
    if (requested_root / "AGENTS.md").exists() and (requested_root / "src" / "ai_client_governance").exists():
        return requested_root.resolve()
    return ai_client_governance_root().resolve()


def read_rule_file(
    role: str,
    project_root: Path,
    path: Path,
    *,
    include_headings: bool,
    heading_limit: int,
) -> RuleFileSummary:
    if not path.exists():
        return RuleFileSummary(
            role=role,
            path=display_path(project_root, path),
            exists=False,
            warning=f"{role} rule file missing",
            headings=[],
        )
    data = path.read_bytes()
    text = data.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    headings: list[HeadingSummary] = []
    heading_count = 0
    if include_headings:
        for index, line in enumerate(lines, start=1):
            match = HEADING_RE.match(line)
            if not match:
                continue
            heading_count += 1
            if len(headings) < max(0, heading_limit):
                headings.append(
                    HeadingSummary(
                        line=index,
                        level=len(match.group(1)),
                        title=match.group(2).strip(),
                    )
                )
    return RuleFileSummary(
        role=role,
        path=display_path(project_root, path),
        exists=True,
        line_count=len(lines),
        byte_count=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        heading_count=heading_count,
        headings=headings,
    )


def run_sync_report(args: argparse.Namespace, project_root: Path, governance_root: Path) -> dict[str, Any]:
    if args.no_sync_check:
        return {
            "status": "skipped",
            "warnings": [],
            "notes": ["sync-check skipped by --no-sync-check"],
            "next_actions": [],
        }
    sync_args = argparse.Namespace(
        target_project_path=str(project_root),
        embedded_repo_path=str(governance_root),
        config_path=None,
        fetch_interval_hours=24,
        remote_name="origin",
        db=args.db,
        force_fetch=bool(args.force_fetch),
        no_fetch=bool(args.no_fetch),
        fail_on_warning=False,
        format="json",
    )
    return asdict(sync_check.check_sync(sync_args))


def safe_commands() -> list[str]:
    entry = ".ai-client/ai-client-governance/scripts/ai_client_governance.py"
    return [
        f"python {entry} session-bootstrap --root .",
        (
            f"python {entry} context-extract --headings --max-lines 120 "
            ".ai-client/ai-client-governance/AGENTS.md .ai-client/project/rules/project/AGENTS.md"
        ),
        (
            f"python {entry} context-extract --range 1:80 --max-lines 80 "
            ".ai-client/ai-client-governance/AGENTS.md"
        ),
        f"python {entry} sync-check --target-project-path .",
    ]


def build_report(args: argparse.Namespace) -> BootstrapReport:
    requested_root = Path(args.root).resolve()
    project_root = host_project_root(requested_root).resolve()
    governance_root = resolve_governance_root(requested_root, project_root)
    root_entry = resolve_relative(project_root, args.root_entry, project_root / "AGENTS.md")
    governance_entry = resolve_relative(project_root, args.governance_entry, governance_root / "AGENTS.md")
    project_entry = resolve_relative(project_root, args.project_entry, project_root / PROJECT_RULES_ENTRY)
    include_headings = not args.no_headings
    heading_limit = max(0, int(args.max_headings))

    rule_files = [
        read_rule_file(
            "root-entry",
            project_root,
            root_entry,
            include_headings=include_headings,
            heading_limit=heading_limit,
        ),
        read_rule_file(
            "common-governance",
            project_root,
            governance_entry,
            include_headings=include_headings,
            heading_limit=heading_limit,
        ),
        read_rule_file(
            "project-rules",
            project_root,
            project_entry,
            include_headings=include_headings,
            heading_limit=heading_limit,
        ),
    ]
    sync_report = run_sync_report(args, project_root, governance_root)
    warnings = [item.warning for item in rule_files if item.warning]
    warnings.extend(str(item) for item in sync_report.get("warnings", []) if item)
    status = "pass" if not warnings else "warning"
    return BootstrapReport(
        status=status,
        requested_root=str(requested_root),
        project_root=str(project_root),
        governance_root=str(governance_root),
        rule_files=rule_files,
        read_policy=[
            "Do not dump long Chinese AGENTS.md files with raw Get-Content -Raw.",
            "Use session-bootstrap first, then context-extract --headings, --match, or --range for bounded detail.",
            "session-bootstrap may run sync-check; sync-check never pulls, pushes, merges, or deletes.",
        ],
        sync_check=sync_report,
        warnings=warnings,
        next_commands=safe_commands(),
    )


def render_text(report: BootstrapReport, *, max_headings: int) -> str:
    lines = [
        f"AI Client Governance session bootstrap: {report.status}",
        f"Project root: {report.project_root}",
        f"Governance root: {report.governance_root}",
        "",
        "Rule files:",
    ]
    for item in report.rule_files:
        if not item.exists:
            lines.append(f"- {item.role}: MISSING {item.path}")
            continue
        lines.append(
            f"- {item.role}: {item.path} lines={item.line_count} bytes={item.byte_count} "
            f"sha256={item.sha256[:12]} headings={item.heading_count}"
        )
        headings = item.headings or []
        for heading in headings[: max(0, max_headings)]:
            marker = "#" * heading.level
            lines.append(f"  {heading.line}: {marker} {heading.title}")
        if item.heading_count > len(headings):
            lines.append(f"  ... {item.heading_count - len(headings)} more heading(s); use context-extract for details")

    sync_status = str(report.sync_check.get("status", "unknown"))
    lines.extend(["", f"Sync-check: {sync_status}"])
    for note in report.sync_check.get("notes", []) or []:
        lines.append(f"- note: {note}")
    for warning in report.sync_check.get("warnings", []) or []:
        lines.append(f"- warning: {warning}")
    for action in report.sync_check.get("next_actions", []) or []:
        lines.append(f"- next: {action}")

    lines.extend(["", "Read policy:"])
    lines.extend(f"- {item}" for item in report.read_policy)
    lines.extend(["", "Safe next commands:"])
    lines.extend(f"- {item}" for item in report.next_commands)
    return "\n".join(lines)


def render_markdown(report: BootstrapReport, *, max_headings: int) -> str:
    lines = [
        "# Session Bootstrap",
        "",
        f"- Status: `{report.status}`",
        f"- Project root: `{report.project_root}`",
        f"- Governance root: `{report.governance_root}`",
        "",
        "## Rule Files",
    ]
    for item in report.rule_files:
        lines.append(
            f"- `{item.role}` `{item.path}` "
            f"exists={str(item.exists).lower()} lines={item.line_count} sha256=`{item.sha256[:12]}`"
        )
        for heading in (item.headings or [])[: max(0, max_headings)]:
            lines.append(f"  - L{heading.line} {'#' * heading.level} {heading.title}")
    lines.extend(["", "## Sync", "", f"- Status: `{report.sync_check.get('status', 'unknown')}`"])
    lines.extend(f"- Warning: {warning}" for warning in report.sync_check.get("warnings", []) or [])
    lines.extend(["", "## Safe Commands"])
    lines.extend(f"- `{command}`" for command in report.next_commands)
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = build_report(args)
    if args.format == "json":
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    elif args.format == "markdown":
        print(render_markdown(report, max_headings=args.max_headings))
    else:
        print(render_text(report, max_headings=args.max_headings))
    if args.fail_on_warning and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
