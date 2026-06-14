# 子 AI 协作协议

## 快速索引

| 项目 | 说明 |
|---|---|
| 关键词 | 子 AI、智能体组、任务量评估、任务树、Agent Brief、状态看板 |
| 适用范围 | 全仓文档重构和后续大型文档任务 |
| 关联架构 | `organization.md` |
| 迁移队列 | `migration-queue.md` |
| 当前状态 | 树形递归执行协议 |

本协议用于把“大文档重构”拆成可验证的小任务。它不是学习正文，
而是后续执行时的协作约束。

## 任务量评估

启动执行前，总控必须先判断当前任务是“小任务”还是“大任务”。这个判断不能等
任务做了一半再补，也不能因为主对话觉得自己能处理就跳过。评估结果要写入
task tracking，并决定是否必须创建智能体组。

评估至少覆盖：

| 维度 | 小任务特征 | 大任务触发条件 |
|---|---|---|
| 文件范围 | 1 到 2 个明确文件 | 3 个以上文件，或跨多个目录职责层 |
| 主题数量 | 1 到 2 个明确问题 | 写作、实现或整理对象超过 3 个 |
| 检查数量 | 少量局部检查 | 检查、审核或验证对象超过 5 个 |
| 状态同步 | 不改 pending、corrections、状态看板 | 需要同步 pending、corrections、`.references` 或看板 |
| 验证复杂度 | 单个命令或人工复核即可 | 需要链接、引用、敏感信息、diff、脚本等多轮验证 |
| 恢复要求 | 不需要后台恢复现场 | 已在 pending 中登记为执行中、待验证、阻塞或可恢复 |

只要命中任一大任务触发条件，就必须先创建智能体组和任务树。总控负责建立根节点、
定义父节点和叶子节点、同步状态文件，再让叶子节点执行具体正文、代码、迁移或验证。
如果边界不清，按大任务处理；只有确认没有跨目录状态同步、没有 pending 恢复现场、
没有超出 3/5 阈值时，主对话才可以直接执行。

## 智能体组

每个用户问题、用户批准后的执行任务或可独立恢复的后台任务，都对应一个
智能体组。主对话是前台总控，负责继续回应用户、接收新问题、维护看板和做最终
收口；后台智能体组负责按任务树推进具体工作。

前台和后台不能互相阻塞：

- 前台继续回答用户问题，但必须知道后台有哪些组正在运行。
- 后台继续处理任务，但必须把父子关系、叶子任务、状态和未完成项写入恢复现场。
- 如果用户在后台运行期间提出新问题，先判断是新增智能体组、补充当前组，
  还是中断/替换当前组；不能让旧组悄悄继续执行过期目标。

## 状态看板

每个长任务或多 AI 任务必须维护智能体组状态看板。看板至少包含：

| 字段 | 含义 |
|---|---|
| `group_id` | 智能体组 ID，使用稳定中文或英文短名。 |
| `group_title` | 该组处理的问题或任务。 |
| `task_tracking_file` | 本组对应的 task tracking 文件，用于恢复完整过程。 |
| `pending_file` | 本组对应的 pending 或恢复现场文件；没有则写明无。 |
| `approval_label` | 本组最近一次执行依据，例如用户批准标签或未启动原因。 |
| `last_checkpoint` | 最近安全停止点，说明断点恢复时不用重复读取的结论。 |
| `restore_reading_list` | 新会话恢复本组时最小读取清单。 |
| `parent_node` | 当前父节点或总控节点。 |
| `leaf_count` | 当前叶子任务数量。 |
| `status` | `待启动`、`运行中`、`暂停`、`待验证`、`已完成`、`阻塞`。 |
| `active_agents` | 正在运行的子 AI ID 或昵称。 |
| `closed_agents` | 已关闭的子 AI。 |
| `residual_agents` | 无法确认、工具侧找不到或 UI 残留的子 AI。 |
| `current_files` | 当前处理或待合并文件。 |
| `unfinished_items` | 未完成项。 |
| `next_action` | 恢复时第一步。 |

用户询问“现在还有几个智能体组”“为什么还在运行”“哪些任务没完成”时，
先展示该看板摘要，再继续执行或解释。

## 看板工具

智能体组看板使用结构化状态文件和脚本：

```text
.codex/agent-groups/current-status.json
scripts/agent_group_status.py
```

状态文件是事实源。总控在以下动作后必须更新它：

- 创建智能体组或父/叶子节点。
- 启动、暂停或关闭子 AI。
- 父节点返回拆分结论。
- 叶子节点完成具体任务。
- 发现工具侧找不到子 AI、UI 残留、悬空链接、敏感信息或验证失败。

