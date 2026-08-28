# 文字优先教学协议（Demo）

## 定位

`text_preferred` 是当前 Demo 的默认媒介策略，不是对学习者的固定类型判断。只要文字能承载目标行为，就先完成一次可验证的文字闭环；不能因为用户说“喜欢文字”就宣称文字教学效果更好。

“文字”必须拆成承载方式与教学活动两个维度：

- `text_document`：可保存、可回看、结构稳定的文字文件；用于定义、关系地图、步骤、对照表、代码轨迹与阶段总结；
- `text_dialogue`：逐轮诊断、提问、提示、纠错与验证；用于定位缺口并要求学习者实际生成答案；
- `text_hybrid`：`text_dialogue → text_document → text_dialogue`；先诊断，再生成只含当前必要内容的文件，最后用未见任务独立验证；
- `activity` 独立描述学习机制，例如 `contrast_cases` 或 `worked_example_fading`，不得把它和承载方式合并成“文字讲解”。

默认选择 `text_hybrid`。仅当目标只是生成参考资料而不要求本轮掌握时用 `text_document`；仅当任务很小、无需长期参考文件时用 `text_dialogue`。

## Agent 内部决策结构

```yaml
text_activity_decision:
  protocol_version: text-demo-v0.5
  scope: {learner_id: ..., goal_id: ..., concept_id: ..., contract_id: ..., contract_version: 1}
  learner_id: ...
  goal_id: ...
  concept_id: ...
  contract_id: ...
  contract_version: 1
  route_id: ...
  route_version: 1
  bound_verification_task_id: ...
  verification_content_guard: {...} # 绑定 Vault 验证资源生成的内部哈希 guard，禁止用户投影
  domain: python
  context_key: domain=python|knowledge_kind=rule|target_performance=discriminate|prior_band=partial|task_difficulty=medium
  comparison_gate: {retention_required: false, task_difficulty: medium}
  task_difficulty: low | medium | high
  knowledge_kind: declarative | rule | causal_structure | symbolic_procedure | diagnosis | transfer | motor_spatial
  target_performance: recall | explain | discriminate | predict | execute | diagnose | transfer
  prior_knowledge_band: unknown | none | partial | mastered
  introduced_terms: [...] # 只有当前任务必需且尚无理解证据的承重术语
  response_profile_refs: []
  profile_selection_status: no_observations | no_qualified_observations | insufficient_alternatives | pareto_ambiguous | tentative_exploration | pareto_selected
  profile_usage_status: default_text_policy | exploration_only_threshold | blocked_by_profile_threshold | activity_only | activity_and_carrier | blocked_by_prerequisite | overridden_by_hard_constraint | overridden_by_text_repair_gate | not_applicable_delivery_intent | rejected_missing_affordance
  selection_consumer: activity_selection
  text_policy: preferred_default
  text_sufficiency: sufficient | unknown | insufficient
  selection_status: selected | repair_selected | blocked | escalation_required
  activity: retrieval_prompt | contrast_cases | predict_explain | worked_example_fading | error_analysis | novel_case_application
  carrier: text_document | text_dialogue | text_hybrid | video | interactive
  text_format: plain | structured_steps | paired_cases | trace | table | code_block | null
  assistance_level: A0 | A1 | A2 | A3 | A4
  reason_codes: [...]
  evidence_refs: [...]
  escalation:
    status: not_eligible | text_repair_required | eligible | selected | not_applicable
    target_medium: video | interactive | null
    affordance_reason: continuous_motion_is_target | spatial_temporal_change_required | real_time_feedback_required | state_manipulation_required | actual_execution_required | null
  visual_support:
    status: selected | not_selected
    kind: annotated_diagram | comparison_image | annotated_screenshot | null
    reason: ownership_or_spatial_relation | multi_object_mapping | multi_state_comparison | interface_or_shape_judgment | learner_reported_relational_complexity | null
```

