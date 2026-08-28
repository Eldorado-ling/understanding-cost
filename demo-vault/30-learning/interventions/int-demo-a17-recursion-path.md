---
schema: "uc-demo/0.2"
id: "int-demo-a17-recursion-path"
type: "intervention"
title: "递归与栈溢出最小学习路径"
learner_id: "demo-a17"
status: "active"
strategy: "text_hybrid_trace_predict_verify"
medium_policy: "text_preferred"
carrier: "text_hybrid"
estimated_minutes: 25
cost_vector: {"diagnosis": 2, "prerequisites": 0, "core_learning": 6, "practice_feedback": 5, "verification": 4, "maintenance_relearning": 8}
adaptation_confidence: "emerging"
teaching_decision_inputs: {"max_assistance_level": "A2", "delivery_intent": "learn", "text_sufficiency": "unknown", "hard_constraints": [], "prerequisite_gap": false}
route_id: "route-demo-a17-recursion"
route_version: 1
goal_id: "goal-demo-a17-recursion"
current_checkpoint: "kc-python-call-stack"
current_activity_id: "res-python-call-stack-faded"
current_probe_id: "probe-python-call-stack-faded-v1"
current_verification_task_id: "verify-python-call-stack-unseen-v1"
completed_step_evidence_ids: ["ev-demo-a17-001", "ev-demo-a17-002"]
parent_route_id: null
return_checkpoint: null
recovery_status: "original"
recovered_from: []
path: ["kc-python-call-stack", "kc-python-recursion", "kc-python-base-case", "kc-python-stack-overflow"]
created_at: "2026-08-28T03:24:07Z"
updated_at: "2026-08-28T03:24:07.841098Z"
privacy: "private"
tags: ["uc/intervention"]
teaching_resolution_schema: "uc-active-teaching-resolution/0.2"
resolved_activity: "worked_example_fading"
resolved_carrier: "text_hybrid"
resolved_resource_id: "res-python-call-stack-faded"
resolved_profile_refs: []
resolved_profile_level: "emerging"
resolved_profile_usage: "overridden_by_text_repair_gate"
resolved_process_refs: ["ev-demo-a17-003"]
resolved_process_status: "repair_required"
resolved_process_feedback_rule: "reduce_information_then_correct_current_error"
resolved_process_next_action: "shorter_text_repair"
resolved_process_cost: {"practice_feedback_seconds": 430.0, "practice_feedback_minutes": 7.167, "total_attempts": 2, "total_hint_count": 1, "mean_self_reported_effort": 5.0}
resolved_process_cost_selection: {"status": "over_estimate", "estimated_minutes": 5.0, "measured_minutes": 7.167, "selected_by_cost": true, "consumer": "activity_selection"}
resolved_cost_vector: {"diagnosis": 2, "prerequisites": 0, "core_learning": 6, "practice_feedback": 7.167, "verification": 4, "maintenance_relearning": 8}
resolved_cost_basis: "measured_process_evidence"
resolved_same_error_count: 1
resolved_text_variants_tried: 1
resolved_latest_teaching_item_id: "teach-python-call-stack-trace-v1"
resolved_max_observed_assistance_level: "A1"
resolved_process_support_load: "high"
resolved_route_binding_id: "rb-demo-a17-call-stack-current-v1"
resolved_context_key: "domain=python|knowledge_kind=causal_structure|target_performance=explain|prior_band=partial|task_difficulty=medium"
resolved_at: "2026-08-28T03:24:07.841098Z"
process_refreshed_at: "2026-08-28T03:24:07.841098Z"
resolved_decision_fingerprint: "86a2dac6733df7094a6d9f366451d9884c7dceabf68158a266dbad5e15c68231"
---

# 递归与栈溢出最小学习路径

先补调用栈返回顺序，再进入递归；终止条件和栈溢出仍被递归理解阻塞。循环作为已掌握类比锚点，而不是先修。

## Relations

- for_learner: [[usr-demo-a17]]
- implements: [[goal-demo-a17-recursion]]
- uses: [[res-python-call-stack-trace]]
- uses: [[res-python-call-stack-contrast]]
- uses: [[res-python-call-stack-faded]]

## Path

1. [[kc-python-call-stack]]
2. [[kc-python-recursion]]
3. [[kc-python-base-case]]
4. [[kc-python-stack-overflow]]