脚本使用方式：

```powershell
python scripts\agent_group_status.py --once
python scripts\agent_group_status.py --once --verbose
python scripts\agent_group_status.py --watch --interval 5 --max-iterations 12
python scripts\agent_group_status.py --once --format json
python scripts\agent_group_status.py --once --validate
```

`--watch` 只在终端或工具输出里持续显示，不能绕过 Codex 对话机制主动发送聊天消息。
主对话仍要在用户询问、状态变化或阶段收口时调用 `--once` 并展示摘要。
`--validate` 用于检查状态文件里手写的 `summary` 是否与脚本实时计算一致；
发现漂移时先修状态文件，再继续启动或关闭子 AI。

## 通信总线

内置多智能体工具适合即时控制：创建子 AI、发送一次指令、等待结果、关闭或恢复。
它不保证提供持久 inbox/outbox、ack、heartbeat、交付物索引和真实 token usage。
因此长期任务和跨会话恢复需要同步维护本机文件型通信总线：

```text
.codex/agent-comm/
  locks.json
  groups/<group-id>/
scripts/agent_comm.py
```

通信总线只保存过程事实，不作为正式学习材料入口。初版使用 UTF-8 JSON/JSONL
作为事实源，后续如果消息量变大，可以添加 SQLite 只读索引；但不能把二进制
数据库变成唯一恢复入口。

总控在创建或判断子 AI 能力前，先查看当前工具 schema、已启用插件和 skill 说明、
`scripts/agent_group_status.py`、`scripts/agent_comm.py`、状态看板和通信总线。
只有这些来源无法确认时，才创建“能力探测”叶子 AI；探测 AI 只读 brief 和指定
通信目录，不读取旧 task tracking、pending 或 corrections 全文。

常用命令：

```powershell
python scripts\agent_comm.py init <group-id> --title "<title>"
python scripts\agent_comm.py register <group-id> <agent-id>
python scripts\agent_comm.py send <group-id> --to <agent-id> --body "..." --requires-ack
python scripts\agent_comm.py ack <group-id> <message-id> --from <agent-id>
python scripts\agent_comm.py heartbeat <group-id> <agent-id> --status running
python scripts\agent_comm.py artifact <group-id> <agent-id> --path "<path>"
python scripts\agent_comm.py report <group-id>
python scripts\agent_comm.py validate <group-id>
```

每个子 AI 的最终输出和通信记录都必须包含 `token_usage_source`。取值优先为
`real_tool_usage`；工具未返回真实 usage 时写 `unavailable`；只有做了明确
文件数、行数、brief 长度等估算时才写 `proxy_estimate`。

### 多组并发

多个智能体组同时存在时，总控必须把它们当作并发系统管理，而不是把每组当作
互不影响的聊天分支。每组启动前至少登记：

- `group_id` 和通信组。
- `write_scopes`，即允许写入的文件或目录。
- 当前 owner，可以是主控、父节点或叶子子 AI。
- 租约过期时间、heartbeat 周期和 stale 处理策略。
- 冲突策略：拒绝、等待、拆分到不同锚点，或由主控顺序合并。

同一文件、同一目录或父子目录范围默认视为重叠写范围。没有锁和冲突策略时，
不得让两个组同时写。确需并发处理同一文件时，必须在 task tracking 写清
不重叠标题、锚点或行段，并在最终合并前由主控复查 diff 和 `.references`。

通信总线的并发命令：

```powershell
python scripts\agent_comm.py init <group-id> --title "<title>" --write-scope "<path>"
python scripts\agent_comm.py lock acquire <group-id> --owner <agent-id> --scope "<path>"
python scripts\agent_comm.py lock release <group-id> --lock-id <lock-id>
python scripts\agent_comm.py lock status --active-only
python scripts\agent_comm.py validate <group-id>
```

`validate` 必须检查未 ack 消息、单个 mailbox 内重复 ID、缺失或过期 heartbeat、
锁范围是否越过声明的 `write_scopes`，以及跨 group 的活跃锁冲突。

## 上下文压缩输入包

创建子 AI 前，总控必须同时设计“做什么”和“读什么”。任务树只解决分工问题，
Agent Brief 解决上下文输入成本问题。

推荐把 brief 写入：

```text
.codex/agent-briefs/<group-node>.md
```

也可以在 spawn 消息中给出等价短输入包，但必须包含同样字段：