`learner_id + goal_id + concept_id + contract_id + contract_version` 是必需知识作用域，并必须在返回对象的 `scope` 中作为一个不可拆散的整体再次给出；`route_id + route_version + bound_verification_task_id` 是已选 `candidate_step` 的必需执行绑定。可信 Vault 调用方还必须用 `build_verification_content_guard(task_id, protected_prompt, protected_answers)` 从该任务资源生成不含原文的 guard；`decide_text_activity()` 要求 guard 的 `task_id` 与 `bound_verification_task_id` 完全相等并将 guard 保留为内部字段。`evidence_refs` 即使为空也必须显式写 `[]`。返回的不是可脱离 route 或验证任务使用的媒介建议。

`context_key` 必须由 `domain + knowledge_kind + target_performance + prior_band + task_difficulty` 按固定顺序生成，不能自由命名。当前决策还必须显式提供 `{retention_required, task_difficulty}` comparison gate。历史 observation 可以来自不同 goal、concept 或 contract，但必须属于同一 learner、同一 canonical key、同一 comparison gate，且历史 assistance 不得高于当前上限。没有可比较记录时写 `response_profile_refs: []`。画像若改变活动或 carrier，必须列出真正被消费的 evidence ID；`selection_consumer` 固定为真实下游 `activity_selection`。

### 唯一响应观察协议

`response_profile_observations` 不能由调用者手写一组表现数字，也不能把调用者提供的 `contract_evaluation.status`、qualified IDs 或自造 evidence 窗口当作事实。唯一生产入口是 `vault_tool.build_response_observation_from_vault(vault, evidence_id)`：它先完整校验 Vault，再要求目标 evidence 被唯一同 scope state 的 `supported_by` 接纳，从该 state 取得 canonical 窗口，从 goal 取得原始 contract，从已校验 route registry 取得 issuance/context，最后在函数内调用合同评估器重算。`valid` evidence 若没有唯一 state 消费者即为非法。低层 `_build_response_observation_from_validated_vault_inputs()` 是私有内部 seam，不承担持久化来源证明，生产调用方不得直接使用。

```python
observation = vault_tool.build_response_observation_from_vault(
    Path("/path/to/understanding-cost-vault"),
    "ev-example-001",
    as_of="2026-08-28T08:00:00Z",
)
```

适配器只输出 `response-observation-v1`，其结构固定包含：

```yaml
schema_version: response-observation-v1
source:
  kind: vault_evidence
  evidence_id: ...
  source_refs: [...]
  source_context_key: ... | null
  phase: diagnostic | teaching_process | verification | retention
  result: pass | partial | fail | conflicted | not_tested
  response_correct: true | false
  derived_mastery_eligible: true | false
  mastery_eligibility_failures: [...]
scope: {learner_id: ..., goal_id: ..., concept_id: ..., contract_id: ..., contract_version: 1}
context_key: ...
activity: retrieval_prompt | contrast_cases | predict_explain | worked_example_fading | error_analysis | novel_case_application | null
carrier: text_document | text_dialogue | text_hybrid | video | interactive | null
profile_actionability:
  status: actionable | not_actionable
  missing_field_bindings: [...]
comparison_gate: {retention_required: true | false, task_difficulty: low | medium | high}
mastery_gate_met: true | false
mastery_gate_derivation:
  method: vault_tool_contract_recompute_and_evidence_membership
  evaluation_scope: {...}
  contract_status: not_tested | in_progress | not_met | met
  qualified_evidence_ids: [...]
  qualified_failure_evidence_ids: [...]
  comparison_gate: {retention_required: true | false, task_difficulty: low | medium | high}
assistance_level: A0 | A1 | A2 | A3 | A4 | null
elapsed_seconds: 0.. | null
attempts: 1.. | null
hint_count: 0.. | null
immediate_performance: 0..1 | null
near_transfer: 0..1 | not_required | pending | not_tested
delayed_retention: 0..1 | not_required | pending | not_tested
self_reported_effort: 1..7 | not_collected
observed_at: ISO-8601-with-timezone | null
validity: valid | provisional | stale
confidence: low | medium | high
```

