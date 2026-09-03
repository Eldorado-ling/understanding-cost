# Demo v0.1.4 状态机与会话协议

本文件与 [v0.1.4 流程图源文件](../review-assets/understanding-cost-flow-v0.1.4.mmd) 是同一执行合同的文字版和图形版；带水印的发布图嵌入在 [SKILL.md](../SKILL.md) 中。三者的版本号、状态、先后顺序、资格门、失败回路和回写语义必须一一对应；任一处发生冲突时，该版本视为未完成，不得选择其中一份继续执行，必须在同一次修改中同时修复。

## 总状态机

```text
INTAKE
  -> CONFIRM_DATA_MODE
       -> unconfirmed: ASK_THREE_OPTIONS_AND_WAIT
       -> create_boundary: CONFIRM_SAVE_SCOPE -> INITIAL_UNKNOWN_STATE_AND_MINIMAL_DIAGNOSIS
       -> use_existing: CONFIRM_EXACT_SOURCE -> READ_AUTHORIZED_EVIDENCE_AND_CHECK_GAPS
       -> no_personal_data: CURRENT_QUESTION_ONLY_AND_LOCAL_PRIOR_CHECK
  -> CLASSIFY_MODE
  -> [continue/recover/rebuild] LOCATE_OR_RECOVER -> DEFINE_GOAL_AND_CONTRACT
  -> [learn-one] DEFINE_GOAL_AND_CONTRACT
  -> [map-domain] COORDINATION_MAP -> USER_SELECTS_NODE? -> DEFINE_GOAL_AND_CONTRACT | END
  -> [inspect] AUTHORIZED_INSPECT -> CORRECT_OR_DELETE? -> INVALIDATE_DERIVED_AND_RECOMPUTE | END
  -> RECOMPUTE_EXISTING_OR_UNKNOWN_BOUNDARY
  -> GRAPH_COVERAGE_AND_LEARNER_EVIDENCE_GATE
  -> BUILD_TARGET_SUBGRAPH
  -> BUILD_EXECUTABLE_CANDIDATE_STEPS
  -> HARD_ELIGIBILITY
  -> ROUTE_LEVEL
  -> ACTION_BINDING
  -> COST_PARETO
  -> USER_COST_PRIORITY
  -> FOCUS_IF_NEEDED
  -> SELECT_STEP
  -> APPEND_IMMUTABLE_ROUTE_ISSUANCE
  -> [diagnose_now] ISSUE_BOUND_DIAGNOSTIC_PROBE -> VALUE_AND_ENVELOPE_GATE -> APPEND_EVIDENCE_ATOMIC -> RECOMPUTE_BOUNDARY -> BUILD_EXECUTABLE_CANDIDATE_STEPS
  -> [teach_now] SELECT_ACTIVITY_AND_CARRIER
  -> RESOLVE_APPLY_ISSUED_RESOURCE
  -> PREPARE_COMPACT_TEACHING_BRIEF
  -> DECLARE_ANCHORS_AND_CAPABILITIES
  -> AGENT_SEMANTIC_REVIEW_OF_DRAFT_OR_REWRITE
  -> BUILD_VERIFICATION_CONTENT_GUARD
  -> TEACHING_BASIS_GATE
  -> PROJECT_INITIAL_TEACHING_AND_TERM_ORDER_GATE
  -> NO_LEAK_GATE
  -> ACTUAL_BODY_CONCEPT_COVERAGE_GATE
  -> APPEND_TEACHING_DELIVERY
  -> AGENT_RECHECK_ACTUAL_PROJECTION_BEFORE_DISPLAY
  -> TEACH
  -> APPEND_PROCESS_EVIDENCE_ATOMIC
  -> UNSEEN_VERIFY
  -> VERIFICATION_ELIGIBILITY
  -> APPEND_VERIFICATION_OR_RETENTION_EVIDENCE_ATOMIC
  -> RECOMPUTE_STATE_BOUNDARY_AND_STALE_FOCUS
  -> [full contract met] RETURN_ROUTE_REISSUE_REQUIRED -> CORE_A_SELECT_AND_APPEND_NEW_ROUTE_ISSUANCE
  -> NEXT_STEP | SCHEDULE_DELAYED_CHECK | COMPLETE | REPLAN
```

先选择数据模式，再确认当前目标的必要知识边界，最后才能正式教学。完整定义和未选择时的唯一问句见[学习入口协议](learning-entry.md)。上图中 Vault 发行、回写与排期链仅适用于获准持久化的创建模式，或另获写权限的兼容既有库；初始 unknown 骨架可以在诊断前建立，但不代表已经确认知识边界。

