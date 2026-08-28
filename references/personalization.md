# 基于证据的学习响应画像

## 内部决策与用户呈现隔离

学习响应画像和 Focus Cone 默认只供 Agent 选择活动，不作为用户界面直接展示。Agent 可以在内部比较 `context_key`、活动、媒介、帮助强度、成本与结果；面向用户时只输出当前学习活动、操作步骤、任务和检验。

普通教学轮次不得向用户输出：画像分数、媒介排名、Focus 分量、内部置信度等级、样本数量、探索概率、原因码或“你属于某种类型”的归类。用户明确要求 `inspect`、纠正或删除画像时，可以提供脱敏记录，但必须同时展示适用情境、证据来源、样本限制和未验证项。

内部选择结果必须先转换成：

```yaml
delivery_plan:
  learning_objective: ...
  activity: ...
  medium: ...
  steps: [...]
  learner_task: ...
  feedback_rule: ...
  verification_rule: ...
  success_criteria: ...
```

初始计划不得包含尚未见的完整 `verification_task`，也不得通过改键名、改写句式或把答案塞进示例来暗示它。可信 Vault 调用方须从当前绑定验证资源的题面与答案生成不含原文的 `verification_content_guard`；初始用户投影递归检查所有可见字符串的规范化整句与 n-gram 指纹，达到保守重叠阈值即拒绝。guard 是 Agent 内部数据，禁止投影。只有当前 decision 绑定的教学过程 evidence 被接受后，才由独立验证投影公开与 guard 完全匹配的题面。不得把内部画像字段直接透传到 `delivery_plan`。`A0–A4` 是 Agent 记录提示强度的内部代码；用户只看到实际提示和独立完成要求。

## 不建立固定学习风格

用户的“喜欢某种方式”是体验偏好，不等于该方式能带来更好的独立表现、迁移或保持。不要把用户分类为视觉型、听觉型、阅读型等固定类型。

本 Demo 使用情境化的学习响应假设：

```text
domain × knowledge_kind × target_performance × prior_knowledge_band
× task_difficulty × activity × carrier × assistance_level
```

例如可以说：

> 在“已有基础的规则辨析”任务中，当前两次观察显示“对比例题后立即练习”用时较低且近迁移较好，证据仍为 tentative。

不能说：

> 你是图像型学习者，所以所有内容都应该看视频。

## 偏好与效果分表

### preference

- 用户愿意使用或拒绝的媒介；
- 设备、带宽、听觉/视觉/动作限制；
- 可用时间、环境和交互容忍度；
- 自报主观轻松度。

Demo 中这些自报偏好对“哪种方式教学效果更好”的选择权重为 `0`。它们只用于可访问性/明确拒绝等硬约束，或安排一次低成本对比的先后顺序；只有同情境的任务表现与成本观察才能进入 Pareto 比较。这样不需要设置缺乏实证依据的任意先验系数。

### response observation

每次活动先由 Vault evidence 与该 evidence 自己的合同重算结果生成唯一 `response-observation-v1`，不得手写扁平表现记录。用于比较的关键结构是：

```yaml
schema_version: response-observation-v1
source: {kind: vault_evidence, evidence_id: ev-..., source_refs: [...]}
scope: {learner_id: usr-..., goal_id: goal-..., concept_id: kc-..., contract_id: mc-..., contract_version: 1}
context_key: domain=python|knowledge_kind=rule|target_performance=discriminate|prior_band=partial|task_difficulty=medium
comparison_gate: {retention_required: false, task_difficulty: medium}
profile_actionability: {status: actionable, missing_field_bindings: []}
activity: contrast_cases
carrier: text_hybrid
assistance_level: A1
elapsed_seconds: 420
attempts: 1
hint_count: 1
immediate_performance: 0.80
near_transfer: 0.75
delayed_retention: pending
mastery_gate_met: false
mastery_gate_derivation:
  evaluation_scope: {...} # 必须等于本 observation.scope
  comparison_gate: {retention_required: false, task_difficulty: medium}
```

