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
diagnostic_probe: {"id": "probe-python-call-stack-faded-v1", "prompt": "这次只练习：一个函数结束后，接着执行哪一步。不必运行代码。下面每个函数是一组有名字的步骤；“调用”表示让另一个函数开始执行。“送信①”就是送信函数的第①步，箭头表示下一步的位置。\n\n完整示例：\n函数送信：①写下“取信”；②调用盖章；③写下“出发”。\n函数盖章：①写下“盖章”。\n从送信开始。\n已完成：送信① → 送信② → 盖章① → 送信③。\n\n现在轮到你：\n函数整理：①写下“取书”；②调用贴签；③写下“放好”。\n函数贴签：①写下“贴标签”；②写下“检查标签”。\n从整理开始。\n待补：整理① → 整理② → 贴签① → ___ → ___。\n\n请补最后两个位置，再说说贴签函数结束后回到哪里继续。\n答题格式：两个空依次是___、___；因为___。如果没把握，指出卡在哪一步即可。", "success_criteria": "能补对两个执行位置，并用自己的话说明被调用的函数结束后从哪一步继续。"}
verification_task: {"id": "verify-python-call-stack-unseen-v1", "prompt": "给定 h(n)：n 等于 0 时返回 1，否则返回 h(n-1)+2。不要运行代码，写出 h(3) 的最大同时存在栈帧数和返回顺序。", "success_criteria": "A0 独立完成，最大深度和逐层返回结果均正确。", "protected_answers": ["最大同时存在四个栈帧", "h(0)=1，h(1)=3，h(2)=5，h(3)=7"]}
duration_minutes: 4
difficulty: "introductory"
language: "zh-CN"
created_at: "2026-09-03T11:16:49Z"
updated_at: "2026-09-03T11:16:49Z"
privacy: "private"
tags: ["uc/resource"]
cost_vector: {"diagnosis": 0.5, "prerequisites": 0.5, "core_learning": 4.0, "practice_feedback": 4.0, "verification": 1.0, "maintenance_relearning": 1.0}
---

# 调用栈逐步撤除支架练习

> Agent 内部教学资源规格；验证题与保护答案不得直接进入学习者材料。实际交付必须经过文字协议白名单和 verification content guard。

## Relations

- teaches: [[kc-python-call-stack]]
- requires: [[kc-python-function]]