既有库默认只读；无个人数据模式不读个人库。两个非持久化分支执行 `当前目标 → 必要前提确认 → 会话内概念交接 → 最小教学稿 → 同一纯内存正文检查与 Agent 语义复核 → 输出 → 用户作答 → 反馈/局部修复 → 未见检查 → 当轮结果`，不接入上述 Vault writer，也不保存圆锥、画像或保持排期。检查失败先改稿；真前置缺口回到临时路径规划。地图先经模式门，再展示最小领域视图；节点选择不是模式授权。无个人数据模式请求恢复旧记录时须说明冲突并让用户重新选择，不自行读库。

阶段不得交换。尤其禁止：先按兴趣或 `focus_z` 选节点再检查先修；把成本并入 Focus；先随意发诊断题再事后绑定 route；只算 activity 却不解析真实 resource；把尚未签发的教学投影交给用户；让初始生成器读取未见验证题或答案；教学题答对后跳过未见验证；合同判定前提前把路线标记为完成。

`issue-teaching` 内部自动完成依据、投影/防泄漏、登记概念检查和追加校验，没有暂停等待 Agent 语义勾选的回调。Agent 在调用前审草稿，返回后、展示前再审实际投影；尤其不能漏掉过程适配器替换的反馈/下一步。返回稿不合格则不展示，改稿后重新签发，旧记录保留且不能据此伪造用户作答。签发本身不证明用户已收到或已理解。

## 并发事务与不可变回执

所有生产 Vault writer 都必须按 canonical Vault path 取得同一把跨进程独占锁，并在持锁期间完成读取、CAS、资格重算、多文件写入、完整校验和失败回滚。锁必须位于 Vault 外，不能成为知识图谱节点或影响 byte-exact 回滚。争用超时、CAS 漂移或任一写后校验失败都必须 fail closed；前两者零写入，后一种只在仍持锁时恢复本事务开始前的精确字节，因此不能删除或回滚另一个成功事务。进程内嵌套写入必须可重入，不能为避免死锁而绕过锁。

`retention_schedule` 与 `verification_open` 是机器回执，不是自由笔记。两者只允许各自的精确 metadata 白名单，`receipt_fingerprint` 覆盖除自身外的全部允许 metadata，正文必须等于生产函数生成的 canonical body。任何额外字段、额外正文、题面、答案、`user_task` 或已允许字段的未重签篡改都使 Vault 无效。只有命令返回对象中的 `user_task` 可投影给学习者；open receipt 本身不保存它。

## 入口与恢复

数据模式确认是入口第一步；其后才路由为 `learn-one`、`map-domain`、`continue`、`inspect`、`recover` 或 `rebuild`。维护者审阅 Skill 本身不构成一轮学习；但任何真实学习分支都不得借只读、试教或纯新问题跳过选择。

```text
LOCATE_OR_RECOVER
  -> UNIQUE_VALID_ROUTE -> RESUME
  -> MULTIPLE_VALID_ROUTES -> ASK_USER
  -> NO_MATCH -> ASK_IF_NEVER_CREATED_OR_REBUILD
  -> EXPLICIT_REBUILD -> CREATE_PROVISIONAL_STATE
```

- `LOCATE_OR_RECOVER` 只在模式允许且用户指定精确数据范围后执行，不搜索未授权父目录。不得从 `NO_MATCH` 静默初始化；改用创建模式或换源必须重新确认。
- `map-domain` 只生成当前判断所需的协调视图；用户选定节点后再进入目标定义。
- `inspect` 只在用户明确要求时展示可校正、可删除且带来源边界的内部数据；校正后重算派生状态。
- 重建状态默认 `unknown`，不得根据笔记数量、链接或旧截图补写掌握。
- `continue/recover` 发现 `retention_status=due + next_action=issue_delayed_verification` 时，恢复结果必须结构化返回 `action + concept/contract + baseline_evidence_id + retention_task_id + scheduled_for + route binding`，优先发出已签发的延迟 A0 任务；不得退化成“沿路线继续”的泛化提示。

## Intake 与掌握合同

第一轮先取得明确数据模式，不把它与兴趣/时间/知识测试混问。其后按需取得当前问题、领域范围、目标表现、使用情境、时间限制、是否要求延迟保持，以及创建或既有模式的精确资料/保存范围。缺少信息时只问当前最能改变安全路径的一到三个问题；无个人数据模式不询问数据库位置，也不创建持久化字段。

教学前必须定义：

```yaml
mastery_contract:
  contract_id: ...
  contract_version: 1
  concept_id: ...
  minimum_qualified_evidence: ...
  required_capabilities: [...]
  min_near_transfer: 0..1 | null
  delayed_retention:
    required: true | false
    min_score: 0..1 | null
    min_delay_days: integer
  far_transfer: observable_behavior | not_required
```

合同修订必须递增版本并记录原因；旧证据不静默计入新合同。goal 只有在所有 `targets` 概念的当前合同均满足时才完成。

## 数值与字段消费者门

