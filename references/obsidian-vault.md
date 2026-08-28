# Obsidian Vault 约定与路由恢复

## 最小目录

```text
<vault>/
├─ .understanding-cost-route.json
├─ 00-system/
│  ├─ manifest.json
│  ├─ index.json
│  └─ ROUTER.md
├─ 10-domain/<domain-id>/
│  ├─ dom-<domain-id>.md
│  └─ kc-<domain-id>-<slug>.md
├─ 20-learner/
│  ├─ usr-<learner-id>.md
│  ├─ states/
│  ├─ goals/
│  ├─ sessions/
│  ├─ evidence/
│  ├─ retention-schedules/
│  └─ verification-opens/
├─ 30-learning/
│  ├─ resources/
│  ├─ interventions/
│  └─ visuals/snapshots/
└─ 90-templates/
```

原生 Obsidian Graph 通过 Markdown Wikilinks 展示节点和连接。边的语义保存在关系行中，原生图不会可靠显示边标签；学习路径计算必须读取关系文本或 index，不能靠肉眼位置。

## Frontmatter 最小字段

```yaml
---
schema: uc-demo/0.2
id: kc-python-recursion
type: concept
title: 递归
created_at: 2026-08-26T06:30:00Z
updated_at: 2026-08-26T06:30:00Z
privacy: shared
tags: [uc/concept, domain/python]
---
```

关系写在正文：

```markdown
## Relations

- requires: [[kc-python-function]]
- related_to: [[kc-python-iteration]]
- part_of: [[dom-python]]
```

## ROUTER 与 manifest

`.understanding-cost-route.json` 只包含相对 manifest 路径和 schema；`00-system/manifest.json` 保存 Vault ID、活跃学习者/目标/会话和创建时间；`ROUTER.md` 为 Obsidian 可读入口。

路由文件不是学习证据。丢失路由时不得重建画像或知识状态。

这里的“路由”仅指 Vault 入口。学习路线由 intervention/route 记录管理，至少包含 `status`、`route_id`、`route_version`、`goal_id`、`path`、`current_checkpoint`、`completed_step_evidence_ids`、`parent_route_id`、`return_checkpoint`、`recovery_status` 和 `recovered_from`。同一 `learner_id + goal_id` 至多一条 `active` 路线：激活支线时原路线必须转为 `paused`，返回时支线先转为 `completed/paused`，再恢复原路线。多条 active 是存储错误；恢复命令只能列出候选让用户选择，并在选择后把其他路线降为非 active。入口修复不能冒充路线恢复。

`visuals/snapshots/` 只保存派生视图缓存。每个 `uc-focus-snapshot/0.4` 必须写明 `learner_id + goal_id + concept_id + route_id + route_version + time_scope + decision_id + calculated_at`，并强制 `privacy: private`、`derived: true`、`rebuildable: true`；文件 ID 也应包含足以区分时间快照的稳定片段。同一 residual 决策只能消费当前 route、当前 chain head time scope、同一 decision batch 且时间不在未来的快照。它可删除重算，不能进入 `supported_by` 掌握证据链，也不能把派生字段回写到共享 concept。

## 固定恢复顺序

1. 若用户给出显式 Vault 路径，校验该路径；
2. 从当前路径逐级向父目录查找 `.understanding-cost-route.json`；
3. 若 marker 不存在，查找 `00-system/manifest.json`；
4. 只在用户指定或当前工作范围内做有界只读搜索；
5. 校验 schema、Vault ID、学习者和链接；
6. 唯一匹配时可建议修复；只有显式 `--repair` 才写 marker；
7. 多个匹配时列出候选并询问用户；不得自行选最新或合并；
8. 无匹配时询问“从未创建”还是“需要继续找/重建”；
9. 只有用户明确确认后初始化或重建；
10. 重建内容写 `reconstruction_status: provisional` 和 `derived_from`，验证后再更新 Router。

Obsidian 图的节点屏幕坐标不是数据，不能用于恢复路由或推断掌握。

## 索引规则

`index.json` 是可重建缓存，不是事实来源。它至少包含：

- `id -> relative_path`；
- 节点 `type`；
- 解析后的 Wikilinks 与关系类型；
- 重建时间；
- 重复 ID、断链和未知关系报告。

事实来源始终是 Markdown frontmatter、关系行和追加式 evidence。

## 图谱呈现

Demo 使用状态节点叠加，而不是尝试给共享 concept 节点写某位用户的颜色：

- `#uc/concept`：领域知识；
- `#uc/state/mastered`：已掌握状态；
- `#uc/state/partial`：部分掌握状态；
- `#uc/state/unknown`：未测量状态；
- `#uc/goal`：目标；
- `#uc/resource`：资源；
- `#uc/intervention`：学习计划；
- `#uc/evidence`：行为证据；
- `#uc/retention-schedule`：私有、append-only 的保持排期 receipt，不是掌握证据；
- `#uc/verification-open`：私有、append-only 的延迟开题 receipt，不保存题面或保护答案，也不是掌握证据。
- `#uc/focus`：私有、派生、可重算的 Focus 快照，不是掌握证据。

这能让原生关系图同时看到“领域结构”和“学习者覆盖层”，而不把两者混为一张认知图。

## 写入与破坏性边界

- `init`、`seed-demo` 只写空目录；
- 默认不覆盖同名文件；
- 所有生产 writer 先取得位于 Vault 外的同路径跨进程独占锁；锁覆盖 read/CAS/write/validate/rollback，争用超时零写入，回滚不得覆盖另一成功事务；
- evidence 只通过 `append-evidence` 追加新文件，不改写旧证据；该命令把同 scope state、全部 boundary、Focus stale 与过程 resolution 的派生改写纳入同一可回滚事务；
- route issuance 只通过 `issue-route` 追加账本事件；`expected_chain_head` 漂移或用户成本优先级非法时零写入；本地事件显式冻结 learning-null/retention-specific baseline；
- retention schedule 只通过 `schedule-retention` 追加 receipt，并用 CAS 更新 state 的当前 receipt 指针；schedule baseline 必须等于 retention issuance baseline，历史 receipt 不覆盖；
- delayed task 只通过 `open-delayed-verification` 先追加或幂等复用 open receipt 再投影；schedule/open receipt 都要求 exact metadata allowlist、全 metadata 指纹和 canonical body，open 不保存题面、答案或 `user_task`，receipt 写失败不得显示题面；
- rebuild-index 只覆盖派生缓存；
- recover-route 默认只读；
- 多条 active 学习路线时禁止自动教学或导出；用户选择后必须显式降级其他路线；
- 删除、合并、覆盖或整库重建必须先向用户确认精确路径。
- 只读搜索范围也不得超过用户明确授权的路径；反链、附件或同账户其他聊天不随 Vault 路由自动获得读取授权。
