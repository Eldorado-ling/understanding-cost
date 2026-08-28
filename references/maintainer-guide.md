# 维护者指南

本文件保存不应占用 SkillHub 用户概述的开发信息。教学行为以 `SKILL.md` 及其他 `references/` 协议为准。

## Demo 与校验

核心 Vault 与测试脚本要求 Python 3.10 或更高版本，并只使用 Python 标准库。发布流程图还需要 Node.js/npm、`@mermaid-js/mermaid-cli@11.12.0` 与 Pillow；这些依赖只用于生成带水印的审阅图，不进入学习运行时。

```powershell
py -3 -X utf8 scripts\vault_tool.py validate --vault demo-vault
py -3 -X utf8 scripts\vault_tool.py issue-route --vault demo-vault --record <route-input.json>
py -3 -X utf8 scripts\vault_tool.py resolve-teaching --vault demo-vault --dry-run
py -3 -X utf8 scripts\vault_tool.py issue-teaching --vault demo-vault --content <delivery-content.json>
py -3 -X utf8 scripts\vault_tool.py append-evidence --vault demo-vault --record <evidence-input.json>
py -3 -X utf8 scripts\vault_tool.py open-verification --vault demo-vault --process-evidence-id <committed-id>
py -3 -X utf8 scripts\vault_tool.py schedule-retention --vault demo-vault --record <retention-schedule.json>
py -3 -X utf8 scripts\vault_tool.py open-delayed-verification --vault demo-vault --state-id <state-id>
py -3 -X utf8 scripts\vault_tool.py inspect-cone --vault demo-vault
py -3 -X utf8 scripts\self_test.py
py -3 -X utf8 scripts\render_flowchart.py --input review-assets\understanding-cost-flow-v4.0.0.mmd --output review-assets\understanding-cost-flow-v4.0.0.png --config review-assets\puppeteer-config.json --scale 3
py -3 -X utf8 scripts\check_release.py --root .
```

macOS / Linux 使用 `python3`。预期 Vault 校验为 `status: ok`、`error_count: 0`、`warning_count: 0`，回归测试为 `status: ok`。

生产锁默认最多等待 10 秒。只有故障注入或运维诊断才可临时设置 `UNDERSTANDING_COST_LOCK_TIMEOUT_SECONDS=0..60`；超时必须返回错误且 Vault 零变化，不能以关闭互斥作为恢复方式。

`append-evidence` 的四阶段完整输入模板位于 [templates/append-evidence](../templates/append-evidence/README.md)；路线与保持模板位于 [templates/route-retention](../templates/route-retention/README.md)。teaching_process 的绑定优先从 `issue-teaching` 返回的内部 `process_binding` 复制；retention 的 `teaching_item_id` 必须来自 `open-delayed-verification` 已持久化的 open receipt。两类内部对象都不能进入用户投影。

再使用当前 Agent 环境中的 `skill-creator/scripts/quick_validate.py` 校验目录结构。SkillHub 发布包另需在暂存副本的 `SKILL.md` frontmatter 中加入平台要求的 `slug`、`version`、`displayName` 和 `summary`；不要把这些平台字段写回要求严格 frontmatter 的 Codex 源目录。

## 流程图与协议同步

[文字协议](workflow.md) 与 [v4.0.0 流程图源文件](../review-assets/understanding-cost-flow-v4.0.0.mmd) 是同一执行合同的文字版和图形版；[带 ELD 水印的审阅 PNG](../review-assets/understanding-cost-flow-v4.0.0.png) 必须由 `scripts/render_flowchart.py` 生成并嵌入 [SKILL.md](../SKILL.md)。不存在“实现优先”或“图只供参考”的关系。修改任一方时必须在同一变更中同步另一方，并运行以下一致性检查；任一状态、门、回路、回写语义、版本号或水印不一致时，该版本不得交付：