任何准备计算、保存或用于推断的字段，都必须先声明：

```yaml
value_binding:
  scope: {learner_id, goal_id, concept_id, contract_id, contract_version, time_scope}
  source_refs: [...]
  observed_or_calculated_at: ...
  confidence_or_validity: ...
  consumer_ids: [...]
```

结果字段允许的消费者类别只有：`boundary_update`、`route_selection`、`anchor_selection`、`activity_selection`、`representation_selection`、`feedback_selection`、`verification_gate`、`contract_recompute`、`retention_recompute`、`recovery`、`inspect_view`、`focus_priority`、`experiment_evaluation`，以及脚本中明确执行的身份、过程、诊断、教学签发与派生断言 guard。`cost_pareto` 是路线/画像的选择状态，不是 raw evidence field consumer；证据中的用时、尝试、提示与努力由实际 `activity_selection` 或过程反馈读取。

evidence envelope 不作为学习结果建立 field binding，但必须按 phase 单独通过：`phase/evidence_kind → phase_schema_guard`，`learner/goal/concept/contract/version → scope_guard`，`source_kind/source_ref_ids → source_provenance_guard`，`observation_validity → observation_validity_guard`，`route_binding_id → route_binding_guard + 当前 phase 的诊断、教学签发、验证或保持 gate`。缺一项即拒绝整条 evidence，不能让结果字段自身证明来源或作用域。

- 没有消费者：不计算、不保存，也不触发 state、boundary、画像或 route 更新。若一个语义适用且非空的受管字段没有真实 field binding，整条提交必须拒绝或在提交前删除该字段，不能把它静默留在 evidence 中。
- 作用域、来源、时间或有效性不完整：写 `unknown/null` 或发起低成本探针，不得猜值。
- 一项结果可以有多个明确消费者，但不得因为“以后可能有用”而保留。
- 用户陈述、兴趣行为、教学过程表现和独立验证必须分流；自述不得直接进入 mastery 消费者。

## 核心一：边界、候选与路径

开始讲解之前必须能说明当前依赖哪些已有知识、哪些仍未知。资料不足时用能改变教学路径的最小诊断；兴趣选择和“学过”不替代诊断。无数据/只读分支仅在会话中使用该判断，不伪造证据文件。以下 canonical evidence、candidate 签发与原子状态要求属于持久化分支；不能为了执行它们而越过只读或无个人数据选择。

边界必须同时输出图谱状态与学习者状态。`derive_boundary_assessments` 的 graph_status 为 `complete / incomplete / unassessed / unmodeled / legacy_unspecified`；后四者不等于用户不会。明确不完整、未评估或缺节点时 `defer_unmodeled`，先修补最小图谱，不能把内部建模缺口转换成用户测试。图谱可用但学习者未知时才 `diagnose_now`；必要前置缺口走 `defer_blocked`，列出有信息价值的未知前置。多层链经过独立掌握节点时不再阻断，但仍保留下层未知的审计原因，不能撤销已验证掌握并强制重学。

`required_contrast_ids` 只选定当前必要辨析对象；其缺口决定内缘及教学对比说明，不变成 requires，也不自动扩大合同。旧 concept 未填 coverage 的兼容状态必须显式说明，不以空 requires 宣称图谱完整。新建图谱只有经 Agent 审核目标必要依赖后才标 complete；这是领域建模声明，不是心理测量。

先从已有 canonical evidence 重算边界；没有证据时保持 `unknown`，不能预填为 `none`。诊断问题应区分至少两个会产生不同安全路径的知识状态。持久化诊断必须先形成 `diagnose_now candidate_step`，绑定真实 resource probe，并通过完整选择与 `issue-route`；之后只发出该 learning issuance 快照中 ID、activity、carrier 唯一匹配的 probe。回答的 evidence 必须精确绑定同一 route，时间不早于 issuance 且不在未来，才会重算 mastery/confidence、诊断快照、误概念和 boundary。停止条件是已足够选出第一条安全路径，不要求一次测完整个领域。

只允许 `requires` 决定先修闭包。先把目标拆成可执行候选步骤，而不是只比较裸 `concept_id`：

```yaml
candidate_step:
  candidate_step_id: ...
  concept_id: ...
  routing_action: diagnose_now | teach_now
  next_step_id: ...
  activity_id: ... | null
  probe_id: ... | null
  verification_task_id: ... | null
```

固定选择顺序：

