---
name: self-correction-planner
description: Record and refine Codex correction notes for this repository. Use when the user says Codex missed something, planned poorly, violated repo rules, needs a correction written down, asks to update requirements from accumulated mistakes, or asks to organize `.codex/corrections/` into durable `AGENTS.md`, README, or skill rules.
---

# Self Correction Planner

## Overview

Use this skill to maintain the repository's correction loop:
user correction -> independent correction note -> index update -> rule extraction plan ->
approved requirement or skill update -> data handling and tooling observation.

This skill is for Codex workflow mistakes and rule gaps, not for ordinary knowledge notes,
interview answers, or project documentation.

## Workflow

1. Read the local rules first:
   - `AGENTS.md`
   - `README.md`
   - `.codex/corrections/README.md`
   - `.codex/corrections/index.md`
   - the current task tracking document when one exists

2. Classify the user feedback:
   - Record only: a single new mistake or missing step needs an audit note.
   - Extract rules: accumulated correction notes need clustering and rule proposals.
   - Implement upgrade: the user has approved a concrete plan to update requirements or skills.

3. For a new correction, create or update one file under `.codex/corrections/`:
   - File name format: `YYYY-MM-DD-错误关键词.md`.
   - Use the template from `.codex/corrections/README.md`.
   - Keep the note focused on one mistake, root cause, candidate rule, status,
     and related task tracking.
   - Update `.codex/corrections/index.md` in the same task.
   - Treat the independent correction file as the fact source; `index.md`
     is only a derived summary.

4. For rule extraction, read only the index plus relevant unresolved notes:
   - Start with records marked `待提炼`.
   - Group by error type and root cause.
   - Propose upgrades only when the issue is high-frequency, severe,
     or general enough to prevent future mistakes.
   - Do not paste one-off user complaints directly into `AGENTS.md`.

5. Before changing `AGENTS.md`, README, or another skill, present a plan and wait for
   the repository approval phrase required by `AGENTS.md`.

6. After an approved upgrade, update statuses:
   - Correction record: set to `已提炼进要求`, `暂不升级`, or `已废弃`.
   - `index.md`: mirror the same status and refresh status counts.
   - Current task tracking: record processed files, checks, final conclusion,
     and circular reference check.

7. After every use, record data handling and tooling observation:
   - In task tracking, record which correction records were read, how they were
     grouped, and which items stayed under observation.
   - In `.codex/corrections/index.md`, update the tooling observation table when
     the workflow involved repeated reading, status counting, grouping,
     rule planning, or status maintenance.
   - Do not define a fixed threshold for tool creation yet; keep counting usage
     and repeated manual steps until the data justifies a tool.
   - If a tool is justified, propose it first. The first script should be
     `scripts/scan_corrections.py`, and its first version should only scan
     corrections, count statuses, group error types, and output a report.
     It must not edit `AGENTS.md`, README, skills, correction records, or indexes.
   - After `scripts/scan_corrections.py` exists, run it before summarizing
     correction status or tooling observations when the repository is available.
     Record its report summary in the current task tracking document.
   - Treat the script output as an audit aid. A human-approved task still decides
     whether to update requirements, skills, correction records, or indexes.

## Boundaries

- Keep `.codex/corrections/` as process audit material, not formal learning content.
- Do not create `questions/` files for Codex workflow corrections.
- Do not turn every correction into a permanent rule; prefer precise, reusable rules.
- Do not store all corrections in one Markdown file; use independent files plus `index.md`.
- Do not let `index.md` become the fact source; rebuild it from independent
  correction records if the two disagree.
- Do not create scripts just because a workflow exists. First preserve data,
  observe frequency, then propose a read-only reporting tool when repetition is clear.
- `scripts/scan_corrections.py` is read-only. Its first report version covers:
  status counts, error-type groups, upgrade counts, index rows missing record files,
  records missing from the index, status/type/upgrade mismatches, candidate upgrades,
  and observation items.
- If changing a skill, run the skill validation required by `AGENTS.md`.

## Validation

- Search for the new entries:
  `rg -n "修正文档|corrections|self-correction-planner|工具化观察|scan_corrections|继续观察" AGENTS.md README.md .codex`
- Check Markdown formatting:
  `git diff --check -- AGENTS.md README.md .codex`
- Run the read-only corrections scan after adding or changing it:
  `python scripts/scan_corrections.py`
- When this skill is changed, run:
  `python C:\Users\he\.codex\skills\.system\skill-creator\scripts\quick_validate.py .codex\skills\self-correction-planner`
