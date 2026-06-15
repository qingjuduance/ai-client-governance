# AI Rules

## 快速索引

| 项目 | 说明 |
|---|---|
| 仓库定位 | 可嵌入到任意项目的通用 Codex/AI 协作规则仓库。 |
| 推荐嵌入位置 | 目标项目 `.codex/ai-rules/` |
| 通用规则入口 | `.codex/ai-rules/AGENTS.md` |
| 项目规则入口 | 目标项目 `.codex/rules/project/AGENTS.md` |
| 机器清单 | `manifest.json` |
| 嵌入脚本 | `install-ai-rules.ps1` |
| 会话检查 | `check-ai-rules-sync.ps1` |
| 推荐嵌入方式 | Git submodule |
| 默认同步策略 | 每次会话检查；最多 24 小时 fetch 一次；不自动 pull/push。 |
| 回写方式 | 进入 `.codex/ai-rules/` 后使用普通 Git 命令提交和推送。 |

这个仓库不是某个项目的 `.codex/rules/common/` 文件夹备份，而是一套完整的
通用 AI 协作规则仓库。目标项目应把本仓库作为一个独立 Git 仓库嵌入进来，
Git 项目默认用 submodule 记录精确规则版本，让通用规则、通用 skills、
门禁脚本、README 和 manifest 保持完整上下文。

## 当前优势

- **完整 Git 边界**：通用规则有自己的 commit、branch、remote 和 history；
  Git submodule 让父项目只记录一个 gitlink commit，项目内修改通用规则时，
  可以直接在 `.codex/ai-rules/` 用 Git 回写。
- **不再依赖复制托管清单**：目标项目不需要把 common 规则、scripts、skills
  分散复制到多个位置，避免复制漏项、旧文件覆盖和双向同步歧义。
- **common/project 边界清楚**：本仓库只维护跨项目通用协作规则；项目业务、
  文档体系、简历、源码快照和本地交付规则留在目标项目。
- **每次会话都能发现不一致**：检查脚本每次运行都会检查 embedded repo 是否
  missing、dirty、ahead、behind 或 diverged；一旦不一致，会持续提示到同步完成。
- **24 小时只限制 fetch**：为了减少远端请求，默认最多 24 小时 fetch 一次；
  但本地 dirty/ahead/behind/diverged 状态每次会话都会检查并提示。
- **适合 GitHub 展示和复用**：README、manifest、AGENTS 和脚本共同说明如何嵌入、
  如何维护边界、如何同步和如何把改动回写给上游。

每次准备把本仓库上传或推送到 GitHub 前，都要回看本 README 的“当前优势”和
`manifest.json`，确认它们真实反映当前仓库能力。新增门禁、skill、脚本或嵌入策略后，
README 需要同步更新，方便别人一眼看懂这个仓库的价值。

## 给其它 AI 的使用约定

当用户在另一个项目里告诉你本仓库位置时，按这个顺序处理：

1. 读取本仓库 `README.md` 和 `manifest.json`，确认当前 schema、嵌入位置和同步策略。
2. 在目标项目中嵌入完整仓库，推荐路径为 `.codex/ai-rules/`；
   目标项目是 Git 仓库时默认使用 Git submodule。
3. 更新目标项目根 `AGENTS.md` 为薄入口：先读 `.codex/ai-rules/AGENTS.md`，
   再读 `.codex/rules/project/AGENTS.md`。
4. 确认项目特有规则只放在 `.codex/rules/project/`，不要写回本仓库。
5. 每次新会话先运行 `.codex/ai-rules/check-ai-rules-sync.ps1` 或目标项目根部
   等价 wrapper；若提示不一致，必须提醒用户，直到 Git 同步完成。

## 嵌入方式

### 推荐：Git submodule

目标项目已经是 Git 仓库，且希望父仓库记录 ai-rules 的精确版本时，使用 submodule：

```powershell
git submodule add <ai-rules-url> .codex/ai-rules
git submodule update --init --recursive
```

后续更新：

```powershell
git -C .codex/ai-rules fetch origin
git -C .codex/ai-rules pull --ff-only
git add .gitmodules .codex/ai-rules
git commit -m "chore: update embedded ai-rules"
```

Git 官方文档把 submodule 定义为“把一个 Git 仓库作为另一个 Git 仓库的子目录”，
这正是本仓库推荐模型：父项目记录所使用的规则版本，规则仓库保留独立历史。

### 备选：嵌套 clone

如果暂时不想让父仓库记录 submodule，也可以直接 clone：

```powershell
git clone <ai-rules-url-or-local-path> .codex/ai-rules
```

这种方式更轻，但父仓库不会自然记录嵌入规则版本。需要在目标项目 README、
`.codex/ai-rules-config.json` 或 task tracking 中记录当前 commit。

### 脚本辅助嵌入

本仓库提供一个脚本化入口，默认使用 Git submodule，不复制 managed paths：

