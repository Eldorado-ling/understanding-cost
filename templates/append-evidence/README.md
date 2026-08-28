# append-evidence 输入模板

四个 JSON 文件与 `scripts/vault_tool.py` 的 `APPEND_EVIDENCE_RAW_FIELDS` 一一对应。使用规则：

1. 复制当前 phase 的模板到工作文件，不要直接改模板；
2. 替换所有以 `$` 开头的占位值；保留该 phase 已写好的 `null`、`false`、`not_tested` 等哨兵；
3. `source_session_id` 必须指向 Vault 中同 learner/goal 的 canonical session；
4. route、task、context 不从用户回答猜测。`teaching_process` 只复制模板中与 `process_binding` **同名**的字段；`route_binding_id`、`context_key` 等其余返回值仅用于回执核验，不得作为 raw input 追加。其他 phase 从已校验 route issuance 读取模板所需字段；
5. 只填写实际观察到的表现。没有观察到的结果不得改成零分；应使用该 phase 允许的哨兵，或先补一个合法探针；
6. 执行 `append-evidence --record <工作文件>`。命令会派生来源、route binding、context、资格、置信度、consumer IDs 与 field bindings，并原子重算 state/boundary/Focus。

retention 模板的 `teaching_item_id` 必须来自 `open-delayed-verification` 返回的内部 `retention_binding`，它引用已持久化的 `verification_open` receipt；不得从 task/binding 自行拼接。保持路线签发与排期输入见 [route-retention 模板](../route-retention/README.md)。

模板是 Agent 内部输入合同，不得直接投影给学习者。
