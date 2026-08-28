---
schema: "uc-demo/0.2"
delivery_contract: "uc-teaching-delivery/0.1"
type: "teaching_delivery"
id: "teach-python-call-stack-trace-v1"
title: "教学签发：kc-python-call-stack"
learner_id: "demo-a17"
goal_id: "goal-demo-a17-recursion"
concept_id: "kc-python-call-stack"
contract_id: "mc-python-call-stack"
contract_version: 1
route_id: "route-demo-a17-recursion"
route_version: 1
route_binding_id: "rb-demo-a17-call-stack-current-v1"
context_key: "domain=python|knowledge_kind=causal_structure|target_performance=explain|prior_band=partial|task_difficulty=medium"
decision_fingerprint: "9dd38ae425af1b38afd56ae2f2b8230c91600ca1a8d694583cc0ca0ab810592f"
resource_id: "res-python-call-stack-trace"
activity: "predict_explain"
carrier: "text_hybrid"
delivery_plan: {"learning_objective": "区分调用展开顺序与返回顺序，并能用自己的话解释。", "method_label": "预测后解释", "medium": "文字文件＋对话", "orientation": "先看清每一步是谁调用谁，再单独追踪返回方向。", "term_grounding": [], "explanation": "调用发生时先进入下一层；到达停止条件后，结果才按相反方向逐层返回。", "example": "像叠放便签：新便签压在上面，处理完最上层后再依次取下。", "visual": null, "learner_task": "不运行代码，写出两层调用的进入顺序和返回顺序，并说明两者为何相反。", "response_format": "先写调用顺序，再写返回顺序，最后用一句话解释。", "feedback_rule": "只纠正当前混淆的一步，不提前给完整轨迹。", "verification_rule": "教学任务完成后再发一个未见例子，独立作答且不使用提示。", "success_criteria": "能够正确区分进入与返回方向，并给出因果解释。", "next_step": {"instruction": "完成当前预测后，根据错误只修正一处再重做。", "when": null}}
delivery_plan_fingerprint: "543f706979c19c68e14849c7a8649eae2b9ef8a1e2c1310c18a86ccbc77b29cf"
issued_at: "2026-08-26T06:19:00Z"
source_kind: "synthetic_demo"
source_ref_ids: ["assets/demo-seed.json"]
created_at: "2026-08-28T03:24:07Z"
updated_at: "2026-08-28T03:24:07Z"
privacy: "sensitive"
tags: ["uc/teaching-delivery", "uc/append-only"]
---

# 已发行教学项

> 追加记录：保存实际用户白名单投影及其指纹；过程作答必须引用本记录。

## Relations

- for_learner: [[usr-demo-a17]]
- for_goal: [[goal-demo-a17-recursion]]
- about: [[kc-python-call-stack]]
- uses: [[res-python-call-stack-trace]]
