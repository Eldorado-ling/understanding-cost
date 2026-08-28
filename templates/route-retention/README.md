# route 与 retention 输入模板

这些模板只供 Agent 构造生产命令输入，不得直接展示给学习者。复制模板到工作文件并替换全部 `$...` 占位值；不能增加由调用者自证的 scope、context、task、fingerprint、hash、状态或时间结论。

- `issue-route-learning.json`：签发下一条当前学习路线。命令会从实时 Vault 重建候选并要求所填 concept/resource 正好等于 canonical selector 的结果。`user_cost_priority` 没有用户明确偏好时保持 `null`；有偏好时只填 canonical 成本维度组成的无重复数组。
- `issue-route-retention.json`：为已满足即时合同的 concept 签发一个不同于 baseline 的未使用保持任务；baseline 也必须列入 `source_ref_ids`，并被发行事件显式冻结。保持签发不执行成本候选比较，因此 `user_cost_priority` 固定为 `null`。
- `schedule-retention.json`：把合格 baseline 与已签发 retention binding 形成不可变 schedule receipt，state 只保存当前 receipt ID。`scheduled_for` 由命令计算为 `max(baseline.observed_at + min_delay_days, not_before)`；`not_before` 可为 `null`。

canonical 成本维度固定为：`diagnosis`、`prerequisites`、`core_learning`、`practice_feedback`、`verification`、`maintenance_relearning`。数组顺序就是词典序优先顺序；不得使用“总成本”“兴趣”等别名，也不得重复维度。

`expected_chain_head` 和 `expected_state_evaluated_at` 是并发前置条件：必须复制读取输入时的真实值；提交前若已变化，命令零写入拒绝，不能刷新后盲目覆盖。所有命令还会在同一 Vault 的跨进程独占锁内重新读取和核验；锁超时同样零写入。

固定执行顺序：

```text
issue-route(purpose=retention)
  -> schedule-retention
  -> 到期前只等待
  -> open-delayed-verification --state-id ...
  -> 先持久化或幂等复用 verification_open receipt
  -> 只向用户显示返回对象中的 user_task
  -> 用 retention_binding 中与 append-evidence 模板同名的字段提交 retention evidence
```

`schedule-retention` 的 baseline 必须精确等于 retention issuance 冻结的 baseline，不能把同一 binding 换绑到另一条合格 evidence。`open-delayed-verification` 返回的 `retention_binding` 是 Agent 内部绑定；其中 `teaching_item_id` 必须原样写入 retention evidence，它引用真实 `verification_open` receipt。`route_binding_id`、`context_key` 等非 raw 字段只供核验，不得强行加入 `append-evidence` 输入。两个 receipt 都是 exact-schema 机器回执，不能手工添加 metadata 或正文；open receipt 不保存题面、答案或 `user_task`。保持失败时不得覆盖旧 receipt；先形成一条更新且合格的 verification baseline，再使用新 task/binding 签发并排期，新的 schedule receipt 以 `supersedes` 指向旧 receipt。
