---
schema: "uc-demo/0.2"
id: "goal-demo-a17-recursion"
type: "goal"
title: "理解递归为什么会导致栈溢出"
learner_id: "demo-a17"
status: "active"
source_question: "为什么递归会发生栈溢出？"
desired_outcome: "explain_predict_and_debug"
retention_check_days: 7
mastery_contracts: [{"id": "mc-python-function-baseline", "version": 1, "concept_id": "kc-python-function", "requirements": {"minimum_qualified_evidence": 1, "required_capabilities": ["independent_application", "explanation", "delayed_retention"], "min_near_transfer": 0.75, "delayed_retention": {"required": true, "min_score": 0.75, "min_delay_days": 7}}}, {"id": "mc-python-iteration-baseline", "version": 1, "concept_id": "kc-python-iteration", "requirements": {"minimum_qualified_evidence": 1, "required_capabilities": ["independent_application", "discrimination", "near_transfer", "delayed_retention"], "min_near_transfer": 0.75, "delayed_retention": {"required": true, "min_score": 0.75, "min_delay_days": 7}}}, {"id": "mc-python-call-stack", "version": 1, "concept_id": "kc-python-call-stack", "requirements": {"minimum_qualified_evidence": 2, "required_capabilities": ["explanation", "trace_prediction", "error_correction"], "min_near_transfer": 0.7, "delayed_retention": {"required": true, "min_score": 0.7, "min_delay_days": 7}}}, {"id": "mc-python-recursion", "version": 1, "concept_id": "kc-python-recursion", "requirements": {"minimum_qualified_evidence": 2, "required_capabilities": ["explanation", "prediction", "error_correction"], "min_near_transfer": 0.7, "delayed_retention": {"required": true, "min_score": 0.7, "min_delay_days": 7}}}, {"id": "mc-python-base-case", "version": 1, "concept_id": "kc-python-base-case", "requirements": {"minimum_qualified_evidence": 1, "required_capabilities": ["boundary_explanation", "error_correction"], "min_near_transfer": 0.7, "delayed_retention": {"required": false, "min_score": null, "min_delay_days": 0}}}, {"id": "mc-python-stack-overflow", "version": 1, "concept_id": "kc-python-stack-overflow", "requirements": {"minimum_qualified_evidence": 2, "required_capabilities": ["diagnosis", "near_transfer", "error_correction"], "min_near_transfer": 0.75, "delayed_retention": {"required": true, "min_score": 0.7, "min_delay_days": 7}}}, {"id": "mc-python-memoization", "version": 1, "concept_id": "kc-python-memoization", "requirements": {"minimum_qualified_evidence": 1, "required_capabilities": ["explanation", "application"], "min_near_transfer": 0.7, "delayed_retention": {"required": false, "min_score": null, "min_delay_days": 0}}}]
created_at: "2026-09-03T11:16:49Z"
updated_at: "2026-09-03T11:16:49Z"
privacy: "private"
tags: ["uc/goal"]
---

# 理解递归为什么会导致栈溢出

> 原问题：为什么递归会发生栈溢出？

## Relations

- for_learner: [[usr-demo-a17]]
- targets: [[kc-python-recursion]]
- targets: [[kc-python-call-stack]]
- targets: [[kc-python-base-case]]
- targets: [[kc-python-stack-overflow]]

## Mastery contract

- 能独立解释一次递归调用如何进入和退出调用栈
- 能预测一个简短递归程序的调用顺序与最大栈深度
- 能指出终止条件缺失或不可达的原因
- 能在表面形式不同的新例子中诊断栈溢出
- 七天后仍能完成一项简化的预测与纠错任务

## Structured contracts

### mc-python-function-baseline

- contract version: 1
- 合同知识点：[[kc-python-function]]
- minimum qualified evidence: 1
- required capabilities: independent_application, explanation, delayed_retention
- minimum near transfer: 0.75
- delayed retention required: true
- delayed threshold: 0.75 after 7 days

### mc-python-iteration-baseline

- contract version: 1
- 合同知识点：[[kc-python-iteration]]
- minimum qualified evidence: 1
- required capabilities: independent_application, discrimination, near_transfer, delayed_retention
- minimum near transfer: 0.75
- delayed retention required: true
- delayed threshold: 0.75 after 7 days

### mc-python-call-stack

- contract version: 1
- 合同知识点：[[kc-python-call-stack]]
- minimum qualified evidence: 2
- required capabilities: explanation, trace_prediction, error_correction
- minimum near transfer: 0.7
- delayed retention required: true
- delayed threshold: 0.7 after 7 days

### mc-python-recursion

- contract version: 1
- 合同知识点：[[kc-python-recursion]]
- minimum qualified evidence: 2
- required capabilities: explanation, prediction, error_correction
- minimum near transfer: 0.7
- delayed retention required: true
- delayed threshold: 0.7 after 7 days

### mc-python-base-case

- contract version: 1
- 合同知识点：[[kc-python-base-case]]
- minimum qualified evidence: 1
- required capabilities: boundary_explanation, error_correction
- minimum near transfer: 0.7
- delayed retention required: false
- delayed threshold: None after 0 days

### mc-python-stack-overflow

- contract version: 1
- 合同知识点：[[kc-python-stack-overflow]]
- minimum qualified evidence: 2
- required capabilities: diagnosis, near_transfer, error_correction
- minimum near transfer: 0.75
- delayed retention required: true
- delayed threshold: 0.7 after 7 days

### mc-python-memoization

- contract version: 1
- 合同知识点：[[kc-python-memoization]]
- minimum qualified evidence: 1
- required capabilities: explanation, application
- minimum near transfer: 0.7
- delayed retention required: false
- delayed threshold: None after 0 days