1. **硬资格**：同一作用域、位于目标/必要先修闭包、mastery 与动作相容、必要前置成立、满足可访问性与明确拒绝项；
2. **路线层级**：优先唯一活动路线当前断点，或恢复该断点所需的最短 `outer_fringe`；跳离断点必须先重规划并递增路线版本；
3. **动作绑定**：`diagnose_now` 必须绑定可执行探针及结果分支；`teach_now` 必须绑定教学活动和未见验证任务；
4. **成本 Pareto**：只在相同掌握门槛、动作类别、路线层级、时间范围和量纲下比较成本向量；
5. **用户成本优先级**：只使用用户明确给出的优先维度，例如“本次先省时间、再少提示”；Demo 在 Pareto 前沿内按这些原始维度做词典序比较，不默认加权或压成总分，并记录其余维度的代价。没有明确优先时可继续；一旦提供但维度无效或互相矛盾，必须询问、补测或使用非 Focus 回退，不能继续进入 Focus；
6. **Focus Cone**：只有以上阶段仍留下至少两个同层级、同动作、Pareto 前沿候选时才排序；
7. **非 Focus 回退**：输入缺失或最高分并列时，使用高信息增益探针、路线默认顺序或稳定 ID，并明确记录选择依据。

成本向量与 Focus 必须分离：

```text
C = (diagnosis, prerequisites, core_learning,
     practice_feedback, verification, maintenance_relearning)
```

Focus 只消费 `goal_relevance + interest_evidence + readiness`。它可以打破已经通过所有高优先级约束的剩余候选顺序，但不能创造资格、恢复被成本支配的方案、改写路线、选择媒介或证明教学效果。生产 selector 只接受同一 `decision_id` 批次、批次内 `selection_basis` 一致、`route_id` 等于当前 active intervention、`route_version` 等于读取时版本、`time_scope=route-chain-head:<expected_chain_head>` 且 `calculated_at` 不在未来的 residual 快照；任一不一致都使该批次不能参与排序。快照中的 `selection_basis` 只是该批次上次计算结果，不作为资格或最终输出；生产 selector 必须用当前输入重算 `focus/stable_tie_break/route_default`。具体契约见 [focus-cone.md](focus-cone.md)。

候选确定后必须用 [route 输入模板](../templates/route-retention/README.md) 执行 `issue-route --record <json>`：命令从实时 Vault 为每个真实 `concept + resource` 重建 candidate_step 并核对最终 concept/resource。`user_cost_priority` 没有用户明确偏好时为 `null`；有偏好时只能是 canonical 成本维度组成的无重复数组。只有 resource 自己的完整六维 `cost_vector` 可进入已解决的 Pareto；缺失时允许保存明确标注的 intervention 向量加 resource duration fallback estimate，但该候选成本仍为 unresolved，不能供 user priority applied。selector 只在已解决的 Pareto 前沿内按优先数组逐维比较，并把每项 resource 指纹、成本向量或缺失状态、估算来源、是否选中和实际选择依据冻结进事件；无效或互相矛盾的显式优先级，以及显式优先级被 unresolved Pareto 阻塞时，必须拒签并回到澄清/补测，不能继续使用 Focus；`priority=null` 的 unresolved 情况只允许保留来源后受限 `route_default`。发行事件冻结完整 scope、route/version、purpose、baseline、五维 `comparison_context`、bound verification task，以及最终选中 resource/intervention 的快照；其他参与比较的候选以 resource 指纹、cost/fallback/source/selected 保存在 `selection_decision.candidate_costs`。learning baseline 固定为 `null`，retention baseline 显式绑定本轮合格 verification。事件按策略只追加顺序 hash chain，并同步 manifest anchor/head/length 与 `route_trust_level`。输入中的 `expected_chain_head` 是 CAS 前置条件，提交前漂移则零写入拒绝。只有账本通过校验后，`diagnose_now` 才可发 probe，`teach_now` 才可进入教学层。`local_chain_only` 只检测非协同漂移；`trusted_seed_source` 只证明账本完整等于 Vault 外 seed；seed 前缀后的本地事件必须显式使用 `trusted_seed_prefix_local_extension`，其后缀仍只是本地哈希链。

## 核心二：活动、表征与教学

解析后使用 `prepare-teaching` 获取 `uc-teaching-brief/0.1`，不要将全图或原始验证资源交给初始教学生成器。简报从同 learner+goal 的附近 canonical state/evidence 重算合格锚点，给出当前合同能力、必要对比、新术语、实际活动/媒介、过程反馈、带来源的成本输入与 opaque guard。v0.1.4 另交接当前概念及本步 requires/related_to/contrasts_with 对象的名称/别名词表 `concept_inventory`。词表供正文查漏，不改变路线或增加先修。`teaching_basis.anchor_ids` 必须来自简报 verified_anchors；`focus_capabilities` 必须是当前合同的非空能力子集。`issue-teaching` 在锁内核对绑定、锚点和能力，再把实际白名单投影交给 `teaching_review.review_teaching_content`；正文或定义引用词表中的未验证概念却未先落地时拒绝签发，即使作者完全漏报 introduced_terms 也不放行。内部词表和检查结果不进入用户投影。词表外的遗漏、概念真假和含义是否充分仍由 Agent 审阅，程序不是自然语言证明器。