`activity` 只允许上表中的 canonical ID，展示用中文名称不得写回该字段。`result` 完全采用 Vault canonical enum；本协议不再接受额外的 `observed` 值，教学过程尚未形成结论时使用 `partial` 或 `not_tested`。`qualified_failure_evidence_ids` 可以绑定资格合格但结果为 `fail`、`partial` 或 `conflicted` 的记录，三者都不会成为通过证据。

`mastery_gate_met` 不是可采集字段：只有原始 evidence 自身满足 `mastery_eligible`、适配器内部合同重算状态为 `met`，并且该 evidence ID 位于重算得到的 `qualified_evidence_ids` 时才生成 `true`。observation 的 `scope` 必须等于它自己的 `mastery_gate_derivation.evaluation_scope`；当前决策只要求同 learner，不要求同 goal/concept/contract。`_validate_profile_observations()` 还会验证 canonical context、comparison gate、帮助上限、来源、时效状态和置信度；source evidence 中获得 `activity_selection` 授权的 `context_key` 必须与比较上下文派生的 canonical key 完全相同，且 `observation_confidence=low` 不得进入画像 Pareto。调用者已没有可以篡改 gate/status/qualified IDs 的 API 参数。

适配器还必须读取 evidence 的 `field_bindings`，不能只相信 note 级 `consumer_ids`。实现必须同时维护并逐项比较四张 phase 表：`DIAGNOSTIC_FIELD_CONSUMERS`、`TEACHING_PROCESS_FIELD_CONSUMERS`、`VERIFICATION_FIELD_CONSUMERS`、`RETENTION_FIELD_CONSUMERS`；全局 `EVIDENCE_FIELD_CONSUMERS` 只是四表的词汇并集，任何 phase 都不得从并集回退取权。Vault 与文字适配器中的同名四表必须严格相等，否则回归校验失败。

evidence 的 envelope 与结果 field binding 分开校验：`phase/evidence_kind` 进入 `phase_schema_guard`，完整 scope 进入 `scope_guard`，`source_kind/source_ref_ids` 进入 `source_provenance_guard`，`observation_validity` 进入 `observation_validity_guard`，`route_binding_id` 进入 `route_binding_guard` 和该 phase 的专用门。envelope 缺失时拒绝整条记录，不能让结果字段的消费者反向证明来源或范围。

四张表的职责边界固定为：

| phase | 允许改变的结果 | 明确禁止 |
|---|---|---|
| `diagnostic` | 探针资格、诊断轨迹、当前 boundary | mastery、方法效果画像、保持 |
| `teaching_process` | 当前反馈、活动、表征、载体升级、实测过程成本、开题资格 | mastery、合同通过、保持、方法效果样本 |
| `verification` | 独立验证资格、即时合同、boundary、下一次活动比较 | 延迟保持字段 |
| `retention` | 延迟验证资格、保持合同、boundary、恢复 | `near_transfer` 与 `explanation_quality`；本 phase 两者是未测哨兵 |

`teaching_process` 的精确允许集合是：

| 过程字段 | 允许消费者 |
|---|---|
| `activity`、`carrier` | `activity_selection`、`representation_selection`、`feedback_selection`、`teaching_delivery_guard` |
| `context_key` | `verification_gate`、`teaching_delivery_guard` |
| `teaching_item_id` | `process_trace`、`teaching_delivery_guard` |
| `teaching_delivery_fingerprint_at_observation` | `teaching_delivery_guard` |
| `verification_task_id`、`bound_verification_task_id` | `verification_gate` |
| route/version、decision fingerprint | `verification_gate`、`teaching_delivery_guard` |
| unseen/reveal 标记、`mastery_eligible` | `verification_gate` |
| `result`、`demonstrates`、`response_correct`、`explanation_quality` | `verification_gate`、`representation_selection`、`feedback_selection` |
| `immediate_performance` | `feedback_selection` |
| `elapsed_seconds` | `activity_selection` |
| `attempts`、`hint_count`、`self_reported_effort` | `feedback_selection` |
| `assistance_level` | `activity_selection`、`representation_selection` |
| `error_signature` | `representation_selection`、`feedback_selection` |
| `observation_confidence` | `process_evidence_gate`、`representation_selection` |
| `observed_at` | `verification_gate`、`feedback_selection`、`activity_selection`、`representation_selection`、`teaching_delivery_guard`、`event_identity_guard` |