```powershell
powershell -ExecutionPolicy Bypass -File <ai-rules-path>\install-ai-rules.ps1 `
  -TargetProjectPath <target-project-path> `
  -RemoteUrl <ai-rules-url>
```

脚本只做三件事：嵌入完整仓库、写目标项目薄入口、写 `.codex/ai-rules-config.json`。
它不会把 `AGENTS.md`、scripts 或 skills 分散复制到目标项目根目录。
如果目标项目不是 Git 仓库，或明确不希望父仓库记录 ai-rules 提交，才传
`-Mode clone` 使用 nested clone。

## 目标项目结构

```text
target-project/
├── AGENTS.md
└── .codex/
    ├── ai-rules/
    │   ├── AGENTS.md
    │   ├── README.md
    │   ├── manifest.json
    │   ├── scripts/
    │   └── .codex/skills/
    ├── ai-rules-config.json
    └── rules/
        └── project/
            └── AGENTS.md
```

- `AGENTS.md`：目标项目薄入口，不承载完整规则正文。
- `.codex/ai-rules/`：本仓库的完整 Git 工作树，是通用规则事实源。
- `.codex/rules/project/`：目标项目维护的本地规则，不写回本仓库。
- `.codex/rules/common/`：旧复制模型的兼容路径；新项目不要再把它当事实源。

## 每次会话检查

在目标项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\.codex\ai-rules\check-ai-rules-sync.ps1 `
  -TargetProjectPath .
```

检查脚本只读检查嵌入仓库状态，默认行为如下：

- 每次会话都检查 `.codex/ai-rules` 是否存在、是否为 Git 仓库、是否有 dirty 改动。
- 如果上次 fetch 已超过 24 小时，执行一次 `git fetch`；未超过 24 小时则跳过 fetch。
- 无论是否 fetch，都会比较本地 HEAD 与 upstream，发现 ahead、behind 或 diverged
  就提示用户。
- 不自动 `git pull`，因为 pull 可能修改规则工作树。
- 不自动 `git push`，因为 push 需要用户明确确认远端边界。
- warning 会每次出现，直到用户在 `.codex/ai-rules/` 中完成同步。

常见处理命令：

```powershell
git -C .codex/ai-rules status
git -C .codex/ai-rules pull --ff-only
git -C .codex/ai-rules push
```

如果出现 diverged 或冲突，停止自动处理，保留现场，让用户决定 merge、rebase
或拆分提交。

## 写回通用规则

修改通用规则时，直接在嵌入仓库中工作：

```powershell
cd .codex/ai-rules
git status
git add AGENTS.md README.md manifest.json scripts
git commit -m "docs: update common AI rules"
git push origin main
```

不要把目标项目 `.codex/rules/project/`、`.codex/task-tracking/`、
`.codex/pending-tasks/`、`.codex/corrections/`、`.codex/tool-invocations/`
或业务文档写回本仓库。

## 通用与项目规则边界

纳入本仓库：

- AI 协作审批、任务量评估、恢复现场、Git 边界和子 AI 协作。
- corrections、pending、task tracking、门禁脚本、编码检查和脚本维护要求。
- 可跨项目复用的 Codex skills 和只读维护脚本。
- 嵌入、同步检查、Git 回写和 README/manifest 自描述规则。

不纳入本仓库：

- 目标项目业务规则、目录结构、学习路线、简历规则和交付物规则。
- 目标项目 `.codex/rules/project/`。
- 目标项目 task tracking、pending、corrections、tool invocation 账本。
- 外部项目状态、日志、源码快照、构建产物和本地临时验证目录。

## Legacy 兼容说明

旧版本使用 `managed_paths` 把通用规则复制到 `.codex/rules/common/`，
还会复制 scripts 和 skills。这个模型已经降级为 legacy：

- 新项目默认使用 `.codex/ai-rules/` 完整嵌入。
- `.codex/rules/common/` 只作为迁移期间 fallback，不再作为通用规则事实源。
- `manifest.json` schema 3 不再声明 `managed_paths`。
- 如需迁移旧项目，先嵌入完整仓库，再把根 `AGENTS.md` 改为读取
  `.codex/ai-rules/AGENTS.md` 和 `.codex/rules/project/AGENTS.md`。

## 验证建议

修改本仓库后，至少运行：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONPYCACHEPREFIX = ".codex\cache\python-pycache"
python scripts\validate_encoding.py --paths AGENTS.md README.md manifest.json scripts --require-paths
python -m py_compile scripts\codex_session_gate.py scripts\codex_task_gate.py scripts\codex_tool_flow.py
python scripts\codex_session_gate.py --help
python scripts\codex_task_gate.py --help
python scripts\codex_tool_flow.py --help
```

修改 PowerShell 脚本后，还要用 PowerShell Parser 做语法检查，并在临时目录跑最小
真实用例：嵌入仓库、写 config、运行每次会话检查、验证 warning/OK 输出符合预期。
