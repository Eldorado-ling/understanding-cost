# Agent 内部实验性 Focus Cone v0.3

## 唯一职责与可见性

Focus Cone 是 Agent 内部、非权威、可删除和可重算的派生排序器。它的唯一决策职责是：

> 在候选已经通过硬资格、当前路线层级、动作绑定和成本 Pareto 过滤后，对仍无法决定先后的候选步骤给出优先尝试顺序。

它不是用户教学界面、领域知识地图或心理测量仪器。`focus_z` 不产生候选资格，不修改 mastery，不生成 `requires`，不选择媒介，也不证明教学效果。

- `audience: agent_internal`；
- `user_visibility: hidden_by_default`；
- `authoritative: false`；
- `score_kind: heuristic_cone_coordinate`；
- `causal_status: not_established`；
- `decision_role: experimental_priority`；
- 普通教学只输出选定的活动、媒介、步骤和检验；
- 只有用户明确请求 `inspect`、纠正或删除画像时，才输出脱敏且带证据边界的视图。

## 可证伪假设

> 在目标、mastery gate、动作类别、路线层级和成本 Pareto 前沿相同，且每个知识点都绑定其自身有效 contract/version 的条件下，优先选择“目标相关性高、兴趣证据较强、当前软就绪度较高”的未掌握步骤，是否比不使用 Focus 的路线默认顺序以更低总理解成本达到迁移与保持标准？

这不是论文已经确认的因果规律。`in_cone` 不表示已掌握，`not_in_cone` 或 `not_in_vault` 不表示不会。删除或重算圆锥不得改写领域图、原始证据或 mastery。

## 三维编码与消费者

- `x/y`：领域关系布局，唯一消费者是明确授权的 Agent inspect 关系视图；
- `z`：显式 `focus/readiness` 派生分数，唯一决策消费者是剩余安全候选的顺序；
- 节点颜色或形状：独立的 mastery 状态；
- 节点边环：当前被选候选；
- 连线：带类型、方向的知识关系。

不得从 Obsidian 力导图的视觉中心反推出 `z`。力导图中心受节点度数、布局算法、过滤条件和随机初值影响。

若当前只有一个剩余候选，且没有 `inspect_view` 或 `experiment_evaluation` 消费者，不得为本次决策新算 `focus_z`；写 `ranking_status: not_needed` 或不创建快照。

## 固定决策顺序

```text
硬资格
  -> 当前路线层级
  -> 可执行动作绑定
  -> 成本向量 Pareto
  -> 用户明确成本优先级
  -> Focus 排序
  -> 非 Focus 回退
  -> 执行
  -> 结果回写与证伪
```

阶段不得交换。成本不得进入 Focus 公式；被成本支配的候选不得被较高 `focus_z` 恢复。

## 候选单位与硬资格

被比较的是可执行候选步骤，不是裸 `concept_id`：

```yaml
candidate_step_id: step-...
concept_id: kc-...
routing_action: diagnose_now | teach_now
next_step_id: ...
activity_id: ... | null
probe_id: ... | null
verification_task_id: ... | null
eligibility_status: eligible | ineligible
decision_pool_status: active | standby | excluded
```

同一知识点的多个活动方案先由响应画像、学习机制和活动成本选择；Focus 不比较媒介偏好。`diagnose_now` 与 `teach_now` 不得放入同一个 Focus 集合；`use_as_anchor`、`defer_blocked`、`defer_unmodeled`、`exclude_mastered` 不参与排序。

候选只有同时满足以下条件才可进入 `active` 集合：

1. 同一 `learner + goal + route_id + route_version + time_scope + decision_id batch`；`time_scope` 必须精确等于读取时的 `route-chain-head:<expected_chain_head>`，`calculated_at` 不得位于未来；每个候选分别绑定自己的 `concept + contract/version`，不同知识点不得为了参与 Focus 共用伪合同；
2. 位于当前目标或必要先修闭包；
3. mastery 与动作类别相容；
4. 必要前置已满足；
5. 位于活动路线当前层级，或是恢复断点所需的最短可学外缘；
6. `diagnose_now` 已绑定可执行探针及可区分结果分支；
7. `teach_now` 已绑定教学活动和未见独立验证任务；
8. 满足用户明确的可访问性、拒绝项和时间上限。

安全可学但不属于当前路线层级的候选只能是 `standby`。跳离检查点必须先重规划并递增路线版本，不能由 Focus 暗中改线。

## 成本 Pareto 前置门

