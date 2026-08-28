---
schema: "uc-demo/0.2"
id: "res-python-call-stack-faded"
type: "resource"
title: "调用栈逐步撤除支架练习"
modality: "text"
carrier: "text_hybrid"
text_format: "worked_example_fading"
activity: "worked_example_fading"
supported_activities: ["worked_example_fading"]
protocol_version: "text-demo-v0.5"
verification_required: true
diagnostic_probe: {"id": "probe-python-call-stack-faded-v1", "prompt": "先看一条完整的调用栈返回轨迹，再补全另一条只保留关键节点的轨迹。", "success_criteria": "能在支架逐步减少后独立补全入栈与返回方向。"}
verification_task: {"id": "verify-python-call-stack-unseen-v1", "prompt": "给定 h(n)：n 等于 0 时返回 1，否则返回 h(n-1)+2。不要运行代码，写出 h(3) 的最大同时存在栈帧数和返回顺序。", "success_criteria": "A0 独立完成，最大深度和逐层返回结果均正确。", "protected_answers": ["最大同时存在四个栈帧", "h(0)=1，h(1)=3，h(2)=5，h(3)=7"]}
duration_minutes: 4
difficulty: "introductory"
language: "zh-CN"
created_at: "2026-08-28T03:24:07Z"
updated_at: "2026-08-28T03:24:07Z"
privacy: "private"
tags: ["uc/resource"]
cost_vector: {"diagnosis": 0.5, "prerequisites": 0.5, "core_learning": 4.0, "practice_feedback": 4.0, "verification": 1.0, "maintenance_relearning": 1.0}
---

# 调用栈逐步撤除支架练习

> Agent 内部教学资源规格；验证题与保护答案不得直接进入学习者材料。实际交付必须经过文字协议白名单和 verification content guard。

## Relations

- teaches: [[kc-python-call-stack]]
- requires: [[kc-python-function]]
