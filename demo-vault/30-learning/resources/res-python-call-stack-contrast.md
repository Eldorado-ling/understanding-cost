---
schema: "uc-demo/0.2"
id: "res-python-call-stack-contrast"
type: "resource"
title: "调用栈成对对比例题"
modality: "text"
carrier: "text_hybrid"
text_format: "paired_cases"
activity: "contrast_cases"
supported_activities: ["contrast_cases"]
protocol_version: "text-demo-v0.5"
verification_required: true
diagnostic_probe: {"id": "probe-python-call-stack-contrast-v1", "prompt": "比较一个嵌套函数调用和一个单分支递归调用，标出两者入栈与返回的共同顺序规则。", "success_criteria": "能指出先调用的栈帧后返回，并区分展开方向与返回方向。"}
verification_task: {"id": "verify-python-call-stack-unseen-v1", "prompt": "给定 h(n)：n 等于 0 时返回 1，否则返回 h(n-1)+2。不要运行代码，写出 h(3) 的最大同时存在栈帧数和返回顺序。", "success_criteria": "A0 独立完成，最大深度和逐层返回结果均正确。", "protected_answers": ["最大同时存在四个栈帧", "h(0)=1，h(1)=3，h(2)=5，h(3)=7"]}
duration_minutes: 6
difficulty: "introductory"
language: "zh-CN"
created_at: "2026-08-28T03:24:07Z"
updated_at: "2026-08-28T03:24:07Z"
privacy: "private"
tags: ["uc/resource"]
cost_vector: {"diagnosis": 0.5, "prerequisites": 0.5, "core_learning": 5.0, "practice_feedback": 1.5, "verification": 2.5, "maintenance_relearning": 1.5}
---

# 调用栈成对对比例题

> Agent 内部教学资源规格；验证题与保护答案不得直接进入学习者材料。实际交付必须经过文字协议白名单和 verification content guard。

## Relations

- teaches: [[kc-python-call-stack]]
- requires: [[kc-python-function]]
