#!/usr/bin/env python3
"""Unified execution telemetry stored in the project SQLite state DB."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_client_governance.records import state_store


SCHEMA_VERSION = 2
SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|ACCESS[_-]?KEY)[A-Z0-9_]*)=([^\s]+)"
)
SENSITIVE_OPTION_EQ = re.compile(
    r"(?i)(--?(?:token|secret|password|passwd|api[-_]?key|access[-_]?key|credential|auth))(=)([^\s]+)"
)
SENSITIVE_OPTION_SPACE = re.compile(
    r"(?i)(--?(?:token|secret|password|passwd|api[-_]?key|access[-_]?key|credential|auth))(\s+)([^\s]+)"
)
SENSITIVE_QUERY_PARAM = re.compile(
    r"(?i)([?&](?:token|secret|password|passwd|api[-_]?key|access[-_]?key|credential|auth)=)([^&#\s]+)"
)
SENSITIVE_KEY = re.compile(
    r"(?i)(token|secret|password|passwd|api[-_]?key|access[-_]?key|credential|auth|authorization)"
)


@dataclass(frozen=True)
class TelemetrySpan:
    span_id: str
    trace_id: str
    parent_span_id: str
    task_id: str
    task_tracking: str
    name: str
    span_kind: str
    subject_type: str
    subject_redacted: str
    subject_hash: str
    cwd: str
    scope_kind: str
    scope_reason: str
    scope_paths: list[str]
    phase: str
    event_type: str
    status: str
    exit_code: int | None
    started_at: str
    ended_at: str
    duration_ms: int | None
    cached: bool
    cache_key: str
    cache_reason: str
    adapter_enforcement: str
    final_gate: bool
    task_types: list[str]
    attempt: int | None
    source: str
    summary: str
    attributes: dict[str, Any]


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        normalized = normalized + "T00:00:00"
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def host_project_root(root: Path) -> Path:
    resolved = root.resolve()
    parts = resolved.parts
    for index in range(len(parts) - 2):
        if parts[index : index + 3] == (".ai-client", "project", ".worktree"):
            host = Path(*parts[:index])
            if (host / ".ai-client" / "project").exists():
                return host
    return resolved


def db_path(root: Path, override: str | None = None) -> Path:
    if override:
        return state_store.db_path(root, override)
    return state_store.db_path(host_project_root(root), None)


def connect(root: Path, override: str | None = None) -> sqlite3.Connection:
    path = db_path(root, override)
    con = state_store.connect(path)
    init_db(con)
    return con


def init_db(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        DROP VIEW IF EXISTS command_metrics_by_name;
        DROP TABLE IF EXISTS command_events;
        DROP TABLE IF EXISTS command_spans;
        """
    )
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS execution_spans (
            span_id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL DEFAULT '',
            parent_span_id TEXT NOT NULL DEFAULT '',
            task_id TEXT NOT NULL DEFAULT '',
            task_tracking TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            span_kind TEXT NOT NULL DEFAULT '',
            subject_type TEXT NOT NULL DEFAULT '',
            subject_redacted TEXT NOT NULL DEFAULT '',
            subject_hash TEXT NOT NULL DEFAULT '',
            cwd TEXT NOT NULL DEFAULT '',
            scope_kind TEXT NOT NULL DEFAULT '',
            scope_reason TEXT NOT NULL DEFAULT '',
            scope_paths_json TEXT NOT NULL DEFAULT '[]',
            phase TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            exit_code INTEGER,
            started_at TEXT NOT NULL DEFAULT '',
            ended_at TEXT NOT NULL DEFAULT '',
            duration_ms INTEGER,
            cached INTEGER NOT NULL DEFAULT 0,
            cache_key TEXT NOT NULL DEFAULT '',
            cache_reason TEXT NOT NULL DEFAULT '',
            adapter_enforcement TEXT NOT NULL DEFAULT '',
            final_gate INTEGER NOT NULL DEFAULT 0,
            task_types_json TEXT NOT NULL DEFAULT '[]',
            attempt INTEGER,
            source TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            attributes_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS execution_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            span_id TEXT NOT NULL,
            trace_id TEXT NOT NULL DEFAULT '',
            event_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            timestamp TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            source_command TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(span_id) REFERENCES execution_spans(span_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_execution_spans_trace
            ON execution_spans(trace_id, started_at, ended_at);
        CREATE INDEX IF NOT EXISTS idx_execution_spans_task
            ON execution_spans(task_id, started_at, ended_at);
        CREATE INDEX IF NOT EXISTS idx_execution_spans_kind_name
            ON execution_spans(span_kind, name, started_at, ended_at);
        CREATE INDEX IF NOT EXISTS idx_execution_spans_subject_hash
            ON execution_spans(subject_hash, started_at, ended_at);
        CREATE INDEX IF NOT EXISTS idx_execution_events_trace
            ON execution_events(trace_id, timestamp);

        CREATE VIEW IF NOT EXISTS execution_metrics_by_name AS
            SELECT
                span_kind,
                name,
                count(*) AS span_count,
                sum(CASE WHEN status = 'failed' OR coalesce(exit_code, 0) != 0 THEN 1 ELSE 0 END) AS failed_count,
                sum(CASE WHEN cached = 1 THEN 1 ELSE 0 END) AS cache_hit_count,
                avg(duration_ms) AS avg_duration_ms,
                max(duration_ms) AS max_duration_ms
            FROM execution_spans
            GROUP BY span_kind, name;
        """
    )
    con.execute(
        "INSERT INTO meta(key, value) VALUES('execution_telemetry_schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    con.commit()


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def decode_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except json.JSONDecodeError:
        return fallback


def redact_sensitive_text(value: str) -> str:
    redacted = SENSITIVE_ASSIGNMENT.sub(r"\1=<redacted>", value or "")
    redacted = SENSITIVE_OPTION_EQ.sub(r"\1\2<redacted>", redacted)
    redacted = SENSITIVE_OPTION_SPACE.sub(r"\1\2<redacted>", redacted)
    return SENSITIVE_QUERY_PARAM.sub(r"\1<redacted>", redacted)


def redact_subject(subject: str) -> str:
    redacted = redact_sensitive_text(subject or "")
    return re.sub(r"\s+", " ", redacted).strip()


def sanitize_value(value: Any, key: str = "") -> Any:
    if SENSITIVE_KEY.search(key or ""):
        if value in (None, ""):
            return value
        return "<redacted>"
    if isinstance(value, dict):
        return {str(item_key): sanitize_value(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [sanitize_value(item, key) for item in value]
    if isinstance(value, tuple):
        return [sanitize_value(item, key) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def sanitize_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {str(key): sanitize_value(item, str(key)) for key, item in value.items()}


def subject_hash(subject: str) -> str:
    normalized = re.sub(r"\s+", " ", (subject or "").strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def subject_from_event(event: dict[str, Any]) -> tuple[str, str]:
    if event.get("subject") not in (None, ""):
        return str(event.get("subject") or ""), str(event.get("subject_type") or "subject")
    if event.get("command") not in (None, ""):
        return str(event.get("command") or ""), "command"
    if event.get("url") not in (None, ""):
        return str(event.get("url") or ""), str(event.get("subject_type") or "http_url")
    if event.get("endpoint") not in (None, ""):
        return str(event.get("endpoint") or ""), str(event.get("subject_type") or "endpoint")
    return str(event.get("name") or ""), str(event.get("subject_type") or "operation")


def as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]


def sanitized_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = sanitize_mapping(dict(event))
    subject, subject_type = subject_from_event(event)
    if "command" in payload:
        payload["command"] = redact_subject(str(payload.get("command") or ""))
    if "subject" in payload:
        payload["subject"] = redact_subject(str(payload.get("subject") or ""))
    if "url" in payload:
        payload["url"] = redact_subject(str(payload.get("url") or ""))
    if "endpoint" in payload:
        payload["endpoint"] = redact_subject(str(payload.get("endpoint") or ""))
    payload["subject_type"] = subject_type
    payload["subject_hash"] = subject_hash(subject)
    return payload


def event_to_span(event: dict[str, Any]) -> TelemetrySpan:
    span_id = str(event.get("invocation_id") or event.get("span_id") or "")
    if not span_id:
        raise ValueError("telemetry event requires invocation_id or span_id")
    subject, subject_type = subject_from_event(event)
    redacted = redact_subject(subject)
    span_kind = str(
        event.get("span_kind")
        or ("command" if event.get("command") not in (None, "") else "")
        or event.get("event_type")
        or event.get("phase")
        or "operation"
    )
    attrs = {
        key: value
        for key, value in event.items()
        if key
        not in {
            "command",
            "invocation_id",
            "span_id",
            "trace_id",
            "parent_invocation_id",
            "parent_span_id",
            "task_id",
            "task_tracking",
            "name",
            "span_kind",
            "subject",
            "subject_type",
            "url",
            "endpoint",
            "status",
            "exit_code",
            "started_at",
            "ended_at",
            "duration_ms",
            "timestamp",
            "schema_version",
            "cwd",
            "source",
            "summary",
            "task_types",
            "phase",
            "event_type",
            "attempt",
            "final_gate",
            "cached",
            "cache_key",
            "cache_reason",
            "scope_kind",
            "scope_reason",
            "scope_paths",
            "adapter_enforcement",
            "task_node_id",
            "parent_task_node_id",
            "attributes",
        }
    }
    extension_attrs = event.get("attributes")
    if isinstance(extension_attrs, dict):
        attrs.update(extension_attrs)
    elif extension_attrs not in (None, ""):
        attrs["attributes"] = extension_attrs
    attrs = sanitize_mapping(attrs)
    return TelemetrySpan(
        span_id=span_id,
        trace_id=str(event.get("trace_id") or span_id),
        parent_span_id=str(event.get("parent_invocation_id") or event.get("parent_span_id") or ""),
        task_id=str(event.get("task_id") or ""),
        task_tracking=str(event.get("task_tracking") or ""),
        name=str(event.get("name") or "unknown"),
        span_kind=span_kind,
        subject_type=subject_type,
        subject_redacted=redacted,
        subject_hash=subject_hash(subject),
        cwd=str(event.get("cwd") or ""),
        scope_kind=str(event.get("scope_kind") or ""),
        scope_reason=str(event.get("scope_reason") or ""),
        scope_paths=as_list(event.get("scope_paths")),
        phase=str(event.get("phase") or ""),
        event_type=str(event.get("event_type") or ""),
        status=str(event.get("status") or ""),
        exit_code=as_int(event.get("exit_code")),
        started_at=str(event.get("started_at") or event.get("timestamp") or ""),
        ended_at=str(event.get("ended_at") or ""),
        duration_ms=as_int(event.get("duration_ms")),
        cached=bool(event.get("cached")),
        cache_key=str(event.get("cache_key") or ""),
        cache_reason=str(event.get("cache_reason") or ""),
        adapter_enforcement=str(event.get("adapter_enforcement") or ""),
        final_gate=bool(event.get("final_gate")),
        task_types=as_list(event.get("task_types")),
        attempt=as_int(event.get("attempt")),
        source=str(event.get("source") or ""),
        summary=str(event.get("summary") or ""),
        attributes=attrs,
    )


def append_event(
    root: Path,
    event: dict[str, Any],
    *,
    db: str | None = None,
    source_command: str = "ai_client_governance.py telemetry",
) -> Path:
    path = db_path(root, db)
    con = connect(root, db)
    span = event_to_span(event)
    payload = sanitized_event(event)
    timestamp = str(event.get("timestamp") or event.get("ended_at") or event.get("started_at") or utc_now())
    now = utc_now()
    terminal = span.status != "started"
    with con:
        con.execute(
            """
            INSERT INTO execution_spans(
                span_id, trace_id, parent_span_id, task_id, task_tracking, name, span_kind,
                subject_type, subject_redacted, subject_hash, cwd, scope_kind, scope_reason, scope_paths_json,
                phase, event_type, status, exit_code, started_at, ended_at, duration_ms,
                cached, cache_key, cache_reason, adapter_enforcement, final_gate,
                task_types_json, attempt, source, summary, attributes_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(span_id) DO UPDATE SET
                trace_id=excluded.trace_id,
                parent_span_id=excluded.parent_span_id,
                task_id=excluded.task_id,
                task_tracking=excluded.task_tracking,
                name=excluded.name,
                span_kind=excluded.span_kind,
                subject_type=excluded.subject_type,
                subject_redacted=excluded.subject_redacted,
                subject_hash=excluded.subject_hash,
                cwd=excluded.cwd,
                scope_kind=excluded.scope_kind,
                scope_reason=excluded.scope_reason,
                scope_paths_json=excluded.scope_paths_json,
                phase=excluded.phase,
                event_type=excluded.event_type,
                status=CASE WHEN ? THEN excluded.status ELSE execution_spans.status END,
                exit_code=CASE WHEN ? THEN excluded.exit_code ELSE execution_spans.exit_code END,
                started_at=CASE
                    WHEN execution_spans.started_at = '' THEN excluded.started_at
                    WHEN excluded.started_at = '' THEN execution_spans.started_at
                    ELSE execution_spans.started_at
                END,
                ended_at=CASE WHEN excluded.ended_at != '' THEN excluded.ended_at ELSE execution_spans.ended_at END,
                duration_ms=coalesce(excluded.duration_ms, execution_spans.duration_ms),
                cached=excluded.cached,
                cache_key=excluded.cache_key,
                cache_reason=excluded.cache_reason,
                adapter_enforcement=excluded.adapter_enforcement,
                final_gate=excluded.final_gate,
                task_types_json=excluded.task_types_json,
                attempt=coalesce(excluded.attempt, execution_spans.attempt),
                source=excluded.source,
                summary=excluded.summary,
                attributes_json=excluded.attributes_json,
                updated_at=excluded.updated_at
            """,
            (
                span.span_id,
                span.trace_id,
                span.parent_span_id,
                span.task_id,
                span.task_tracking,
                span.name,
                span.span_kind,
                span.subject_type,
                span.subject_redacted,
                span.subject_hash,
                span.cwd,
                span.scope_kind,
                span.scope_reason,
                encode(span.scope_paths),
                span.phase,
                span.event_type,
                span.status,
                span.exit_code,
                span.started_at,
                span.ended_at,
                span.duration_ms,
                int(span.cached),
                span.cache_key,
                span.cache_reason,
                span.adapter_enforcement,
                int(span.final_gate),
                encode(span.task_types),
                span.attempt,
                span.source,
                span.summary,
                encode(span.attributes),
                now,
                now,
                terminal,
                terminal,
            ),
        )
        con.execute(
            """
            INSERT INTO execution_events(span_id, trace_id, event_name, status, timestamp, payload_json, source_command, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                span.span_id,
                span.trace_id,
                span.event_type or span.phase or span.span_kind,
                span.status,
                timestamp,
                encode(payload),
                source_command,
                now,
            ),
        )
    return path


def read_events(
    root: Path,
    *,
    db: str | None = None,
    task_id: str = "",
    trace_id: str = "",
    since: str = "",
    until: str = "",
) -> list[dict[str, Any]]:
    con = connect(root, db)
    clauses: list[str] = []
    params: list[Any] = []
    if task_id:
        clauses.append("s.task_id = ?")
        params.append(task_id)
    if trace_id:
        clauses.append("e.trace_id = ?")
        params.append(trace_id)
    if since:
        clauses.append("e.timestamp >= ?")
        params.append(since)
    if until:
        clauses.append("e.timestamp <= ?")
        params.append(until)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = con.execute(
        f"""
        SELECT e.payload_json
        FROM execution_events e
        JOIN execution_spans s ON s.span_id = e.span_id
        {where}
        ORDER BY e.timestamp, e.event_id
        """,
        params,
    ).fetchall()
    return [decode_json(row["payload_json"], {}) for row in rows]


def span_rows(
    root: Path,
    *,
    db: str | None = None,
    task_id: str = "",
    trace_id: str = "",
    since: str = "",
    until: str = "",
) -> list[dict[str, Any]]:
    con = connect(root, db)
    clauses: list[str] = []
    params: list[Any] = []
    if task_id:
        clauses.append("task_id = ?")
        params.append(task_id)
    if trace_id:
        clauses.append("trace_id = ?")
        params.append(trace_id)
    if since:
        clauses.append("coalesce(ended_at, started_at) >= ?")
        params.append(since)
    if until:
        clauses.append("coalesce(ended_at, started_at) <= ?")
        params.append(until)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = con.execute(
        f"""
        SELECT *
        FROM execution_spans
        {where}
        ORDER BY coalesce(ended_at, started_at), span_id
        """,
        params,
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["scope_paths"] = decode_json(item.pop("scope_paths_json"), [])
        item["task_types"] = decode_json(item.pop("task_types_json"), [])
        item["attributes"] = decode_json(item.pop("attributes_json"), {})
        item["cached"] = bool(item["cached"])
        item["final_gate"] = bool(item["final_gate"])
        result.append(item)
    return result


def percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * pct)))
    return ordered[index]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    spans = span_rows(
        root,
        db=args.db,
        task_id=args.task_id or "",
        trace_id=args.trace_id or "",
        since=args.since or "",
        until=args.until or "",
    )
    terminal = [span for span in spans if span.get("status") != "started"]
    durations = [int(span["duration_ms"]) for span in terminal if span.get("duration_ms") is not None]
    failures = [
        span
        for span in terminal
        if span.get("status") == "failed" or (span.get("exit_code") not in (None, 0))
    ]
    subject_counts = Counter(str(span.get("subject_redacted") or "") for span in terminal if span.get("subject_redacted"))
    duplicates = [
        {"subject": subject, "count": count}
        for subject, count in subject_counts.most_common()
        if count > 1
    ]
    return {
        "db": str(db_path(root, args.db)),
        "filters": {
            "task_id": args.task_id or "",
            "trace_id": args.trace_id or "",
            "since": args.since or "",
            "until": args.until or "",
        },
        "span_count": len(spans),
        "terminal_span_count": len(terminal),
        "failed_count": len(failures),
        "failure_rate": (len(failures) / len(terminal)) if terminal else 0,
        "duration_ms": {
            "sum": sum(durations),
            "avg": round(sum(durations) / len(durations), 2) if durations else None,
            "p50": percentile(durations, 0.50),
            "p95": percentile(durations, 0.95),
            "max": max(durations) if durations else None,
        },
        "cache": {
            "hits": len([span for span in terminal if span.get("cached")]),
            "misses": len([span for span in terminal if span.get("cache_key") and not span.get("cached")]),
        },
        "top_operations": [
            {"name": name, "count": count}
            for name, count in Counter(str(span.get("name") or "unknown") for span in terminal).most_common(args.top)
        ],
        "top_subjects": [
            {"subject": subject, "count": count}
            for subject, count in subject_counts.most_common(args.top)
        ],
        "span_kind_counts": dict(Counter(str(span.get("span_kind") or "unknown") for span in terminal)),
        "subject_type_counts": dict(Counter(str(span.get("subject_type") or "unknown") for span in terminal)),
        "duplicate_subjects": duplicates[: args.top],
        "status_counts": dict(Counter(str(span.get("status") or "unknown") for span in spans)),
        "scope_kind_counts": dict(Counter(str(span.get("scope_kind") or "unknown") for span in terminal)),
        "adapter_enforcement_counts": dict(
            Counter(str(span.get("adapter_enforcement") or "none") for span in terminal)
        ),
        "latest_spans": terminal[-args.top :],
    }