`teaching_basis` 还必须绑定当前 `route_binding_id / decision_fingerprint / brief_fingerprint`；简报指纹覆盖内容和同范围当前证据 revision，不因时钟每次读而任意变化。目标、证据或 route 漂移时拒绝旧草稿。简报与签发使用同一已存储决策 epoch；要选择新方法先 resolve，再重新准备。`routing_action` 与 `process_next_action` 不可混用，诊断时只发当前签发资源的 diagnostic_probe。

选定步骤必须把当前 `route_id + route_version + bound_verification_task_id` 一并交给核心二，不能只传裸 `concept_id`。随后读取 [personalization.md](personalization.md) 的同情境响应观察；`context_key` 必须由领域、知识类型、目标表现、先验区间和任务难度生成，不能接受任意相似标签。每条观察只能由生产入口从已通过 Vault 校验的 state `supported_by` canonical 窗口、原始 contract 与 route issuance 反查后重算；调用者不得直接提交窗口或 `mastery_gate_met`。孤立 evidence 不进入画像。方法效果只消费绑定已签发任务的独立 verification/retention；同一 route binding 的同一 task 只允许一条 canonical 观察，重试必须签发新的 task 或 route/version，复制文件、换 evidence ID 或自造 item ID 都按 replay 拒绝。teaching_process 允许对同一已签发教学项逐次追加真实重试，但只进入错误修复、反馈、载体升级与实测成本通道，不进入方法效果 Pareto 或 mastery 门槛。与当前决策比较时允许 concept/contract 不同，但必须同一学习者、同一规范 `context_key`、同一 comparison gate，历史帮助强度不超过当前允许上限，且低观察置信度记录不能进入画像 Pareto。只有达到跨知识点画像使用门槛并形成唯一 Pareto 优势的历史方案才能改变 activity/carrier；无可靠占优方案时回到知识机制默认，并保留小规模、单变量探索。

这里的规范 `context_key` 只能从已校验的 `uc-route-bindings/0.2` 顺序签发事件中读取 `comparison_context` 后派生，不能信任 evidence 自带标签。签发账本用连续 `sequence + previous_hash + event_hash` 和 manifest 的 anchor/head/length 检查普通删改、重排与截断；本地事件还必须有封闭的 `route_purpose=learning|retention`，且 `issued_at` 不在未来。事件冻结 route scope、最终选中 resource/intervention、未见验证任务及三类指纹；其他候选只以规范成本记录和 resource 指纹进入 `selection_decision.candidate_costs`。新任务还要按完整 task fingerprint 去重，不能只换 task ID 复用同一题。active learning route 还必须与当前 Markdown 节点逐项一致。合成 Demo 的 seed 前缀与 Vault 外 seed 重建结果相等；其本地追加段和 generic `local_chain_only` Vault 都必须返回明确的信任边界 warning。

文字决策完成后不能停在内存或测试输出。必须执行一次 resolve/apply：在 active intervention 的 `uses` 资源中，寻找同时属于已签发候选集、显式支持所选 activity、carrier 一致、teaches 当前 checkpoint、且 verification task 指纹一致的唯一 resource。找不到或多于一个都停止，不得把机制名硬塞进现有材料。成功后原子更新 current activity/probe/task/carrier，并保存 `resolved_activity`、实际消费的 profile refs、profile level/usage、route binding/context 和决策指纹；同一次解析还要从当前 state 的 canonical teaching_process 派生 `resolved_process_status/refs/feedback_rule/next_action` 与实测过程成本。若已有过程证据，实测 `practice_feedback` 覆盖路线估计值并作为下一次同范围候选比较的原始成本维度；没有可比候选时不得声称它已经产生 Pareto 胜者。后续教学、恢复和 Cone 只读取这些已解析字段。Demo/工具入口为 `resolve-teaching --vault <path>`，`seed-demo` 在构建完成后自动执行同一桥接。

用户白名单投影通过防泄漏门后，必须通过 `issue-teaching --content <json>` 追加 `uc-teaching-delivery/0.1`。该 append-only 节点保存实际 `delivery_plan` 和其 SHA-256，并冻结 scope、route/version/binding、context、非空 decision fingerprint、resource、activity/carrier 与签发时间；完整校验失败时回滚本次新节点。命令同时向 Agent 返回独立的内部 `process_binding`，包含下一条过程证据需要的 delivery/task/decision/route/context/activity/carrier 绑定；它不得进入用户 `delivery_plan`。`issued_at` 必须来自真实当前时钟且不在未来；若当前时刻不能严格晚于 resolution，则签发失败并重试，不能为了凑出顺序而制造未来时间。用户只能看到已签发投影，后续 teaching_process 必须逐项精确引用它，不能自己发明 `teaching_item_id`。

