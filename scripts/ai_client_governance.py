#!/usr/bin/env python3
# Unified entry for ai-client-governance commands.

from __future__ import annotations

from pathlib import Path
import sys

AI_CLIENT_GOVERNANCE_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = AI_CLIENT_GOVERNANCE_ROOT / "src"
SRC_DIR_TEXT = str(SRC_DIR)
sys.path = [path for path in sys.path if Path(path or ".").resolve() != SRC_DIR]
sys.path.insert(0, SRC_DIR_TEXT)

from ai_client_governance.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