`teaching_process` 的 `independence`、`verification_item_id`、`near_transfer`、`delayed_retention` 与 `retention_delay_days` 当前不绑定消费者，只允许阶段规定的 `null/not_tested` 哨兵，不能借全局表进入画像、成本 Pareto 或合同重算。

只有字段存在、非 `null` 且在该 phase 有意义时才可能要求 binding；`delayed_retention` 与 `retention_delay_days` 只在 `phase=retention` 时适用，`not_tested/pending/not_required/not_collected` 标记不是可行动数值，不要求对应表现 binding。对适用字段，field binding 必须存在；没有实际消费者的 binding 反而属于非法多余字段。每个 binding 都必须包含非空 `consumers + source_ref_ids + scope + observed_at + validity`：消费者是该行允许集合的非空子集；来源是 evidence `source_ref_ids` 的非空子集；完整 scope、时间与 validity 和 evidence 一致。Demo 的生成器从这张有限映射派生 note 级消费者并集，不再接受 seed 自报消费者。`representation`、`learner_confidence` 与 `interest_event` 当前没有已实现的 evidence 下游，因此不持久化；以后必须先实现消费者，再扩展本表与测试。

此外，进入方法效果画像的 activity/carrier/context、帮助、表现、成本、observed_at 与 confidence 字段，其 binding 必须明确包含 `activity_selection`；只有其他合法消费者并不够。缺少这些 binding 时适配器仍生成 canonical observation，但写成 `profile_actionability=not_actionable` 且把未获授权的画像值投影为 `null/not_tested`。verification/retention 的 result、task、route/version 等资格字段则必须按各自 phase 表绑定；retention 的 `retention_delay_days` 是时间链重算后的派生断言，只进入 `derived_assertion_guard`，真正的保持重算读取 baseline/task/schedule/result/delayed_retention。teaching_process 永远不进入该适配器的效果 Pareto；它的 `activity_selection` 只代表当前修复活动会读取实测过程成本和上一活动，不能解释成历史方法效果样本。诊断记录同样不能因具有某个 binding 就冒充 mastery。

`prepare_observation_update()` 的 `prepared_fields` 可直接作为同一适配器的可选输入；其中 `immediate_performance`、activity、carrier、成本和反馈字段都必须各自通过消费者白名单，并与已经提交的 Vault evidence 同名字段完全一致。它不是第二种画像 schema，也不能覆盖 evidence、形成第二份事实或绕过合同评估。没有当前消费者的字段会以 `field_not_allowlisted` 丢弃。

### 隔离校验用例

不依赖 `self_test.py` 的最小隔离校验应覆盖：四张 phase 表与 envelope guard 在 Vault/文字适配器两侧逐项相等；Demo evidence 均能桥接，`not_tested` 被当作 canonical marker；目标 evidence 不在完整窗口、窗口跨 scope、contract 错配或 caller 企图传入旧式评估对象均被拒绝；缺画像消费者的记录成为 `not_actionable` 而不是使整条桥接失败；canonical `pass` 可生成观察；`partial/fail/conflicted` 可进入 qualified failure 但 gate 必为 false；`observed` 被拒绝；source `context_key` 与 canonical comparison context 不一致被拒绝；适用 binding 的消费者、来源、scope、时间或 validity 错误均被拒绝；过程记录缺 teaching delivery、route task、decision fingerprint 或表征消费者时拒绝；note 有任意合法消费者但画像字段未包含 `activity_selection` 时不能进入选择；跨 concept 的同 learner/canonical context 可比较，跨 domain 或 comparison gate 不同被拒绝；低置信度记录不进入 Pareto；只有唯一胜出 `(activity, carrier)` 自身 3 条且 2 concept 才最多改变文字 activity，自身 5 条且 3 concept 并含迁移/保持才允许强复用，其他候选的证据不得补足门槛；guard 必须拒绝初始投影中改写键名的题面/答案泄露；`evaluate_text_unit(record, decision)` 必须拒绝与当前 decision scope、route/version 或 task 不一致的自洽 record。