教学活动和承载媒介分别选择。默认执行 [text-learning.md](text-learning.md) 的：

```text
text_dialogue diagnosis
  -> minimal text_document
  -> text_dialogue generation and feedback
  -> gated unseen verification
```

静态图示属于文字闭环的辅助表征，可在首次解释中直接使用。视频或交互只有在目标本身具有非文字硬需求、同情境证据显示其 Pareto 占优，或重复文字失败通过升级门时才可选择。

任何解释都必须满足依赖闭包：只依赖已验证知识锚点和本单元已经落地的概念。兴趣锚点只能提供情境和动机，不能承担推理。新承重术语先解释“是什么、属于谁/在哪里、本例作用、关系方向”，拒绝明显占位和循环自称，再用小问题确认；真正的前置缺口返回核心一。新模型/算法按“问题 → 表示的含义 → 最小例子 → 等待用户说明 → 按需公式”推进，不在等待前提前给完整公式推导。提过名称或已讲过不等于用户懂，更不直接改 mastery。具体正文、只读执行与失败示例见[文字教学](text-learning.md)。

## 教学、过程证据与独立验证

单元顺序：

```text
ORIENT
  -> VERIFIED_ANCHOR_OR_LOCAL_CONTEXT
  -> MINIMAL_EXPLANATION_OR_DEMO
  -> BUILD_OPAQUE_GUARD_FROM_BOUND_TASK
  -> PROJECT_INITIAL_CONTENT_WITHOUT_RAW_TASK
  -> REJECT_PROMPT_OR_ANSWER_OVERLAP
  -> APPEND_TEACHING_DELIVERY(plan + sha256 + decision epoch)
  -> LEARNER_GENERATE
  -> MINIMAL_FEEDBACK
  -> APPEND_PROCESS_EVIDENCE(mastery_eligible=false)
  -> DERIVE_PROCESS_STATUS_AND_MEASURED_COST
  -> READY(pass + correct + explanation-pass + current decision epoch)?
     -> no: REPAIR_OR_ESCALATE -> RESOLVE_ACTIVITY_AGAIN
     -> yes: OPEN_RAW_TASK_AND_MATCH_GUARD
  -> UNSEEN_PARALLEL_TASK
  -> LEARNER_COMPLETES_AT_A0
  -> VERIFICATION_ELIGIBILITY
```

教学过程观察必须绑定已经存在的 teaching delivery ID、其实际投影 SHA-256、当前 route issuance task、decision fingerprint、route binding 和签发时间；未签发、task 为空、错指纹或先作答后签发一律拒绝。有效过程观察可以更新错误签名、最小反馈、文字修复/升级判断与实测成本，但不得更新用于证明方法效果的响应画像，也不得直接满足 mastery contract。对同一教学题的真实重试必须具有不同 `observed_at`；同一题、同一时间的换 ID 副本是 replay，校验必须拒绝。`project_delivery_plan()` 必须用这一派生状态覆盖调用者自填的 `feedback_rule/next_step`。若实测 `practice_feedback` 高于当前路线估计，下一次 resolve 只在已签发且真实兼容的文字修复资源中选择 `duration_minutes` 最低者；这个比较改变实际 activity/resource，并保存成本比较状态。学习者实际作答后，独立验证资格必须同时满足：

初始教学生成器只取得验证内容 guard 的哈希指纹与固定阈值，不取得原始题面或保护答案；用户可见对象的所有嵌套字符串及组合阅读流都必须过重叠检查。命中题面或答案指纹时拒绝投影并重建，不能放宽阈值。process 必须晚于它实际收到的 teaching delivery，并精确绑定该 delivery ID、投影指纹与 response decision fingerprint；追加后 active resolution 会重新落地过程状态，因此 `open-verification` 不把刷新后的 `resolved_at/fingerprint` 误当作作答前 epoch。只有该 process 同时成为当前 resolution 的最后一条 `resolved_process_ref`、当前 `resolved_process_status=ready_for_verification`，且 route/version/task/binding/resource/activity/carrier 未漂移，重算为 `pass + response_correct=true + explanation_quality=pass` 后，才可读取原始验证题，并验证公开题面的完整指纹与 guard 匹配。fail/partial 必须先按派生反馈修复；调用者传入的 process evaluation 字典不构成提交证明。

- 教学题与验证题 `item_id` 不同；独立验证记录的 `verification_item_id`、`verification_task_id`、`bound_verification_task_id` 必须都等于签发任务 ID；
- 验证题未见，完整答案未在首次尝试前泄露；
- 验证时 `A0`；
- evidence 与 `learner + goal + concept + contract/version` 完整同范围；
- evidence 绑定当前 `route_id + route_version + verification_task_id`；三者必须能解析到当前 decision 或不可变的历史任务发行记录，不能只在同一 evidence 内让两组字符串彼此相等。
- 验证任务发行记录必须能解析到签发快照中的真实 resource task；初始教学内容在输出前使用该 task 的 prompt/内部 protected answers 所生成的不可逆 guard 检查，guard 和答案不得投影给学习者。