| 字段 | 含义 |
|---|---|
| `task_scope` | 当前节点只负责什么对象。 |
| `allowed_files` | 允许修改的文件或目录。 |
| `required_inputs` | 必读 brief、正文、`.references`、源码或官方链接。 |
| `skip_inputs` | 已由总控压缩、禁止重复全量读取的历史材料。 |
| `confirmed_facts` | 总控已核对的版本、源码入口、状态和边界。 |
| `validation` | 子 AI 必须运行或汇报的验证命令。 |
| `output_contract` | 返回时必须包含的 delta summary。 |
| `token_proxy` | 真实 token usage 或文件数、行数、brief 长度等代理指标。 |
| `comm_bus` | 通信组、agent id、inbox/outbox、ack、heartbeat 和 artifact 要求。 |
| `write_scope` | 本节点允许写入的文件、目录、标题或锚点范围。 |
| `lock_policy` | 是否必须获取锁、租约时长、冲突处理和释放时机。 |

默认流程：

1. 总控读取全局规则、pending、task tracking、corrections 和状态看板。
2. 总控把当前节点需要的事实压缩进 brief。
3. 总控按需初始化 `.codex/agent-comm/` 通信组并发送需要 ack 的消息。
4. 子 AI 只读 brief、自己的目标文件、必要 `.references`、必要源码和官方链接。
5. 子 AI 返回 delta summary，总控再写回 task tracking。

不默认传递完整历史上下文。只有任务强依赖当前长对话细节、文件强耦合或用户明确
要求时，才允许创建带完整历史的子 AI；总控必须在 task tracking 写明原因、风险、
额外输入范围和为何 brief 不足。

当前工具不一定返回每个子 AI 的真实 token usage。没有真实统计时，只能写
“通过少读文件、压缩输入降低上下文输入量”，并列出代理指标；不能写
“已精确节省 token”。

## 核心模型

子 AI 分工按“任务树”执行。根节点和中间节点是父节点 AI，只负责判断、
拆分、调度、合并和验收；真正写正文、改代码、迁移文件、跑验证的只能是
叶子节点 AI。

```text
根节点总控
├── 父节点：Java 内容重构
│   ├── 叶子：Java 路线复核
│   ├── 叶子：Java 语言三层补缺
│   └── 叶子：Java 索引和引用检查
├── 父节点：C++/Qt 内容重构
│   ├── 叶子：C++ language
│   ├── 叶子：Qt core/widgets
│   └── 叶子：Chromium 项目链路
└── 父节点：验证收口
    ├── 叶子：链接检查
    ├── 叶子：pending/corrections 检查
    └── 叶子：敏感信息和 diff 检查
```

如果某个节点拿到的任务还能继续拆成超过阈值的具体任务，它就是父节点，
不能直接处理正文。只有当任务已经足够具体、输入输出明确，并且不超过阈值，
该节点才是叶子节点。

## 角色分层

| 角色 | 职责 | 默认负载上限 |
|---|---|---:|
| 总控 AI | 建根任务树、定目录、回收子 AI、最终验收 | 不直接写正文 |
| 父节点 AI | 拆分、判断阈值、创建必要子 AI、整合子结果 | 不直接写正文 |
| 盘点叶子 AI | 只读检查旧文件、迁移归属、链接风险 | 3 个对象 |
| 写作叶子 AI | 在明确目标目录内写正文或 README | 3 个对象 |
| 整合叶子 AI | 检查结构、链接、循环引用、风格和遗漏 | 5 个对象 |
| 验证叶子 AI | 执行检查命令、汇总失败项 | 5 个对象 |

阈值是“每个 AI 节点的直接子任务上限”，不是整棵任务树的全局上限。
写作、实现和资料整理叶子节点默认最多 3 个对象；检查和整合叶子节点默认最多
5 个对象。阈值不是永久固定值，每批任务都记录实际负载、返工次数、等待时间
和质量问题，后续根据这些数据调整默认上限。

## 通信规则

每个父节点或叶子节点的任务说明必须包含：

- 节点类型：父节点或叶子节点。
- 父节点 ID 或父节点名称。
- 当前节点负责对象；叶子写作节点最多 3 个，叶子检查节点最多 5 个。
- 禁止范围，例如不能修改 `code/`、`quick-review/`、`interview/`、`delivery/`。
- 目标目录和文件命名。
- 是否允许修改 README、`.references/`、task tracking。
- Agent Brief 路径或等价短输入包。
- 必读文件、可跳过文件和 token 代理指标。
- 通信组 ID、agent id、是否需要 ack、heartbeat 周期和 artifact 登记要求。
- 写范围、锁 ID、租约过期时间、并发组列表和冲突策略。
- 如果任务超过阈值，必须继续拆分，不得硬做。
- 输出格式：改动文件、覆盖点、风险、未处理项。