内部原因码只允许：

```text
text_can_represent_target
text_default_low_coordination
historical_text_pareto_preferred
no_context_evidence
prerequisite_gap
text_repair_required
same_error_repeated
text_representation_exhausted
continuous_motion_is_target
spatial_temporal_change_required
real_time_feedback_required
accessibility_conflict
user_explicit_medium_constraint
nontext_supported_pareto_dominance
response_profile_pareto_selected
response_profile_exploration
```

这些 ID、状态、原因码和帮助等级默认不得进入用户输出。

## 活动的确定性默认映射

| 目标行为 | 默认活动 | 默认格式 |
|---|---|---|
| `recall` | `retrieval_prompt` | `plain` |
| `discriminate` | `contrast_cases` | `paired_cases` |
| `explain` / `predict` | `predict_explain` | `structured_steps` |
| `execute` | `worked_example_fading` | `trace` 或 `code_block` |
| `diagnose` | `error_analysis` | `trace` 或 `paired_cases` |
| `transfer` | `novel_case_application` | `structured_steps` |

同一 canonical 情境有有效历史观察时，先排除未达到自身 mastery gate、comparison gate、帮助上限、`profile_actionability`，或仅有低观察置信度的记录，再比较用时、提示、尝试、近迁移和保持。门槛只统计唯一 Pareto 胜出 `(activity, carrier)` 自身：自身 1–2 条仅能提出单变量探索；自身至少 3 条且覆盖 2 个 concept 时最多改变文字 activity；自身至少 5 条、3 个 concept 且该选项含迁移或保持时才允许更强复用。候选池总样本不能补足胜出选项的门槛；无唯一 Pareto 优势时回到上表，不能秘密压成单一效果分。

## 单个文字学习单元

严格按以下状态推进：

```text
TEXT_SELECT
  -> TEXT_DIAGNOSE
  -> TEXT_MINIMAL_EXPLANATION
  -> PROJECT_USER_ALLOWLIST_AND_NO_LEAK_GATE
  -> ISSUE_TEACHING_DELIVERY(plan + sha256 + task + decision)
  -> USER_GENERATE
  -> TEXT_FEEDBACK
  -> APPEND_EVIDENCE(teaching_process, mastery_eligible=false)
  -> RECOMPUTE_PROCESS_ADAPTATION_AND_RESOLUTION
  -> UNSEEN_TEXT_VERIFY
  -> VERIFICATION_ELIGIBILITY
  -> APPEND_EVIDENCE(verification)
  -> QUALIFIED_PASS: CONTRACT_RECOMPUTE_AND_ROUTE_REISSUE_REQUIRED
  -> QUALIFIED_FAIL: REPAIR_OR_REPLAN
  -> INELIGIBLE_VERIFY: REBUILD_VERIFY_TASK
  -> PREREQUISITE_GAP: REPLAN_PREREQUISITE
  -> FIRST_FAIL: TEXT_REPAIR
  -> REPEATED_FAIL: EVALUATE_ESCALATION
```

每个单元必须满足：

1. 只验证一个当前目标行为；
2. 已知锚点必须引用已有证据；没有证据就写 `unavailable`，不得编造；
3. 学习者第一次作答前不得展示完整答案；
4. 教学任务与验证任务使用不同 `item_id`；
5. 验证任务是未见过的平行任务，并要求 `A0` 独立完成；evidence 的 `verification_task_id` 必须与当前路线的 `bound_verification_task_id` 一致；
6. `A3/A4` 下完成只能作为教学过程证据；
7. 阅读文件、复述原句或说“懂了”不能单独结束单元；
8. 文字文件负责稳定呈现，文字对话负责诊断、主动生成、反馈和验收，两者不得互相替代。

用户第一次看到教学内容前，先用 `issue-teaching` 持久化实际白名单投影。其 `issued_at` 必须来自真实当前时钟且不在未来；若不能严格晚于当前 resolution，就失败重试，不能制造未来时间。