def format_text(report: dict[str, Any]) -> str:
    duration = report["duration_ms"]
    cache = report["cache"]
    lines = [
        "AI Client Governance Execution Telemetry Report",
        f"DB: {report['db']}",
        f"Spans: {report['span_count']} terminal={report['terminal_span_count']}",
        f"Failures: {report['failed_count']} rate={report['failure_rate']:.2%}",
        (
            "Duration ms: "
            f"sum={duration['sum']} avg={duration['avg']} p50={duration['p50']} "
            f"p95={duration['p95']} max={duration['max']}"
        ),
        f"Cache: hits={cache['hits']} misses={cache['misses']}",
        "",
        "Top operations:",
    ]
    for row in report["top_operations"]:
        lines.append(f"  {row['name']}: count={row['count']}")
    lines.append("")
    lines.append("Top subjects:")
    for row in report["top_subjects"]:
        lines.append(f"  count={row['count']} {row['subject']}")
    lines.append("")
    lines.append("Duplicate subjects:")
    if report["duplicate_subjects"]:
        for row in report["duplicate_subjects"]:
            lines.append(f"  count={row['count']} {row['subject']}")
    else:
        lines.append("  none")
    lines.append("")
    lines.append(f"Span kinds: {json.dumps(report['span_kind_counts'], ensure_ascii=False, sort_keys=True)}")
    lines.append(f"Subject types: {json.dumps(report['subject_type_counts'], ensure_ascii=False, sort_keys=True)}")
    lines.append(f"Scope kinds: {json.dumps(report['scope_kind_counts'], ensure_ascii=False, sort_keys=True)}")
    lines.append(
        f"Adapter enforcement: {json.dumps(report['adapter_enforcement_counts'], ensure_ascii=False, sort_keys=True)}"
    )
    return "\n".join(lines)


