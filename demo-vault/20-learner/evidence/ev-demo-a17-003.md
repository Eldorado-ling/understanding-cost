---
schema: "uc-demo/0.2"
id: "ev-demo-a17-003"
type: "evidence"
title: "证据：kc-python-call-stack / explanation"
learner_id: "demo-a17"
concept_id: "kc-python-call-stack"
goal_id: "goal-demo-a17-recursion"
contract_id: "mc-python-call-stack"
contract_version: 1
phase: "teaching_process"
carrier: "text_hybrid"
teaching_item_id: "teach-python-call-stack-trace-v1"
teaching_delivery_fingerprint_at_observation: "543f706979c19c68e14849c7a8649eae2b9ef8a1e2c1310c18a86ccbc77b29cf"
verification_item_id: null
verification_unseen: false
answer_revealed_before_first_attempt: false
verification_task_id: "verify-python-call-stack-unseen-v1"
bound_verification_task_id: "verify-python-call-stack-unseen-v1"
route_id_at_observation: "route-demo-a17-recursion"
route_version_at_observation: 1
decision_fingerprint_at_observation: "9dd38ae425af1b38afd56ae2f2b8230c91600ca1a8d694583cc0ca0ab810592f"
consumer_ids: ["activity_selection", "event_identity_guard", "feedback_selection", "process_evidence_gate", "process_trace", "representation_selection", "teaching_delivery_guard", "verification_gate"]
source_ref_ids: ["assets/demo-seed.json"]
observation_validity: "valid"
mastery_eligible: false
evidence_kind: "explanation"
demonstrates: ["explanation", "trace_prediction"]
result: "partial"
independence: "not_observed"
assistance_level: "A1"
activity: "predict_explain"
error_signature: "return_order_confusion"
context_key: "domain=python|knowledge_kind=causal_structure|target_performance=explain|prior_band=partial|task_difficulty=medium"
route_binding_id: "rb-demo-a17-call-stack-current-v1"
elapsed_seconds: 430
attempts: 2
hint_count: 1
immediate_performance: 0.72
near_transfer: "not_tested"
delayed_retention: "not_tested"
response_correct: true
explanation_quality: "partial"
self_reported_effort: 5
retention_delay_days: 0
baseline_evidence_id: null
retention_task_id: null
scheduled_for: null
source_kind: "synthetic_demo"
observed_at: "2026-08-26T06:20:00Z"
created_at: "2026-09-03T11:16:49Z"
updated_at: "2026-09-03T11:16:49Z"
privacy: "sensitive"
tags: ["uc/evidence"]
field_bindings: {"activity": {"consumers": ["activity_selection", "feedback_selection", "representation_selection", "teaching_delivery_guard"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "answer_revealed_before_first_attempt": {"consumers": ["verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "assistance_level": {"consumers": ["activity_selection", "representation_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "attempts": {"consumers": ["feedback_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "bound_verification_task_id": {"consumers": ["verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "carrier": {"consumers": ["activity_selection", "feedback_selection", "representation_selection", "teaching_delivery_guard"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "context_key": {"consumers": ["teaching_delivery_guard", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "decision_fingerprint_at_observation": {"consumers": ["teaching_delivery_guard", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "demonstrates": {"consumers": ["feedback_selection", "representation_selection", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "elapsed_seconds": {"consumers": ["activity_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "error_signature": {"consumers": ["feedback_selection", "representation_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "explanation_quality": {"consumers": ["feedback_selection", "representation_selection", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "hint_count": {"consumers": ["feedback_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "immediate_performance": {"consumers": ["feedback_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "mastery_eligible": {"consumers": ["verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "observation_confidence": {"consumers": ["process_evidence_gate", "representation_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "observed_at": {"consumers": ["activity_selection", "event_identity_guard", "feedback_selection", "representation_selection", "teaching_delivery_guard", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "response_correct": {"consumers": ["feedback_selection", "representation_selection", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "result": {"consumers": ["feedback_selection", "representation_selection", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "route_id_at_observation": {"consumers": ["teaching_delivery_guard", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "route_version_at_observation": {"consumers": ["teaching_delivery_guard", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "self_reported_effort": {"consumers": ["feedback_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "teaching_delivery_fingerprint_at_observation": {"consumers": ["teaching_delivery_guard"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "teaching_item_id": {"consumers": ["process_trace", "teaching_delivery_guard"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "verification_task_id": {"consumers": ["verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}, "verification_unseen": {"consumers": ["verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-call-stack", "contract_id": "mc-python-call-stack", "contract_version": 1}, "observed_at": "2026-08-26T06:20:00Z", "validity": "valid"}}
observation_confidence: "medium"
observation_confidence_basis: "observed_process_or_diagnostic_behavior"
---

# 证据：kc-python-call-stack / explanation

能在轻提示下跟踪两层函数调用，但仍混淆返回顺序。

## Relations

- about: [[kc-python-call-stack]]
- derived_from: [[ses-demo-a17-20260826t063000z]]