成本比较只在 mastery gate、动作类别、路线层级、预测时间范围、维度和量纲相同时进行：

```yaml
cost_status: complete | incomplete | stale | not_needed
pareto_status: frontier | dominated | unresolved | not_needed
cost_vector:
  diagnosis: ...
  prerequisites: ...
  core_learning: ...
  practice_feedback: ...
  verification: ...
  maintenance_relearning: ...
```

若 A 在所有可比维度都不高于 B，且至少一维严格更低，则 A 支配 B。缺失值、不同门槛或不可比估计写 `unresolved`；不得把缺失当零，也不得宣称占优。

- 普通 Focus 只读取 `pareto_status: frontier`；
- `dominated` 不能被 Focus 恢复；
- `unresolved` 进入低成本补测、受限探索或路线默认策略，`selection_basis` 不得写 `focus`；
- 用户明确的成本优先维度先作用于 Pareto 前沿；Demo 按这些原始维度做词典序比较，不默认加权或压成总分。没有明确优先时，剩余多个候选可进入 Focus；一旦优先维度无效或互相矛盾，只能补测、询问或使用非 Focus 回退，`selection_basis` 不得写 `focus`。

## Focus 输入与公式

```text
focus_z =
  0.40 × goal_relevance
+ 0.30 × interest_evidence
+ 0.30 × readiness
```

权重是 Demo 默认值，不是科学常数。所有原始分量、权重、来源、时间、置信度和实际结果必须保留。

- `goal_relevance`：只来自当前 goal、mastery contract 和目标子图；
- `interest_evidence`：只来自明确陈述、主动追问、重复回访或自主实践选择；单次点击、停留或被推荐后的完成不能单独成立；
- `readiness`：必要前置通过硬门后，由已知锚点、证据新鲜度和误概念风险形成的软就绪度；它不能补偿未满足前置；
- `mastery`：独立显示，不进入默认 `z`。

同一表现不得自动同时写成兴趣和 readiness。没有完整同范围行为证据时，mastery 为 `unknown`；兴趣、自报熟悉和模型生成成果不能自动写成 `partial/mastered`。

## 缺失值与适用门

未测量、来源失效、作用域不一致或无法归因时写 `null`，不得写 `0` 或借用其他学习者、目标或领域的数据。

出现以下任一情况时：

```yaml
ranking_status: incomplete
focus_z: null
```

- 任一必需分量为 `null`；
- 权重非法或和不为 1；
- 输入作用域不一致、过期、冲突或已撤回；
- 候选不在同一动作类别、路线层级或 Pareto 前沿。

不得只排序资料完整的子集并把缺失候选自动降级。若缺失值可能改变选择且有低成本探针，执行 `diagnose_now`；否则使用路线默认顺序并写非 Focus 选择依据。

## Focus 如何改变顺序

Focus 只有在以下条件全部成立时才能参与选择：

1. 至少两个 `decision_pool_status: active` 候选；
2. 候选属于相同动作类别、路线层级和 mastery gate；
3. 全部位于成本 Pareto 前沿；
4. 全部 Focus 输入完整、有效且同范围。

按 `focus_z` 从高到低排序。唯一最高者可以写：

```yaml
selection_status: selected
selection_basis: focus
```

若最高值完全并列，Focus 保留并列，依次使用路线既定顺序和稳定 ID 做可复现回退：

```yaml
selection_basis: route_default | stable_tie_break
```

稳定 ID 只保证复现，不表示更优。

核心约束是：

> `focus_z` 不得改变候选资格、动作类别、路线层级或 Pareto 状态；但它的唯一职责正是在这些更高优先级约束都无法决定先后时，打破剩余候选的并列。若不允许它改变该集合的顺序，就不得为该决策计算或保存 `focus_z`。

## 快照契约