def format_markdown(report: dict[str, Any]) -> str:
    duration = report["duration_ms"]
    cache = report["cache"]
    lines = [
        "# AI Client Governance Execution Telemetry Report",
        "",
        f"- DB: `{report['db']}`",
        f"- Spans: {report['span_count']} terminal={report['terminal_span_count']}",
        f"- Failures: {report['failed_count']} rate={report['failure_rate']:.2%}",
        (
            "- Duration ms: "
            f"sum={duration['sum']} avg={duration['avg']} p50={duration['p50']} "
            f"p95={duration['p95']} max={duration['max']}"
        ),
        f"- Cache: hits={cache['hits']} misses={cache['misses']}",
        "",
        "## Top Operations",
        "",
        "| Operation | Count |",
        "| --- | ---: |",
    ]
    for row in report["top_operations"]:
        lines.append(f"| `{row['name']}` | {row['count']} |")
    lines.extend(["", "## Top Subjects", "", "| Count | Subject |", "| ---: | --- |"])
    for row in report["top_subjects"]:
        lines.append(f"| {row['count']} | `{row['subject']}` |")
    lines.extend(["", "## Duplicate Subjects", ""])
    if report["duplicate_subjects"]:
        lines.extend(["| Count | Subject |", "| ---: | --- |"])
        for row in report["duplicate_subjects"]:
            lines.append(f"| {row['count']} | `{row['subject']}` |")
    else:
        lines.append("None.")
    return "\n".join(lines)


