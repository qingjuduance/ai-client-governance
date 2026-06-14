# AI Rules

## 快速索引

| 项目 | 说明 |
|---|---|
| 用途 | 保存可跨电脑、跨项目复用的 Codex/AI 协作规则。 |
| 主规则 | `AGENTS.md` |
| 本地 skills | `.codex/skills/` |
| 协作协议 | `docs/_meta/agent-collaboration.md` |
| 安装脚本 | `install-ai-rules.ps1` |
| 会话检查 | `check-ai-rules-sync.ps1` |
| 同步脚本 | `sync-ai-rules.ps1` |

本仓库只保存 AI 规则、协作脚本和安装同步工具，不保存具体简历、学习正文、
项目源码快照或会话运行状态。

## 使用方式

在目标项目中安装规则：

```powershell
powershell -ExecutionPolicy Bypass -File D:\root\file\resume\ai-rules\install-ai-rules.ps1 -TargetProjectPath D:\path\to\project
```

安装会复制 `AGENTS.md`、本地 skills、协作脚本和会话检查脚本。若目标路径已有
同名文件或目录，脚本会先备份到 `.codex/ai-rules-backups/`，再覆盖托管规则文件。

安装后，每次开启新的 Codex 会话时，先执行目标项目根目录下的：

```powershell
powershell -ExecutionPolicy Bypass -File .\check-ai-rules-sync.ps1
```

检查脚本会读取 `.codex/ai-rules-config.json`，找到这份规则仓库；如果距离上次
成功同步已经超过 24 小时，就执行一次拉取、合并和推送。未超过 24 小时时只输出
跳过说明。

## 同步行为

`sync-ai-rules.ps1` 在规则仓库中执行：

1. 检查 Git 仓库，不存在时初始化。
2. 如果有本地规则变更，先提交到本地 Git。
3. 如果配置了 `origin`，执行 `git pull --no-rebase --no-edit origin <branch>`。
4. 合并没有冲突后执行 `git push -u origin <branch>`。
5. 把本次同步、推送、commit 和结果写入 `.ai-rules-sync/state.json`。

如果发生合并冲突，脚本会停止并保留现场，不会自动覆盖任何一方的规则。

## 远程仓库

首次使用远程仓库时，在本目录执行：

```powershell
git remote add origin git@github.com:your-name/ai-rules.git
powershell -ExecutionPolicy Bypass -File .\sync-ai-rules.ps1
```

如果没有配置 remote，脚本只维护本地 Git 和同步状态，不会尝试推送。

## 规则范围

纳入同步：

- `AGENTS.md`
- `.codex/skills/agents-rule-maintainer/`
- `.codex/skills/locate-pasted-content/`
- `.codex/skills/self-correction-planner/`
- `scripts/agent_comm.py`
- `scripts/agent_group_status.py`
- `scripts/scan_corrections.py`
- `scripts/scan_markdown_compliance.py`
- `docs/_meta/agent-collaboration.md`

不纳入同步：

- `.codex/task-tracking/`
- `.codex/pending-tasks/`
- `.codex/agent-comm/`
- `.codex/agent-groups/`
- 简历、学习正文、源码快照和会话运行日志。

