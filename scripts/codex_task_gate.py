#!/usr/bin/env python3
"""Read-only gate for task-type specific Codex evidence.

The session gate checks whether work can close at all. This script checks
whether the selected task type recorded the evidence that makes closure
credible: network sources for rule/tool design, logs for debug work,
correction writeback for user complaints, and validation for script/rule work.
It never writes files.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


TASK_ALIASES = {
    "code-debug": {
        "code",
        "debug",
        "mod",
        "代码",
        "调试",
        "故障排查",
        "日志",
    },
    "correction": {
        "correction",
        "corrections",
        "纠错",
        "修正",
        "用户投诉",
        "用户纠错",
    },
    "rules-script": {
        "rules",
        "rule",
        "script",
        "skill",
        "规则",
        "脚本",
        "门禁",
        "skill",
    },
    "docs": {
        "docs",
        "doc",
        "document",
        "文档",
        "重构",
        "新文档",
    },
    "git": {
        "git",
        "commit",
        "push",
        "提交",
        "推送",
    },
    "frontend": {
        "frontend",
        "ui",
        "browser",
        "前端",
        "页面",
        "浏览器",
    },
    "resume": {
        "resume",
        "pdf",
        "简历",
        "导出",
    },
    "multi-agent": {
        "multi-agent",
        "agent",
        "sub-agent",
        "子ai",
        "子 AI",
        "智能体",
    },
    "long-running": {
        "long-running",
        "pending",
        "恢复",
        "长任务",
        "未完成",
    },
}

URL_RE = re.compile(r"https?://[^\s)>\]]+")
CORRECTION_PATH_RE = re.compile(r"\.codex/corrections/[^\s`|,)]+?\.md")


@dataclass
class Finding:
    level: str
    message: str
    file: str | None = None


@dataclass
class Report:
    root: str
    task_tracking: str | None
    task_types: list[str]
    errors: list[Finding]
    warnings: list[Finding]
    notes: list[Finding]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check task-type specific evidence in a Codex task tracking file."
    )
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--task-tracking", help="Task tracking file to check.")
    parser.add_argument(
        "--task-types",
        nargs="*",
        default=None,
        help="Task types to require. If omitted, parse them from ## 任务类型门禁.",
    )
    parser.add_argument(
        "--require-task-types",
        action="store_true",
        help="Fail when no task type can be determined.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit non-zero when warnings are found.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def rel_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def section_text(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1) if match else ""


def normalize_task_type(value: str) -> str | None:
    lowered = value.strip().lower()
    for canonical, aliases in TASK_ALIASES.items():
        if lowered == canonical:
            return canonical
        if lowered in {alias.lower() for alias in aliases}:
            return canonical
    return None


def parse_task_types(text: str, explicit: list[str] | None) -> list[str]:
    found: list[str] = []
    candidates: list[str] = []
    if explicit:
        candidates.extend(explicit)
    gate = section_text(text, "任务类型门禁")
    if gate:
        candidates.extend(re.split(r"[\s,，、/|:：]+", gate))

    for candidate in candidates:
        normalized = normalize_task_type(candidate)
        if normalized and normalized not in found:
            found.append(normalized)
    return found


def infer_task_types(text: str) -> list[str]:
    inferred: list[str] = []
    log_section = section_text(text, "日志与可观测性记录")
    code_debug_explicitly_not_applicable = contains_any(
        log_section,
        ["code-debug` 不适用", "code-debug 不适用", "不是代码运行"],
    )
    if not code_debug_explicitly_not_applicable and contains_any(
        text,
        [
            "UE4SS.log",
            "BGUHasBuffByID",
            "BGUAddBuff",
            "TriggerEffectToTarget",
            "hasBuffAfter",
            "watched runtime event",
            "main.lua",
            "OwnedBuffConfig.lua",
            "Lua 静态",
            "运行日志",
        ],
    ):
        inferred.append("code-debug")
    if contains_any(text, [".codex/corrections/", "用户纠错", "修正文档"]):
        inferred.append("correction")
    if contains_any(
        text,
        [
            "codex_task_gate.py",
            "codex_session_gate.py",
            "门禁脚本",
            "通用规则",
            "规则/脚本",
            "AGENTS.md",
        ],
    ):
        inferred.append("rules-script")
    if contains_any(text, ["validate_doc_task.py", ".references", "Definition of Done"]):
        inferred.append("docs")
    if contains_any(text, [".codex/pending-tasks", "active pending", "恢复现场"]):
        inferred.append("long-running")
    return inferred


def contains_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def has_section(text: str, heading: str) -> bool:
    return bool(section_text(text, heading).strip())


def matching_sections(text: str, heading_keywords: list[str]) -> str:
    parts: list[str] = []
    pattern = re.compile(r"^##\s+(.+?)\s*$([\s\S]*?)(?=^##\s+|\Z)", re.MULTILINE)
    for match in pattern.finditer(text):
        heading = match.group(1)
        if contains_any(heading, heading_keywords):
            parts.append(match.group(2))
    return "\n".join(parts)


def has_network_evidence(text: str) -> bool:
    section = section_text(text, "联网核对记录")
    if not section.strip():
        return False
    if URL_RE.search(section):
        return True
    return contains_any(
        section,
        ["不适用", "无需联网", "无法联网", "未找到权威资料", "风险边界"],
    )


def add(items: list[Finding], level: str, message: str, file: str | None = None) -> None:
    items.append(Finding(level=level, message=message, file=file))


def validate_network(text: str, errors: list[Finding], tracking: str) -> None:
    if not has_network_evidence(text):
        add(
            errors,
            "error",
            "Rules/scripts/design work must record network sources or an explicit non-applicable reason.",
            tracking,
        )


def validate_code_debug(text: str, errors: list[Finding], tracking: str) -> None:
    section = section_text(text, "日志与可观测性记录")
    if not section.strip():
        section = matching_sections(text, ["日志", "可观测", "归因", "验证记录"])
    if not section.strip():
        add(errors, "error", "code-debug requires ## 日志与可观测性记录.", tracking)
        return

    required_groups = [
        ("log source or diagnostic command", ["日志来源", "日志路径", "UE4SS.log", "stdout", "stderr", "复现命令"]),
        ("key log summary", ["关键日志", "日志证据", "已确认", "错误码", "Lua error", "hasBuffAfter"]),
        ("validation pattern or next diagnostic", ["pattern", "验证用日志", "hasBuffAfter", "watched runtime event", "loaded", "待验证"]),
    ]
    for label, patterns in required_groups:
        if not contains_any(section, patterns):
            add(errors, "error", f"code-debug log evidence lacks {label}.", tracking)


def has_nonempty_severity(text: str) -> bool:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "严重程度" not in line:
            continue
        suffix = re.split(r"[:：]", line, maxsplit=1)
        if len(suffix) > 1 and suffix[1].strip():
            return True
        for next_line in lines[index + 1 : index + 4]:
            stripped = next_line.strip()
            if not stripped:
                continue
            if stripped.startswith("## "):
                return False
            return True
    return False


def validate_correction_records(
    text: str,
    root: Path,
    errors: list[Finding],
    tracking: str,
) -> list[tuple[str, str]]:
    normalized = text.replace("\\", "/")
    refs = sorted(set(CORRECTION_PATH_RE.findall(normalized)))
    record_refs = [
        ref
        for ref in refs
        if Path(ref).name not in {"README.md", "index.md"}
    ]
    if not record_refs:
        add(errors, "error", "correction task must name independent correction record files.", tracking)
        return []

    index_path = root / ".codex" / "corrections" / "index.md"
    index_text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    if not index_text:
        add(errors, "error", "corrections index.md is missing or empty.", ".codex/corrections/index.md")

    records: list[tuple[str, str]] = []
    for ref in record_refs:
        record_path = root / ref
        if not record_path.exists():
            add(errors, "error", "referenced correction record does not exist.", ref)
            continue
        record_text = record_path.read_text(encoding="utf-8")
        records.append((ref, record_text))
        if Path(ref).name not in index_text:
            add(errors, "error", "referenced correction record is not listed in index.md.", ref)
    return records


def validate_correction_severity_and_impact(
    text: str,
    records: list[tuple[str, str]],
    errors: list[Finding],
    tracking: str,
) -> None:
    if not records:
        return

    if not any(has_nonempty_severity(record_text) for _, record_text in records):
        add(
            errors,
            "error",
            "correction records must contain a non-empty severity field.",
            tracking,
        )

    combined_records = "\n".join(record_text for _, record_text in records)
    combined = f"{text}\n{combined_records}"
    if not contains_any(combined, ["影响面审计", "影响面扫描", "受影响", "影响判断"]):
        add(
            errors,
            "error",
            "correction task must record impact audit or affected-scope analysis.",
            tracking,
        )

    if contains_any(combined, ["暂不升级"]) and not contains_any(
        combined,
        ["不表示问题轻微", "不代表问题轻微", "不表示不严重", "已有防线", "后续观察"],
    ):
        add(
            errors,
            "error",
            "`暂不升级` must explain that it is not a severity downgrade and record existing defenses or observation.",
            tracking,
        )


def validate_python_cache_boundary(text: str, errors: list[Finding], tracking: str) -> None:
    if contains_any(
        text,
        [
            "py_compile",
            "python scripts",
            "python scripts\\",
            "codex_task_gate.py",
            "codex_session_gate.py",
            "Python 脚本",
        ],
    ) and not contains_any(text, ["PYTHONPYCACHEPREFIX", "python-pycache", "pycache_prefix"]):
        add(
            errors,
            "error",
            "Python script validation must record pycache redirection to .codex/cache.",
            tracking,
        )


def validate_applicability_gate(text: str, errors: list[Finding], tracking: str) -> None:
    section = section_text(text, "适用范围门禁")
    if not section.strip():
        add(
            errors,
            "error",
            "rules-script design work must record ## 适用范围门禁.",
            tracking,
        )
        return

    required_groups = [
        ("intended scope", ["适用范围", "适用场景", "触发场景", "覆盖对象"]),
        ("exclusions", ["排除范围", "不适用", "丢弃", "不处理"]),
        ("practicality", ["实用性", "可操作", "人工步骤", "成本"]),
        ("efficiency", ["效率", "提速", "耗时", "读取文件数", "脚本化检查项数"]),
        ("extensibility", ["扩展性", "可扩展", "后续升级", "兼容", "树形", "trace"]),
        ("quantitative source", ["量化", "指标", "统计口径", "事实源", "账本"]),
    ]
    for label, patterns in required_groups:
        if not contains_any(section, patterns):
            add(errors, "error", f"applicability gate lacks {label}.", tracking)


def validate_task_type(
    task_type: str,
    text: str,
    root: Path,
    errors: list[Finding],
    warnings: list[Finding],
    notes: list[Finding],
    tracking: str,
) -> None:
    if task_type == "code-debug":
        validate_code_debug(text, errors, tracking)
    elif task_type == "correction":
        if not contains_any(text, [".codex/corrections", "correction", "修正文档"]):
            add(errors, "error", "correction task must mention correction records.", tracking)
        if "index.md" not in text:
            add(errors, "error", "correction task must mention index.md writeback.", tracking)
        if not contains_any(text, ["是否需要升级", "已提炼进要求", "规则沉淀判断"]):
            add(errors, "error", "correction task must record upgrade/rule decision.", tracking)
        records = validate_correction_records(text, root, errors, tracking)
        validate_correction_severity_and_impact(text, records, errors, tracking)
    elif task_type == "rules-script":
        validate_network(text, errors, tracking)
        if not contains_any(text, ["批准标签", "批准：", "approval"]):
            add(errors, "error", "rules-script task must record approval label.", tracking)
        if not has_section(text, "验证记录"):
            add(errors, "error", "rules-script task must record ## 验证记录.", tracking)
        validate_applicability_gate(text, errors, tracking)
        validate_python_cache_boundary(text, errors, tracking)
        if contains_any(text, ["scripts/", "scripts\\"]) and not contains_any(
            text,
            ["py_compile", "--help", "语法解析", "最小真实用例"],
        ):
            add(
                warnings,
                "warning",
                "script changes should record compile/help or minimum real-use validation.",
                tracking,
            )
    elif task_type == "docs":
        if not contains_any(text, ["影响面扫描", "Definition of Done", "validate_doc_task.py"]):
            add(errors, "error", "docs task requires impact scan, DoD, and doc gate evidence.", tracking)
    elif task_type == "git":
        if not contains_any(text, ["git status", "工作区", "push", "推送边界"]):
            add(errors, "error", "git task requires status and push boundary evidence.", tracking)
    elif task_type == "frontend":
        if not contains_any(text, ["browser", "screenshot", "截图", "Playwright", "localhost"]):
            add(warnings, "warning", "frontend task should record browser/screenshot verification.", tracking)
    elif task_type == "resume":
        if not contains_any(text, ["PDF", "导出", "页数", "留白"]):
            add(errors, "error", "resume task requires PDF export/layout evidence.", tracking)
    elif task_type == "multi-agent":
        if not contains_any(text, ["agent", "智能体", "current-status", "brief"]):
            add(errors, "error", "multi-agent task requires agent status/brief evidence.", tracking)
    elif task_type == "long-running":
        if not contains_any(text, ["pending", "恢复现场", "下一步"]):
            add(errors, "error", "long-running task requires pending/recovery evidence.", tracking)
    else:
        add(notes, "note", f"No task-type rule implemented for {task_type}.", tracking)


def build_report(
    root: Path,
    task_tracking_arg: str | None,
    explicit_task_types: list[str] | None,
    require_task_types: bool,
) -> Report:
    errors: list[Finding] = []
    warnings: list[Finding] = []
    notes: list[Finding] = []

    if not task_tracking_arg:
        add(errors, "error", "Provide --task-tracking for task-type gate validation.")
        return Report(str(root.resolve()), None, [], errors, warnings, notes)

    task_tracking = Path(task_tracking_arg)
    if not task_tracking.is_absolute():
        task_tracking = root / task_tracking
    tracking_rel = rel_path(task_tracking, root)

    if not task_tracking.exists():
        add(errors, "error", "Task tracking file does not exist.", tracking_rel)
        return Report(str(root.resolve()), tracking_rel, [], errors, warnings, notes)

    text = read_text(task_tracking)
    task_types = parse_task_types(text, explicit_task_types)
    inferred_task_types = infer_task_types(text)
    for task_type in inferred_task_types:
        if task_type not in task_types:
            task_types.append(task_type)
    if require_task_types and not task_types:
        add(errors, "error", "No task type selected in ## 任务类型门禁 or --task-types.", tracking_rel)

    for task_type in task_types:
        validate_task_type(task_type, text, root, errors, warnings, notes, tracking_rel)

    if inferred_task_types:
        add(notes, "note", f"Inferred task types: {', '.join(inferred_task_types)}.", tracking_rel)
    if task_types:
        add(notes, "note", f"Checked task types: {', '.join(task_types)}.", tracking_rel)

    return Report(
        root=str(root.resolve()),
        task_tracking=tracking_rel,
        task_types=task_types,
        errors=errors,
        warnings=warnings,
        notes=notes,
    )


def format_findings(title: str, items: list[Finding]) -> list[str]:
    lines = [f"{title}: {len(items)}"]
    if not items:
        lines.append("  none")
        return lines
    for item in items:
        location = f" [{item.file}]" if item.file else ""
        lines.append(f"  - {item.message}{location}")
    return lines


def format_text(report: Report) -> str:
    lines = [
        "Codex Task Gate Report",
        f"Root: {report.root}",
        f"Task tracking: {report.task_tracking or 'none'}",
        f"Task types: {', '.join(report.task_types) if report.task_types else 'none'}",
        "",
    ]
    lines.extend(format_findings("Errors", report.errors))
    lines.append("")
    lines.extend(format_findings("Warnings", report.warnings))
    lines.append("")
    lines.extend(format_findings("Notes", report.notes))
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = build_report(
        root=Path(args.root).resolve(),
        task_tracking_arg=args.task_tracking,
        explicit_task_types=args.task_types,
        require_task_types=args.require_task_types,
    )

    if args.format == "json":
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print(format_text(report))

    if report.errors:
        return 1
    if args.fail_on_warning and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
