#!/usr/bin/env python3
"""Query JSON without shell pipes or inline ``python -c`` snippets."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PathStep:
    kind: str
    value: str | int | None = None


def command_to_string(command: list[str]) -> str:
    return subprocess.list2cmdline(command).strip() if sys.platform.startswith("win") else " ".join(command).strip()


def parse_path(path: str) -> list[PathStep]:
    text = path.strip()
    if not text or text == "$":
        return []
    if text.startswith("$."):
        text = text[2:]
    elif text.startswith("$"):
        text = text[1:]
    steps: list[PathStep] = []
    for part in [item for item in text.split(".") if item]:
        cursor = part
        while cursor:
            if cursor.startswith("["):
                end = cursor.find("]")
                if end < 0:
                    raise ValueError(f"invalid JSON path segment: {part}")
                token = cursor[1:end].strip()
                if token in ("", "*"):
                    steps.append(PathStep("all"))
                else:
                    try:
                        steps.append(PathStep("index", int(token)))
                    except ValueError as exc:
                        raise ValueError(f"invalid JSON list index: {token}") from exc
                cursor = cursor[end + 1 :]
                continue
            bracket = cursor.find("[")
            key = cursor if bracket < 0 else cursor[:bracket]
            if key:
                steps.append(PathStep("key", key))
            cursor = "" if bracket < 0 else cursor[bracket:]
    return steps


def query_path(value: Any, path: str) -> list[Any]:
    values = [value]
    for step in parse_path(path):
        next_values: list[Any] = []
        for item in values:
            if step.kind == "key":
                if isinstance(item, dict) and step.value in item:
                    next_values.append(item[step.value])
            elif step.kind == "all":
                if isinstance(item, list):
                    next_values.extend(item)
            elif step.kind == "index":
                if isinstance(item, list) and isinstance(step.value, int):
                    index = step.value
                    if -len(item) <= index < len(item):
                        next_values.append(item[index])
        values = next_values
    return values


def tail_text(text: str, limit: int = 1200) -> str:
    normalized = (text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[-limit:]


def load_json_from_command(command: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True)
    return completed.returncode, completed.stdout, completed.stderr


def load_json_text(args: argparse.Namespace) -> tuple[str, str, int]:
    if args.input:
        path = Path(args.input)
        return path.read_text(encoding="utf-8-sig"), f"input:{path}", 0
    command = list(args.command or [])
    if command and command[0] == "--":
        command = command[1:]
    if command:
        exit_code, stdout, stderr = load_json_from_command(command)
        if exit_code != 0 and not args.allow_nonzero:
            raise RuntimeError(
                json.dumps(
                    {
                        "status": "failed",
                        "source": "command",
                        "exit_code": exit_code,
                        "command": command_to_string(command),
                        "stderr_tail": tail_text(stderr),
                        "stdout_preview": tail_text(stdout, 400),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        return stdout, f"command:{command_to_string(command)}", exit_code
    if args.stdin:
        return sys.stdin.read(), "stdin", 0
    raise ValueError("json-query requires --input, --stdin, or a command after --")


def render_text(results: dict[str, list[Any]]) -> str:
    lines: list[str] = []
    multiple = len(results) > 1
    for path, values in results.items():
        if multiple:
            lines.append(f"{path}:")
        if not values:
            lines.append("  <no matches>" if multiple else "<no matches>")
            continue
        for value in values:
            if isinstance(value, (dict, list)):
                rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
            else:
                rendered = str(value)
            lines.append(f"  {rendered}" if multiple else rendered)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run or read JSON and extract fields without PowerShell pipes or inline python -c."
    )
    parser.add_argument("--input", help="Read JSON from a UTF-8 file.")
    parser.add_argument("--stdin", action="store_true", help="Read JSON from stdin explicitly.")
    parser.add_argument("--path", action="append", required=True, help="Simple path, e.g. items[].item_id or $.tools[0].name.")
    parser.add_argument("--allow-nonzero", action="store_true", help="Try to parse stdout even when the command exits non-zero.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="JSON-producing command after --.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        text, source, exit_code = load_json_text(args)
        data = json.loads(text)
        results = {path: query_path(data, path) for path in args.path}
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "source": source,
                        "source_exit_code": exit_code,
                        "path_count": len(results),
                        "result_count": sum(len(values) for values in results.values()),
                        "results": results,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(render_text(results))
        return 0
    except json.JSONDecodeError as exc:
        payload = {
            "status": "failed",
            "error": "json_decode_error",
            "message": str(exc),
            "recommendation": "Use the producer's --format json without warnings, or query a JSON file produced by the command.",
        }
    except (OSError, RuntimeError, ValueError) as exc:
        try:
            payload = json.loads(str(exc))
        except json.JSONDecodeError:
            payload = {"status": "failed", "error": type(exc).__name__, "message": str(exc)}
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
    else:
        print(f"json-query failed: {payload.get('message') or payload.get('error')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
