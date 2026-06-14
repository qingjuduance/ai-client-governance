#!/usr/bin/env python3
"""Read-only Markdown compliance scan for the documentation repository.

The script reports common maintenance risks from AGENTS.md. It never edits
Markdown files, reference records, or indexes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote


DEFAULT_TARGETS = ("README.md", "AGENTS.md", "docs", ".codex")
ARCHIVE_REL_PARTS = ("docs", "archive")
EXCLUDED_DIRS = {
    ".git",
    ".idea",
    ".source-projects",
    ".uploads",
    ".trae",
    "__pycache__",
}
EXCLUDED_CODEX_DIRS = {
    "agent-groups",
    "task-tracking",
}
FORMAL_NAMES = {"README.md", "roadmap.md"}
INDEX_HEADINGS = ("快速索引", "文档索引", "索引")

LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
REFERENCE_LINK_RE = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)")
HEADING_RE = re.compile(r"^#\s+.+")


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    detail: str


@dataclass(frozen=True)
class ScanReport:
    root: str
    scanned_files: int
    findings: list[Finding]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only scan for repository Markdown compliance risks."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=list(DEFAULT_TARGETS),
        help="Files or directories to scan. Defaults to README.md AGENTS.md docs .codex.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format. Default: text.",
    )
    parser.add_argument(
        "--max-line-length",
        type=int,
        default=120,
        help="Report non-code lines longer than this. Default: 120.",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit with status 1 when findings are present.",
    )
    parser.add_argument(
        "--include-archive",
        action="store_true",
        help="Include docs/archive in the scan. Default: excluded.",
    )
    return parser.parse_args()


def is_under(path: Path, ancestor: Path) -> bool:
    try:
        path.relative_to(ancestor)
        return True
    except ValueError:
        return False


def is_docs_archive_path(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    return rel_parts[: len(ARCHIVE_REL_PARTS)] == ARCHIVE_REL_PARTS


def is_excluded(path: Path, root: Path, include_archive: bool = False) -> bool:
    rel_parts = path.relative_to(root).parts
    if any(part in EXCLUDED_DIRS for part in rel_parts):
        return True
    if not include_archive and is_docs_archive_path(path, root):
        return True
    if len(rel_parts) >= 2 and rel_parts[0] == ".codex":
        return rel_parts[1] in EXCLUDED_CODEX_DIRS
    return False


def iter_markdown_files(
    root: Path, targets: list[str], include_archive: bool
) -> list[Path]:
    files: set[Path] = set()
    for target in targets:
        path = (root / target).resolve()
        if not path.exists():
            continue
        if path.is_file() and path.suffix.lower() == ".md":
            if not is_excluded(path, root, include_archive):
                files.add(path)
            continue
        if path.is_dir():
            for child in path.rglob("*.md"):
                resolved = child.resolve()
                if not is_excluded(resolved, root, include_archive):
                    files.add(resolved)
    return sorted(files)


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def strip_anchor(target: str) -> str:
    return target.split("#", 1)[0]


def strip_query(target: str) -> str:
    return target.split("?", 1)[0]


def normalize_target(target: str) -> str:
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    return unquote(target)


def is_external_target(target: str) -> bool:
    lower = target.lower()
    return bool(re.match(r"^[a-z][a-z0-9+.-]*:", lower)) and not lower.startswith(
        "file:"
    )


def is_local_absolute_target(target: str) -> bool:
    normalized = normalize_target(target)
    return bool(
        re.match(r"^[a-zA-Z]:[\\/]", normalized)
        or normalized.lower().startswith("file:")
        or normalized.startswith("/")
    )


def local_target_path(source: Path, target: str, root: Path) -> Path | None:
    normalized = strip_query(strip_anchor(normalize_target(target))).strip()
    if not normalized or normalized.startswith("#"):
        return None
    if is_external_target(normalized) or is_local_absolute_target(normalized):
        return None
    candidate = (source.parent / normalized).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def line_is_probable_exception(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("|") and stripped.endswith("|"):
        return True
    if "http://" in stripped or "https://" in stripped:
        return True
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    return False


def is_reference_record(path: Path) -> bool:
    return ".references" in path.parts


def is_questions_file(path: Path) -> bool:
    return "questions" in path.parts


def is_markdown_file_target(path: Path) -> bool:
    return path.suffix.lower() == ".md"


def is_formal_entry_file(path: Path) -> bool:
    if is_reference_record(path) or is_questions_file(path):
        return False
    if path.name in FORMAL_NAMES:
        return True
    stem = path.stem.lower()
    return any(token in stem for token in ("overview", "index", "总览", "索引"))


def should_require_index(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if rel.parts[0] != "docs":
        return False
    if is_reference_record(path) or is_questions_file(path) or is_docs_archive_path(path, root):
        return False
    return True


def has_light_index(lines: list[str]) -> bool:
    first_heading = next(
        (index for index, line in enumerate(lines) if HEADING_RE.match(line)),
        None,
    )
    if first_heading is None:
        return False
    window = lines[first_heading + 1 : first_heading + 35]
    return any(
        re.match(r"^##\s+" + re.escape(heading) + r"\s*$", line.strip())
        for line in window
        for heading in INDEX_HEADINGS
    )


def reference_record_path(path: Path) -> Path:
    return path.parent / ".references" / path.name


def markdown_links(lines: list[str]) -> Iterable[tuple[int, str, str]]:
    for line_no, line in enumerate(lines, start=1):
        for match in LINK_RE.finditer(line):
            yield line_no, match.group(1), match.group(2)
        reference_match = REFERENCE_LINK_RE.match(line)
        if reference_match:
            yield line_no, "", reference_match.group(1)


def add_finding(
    findings: list[Finding],
    root: Path,
    rule: str,
    severity: str,
    path: Path,
    line: int,
    detail: str,
) -> None:
    findings.append(
        Finding(
            rule=rule,
            severity=severity,
            file=path.relative_to(root).as_posix(),
            line=line,
            detail=detail,
        )
    )


def scan_file(path: Path, root: Path, max_line_length: int) -> list[Finding]:
    findings: list[Finding] = []
    lines = read_lines(path)
    internal_link_count = 0
    in_fence = False

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if (
            not in_fence
            and len(line) > max_line_length
            and not line_is_probable_exception(line)
        ):
            add_finding(
                findings,
                root,
                "long-line",
                "info",
                path,
                line_no,
                f"line length {len(line)} exceeds {max_line_length}",
            )

    for line_no, text, target in markdown_links(lines):
        normalized = normalize_target(target)
        if is_local_absolute_target(normalized):
            add_finding(
                findings,
                root,
                "absolute-local-link",
                "error",
                path,
                line_no,
                f"link target uses local absolute path: {normalized}",
            )

        resolved = local_target_path(path, normalized, root)
        if resolved is None:
            continue
        if resolved.suffix.lower() == ".md" or resolved.is_dir():
            internal_link_count += 1

        target_parts = resolved.parts
        target_name = resolved.name
        link_label = text or normalized
        if (
            is_formal_entry_file(path)
            and is_markdown_file_target(resolved)
            and "questions" in target_parts
        ):
            add_finding(
                findings,
                root,
                "formal-entry-links-questions",
                "error",
                path,
                line_no,
                f"formal entry links questions content: {link_label} -> {normalized}",
            )
        if is_questions_file(path):
            if (
                is_markdown_file_target(resolved)
                and "questions" in target_parts
                and resolved != path
            ):
                add_finding(
                    findings,
                    root,
                    "questions-cross-link",
                    "warning",
                    path,
                    line_no,
                    f"questions file links another questions file: {normalized}",
                )
            if target_name in FORMAL_NAMES:
                add_finding(
                    findings,
                    root,
                    "questions-links-formal-entry",
                    "error",
                    path,
                    line_no,
                    f"questions file links formal entry: {normalized}",
                )

    if internal_link_count and not is_reference_record(path):
        ref_path = reference_record_path(path)
        if not ref_path.exists():
            add_finding(
                findings,
                root,
                "missing-reference-record",
                "warning",
                path,
                1,
                f"file emits {internal_link_count} internal link(s) but {ref_path.relative_to(root).as_posix()} is missing",
            )

    if should_require_index(path, root) and not has_light_index(lines):
        add_finding(
            findings,
            root,
            "missing-light-index",
            "warning",
            path,
            1,
            "docs Markdown file has no light index section near the top",
        )

    return findings


def build_report(
    root: Path, targets: list[str], max_line_length: int, include_archive: bool
) -> ScanReport:
    files = iter_markdown_files(root, targets, include_archive)
    findings: list[Finding] = []
    for path in files:
        findings.extend(scan_file(path, root, max_line_length))
    findings.sort(key=lambda item: (item.severity, item.rule, item.file, item.line))
    return ScanReport(root=str(root), scanned_files=len(files), findings=findings)


def render_text(report: ScanReport) -> str:
    lines = [
        "Markdown Compliance Scan",
        f"Root: {report.root}",
        f"Scanned files: {report.scanned_files}",
        f"Findings: {len(report.findings)}",
        "",
    ]
    if not report.findings:
        lines.append("No findings.")
        return "\n".join(lines)

    counts: dict[tuple[str, str], int] = {}
    for finding in report.findings:
        key = (finding.severity, finding.rule)
        counts[key] = counts.get(key, 0) + 1
    lines.append("Summary:")
    for (severity, rule), count in sorted(counts.items()):
        lines.append(f"  {severity} {rule}: {count}")
    lines.append("")
    lines.append("Details:")
    for finding in report.findings:
        lines.append(
            f"- [{finding.severity}] {finding.rule}: "
            f"{finding.file}:{finding.line} - {finding.detail}"
        )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    root = Path.cwd().resolve()
    report = build_report(root, args.paths, args.max_line_length, args.include_archive)

    if args.format == "json":
        payload = asdict(report)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))

    if args.fail_on_findings and report.findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
