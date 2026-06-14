---
name: agents-rule-maintainer
description: Maintain this repository's AGENTS.md rule system. Use when the user asks to add, compress, split, extract, or refine AGENTS rules; promote corrections or task tracking lessons into durable rules; audit whether a workflow should become a rule, script, or skill; or prepare a plan for AGENTS rule maintenance.
---

# Agents Rule Maintainer

## Workflow

Use this skill as a planning and rule-design guide. Do not directly modify
`AGENTS.md` just because the skill triggered; first produce a labeled plan and
wait for explicit approval.

Read in this order:

1. Current user request and any scope limits.
2. Repository `AGENTS.md`, then nearer directory instructions if relevant.
3. Existing `.codex/corrections/` entries and task tracking only when the
   request asks to promote or audit them.
4. The target rule section, nearby overlapping rules, and validation scripts or
   README files that already govern the same workflow.

## Task Sizing

Before planning, classify the task size. Record the reason in the response or
task tracking when applicable.

- Small: one focused rule wording change, no file moves, no cross-reference
  updates, and no broad validation.
- Medium: several related rules, one directory or section, or one source such as
  corrections/task tracking being promoted.
- Large: many files or sections, directory architecture changes, recursive
  references, pending/corrections synchronization, Git closure, or multi-round
  validation.

For large work, propose an agent-group or task-tree plan. For small work, say why
that is unnecessary.

## Approval Plan

Every plan must include:

1. A semantic label such as `计划-压缩审批流程` or `计划-升级规则沉淀`.
2. Numbered steps.
3. Expected files or directories to read and modify.
4. Validation commands.
5. Risk boundary and explicit exclusions.

End the approval request with a standalone Markdown level-three line:

### 请回复：批准：计划-示例标签 / 批准：全部

If multiple plans are listed, plain `批准` is ambiguous; ask which label is
approved.

## Rule Extraction Boundaries

Extract durable rules only from repeated failures, explicit user preferences,
repo-wide maintenance needs, or workflows that must be consistently enforced.
Do not promote one-off taste, temporary workaround, speculative advice, or a
task-specific detail into `AGENTS.md`.

Prefer compressing duplicated rules before adding new ones. Split a rule only
when it mixes different triggers, ownership boundaries, or validation duties.
If a rule describes deterministic repeated actions, consider whether a script or
skill is better than more prose.

When rules conflict, preserve higher-priority instructions and ask for a plan
decision instead of silently choosing. Never rewrite unrelated sections just to
make nearby wording look uniform.

## Writeback

If the approved work uses corrections or task tracking as evidence, record the
promotion result back to the relevant tracking place required by the repository:
what rule changed, which source lesson it came from, what remains pending, and
why anything was not promoted. Keep this writeback inside the approved scope.

## Validation

After editing a skill, run:

```bash
python C:/Users/he/.codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/agents-rule-maintainer
```

For AGENTS rule edits, also run targeted text checks such as:

```bash
rg -n "old-rule-text|new-rule-text" AGENTS.md .codex/corrections .codex/task-tracking
```

Report changed files, validation commands, trigger scenarios, and remaining risk
boundaries in the final response.