```yaml
schema: uc-demo/0.2 # 所属 Vault 的笔记 schema
focus_snapshot_contract: uc-focus-snapshot/0.4
type: focus_snapshot
id: focus-...
learner_id: usr-...
goal_id: goal-...
concept_id: kc-...
state_id: ks-...
contract_id: mc-...
contract_version: 1
route_id: route-...
route_version: 1
time_scope: route-chain-head:<64位SHA-256>
decision_id: dec-...
focus_model: focus-cone-agent-v0.3
goal_relevance: 0.90
interest_evidence: 0.75
interest_evidence_kind: repeated_questions
readiness: 0.65
focus_weights: {goal: 0.40, interest: 0.30, readiness: 0.30}
focus_z: 0.785
ranking_status: complete | incomplete | not_needed | stale
calculation_purpose: residual_candidate_order | inspect_view | experiment_evaluation
consumer_ids: [focus_priority]
used_in_decision: true
selection_basis: focus | route_default | diagnose_information_gain | stable_tie_break | not_used
input_evidence_ids: [ev-...]
input_source_refs: [ks-..., goal-..., deterministic-rule-id]
input_confidence: {goal_relevance: medium, interest_evidence: low, readiness: low}
calculated_at: 2026-08-26T06:50:00Z
validity: valid | stale | provisional
privacy: private
derived: true
rebuildable: true
authoritative: false
score_kind: heuristic_cone_coordinate
causal_status: not_established
decision_role: experimental_priority
audience: agent_internal
user_visibility: hidden_by_default
export_policy: explicit_inspect_or_debug
```

每个派生值必须声明消费者。正常决策的 `goal_relevance/interest_evidence/readiness` 消费者是 `focus_z`，`focus_z` 的消费者是 `residual_candidate_order`；inspect 快照的消费者是 `inspect_view`。没有消费者不创建快照。

同一次 residual 候选比较的所有快照必须共享同一 `decision_id`，并共享同一个 residual `selection_basis`（仅 `focus | stable_tie_break | route_default`）。validator 对同 scope/current time 的混合 decision batch 或混合 basis 直接拒绝；route head、route/version 或任一输入变化后，旧批次只能标为 stale，不能凭“它还是最新文件”继续参与签发。快照中的 `selection_basis` 记录该批次上次计算结果，不能预先决定生产选择；`issue-route` 必须重新校验当前输入并重算最终 basis，因此合法的 tie/default 批次不会被忽略，也不能利用伪造的 basis 强迫 selector 选中某项。

## Agent 决策输出

每个候选必须生成：

```yaml
selection_status: selected | not_selected | ineligible | not_evaluated
selection_basis: focus | active_route | cost_pareto | user_cost_priority | route_default | diagnose_information_gain | stable_tie_break | not_selected
routing_action: diagnose_now | teach_now | use_as_anchor | defer_blocked | defer_unmodeled | exclude_mastered
reason_codes: [...]
next_step_id: ... | null
```

允许的核心原因包括：`goal_required`、`active_route_checkpoint`、`prerequisites_satisfied`、`prerequisite_gap`、`mastery_contract_met`、`probe_available`、`probe_unavailable`、`teaching_binding_unavailable`、`high_information_gain`、`pareto_nondominated_cost`、`pareto_cost_unresolved`、`focus_inputs_incomplete`、`focus_priority_selected`、`focus_exact_tie`、`outside_goal_subgraph`、`not_active_route_checkpoint`。

## 教学结果回写

每次活动结束后：

1. 追加原始行为证据；
2. 只用合格未见独立验证重算 mastery；
3. 重算 boundary、阻塞前置和路线；
4. 用实际用时、提示、尝试、迁移、保持和重学更新成本与响应观察；
5. 只有独立兴趣行为可以更新 `interest_evidence`；
6. 目标、状态、路线、兴趣证据或权重变化时把旧快照标为 `stale/superseded`；
7. 下一次真实多候选决策再计算，不得直接修改旧 `focus_z`。

“被 Focus 选中”“看完推荐内容”或一次答对，均不得回写成兴趣、准备度、掌握或 Focus 有效性。

## 可证伪记录

每次真实使用 Focus 必须保存：

```yaml
candidate_set_before_focus: [...]
pareto_frontier: [...]
baseline_choice_without_focus: ...
focus_choice: ...
focus_model_version: focus-cone-agent-v0.3
observed_outcome_evidence_ids: [...]
```

基线必须使用相同硬资格、路线、Pareto 和用户明确成本优先维度，只是不使用 Focus。只缩短即时完成时间、把提示或重学成本推迟、同时改变多个教学因素、Focus 实际没有改变选择，或只有一次成功，都不得记为模型成功。

若同一情境中 Focus 反复被基线 Pareto 支配或持续无优势，标记 `contradicted_in_context` 并停止该情境自动排序；调整分量、缩小范围或弃用。跨多个匹配任务且包含迁移或保持证据前，只能写 `untested/inconclusive`。

## 用户教学层投影

Agent 选择后另行生成 `delivery_plan`。普通输出不得包含 `learner_id`、`focus_z`、分量、权重、排名、坐标、内部置信度、原因码、A0–A4 代码或原始证据引用；不得说“模型判定你最适合”或把暂时响应假设写成人格类型。