- 每个计算或保存字段都有明确消费者；无消费者分支不得进入提交；
- 候选顺序固定为硬资格 → 路线层级 → 动作绑定 → 成本 Pareto → 用户明确成本优先维度（Demo 词典序）→ Focus；
- Focus 不包含成本，只能排序剩余 active 候选；
- residual Focus 使用 `uc-focus-snapshot/0.4`，必须精确匹配当前 `route_id + route_version + route-chain-head time_scope + decision_id batch`，并拒绝未来 `calculated_at`；
- 选中步骤后通过 `issue-route` 追加可重算验证的 route issuance hash chain，task/context/resource 快照不能由 evidence 自证；同时声明 `route_trust_level`，`trusted_seed_prefix_local_extension` 只保护 seed 前缀，本地后缀不得冒充外部防伪；
- `issue-route.user_cost_priority` 必须是 `null` 或 canonical 成本维度无重复数组；非法/矛盾的显式优先级，或显式优先级被 unresolved 阻塞时零写入拒签；`priority=null` 的 unresolved 情况只允许保留来源后受限 `route_default`，且不得消费 Focus。发行事件显式冻结 `baseline_evidence_id`：learning 为 `null`，retention 与 schedule baseline 精确相等；
- production 为每个 `concept + resource` 建立候选；只有资源完整六维 `cost_vector` 可进入已解决 Pareto。缺失时可保留带来源标签的 intervention+duration fallback estimate，但成本仍为 unresolved，显式 priority 必须拒签。发行事件冻结全部 candidate cost/缺失状态、resource fingerprint、来源和选中项，证明优先级确实改变了哪个实际资源；
- 画像只消费 state `supported_by` canonical 窗口；同一 `route binding + phase + verification task` 只允许一条 canonical evidence，重试必须签发新的 task 或 route/version，换文件或 evidence/item ID 不得增加独立样本；teaching_process 的真实重试允许追加但必须有不同 observed_at，同题同时间换 ID 是 replay；
- teaching_process 使用独立的 phase-aware 消费者窄表，两侧映射必须严格相等；它不得绑定 contract/retention/方法效果成本消费者；
- 画像选出的 activity/carrier 必须唯一解析并持久化到真实支持它的已签发 resource；同一 resolution 还要持久化从 process evidence 派生的反馈、下一动作与实测成本。实测高于路线估计时，必须在真实兼容资源中改变为最低 duration 的文字修复活动；Cone、教学投影与恢复只读该结果；
- 初始教学生成器只接收 verification content guard，用户完成教学过程前不能读取或投影原始验证题与保护答案；
- 教学过程证据必须同时绑定它实际收到的 teaching delivery ID/投影 SHA-256、route task 与 response decision fingerprint；追加后的 active resolution 还必须把它列为最后一条 process ref 且状态为 ready，只有这时可以开题，不能绕过未见 A0 验证；
- teaching delivery 的 `issued_at` 必须取真实当前时钟且不在未来；当前时刻若不能严格晚于 resolution 就失败重试，禁止用 `resolved_at + 1s` 制造顺序；
- 所有 diagnostic、teaching_process、verification、retention 提交都经过同一 `append-evidence` 事务：从 canonical session 反查来源、派生资格/置信度/消费者与 field bindings、重算同 scope state 和全部 boundary、标记旧 Focus stale；过程记录刷新 process refs/status、反馈、修复输入与成本，但保留作答前 decision epoch，真正换活动需显式 resolve + 重新签发。任一步失败必须精确回滚；完整合同满足时只返回 `route_reissue_required`，不得在证据事务中伪造下一 route issuance；
- 响应画像必须既被写入，也在下次同情境活动选择中被读取；
- `immediate_contract_status`、`retention_status` 与完整 `contract_status` 分开重算；即时满足且保持待定只进入保持安排，不能误回概念修复；
- retention 先追加 schedule receipt，due 开题前再追加或幂等复用 open receipt；两类 receipt 必须 exact metadata allowlist + full-metadata fingerprint + canonical body，open 不得保存题面/答案/`user_task`。state 只指当前 schedule，历史 evidence 按自己的 open→schedule→issuance 校验。保持失败必须经过更新且合格的新 verification baseline、新 task/binding 和 superseding schedule，不能停在永久 pending；
- `issue-route.expected_chain_head` 与 `schedule-retention.expected_state_evaluated_at` 是 CAS 前置条件；漂移时必须零写入。所有生产 writer 在同一外部跨进程 Vault 锁内完成 read/CAS/write/validate/rollback，锁超时零写入；所有写后失败都要求仍持锁的全树 byte-exact 回滚。

每次发布版本都必须创建使用完整版本号命名的新 `.mmd + .png`，更新 `SKILL.md` 中的内联图片，并保留 `ELD` 水印与版权标记。流程图通过审阅后，才允许同步发布包或推送远端；缺少版权所有者对该次外部发布的明确授权时，只能停留在本地。

## 路由恢复

```powershell
py -3 -X utf8 scripts\vault_tool.py recover-route --start <可能包含 Vault 的目录>
py -3 -X utf8 scripts\vault_tool.py recover-learning-route --vault <精确 Vault 路径>
```

两个命令默认只读。未找到旧数据时不得自动创建新 Vault；多条活动路线或支线歧义必须让用户选择。

## 当前边界

- “理解成本”是工程化工作定义，不是公认心理量表；
- Focus Cone 是 Agent 内部实验视图，不代表能力或教学效果已被验证；
- Demo 数据为合成数据；真实学习结论必须来自同范围行为证据；
- evidence 的 `source_kind/source_ref` 必须从其唯一 canonical session 反查；本地 session 和 evidence 同时被协同改写仍超出无密钥本地校验能力，真实来源真实性需要宿主 receipt 或签名；
- active resolution 是可重算缓存：生产 `write=True` 禁止 caller 提供 `_as_of`。process 绑定作答前 teaching delivery 的 response decision fingerprint；刷新后的 resolution 用 `resolved_process_refs/status` 接纳该记录，不能反过来要求 process 晚于刷新后的 `resolved_at`。无外部单调 receipt 时，不声称能抵抗对历史 resolution 与全部本地 evidence 的协同回拨；
- 发布前重新运行结构校验、回归测试和 SkillHub `publish --dry-run`。