`context_key` 是可验证的 canonical key，五个维度缺一不可；因此不同 goal、concept、contract 可以复用，但不同 learner 或 domain 不能混入。`comparison_gate` 从 observation 自己的合同重算增强结果派生，当前决策必须提供完全相同的 gate；历史帮助强度还必须不高于当前 `max_assistance_level`。不适用项写 `not_required`、`pending` 或 `not_tested`，不能猜值。

`profile_actionability=actionable` 还要求 activity、carrier、context、帮助、成本、即时表现、时间和置信度的 field binding 明确包含真实下游 `activity_selection`；只有 `boundary_update` 或 `feedback_selection` 不够。缺少这些 binding 仍可形成 canonical observation，但只能是 `not_actionable`，不得进入画像选择。即使 binding 完整，`observation_confidence=low` 也只能保留为探索线索，不能进入画像 Pareto。teaching_process 不进入这一方法效果画像；其 activity、carrier、作答、解释质量、错误、帮助强度与时间分别由当前 `activity_selection`、`representation_selection`、`feedback_selection` 和教学签发／开题 guard 消费。

## 读写闭环与消费者

响应画像必须先读后选、活动后再写，不能只累计数据而不改变任何决策。唯一合法读入口是由 Vault evidence 与同范围合同重算结果生成的 `response-observation-v1`；不接受调用者拼装的扁平 observation：

```text
加载同 learner + canonical context_key 的有效观察
  -> 校验每条 observation.scope 等于其自身 evaluation_scope
  -> 匹配 comparison gate，并排除帮助超出当前上限或低观察置信度的记录
  -> 排除未达到自身 mastery gate 或不可行动的方案
  -> 比较活动成本与学习结果
  -> 唯一 Pareto 占优则选择
  -> 无唯一占优则知识机制默认或单变量探索
  -> 执行活动
  -> 追加 teaching_process，派生当前错误、反馈与实测成本
  -> 追加独立 verification/retention，更新下一次同情境方法效果选择
```

每个响应字段必须声明消费者：

- `context_key`：选择可比较的历史集合；
- `activity/carrier`：确定被比较的教学方案；
- `assistance_level`：区分独立表现与高帮助完成；
- 时间、尝试、提示和主观努力：进入成本 Pareto；
- 即时表现、近迁移和延迟保持：进入 mastery gate、活动比较和实验评估；
- `source_evidence_id`：追溯与撤回；
- `mastery_gate_met`：由 observation 自身 scope 的合同重算派生，决定该观察能否支持“效果较优”的活动选择；不同知识点可比较不等于共享 mastery。

没有当前决策消费者的字段不计算、不保存。过程证据必须标记 `mastery_eligible: false`，只更新当前错误、反馈/修复动作与实测成本；只有绑定已签发任务、未见、A0、同范围的独立 verification/retention 才能进入方法效果画像与 mastery contract。

## 透明选择算法

1. 先按当前 learner 与 canonical `context_key` 找历史观察；允许 goal/concept/contract 不同，但拒绝跨 learner、跨 domain、来源或时间状态失效的记录；
2. 每条记录先由 `vault_tool.build_response_observation_from_vault(vault, evidence_id)` 从 state `supported_by` canonical 窗口、原始 contract 和 route issuance 反查并重算 mastery gate；调用者不得传入自造窗口、自报 status 或 qualified evidence IDs；只有绑定已签发 task 的独立 verification/retention 进入方法效果比较，同一 `route binding + phase + task` 只允许一条 canonical evidence，重试必须先签发新的 task 或 route/version。teaching_process 重试另行进入反馈、表征／载体修复和实测成本通道，不增加这里的样本门槛；随后再匹配当前 `retention_required + task_difficulty` 和帮助上限；
3. 在相同 gate、相同任务难度和相同允许帮助下，比较用时、提示、尝试、迁移、延迟保持和主观负担；
4. 只有唯一 Pareto 占优且证据达到当前使用门槛时，才让画像改变活动或 carrier；
5. 没有唯一占优方案时，根据知识机制使用文字默认活动，或只改变一个主要因素做低成本探索；
6. 记录 `profile_selection_status + selected_observation_ids + selection_consumer=activity_selection`；
7. 活动后追加观察，再更新假设；不得用本次被选中本身证明画像正确。

