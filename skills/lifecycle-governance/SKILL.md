---
name: lifecycle-governance
description: Use when a task may touch governance rules/scripts, task lifecycle state, worktrees, corrections, framework debt, multi-agent coordination, final gates, stale commands, skill routing conflicts, or long-running/mutating work that must produce structured lifecycle facts.
---

# Lifecycle Governance

Use this skill to keep AI Client Governance work inside the structured lifecycle instead of relying on prose status reports. It helps route work through sync-check, task intake, task records, worktree coordination, gates, validation, and final closeout evidence.

## Required Checks

1. Confirm the embedded governance repository is present and run the sync check before mutating work.
2. Use the SQLite task record and task queue as current state. Treat Markdown reports, old JSON state, and historical correction exports as audit inputs only.
3. For mutating or medium/large work, create or reuse a task id, run lifecycle input-filter/preflight, and record facts before write-intent.
4. For worktree tasks, use the worktree-task commands and preserve lock/session facts. Do not edit through an unmanaged copy of the governance repository.
5. Before final output, run the appropriate gate-pool/task-record/task-queue lifecycle checks and record validation or explicit blocker facts.
6. If a claimed rule needs enforcement, implement the gate/runtime check or register follow-up framework debt. Do not document enforcement that only exists as intent.

## Routing

Read `references/lifecycle-phases.md` when you are unsure which lifecycle phase or command applies.

Read `references/skill-routing-conflicts.md` when project and common skills/rules overlap.

Read `references/feature-self-iteration.md` before changing governance features, commands, gates, or schemas that should self-test or generate follow-up debt.

## Boundaries

This skill does not replace task-record gates, task-queue lifecycle checks, architecture guard, sync-check, completion-test, or selftest. It is a routing checklist for when to invoke them and what evidence must exist.
