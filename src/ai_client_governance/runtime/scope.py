"""Classify governance facts as common, project-specialized, or native project scope."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


COMMON_SCOPE = "ai-client-governance-common"
PROJECT_SCOPE = "project-specialization"
NATIVE_SCOPE = "native-project-assets"
MIXED_SCOPE = "mixed"
UNKNOWN_SCOPE = "unknown"

PROJECT_PREFIXES = (
    ".ai-client/project/",
    ".ai-client\\project\\",
)
COMMON_PREFIXES = (
    ".ai-client/ai-client-governance/",
    ".ai-client\\ai-client-governance\\",
)
NATIVE_ENTRY_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "CONVENTIONS.md",
    ".github/copilot-instructions.md",
}
COMMON_REPO_TOP_LEVEL = {
    "AGENTS.md",
    "README.md",
    "manifest.json",
    "scripts",
    "src",
    "skills",
    "check-ai-client-governance-sync.ps1",
}


@dataclass(frozen=True)
class ScopeClassification:
    scope_kind: str
    scope_reason: str
    paths: list[str]
    counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_path(value: str | Path) -> str:
    return str(value).strip().replace("\\", "/").strip("/")


def is_governance_repo_root(root: Path) -> bool:
    return (
        (root / "scripts" / "ai_client_governance.py").exists()
        and (root / "src" / "ai_client_governance").exists()
        and (root / "manifest.json").exists()
    )


def _path_scope(path: str, root: Path) -> tuple[str, str]:
    normalized = normalize_path(path)
    lowered = normalized.lower()
    if not normalized:
        return UNKNOWN_SCOPE, "empty path"
    if normalized == "." and is_governance_repo_root(root):
        return COMMON_SCOPE, "current directory is ai-client-governance repository root"
    if lowered == ".ai-client/ai-client-governance":
        return COMMON_SCOPE, "path is the embedded .ai-client/ai-client-governance repository"
    if any(lowered.startswith(prefix.replace("\\", "/").lower()) for prefix in COMMON_PREFIXES):
        return COMMON_SCOPE, "path is under embedded .ai-client/ai-client-governance"
    if lowered == ".ai-client/project":
        return PROJECT_SCOPE, "path is the .ai-client/project specialization root"
    if any(lowered.startswith(prefix.replace("\\", "/").lower()) for prefix in PROJECT_PREFIXES):
        return PROJECT_SCOPE, "path is under .ai-client/project"
    if is_governance_repo_root(root):
        first = normalized.split("/", 1)[0]
        if first in COMMON_REPO_TOP_LEVEL:
            return COMMON_SCOPE, "running inside ai-client-governance repository"
    if normalized in NATIVE_ENTRY_FILES or normalized.startswith(".github/instructions/"):
        return NATIVE_SCOPE, "path is a native project AI entry or instruction"
    return NATIVE_SCOPE, "path belongs to the host project surface"


def _command_paths(command: str) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(r"(?P<path>(?:\.ai-client|src|scripts|skills|docs|AGENTS\.md|README\.md)[^\s\"']*)", command):
        candidates.append(normalize_path(match.group("path")))
    return candidates


def classify_scope(
    *,
    root: Path,
    paths: Iterable[str | Path] = (),
    command: str = "",
    cwd: str | Path | None = None,
) -> ScopeClassification:
    """Return a stable common/project/native classification for lifecycle and ledger facts."""

    root = root.resolve()
    observed: list[str] = []
    for value in paths:
        normalized = normalize_path(value)
        if normalized and normalized not in observed:
            observed.append(normalized)
    for value in _command_paths(command):
        if value and value not in observed:
            observed.append(value)

    cwd_path = Path(cwd).resolve() if cwd else root
    if not observed and is_governance_repo_root(cwd_path):
        observed.append(".")
    if not observed and is_governance_repo_root(root):
        observed.append(".")

    if not observed:
        return ScopeClassification(
            scope_kind=UNKNOWN_SCOPE,
            scope_reason="no changed path, command path, or governance repo cwd was available",
            paths=[],
            counts={UNKNOWN_SCOPE: 1},
        )

    classifications = [_path_scope(path, cwd_path if is_governance_repo_root(cwd_path) else root) for path in observed]
    counts = Counter(scope for scope, _reason in classifications)
    if len(counts) == 1:
        scope_kind = next(iter(counts))
        reason = classifications[0][1]
    else:
        scope_kind = MIXED_SCOPE
        reason = "multiple governance scopes are present: " + ", ".join(f"{scope}={count}" for scope, count in sorted(counts.items()))
    return ScopeClassification(
        scope_kind=scope_kind,
        scope_reason=reason,
        paths=observed,
        counts=dict(sorted(counts.items())),
    )
