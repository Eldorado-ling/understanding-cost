---
schema: "uc-demo/0.2"
id: "res-python-call-stack-trace"
type: "resource"
title: "递归调用栈预测轨迹"
modality: "text"
carrier: "text_hybrid"
text_format: "trace"
activity: "predict_explain"
supported_activities: ["predict_explain"]
protocol_version: "text-demo-v0.5"
verification_required: true
diagnostic_probe: {"id": "probe-python-call-stack-order-v1", "prompt": "在不运行代码的情况下，写出 f(3) 到基例再返回的调用与返回顺序。", "success_criteria": "独立区分入栈顺序与返回顺序，并正确标出基例。"}
verification_task: {"id": "verify-python-call-stack-unseen-v1", "prompt": "给定 h(n)：n 等于 0 时返回 1，否则返回 h(n-1)+2。不要运行代码，写出 h(3) 的最大同时存在栈帧数和返回顺序。", "success_criteria": "A0 独立完成，最大深度和逐层返回结果均正确。", "protected_answers": ["最大同时存在四个栈帧", "h(0)=1，h(1)=3，h(2)=5，h(3)=7"]}
duration_minutes: 6
difficulty: "introductory"
language: "zh-CN"
created_at: "2026-08-28T03:24:07Z"
updated_at: "2026-08-28T03:24:07Z"
privacy: "private"
tags: ["uc/resource"]
cost_vector: {"diagnosis": 0.5, "prerequisites": 0.5, "core_learning": 4.5, "practice_feedback": 2.5, "verification": 2.0, "maintenance_relearning": 2.0}
---

# 递归调用栈预测轨迹

> Agent 内部教学资源规格；验证题与保护答案不得直接进入学习者材料。实际交付必须经过文字协议白名单和 verification content guard。

## Relations

- teaches: [[kc-python-call-stack]]
- requires: [[kc-python-function]]