教学题的回答、提示下修正和读图任务都通过 `append-evidence` 记为过程证据，并固定 `mastery_eligible: false`。它们只更新当前错误、反馈/修复动作、表征、文字变体和实测成本，不进入用于证明方法效果的响应画像，也不能直接进入合同的合格通过集合。过程记录必须精确绑定已经发行的 teaching delivery ID、投影 SHA-256、route task 与 decision fingerprint；同一教学题允许真实重试，但每次必须有不同 `observed_at`，同一题、同一时间换 evidence ID 的副本是 replay。只有绑定不同已签发验证任务的未见、未提前泄露完整答案、A0、同范围记录才可能由原始字段推导为 `mastery_eligible: true`；`verification_item_id`、`verification_task_id`、`bound_verification_task_id` 必须都等于 issuance task ID。verification 只能绑定 `purpose=learning` 的本地 issuance；retention 只能绑定 `purpose=retention`，且 `teaching_item_id` 必须引用真实 `verification_open` receipt，receipt 再绑定当前证据自己的 schedule 与 issuance。新任务按完整 task fingerprint 去重，不能只换 ID。同一 route binding + phase + task 只允许一条 canonical evidence；重试必须先签发新的 task 或 route/version，不能靠覆盖旧结果或换 ID 增加独立样本。其中正确与错误结果都追加，只有正确且 `demonstrated_capabilities` 覆盖当前合同 `required_capabilities` 者可能满足合同。`mastery_eligible` 是唯一权威资格字段；若旧数据中存在 `verification_evidence_eligible`，它只能是该字段的派生同义显示，不能独立存储或覆盖前者。

## 结果字段消费者门

每个准备写入的教学或验证字段必须绑定至少一个明确消费者：

```yaml
field_observation:
  value: ...
  scope: {learner_id, goal_id, concept_id, contract_id, contract_version}
  source_refs: [...]
  observed_at: ...
  validity: valid | provisional | stale
  confidence: low | medium | high
  consumer_ids: [feedback_selection | activity_selection | representation_selection | verification_gate | contract_recompute | retention_recompute | recovery]
```

- 消费者为空或非法：丢弃该字段，不得进入提交白名单；
- 至少一个字段合格：只提交白名单字段；
- 没有任何字段合格：不追加 evidence，不更新 state、boundary、画像或 route；
- `learner_response_present`、阅读完成或自报“懂了”不是 mastery 消费者的充分输入。

## 新术语落地门

学习者尚未用行为证据证明理解的术语，不得直接承担后续解释。首次使用一个必要新术语时，先用当前学习者已知的语言交代：

1. `是什么`：它属于对象、数值、操作、关系还是规则；
2. `属于谁／存在于哪里`：明确它的所有者、作用域或所在系统；
3. `在当前例子中做什么`：指出它控制、改变或连接的具体对象；
4. `关系方向`：明确谁作用于谁，避免用“某某的参数”一类可能颠倒归属的简称。

只有这四项已用本地语言说明，或已有同范围证据表明学习者理解，术语才可作为后续推理的前提。若定义中又出现未经确认的新术语，继续向下改写，直到解释只依赖已验证锚点和本单元已经落地的概念。学习者曾见过名称、参与过相关项目或能复述词语，都不能跳过此门。

例如介绍 Live2D 的“参数”时，应先说明：它是 `Live2D 模型内部的一项带名称和数值范围的控制项`；“嘴巴开合”是这项控制的名称；嘴巴的可见图形与它建立关系并随数值变化。不得在此前直接说“嘴巴有一个参数”，因为这会把参数的归属与被控制对象混在一起。

在内部决策中把这些必要新词逐项写入 `introduced_terms`；用户可见内容则为每项提供 `term + what_it_is + owner_scope + role_here + relation_direction`。投影时两组术语必须一一对应，否则拒绝生成教学计划。普通日常词和已有同范围理解证据的词不放入该列表，避免把解释膨胀成词典。

## 文字优先下的静态视觉支持

`text_preferred` 表示文字承担定义、推理、反馈和验证，不表示只能出现纯文字。静态图示是文字单元的辅助表征，不等于切换到视频或交互，也不受“重复失败后才能升级”的闸门限制。