叶子 AI 返回后，父节点 AI 先做两件事：

1. 检查它是否越界、重复、形成冲突。
2. 把结果合并成父节点交付摘要，标明已完成、未完成、风险和需要上级处理的项。

父节点 AI 返回给上级时，不交付零散正文，而交付“子节点结果汇总”：

- 任务树节点和子节点列表。
- 每个叶子节点的文件范围、完成状态和未完成项。
- 是否有子 AI 未关闭、无法确认或 UI 残留。
- 需要总控合并到迁移队列、README、`.references/`、pending 和 task tracking 的内容。

## 启动前清理

启动新的任务树前，总控必须先处理上一批子 AI：

1. 关闭已经完成、暂停或不再需要的子 AI。
2. 不复用旧子 AI，也不把旧子 AI 换名继续承担新职责。
3. 如果工具返回 `not found`、无法关闭或 UI 仍显示运行，记录为“无法确认残留”，
   写入 task tracking 和 pending。
4. 不得在旧子 AI 仍按过期任务运行时启动新分工。
5. 如果只剩工具侧找不到 ID 的 UI 残留，先写入状态看板和恢复现场；
   用户批准继续后，可以创建全新的子 AI，但不得复用或换名使用旧子 AI。

用户中途纠正规则、要求暂停或发现分工错误时，总控必须立即中断相关子 AI，
要求它们只汇报已改文件、未完成项和子任务状态，然后关闭或登记无法关闭状态。

## 动态调参数据

每批任务记录以下字段：

| 字段 | 含义 |
|---|---|
| `task_size_assessment` | 执行前任务量评估结论，小任务或大任务及触发原因。 |
| `task_tree_root` | 本批任务树根节点。 |
| `group_id` | 当前智能体组 ID。 |
| `group_status` | 当前组状态。 |
| `parent_node` | 当前节点的父节点。 |
| `node_type` | 父节点或叶子节点。 |
| `planned_objects` | 计划对象数量。 |
| `actual_objects` | 实际处理对象数量。 |
| `over_limit` | 是否超过默认 3/5 阈值。 |
| `spawned_children` | 是否因为超限再次拆分子 AI。 |
| `leaf_tasks` | 真正执行正文、代码、迁移或验证的叶子任务。 |
| `closed_children` | 已关闭的子 AI 列表。 |
| `residual_children` | 无法关闭、无法确认或 UI 残留的子 AI。 |
| `agent_brief` | 子 AI 使用的 brief 路径或等价短输入包说明。 |
| `required_input_count` | 子 AI 必读文件数或输入片段数。 |
| `skipped_input_count` | 由总控压缩后禁止重复读取的文件数或片段数。 |
| `token_usage_source` | 真实工具统计、模型上下文估算、代理指标或暂无数据。 |
| `comm_group` | `.codex/agent-comm/` 中的通信组 ID。 |
| `comm_ack_status` | 需要确认的消息是否已 ack。 |
| `heartbeat_status` | 子 AI 最近一次 heartbeat 状态和时间。 |
| `write_scopes` | 本组声明的写范围。 |
| `active_locks` | 本组当前持有的锁。 |
| `lock_conflicts` | 跨组锁冲突或重叠写范围。 |
| `review_batch_size` | 整合或检查批次对象数量。 |
| `rework_count` | 因结构、链接、内容质量造成的返工次数。 |
| `wait_minutes` | 等待子 AI 输出的时间。 |
| `quality_notes` | 错误、遗漏、越界或值得保留的经验。 |

这些数据写入本次 `.codex/task-tracking/`，不写入正式学习正文。

## 小时 commit 检查

长任务每隔 1 小时做一次 commit 检查，检查不等于自动提交。

检查内容：

- 当前时间和上次检查时间。
- 是否有子 AI 正在运行。
- 是否存在未合并子 AI 输出。
- 工作区是否有无关脏改动。
- 准备暂存的文件范围。
- 验证命令是否通过。
- 是否已获得用户批准。
- commit hash 或跳过原因。

如果仍有子 AI 在运行，总控 AI 只能在确认不覆盖其写入范围后提交；
否则记录“等待子 AI 完成”或“只提交不冲突范围”的原因。

## 循环引用边界

正式 README、路线和项目入口不能链接 `questions/` 文件。
`questions/` 文件也不能反向链接正式 README 或路线。

发现循环时，优先保留真实源码、官方文档、系统知识和项目落地文件，
删除或改写会造成互链的学习入口链接。