验证任务本身必须绑定当前合同要求的能力；资格门只判断这条作答能否作为独立验证证据。学习者实际展示了哪些能力、答案是否正确、解释与迁移是否达标，在结果记录中保存，再由即时合同重算统一判断，不能在作答前预填“已覆盖能力”。

通过资格门的正确或错误验证都追加为行为证据：正确证据可能满足合同，错误证据参与冲突和最新失败判断。未通过资格门的结果只作为过程证据，必须修复任务或重新验证，不能进入合同重算的合格通过集合。

## 失败路由与媒介升级

```text
PREREQUISITE_GAP -> CORE_A_REPLAN
FIRST_NONPREREQUISITE_FAIL -> TEXT_REPAIR
REPEATED_SAME_ERROR -> ESCALATION_GATE
CONCEPT_MISCONCEPTION -> MINIMAL_RETEACH
REPRESENTATION_MISMATCH -> REPRESENTATION_RESELECT
```

重复失败升级门必须同时满足：同一错误至少两次、至少两种文字活动/表征、最高帮助达到 A2、无未处理先修缺口，并且候选媒介提供匹配可供性。视频必须绑定连续动作/时空变化，交互必须绑定状态操纵、实际执行或实时反馈。无明确补充能力时继续文字修复，不为换形式而升级。

## 原子回写顺序

所有 diagnostic、teaching_process、verification 与 retention 的生产提交都必须调用 `append-evidence --record <json>`；不存在可以只落 evidence 而跳过派生重算的第二条写路径。必须从 [四阶段输入模板](../templates/append-evidence/README.md) 复制对应 JSON，替换全部 `$...` 占位值而不删除字段或改写哨兵。输入只含 `source_session_id + 原始观察`；`evidence_kind` 是原始观察类型，但必须命中当前 phase 的封闭枚举。事务从 canonical session 反查 `source_kind/source_ref_ids`，并在内部派生 schema、资格、置信度、consumer IDs 与 field bindings。每轮只能按以下顺序提交：

1. 过滤掉无消费者或作用域无效字段；
2. 初始教学先追加 teaching delivery，再在用户响应后追加原始过程/验证 evidence；旧记录不覆盖；
3. 以提交时 `as_of` 从同范围 evidence 分别重算 concept 的 `immediate_contract_status`、`retention_status`、完整 `contract_status`、mastery/confidence、诊断快照与误概念；未来 evidence 不进入当前重算；
4. 从上述派生 mastery 精确重算 boundary、阻塞前置和目标子图；
5. 新的独立 verification/retention 结果进入下一次方法效果画像读取；用 teaching_process 重试更新错误、反馈、表征／载体修复路径和实测过程成本；
6. teaching_process 提交先只刷新当前 active resolution 的 process refs/status、反馈、修复／表征／载体输入和成本，保持作答前 decision epoch 不变；若这些输入要求真正更换 activity/resource，再显式运行文字决策与 `resolve-teaching`，随后必须重新 `issue-teaching`；
7. 完整合同满足时，证据事务只返回 `route_reissue_required`，不直接转换 route；核心一必须基于新边界重新选择，再调用 `issue-route` 递增 route/version 并向签发 hash chain 追加事件；
8. 目标、状态、路线或 Focus 输入变化时，将旧 Focus 快照标为 stale/superseded；
9. 下一次真实多候选决策时重新计算 Focus。

事务必须把“新 evidence 文件、state 关系和派生字段、所有受影响 boundary、同 learner/goal 的 Focus stale 状态、过程 evidence 触发的 active resolution”作为一个回滚集合；最终完整校验任一错误都恢复旧字节并删除本次新记录。

这形成双向闭环：核心一的边界、路径和 Focus 为核心二提供当前步骤；核心二的教学过程把错误、反馈、表征与实测成本送回下一次活动/路径选择，独立验证、迁移与保持结果再更新边界并成为下一次方法效果画像的输入。两类证据互通，但消费者严格分开，不能拿教学中的被帮助完成冒充掌握或方法胜出。

## Goal 与延迟保持闭环