不要为了得到单一排名而偷偷设置权重。如果用户明确说“今天先省时间、再考虑一周后保持”，把它记录成有序成本维度，只在 Pareto 前沿内按原始值做词典序比较，并说明其他维度的代价。

## 置信度规则（Demo 约定，不是心理量表）

| 等级 | 最低证据条件 |
|---|---|
| `unknown` | 0 次有效观察 |
| `tentative` | 唯一 Pareto 胜出选项自身只有 1–2 次合格观察；重复样本更多但不足 2 个知识点时也封顶于此 |
| `emerging` | 唯一 Pareto 胜出的同一 `(activity, carrier)` 选项自身至少 3 次合格观察，覆盖至少 2 个知识点 |
| `supported` | 唯一 Pareto 胜出的同一 `(activity, carrier)` 选项自身至少 5 次合格观察、3 个知识点，且该选项自身含至少 1 次数值化近迁移或延迟保持证据 |

这些门槛是执行约束，不只是标签，且不得把其他候选的样本数、知识点覆盖或迁移/保持证据合并给胜出选项：`tentative` 只能输出受限的单变量探索候选，不能覆盖默认活动或 carrier；`emerging` 只有出现唯一 Pareto 优势时才能改变文字 activity，不能改变 carrier；`supported` 才允许更强的跨知识点文字 activity/carrier 复用。非文字 carrier 即使达到 `supported`，仍须有与目标匹配的 affordance。`profile_selection` 必须分别给出候选池统计和胜出选项自身的观察数、知识点覆盖、迁移/保持条件及未达门槛原因，`profile_usage_status` 必须明确是探索、阈值阻止、只改 activity 或 activity+carrier。

跨领域、跨知识类型、目标表现、先验带或任务难度的观察只能生成 `transfer_hypothesis`，不得直接更新目标领域 mastery 或活动选择。阈值只是为了让 Demo 可重复，应在真实试验后校准。

## 探索与利用

这个过程可借鉴 contextual bandit 的“探索—利用”思想，但 Demo 不训练不透明模型：

- `unknown/tentative`：在两个机制合理且成本可接受的活动间做微型对比；
- `emerging`：多数使用当前较优活动，偶尔验证替代方案；
- `supported`：在相同情境优先使用较优活动，但出现退化、目标改变或新限制时重新探索。

一次活动只改变一个主要因素，避免同时更换内容难度、媒介、提示和任务，导致无法解释结果。

## 选择媒介的顺序

1. 目标行为需要什么信息加工或动作；
2. 知识是否动态、空间化、程序化或高度依赖反馈；
3. 用户当前先验知识与误概念；
4. 哪种教学活动最匹配；
5. 哪种媒介能以最低额外协调成本承载该活动；
6. 用户可访问性和偏好是否形成硬约束。

媒介只是活动的载体。视频没有预测、暂停、练习和反馈时，不会因“是视频”自动降低成本。

当前 Demo 采用 `text_preferred`：没有同情境效果证据或非文字硬需求时，先使用 [text-learning.md](text-learning.md) 的 `text_document`、`text_dialogue` 或 `text_hybrid` 完成一轮可验证闭环。这是低协调成本的默认策略，不是“文字最适合该用户”的结论。

同情境历史观察只有某个 `(activity, carrier)` 自身达到上述门槛且形成唯一 Pareto 优势时才改变选择：`emerging` 最多改变文字 activity；`supported` 才能复用 carrier。候选池合计达到门槛但胜出选项自身未达到时，只能探索或使用默认。即使 `supported` 支持视频或交互，仍须满足 [text-learning.md](text-learning.md) 的目标可供性与独立验证要求。

## 推荐语言

使用：

- “当前观察表明……”；
- “只在这类任务中暂时成立……”；
- “偏好证据与效果证据不一致……”；
- “延迟保持尚未验证……”；
- “下一次用一个小任务比较……” 。

避免：

- “你天生擅长……”；
- “最适合你的永远是……”；
- “模型已经证明你……”；
- “完成一次就是掌握”。