def parse_attribute_kv(values: list[str] | None) -> dict[str, Any] | None:
    if not values:
        return None
    parsed: dict[str, Any] = {}
    for item in values:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"attribute must use key=value form: {item}")
        parsed[key.strip()] = value
    return parsed


def command_record(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        attributes = parse_attribute_kv(args.attribute_kv)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    span_id = args.span_id or str(uuid4())
    trace_id = args.trace_id or span_id
    timestamp = args.timestamp or args.ended_at or args.started_at or utc_now()
    event = {
        "span_id": span_id,
        "trace_id": trace_id,
        "parent_span_id": args.parent_span_id or "",
        "task_id": args.task_id or "",
        "task_tracking": args.task_tracking or "",
        "name": args.name or args.span_kind or "operation",
        "span_kind": args.span_kind or "operation",
        "subject": args.subject or "",
        "subject_type": args.subject_type or "operation",
        "command": args.command or "",
        "url": args.url or "",
        "endpoint": args.endpoint or "",
        "status": args.status,
        "exit_code": args.exit_code,
        "started_at": args.started_at or timestamp,
        "ended_at": args.ended_at or (timestamp if args.status != "started" else ""),
        "duration_ms": args.duration_ms,
        "timestamp": timestamp,
        "cwd": args.cwd or str(Path.cwd().resolve()),
        "source": args.source or "ai_client_governance.py telemetry",
        "summary": args.summary or "",
        "task_types": as_list(args.task_type),
        "phase": args.phase or "",
        "event_type": args.event_type or "telemetry.record",
        "attempt": args.attempt,
        "final_gate": bool(args.final_gate),
        "cached": bool(args.cached),
        "cache_key": args.cache_key or "",
        "cache_reason": args.cache_reason or "",
        "scope_kind": args.scope_kind or "",
        "scope_reason": args.scope_reason or "",
        "scope_paths": as_list(args.scope_path),
        "adapter_enforcement": args.adapter_enforcement or "",
    }
    if attributes:
        event["attributes"] = attributes
    path = append_event(root, event, db=args.db, source_command="ai_client_governance.py telemetry record")
    print(f"recorded telemetry span={span_id} kind={event['span_kind']} status={args.status} db={path}")
    return 0


def command_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    connect(root, args.db)
    print(f"telemetry initialized: {db_path(root, args.db)}")
    return 0


def command_report(args: argparse.Namespace) -> int:
    report = build_report(args)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.format == "markdown":
        print(format_markdown(report))
    else:
        print(format_text(report))
    return 0


def telemetry_events(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    events = read_events(
        root,
        db=args.db,
        task_id=args.task_id or "",
        trace_id=args.trace_id or "",
        since=args.since or "",
        until=args.until or "",
    )
    print(json.dumps(events[-args.top :], ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record and analyze unified execution telemetry in aicg.db.")
    parser.add_argument("--root", default=".", help="Host project root. Default: current directory.")
    parser.add_argument("--db", help="SQLite database path. Default: <root>/.ai-client/project/state/aicg.db.")
    sub = parser.add_subparsers(dest="command_name", required=True)

    sub.add_parser("init", help="Create or migrate telemetry tables.").set_defaults(func=command_init)

    record = sub.add_parser("record", help="Record one execution telemetry span/event.")
    record.add_argument("--span-id", default="", help="Explicit span id. Default: generated UUID.")
    record.add_argument("--trace-id", default="", help="Trace id shared by related spans. Default: span id.")
    record.add_argument("--parent-span-id", default="", help="Parent span id.")
    record.add_argument("--task-id", default="", help="Structured task id.")
    record.add_argument("--task-tracking", default="", help="Human-readable task tracking reference, if any.")
    record.add_argument("--task-type", action="append", help="Related task type.")
    record.add_argument("--name", default="", help="Operation name.")
    record.add_argument("--span-kind", default="operation", help="Execution kind, e.g. command, model_http, sub_agent.")
    record.add_argument("--subject", default="", help="Primary execution subject.")
    record.add_argument("--subject-type", default="operation", help="Subject kind, e.g. command, http_url, model.")
    record.add_argument("--command", default="", help="Command subject for command spans.")
    record.add_argument("--url", default="", help="HTTP URL subject for network/model spans.")
    record.add_argument("--endpoint", default="", help="Endpoint subject for external service spans.")
    record.add_argument("--status", default="succeeded", help="Span status.")
    record.add_argument("--exit-code", type=int, help="Process exit code for command-like spans.")
    record.add_argument("--started-at", default="", help="ISO start timestamp.")
    record.add_argument("--ended-at", default="", help="ISO end timestamp.")
    record.add_argument("--timestamp", default="", help="Event timestamp.")
    record.add_argument("--duration-ms", type=int, help="Duration in milliseconds.")
    record.add_argument("--cwd", default="", help="Working directory for this span.")
    record.add_argument("--source", default="", help="Telemetry producer.")
    record.add_argument("--summary", default="", help="Short result summary.")
    record.add_argument("--phase", default="", help="Lifecycle phase.")
    record.add_argument("--event-type", default="", help="Telemetry event type.")
    record.add_argument("--attempt", type=int, help="Retry attempt.")
    record.add_argument("--final-gate", action="store_true", help="Mark as final gate evidence.")
    record.add_argument("--cached", action="store_true", help="Mark as a cache hit.")
    record.add_argument("--cache-key", default="", help="Cache key.")
    record.add_argument("--cache-reason", default="", help="Cache reason.")
    record.add_argument("--scope-kind", default="", help="Governance scope kind.")
    record.add_argument("--scope-reason", default="", help="Governance scope reason.")
    record.add_argument("--scope-path", action="append", help="Path associated with scope classification.")
    record.add_argument("--adapter-enforcement", default="", help="Enforcement adapter label.")
    record.add_argument("--attribute-kv", action="append", help="Extension attribute in key=value form.")
    record.set_defaults(func=command_record)

    report = sub.add_parser("report", help="Summarize execution telemetry.")
    report.add_argument("--task-id", default="", help="Only include spans for one structured task id.")
    report.add_argument("--trace-id", default="", help="Only include spans for one trace id.")
    report.add_argument("--since", default="", help="Only include spans at or after this ISO timestamp.")
    report.add_argument("--until", default="", help="Only include spans at or before this ISO timestamp.")
    report.add_argument("--top", type=int, default=10, help="Number of top rows to show.")
    report.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    report.set_defaults(func=command_report)

    events = sub.add_parser("events", help="Print raw normalized telemetry events as JSON.")
    events.add_argument("--task-id", default="", help="Only include events for one structured task id.")
    events.add_argument("--trace-id", default="", help="Only include events for one trace id.")
    events.add_argument("--since", default="", help="Only include events at or after this ISO timestamp.")
    events.add_argument("--until", default="", help="Only include events at or before this ISO timestamp.")
    events.add_argument("--top", type=int, default=50, help="Number of latest events to show.")
    events.set_defaults(func=telemetry_events)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