```text
RECOMPUTE_CONCEPT_CONTRACT
  -> IMMEDIATE_NOT_MET -> CLASSIFY_ERROR_AND_REPAIR
  -> IMMEDIATE_MET -> RETENTION_REQUIRED?
     -> no -> FULL_CONTRACT_MET
     -> yes -> RETENTION_STATUS?
        -> not_started
           -> ISSUE_ROUTE(purpose=retention, new task fingerprint)
           -> SCHEDULE_RETENTION_AND_APPEND_RECEIPT
           -> SAVE_CHECKPOINT_AND_WAIT
        -> pending_before_scheduled_for -> SAVE_CHECKPOINT_AND_WAIT
           -> [user proactively reviews] NEW_LEARNING_TASK_AND_INDEPENDENT_VERIFICATION
           -> [old schedule unopened and still pending] NEW_RETENTION_BINDING_AND_SUPERSEDING_SCHEDULE
        -> due
           -> OPEN_DELAYED_AND_APPEND_OR_REUSE_OPEN_RECEIPT
           -> DELAYED_VERIFY_AT_A0
           -> APPEND_DELAYED_EVIDENCE
           -> RECOMPUTE_CONCEPT_CONTRACT
        -> passed_Nd -> FULL_CONTRACT_MET
        -> failed | conflicted
           -> RETENTION_REPAIR
           -> NEW_QUALIFIED_VERIFICATION_BASELINE
           -> NEW_ROUTE_TASK_AND_SUPERSEDING_SCHEDULE_RECEIPT
  -> FULL_CONTRACT_MET -> UPDATE_BOUNDARY_AND_ROUTE
     -> ALL_TARGETS_FULLY_MET? no -> NEXT_CANDIDATE
     -> ALL_TARGETS_FULLY_MET? yes -> COMPLETE_WITH_SCOPED_RESULT
```

必须分开保存 `immediate_contract_status`、`retention_status` 与完整 `contract_status`。即时要求满足但所需延迟检查尚未通过时，`immediate_contract_status=met`、`retention_status=not_started|pending|due`、`contract_status=in_progress`；这不是概念错误，不回到概念教学，只进入保持安排。先用 `issue-route(purpose=retention)` 签发不同 task fingerprint，并在发行事件中显式冻结唯一 `baseline_evidence_id`；再用 `schedule-retention` 要求 schedule baseline 与 issuance baseline 精确相等，并从 `baseline + min_delay_days + 可选 not_before` 内部派生 `scheduled_for`，追加不可变 `retention_schedule` receipt；state 只引用当前 receipt。若派生时间已经过去，直接为 `due`，不能制造新的未来等待。到期后 `open-delayed-verification` 必须先原子追加或幂等复用 `verification_open` receipt，写失败不得显示题面；只把 `user_task` 投影给用户。retention evidence 的 `teaching_item_id` 必须引用该 open receipt，validator 重算 open → schedule → issuance、精确 baseline 及 `scheduled_at <= opened_at < observed_at`。保持失败后只有更新且合格的新 verification baseline 才能签发不同任务并追加 superseding schedule；旧 receipts/evidence 保留历史，不与 state 当前 schedule 强行等同。

## 主线、支线与循环保护

### 主动复习的基线更新

主动复习只在旧排期尚未到期、没有任何开题回执时允许：新 learning issuance 和合格 A0 verification 均必须晚于旧 schedule；新证据属于同一 learner/goal/concept/contract/version，且是当前合格通过集合的一部分。随后签发全新 retention task/binding，并追加 `supersedes_schedule_id` 指向旧回执的 schedule；`not_before` 必须为 null。新检查日期由新 baseline + 合同最小延迟派生，不允许借此自选额外延期。已经 due 或 opened 时必须继续原检查。返回 `schedule_reason=initial|failed_retention_repair|proactive_review` 供恢复/审计，不另存一个可篡改的事实字段。旧回执、证据和账本前缀保持不变；历史校验按当时截止时间重算，后续失败不回写历史通过。

### 请求内读取复用

`validate` 与 `resolve-teaching` 在一次操作中复用私有解析快照，消费方拿到独立副本；每次公开入口仍从磁盘重新读取。写后重新扫描，保留完整校验、事务锁、CAS 与失败回滚。没有跨请求缓存或 SQLite；不把文件 I/O 改善误报成模型 Token 节省。

- 同一 `learner_id + goal_id` 至多一条 `active` 路线。
- 激活支线与暂停主线必须作为同一次状态转换；返回时先结束或暂停支线，再恢复主线断点。
- 路线状态只允许 `active`、`paused`、`completed`、`superseded`、`abandoned`。
- `completed_step_evidence_ids` 只能引用同范围、同合同版本且已经使 state 满足合同的证据。
- 同一 `goal + checkpoint + evidence set` 连续两次切换而没有新证据时停止跳转并请求用户确认。
- 路线缺失时只构造 `reconstructed_unconfirmed` 候选；用户确认前不得冒充原路线。

## 停止规则

- 当前合同和所需保持标准满足：完成；
- 必需前置不成立：回退最短阻塞点；
- 用户时间或认知预算到达：保存断点，不标为失败或掌握；
- 目标改变：新建或修订 goal，不污染原证据链；
- 数据、路线或作用域冲突无法安全决定：停止自动路由，请用户选择。