简单的一对一关系优先用一句话或最小文本图。出现下列任一需求时，可在第一次解释中直接加入具体静态图示，而不必先让学习者失败：

- 需要辨认所有者、被控制对象、层级、连接或空间位置；
- 一个控制项同时影响多个对象，或一个对象同时受多个控制项影响；
- 三个及以上状态、分支或重复字段必须同时对照；
- 目标要求从界面位置、形状差异或离散步骤变化中作判断；
- 学习者明确指出线性文字使同类复杂关系难以保持在脑中。

只选择能减少当前歧义的最小视觉：空间与连接关系用带标注的示意图或截图，离散变化用并列步骤图；只有连续运动或时间变化本身是目标时才用视频，只有必须操纵状态或获得实时反馈时才用交互。

每张教学图必须：突出当前目标对象；用箭头表示关系方向；只使用已落地术语作为标签；配一句“要观察什么”；并绑定一个要求学习者读取图中关系的任务。装饰图片、未标注截图和仅重复正文的图片不得计为视觉支持。视觉只改变表征，不得替代学习者生成答案和未见任务验证。

选择静态图示时必须在内部写明一个 `visual_support.reason`，由它确定图示类型；用户输出必须包含实际可呈现的 `asset`、观察重点、文字等价说明和读图任务。只有“见下图”、空白占位符或建议用户自行想象，不算已经提供视觉支持。未选择视觉支持时也不得临时塞入图片，以免无法解释该表征为何出现。

## 失败与非文字媒介升级

第一次非先修错误必须保持文字媒介，只改变一种活动或文字表征。出现 `prerequisite_gap` 时回退先修，不能归因于文字媒介。

只有同时满足以下条件，才允许从文字升级：

- 同一 `learner + goal + concept` 连续至少两次出现同一错误签名；
- 已使用至少两种不同文字活动或文字表征；
- 最高帮助已达到 `A2` 或更高；
- 没有未处理的先修缺口；
- 候选媒介提供文字缺少且目标确实需要的能力。

目标依赖连续动作或时空变化时选 `video`；目标依赖状态操纵、实际执行或实时反馈时选 `interactive`。若非文字媒介没有补足明确能力，不得只为“换个形式”升级。

每次非文字升级必须同时记录与目标媒介匹配的 `affordance_reason`；仅写“视频更直观”“用户可能更喜欢”不合格。`video` 只接受连续动作/时空变化原因，`interactive` 只接受状态操纵、实际执行或实时反馈原因。

以下硬约束允许直接跳过文字：

```text
continuous_motion_is_target
spatial_temporal_change_required
real_time_feedback_required
accessibility_conflict
user_explicit_medium_constraint
```

即使升级到视频，也必须包含暂停预测、学习者生成和独立验证；“看完”不是掌握证据。

## 用户可见投影

普通教学只允许生成：

```yaml
delivery_plan:
  learning_objective: ...
  method_label: ...
  medium: 文字文件 | 文字对话 | 文字文件＋对话 | 文字文件＋静态图示 | 文字对话＋静态图示 | 文字文件＋静态图示＋对话 | 视频 | 交互
  orientation: ...
  term_grounding: ...
  explanation: ...
  example: ...
  visual: ...
  learner_task: ...
  response_format: ...
  feedback_rule: ...
  verification_rule: ...
  success_criteria: ...
  next_step: ...
```

