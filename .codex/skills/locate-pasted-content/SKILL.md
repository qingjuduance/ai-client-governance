---
name: locate-pasted-content
description: Locate the repository file or documentation section that a user's pasted code, Markdown, or notes came from before answering or editing. Use whenever the user pastes a snippet and asks for explanation, modification, continuation, correction, documentation cleanup, or learning-note sedimentation in this repository.
---

# Locate Pasted Content

## Workflow

Before answering or editing based on pasted content, first locate where the pasted text belongs in the current repository.

1. Extract distinctive search terms from the paste:
   - Prefer exact function names, headings, struct names, route paths, code lines, or unusual Chinese phrases.
   - For long pasted blocks, search two or three shorter stable fragments instead of the whole block.
   - Ignore generic terms such as `理解`, `示例`, `return`, `nil`, or common boilerplate unless they are part of a unique line.

2. Search with `rg` from the repository root:

```powershell
rg -n --fixed-strings "unique fragment" .
```

Use regex search only when exact fixed-string search is too narrow:

```powershell
rg -n "runTask|goroutine|provider" .
```

3. If multiple files match, choose the current source by context:
   - Prefer the file whose surrounding headings match the pasted section.
   - Prefer the file in the directory named or implied by the user.
   - Prefer maintained Markdown files over generated outputs or copied external snapshots.
   - Do not treat `.source-projects/` snapshots as the documentation source unless the user is asking about source code itself.

4. Read the target directory guidance before changing files:
   - Read the current directory `README.md` when present.
   - If absent, read the nearest parent `README.md`, then the root `README.md`.
   - Follow `AGENTS.md` repository rules for question sedimentation and links.

5. Answer in the current conversation:
   - Explain the concept or change directly in the reply.
   - Do not only write a new document and point the user to it.
   - Mention the located file when it affects where the change should be made.

6. Make document changes only in the relevant location:
   - If the paste comes from `basics/`, create or update only `basics/questions/` unless the user explicitly asks for more.
   - If it comes from `learning/`, create or update only `learning/questions/`.
   - If it comes from `notes/`, create or update only `notes/questions/`.
   - Keep Markdown links relative inside repository documents.

7. Record location effectiveness in the current task tracking document:
   - Whether the session cache was checked and whether it hit.
   - Search terms used, `rg` query count, hit scope, and candidate file count.
   - Final matched file or section, and whether the search scope had to expand.
   - Files, line ranges, or fragments actually read before deciding.
   - Whether precise search avoided a full-repository scan or large-file full read.
   - If no match was found, the no-hit evidence and the directory inference used.
   - Token data source: real tool statistics, proxy metrics, or no data.

Do not claim that the skill saved tokens unless real token data exists. When only proxy
metrics are available, describe reduced context input through fewer files, fewer lines,
or narrower fragments.

## When Location Is Unclear

If `rg` finds no match, say that the pasted content was not found in the repository, then infer the most likely target directory from the user's wording. Ask a concise clarification only when writing to the wrong directory would create misleading documentation.

If the user asks a purely conceptual question and the paste is only illustrative, still try to locate it once. If it cannot be located, answer directly and avoid creating repository files unless the user asks to persist the explanation.

## Validation

After edits, verify:

```powershell
git diff --check -- <changed-files>
git status --short
```

For question sedimentation, also verify that only the intended `questions/` directory received the new or updated file.