初始 `delivery_plan` 只说明验证规则与成功标准，不得包含、暗示或嵌套完整的未见验证题。不能只检查 `verification_task` 键名：`project_delivery_plan()` 必须从 decision 取得与绑定 task 一致的 `verification_content_guard`，对 `orientation/term_grounding/explanation/example/visual/learner_task/response_format/feedback_rule/verification_rule/success_criteria/next_step` 等全部用户可见字符串递归执行 NFKC、casefold、去标点空白后的整句、全文片段与字符 n-gram SHA-256 指纹比较；还要按实际投影顺序拼接全部嵌套可见字符串后再次扫描，防止把短片段拆到相邻字段或数组项。与保留题面或答案精确重合，或达到固定保守重叠阈值时拒绝投影。guard 只含哈希和固定阈值，不含原题/答案，也不得出现在用户对象中。哈希 guard 只检测规范化后的字面重叠，不能证明语义改写安全；主要防线始终是初始生成器根本不能读取原题与保护答案，guard 只是额外的失败关闭检查。`learner_task` 是教学过程中的主动生成任务，不是最终未见题。教学过程记录必须绑定当前完整 scope、route/version、route binding、bound verification task，以及它实际收到的 delivery 所冻结的 `decision_fingerprint_at_observation`；记录内自相等不构成资格。生产路径只能调用 `vault_tool.py open-verification --process-evidence-id ...`：它先复核 process 晚于该 delivery，再要求它是刷新后 active resolution 的最后一条 `resolved_process_ref`、状态为 `ready_for_verification`，且 route/task/resource/activity/carrier 未漂移；不会错误地要求作答晚于刷新后的 `resolved_at`。满足这些条件并重算为 `result=pass + response_correct=true + explanation_quality=pass + demonstrates 包含 explanation` 后，才调用私有投影原语。partial、fail、not_tested、未落盘、非最新记录或刷新后发生教学决策漂移都拒绝；调用者手写一个形似 `teaching_process_recorded` 的字典没有开题能力。

调用验证投影时，内部 content 还必须带 `task_id`，并与 decision 的 `bound_verification_task_id` 完全一致；公开的 `verification_task` 规范化全文指纹还必须精确命中 guard 的 prompt 指纹，防止同一 task ID 下替换题面。`task_id` 与 guard 都只用于投影前硬校验，不进入用户对象：

```yaml
verification_projection:
  verification_task: ...
  response_format: ...
  success_criteria: ...
```

`medium` 必须由通过状态机校验的内部 `carrier` 映射得到，用户内容不能自行指定。不得透传：嵌套的 `verification_task`、`verification_content_guard` 或 `protected_content_fingerprints`、内部 scope/context/comparison gate/route/task 绑定、内部 ID、Focus 字段、画像置信度、样本量、`cost_vector`、`pareto_status`、`consumer_ids`、`field_bindings`、原因码、错误签名、`selection_status`、`A0–A4` 代码、原始证据路径或未授权聊天内容。实现必须逐项新建上述白名单对象，并递归拒绝嵌套内部字段；不能把内部决策整体序列化后再删除表层字段。`next_step` 只允许非空字符串、`null`，或固定对象 `{instruction: 非空字符串, when: 字符串或 null}`，不得用任意字典夹带内部结构。

## 通过标准

一个文字学习单元只在以下条件全部满足时产生 `qualified_pass`：

- 学习者产生了独立回答；
- 验证题与教学题不是同一个项目；
- 完整答案未在首次尝试前泄露；
- 验证时帮助等级为 `A0` 且回答正确；
- 合同要求解释时，`explanation_quality=pass`；
- 合同要求近迁移时，达到该合同阈值；
- 证据与当前 `learner + goal + concept + contract/version` 完全同范围。
- evidence scope 等于显式传入的当前 decision scope；`route_id_at_observation`、`route_version_at_observation` 以及记录内 bound route 都等于当前 decision 的 route/version；verification task ID 与记录内 bound task 都等于 decision 的 `bound_verification_task_id`。任一值缺失或错配都只能是 `unqualified`。

验证任务还必须显式写 `verification_unseen: true`；系统由原始字段重算 `mastery_eligible: true`，不接受调用者手填资格结论。资格合格但回答错误时追加 `qualified_fail`，用于错误路由和新旧证据冲突；不得因为失败而删除证据。资格不合格时只能写过程观察并重新构造验证任务。

单元通过不自动等于 `mastered`；只有完整 mastery contract 满足时才能更新为掌握。

若 mastery contract 要求校准能力，必须在作答前记录成功概率预测，并在多题证据窗口中比较预测与实际表现；窗口大小、校准指标与允许误差由合同声明。单题自评或一句“我有信心”不能作为校准通过。
