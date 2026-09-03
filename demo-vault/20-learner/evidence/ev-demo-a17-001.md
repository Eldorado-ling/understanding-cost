---
schema: "uc-demo/0.2"
id: "ev-demo-a17-001"
type: "evidence"
title: "证据：kc-python-function / independent_performance"
learner_id: "demo-a17"
concept_id: "kc-python-function"
goal_id: "goal-demo-a17-recursion"
contract_id: "mc-python-function-baseline"
contract_version: 1
phase: "verification"
carrier: "text_hybrid"
teaching_item_id: "teach-python-function-call-v1"
teaching_delivery_fingerprint_at_observation: null
verification_item_id: "verify-python-function-call-v1"
verification_unseen: true
answer_revealed_before_first_attempt: false
verification_task_id: "verify-python-function-call-v1"
bound_verification_task_id: "verify-python-function-call-v1"
route_id_at_observation: "route-python-function-baseline-v1"
route_version_at_observation: 1
decision_fingerprint_at_observation: null
consumer_ids: ["activity_selection", "boundary_update", "contract_recompute", "derived_assertion_guard", "event_identity_guard", "recovery", "verification_gate"]
source_ref_ids: ["assets/demo-seed.json"]
observation_validity: "valid"
mastery_eligible: true
evidence_kind: "independent_performance"
demonstrates: ["independent_application", "explanation", "near_transfer"]
result: "pass"
independence: "independent"
assistance_level: "A0"
activity: "contrast_cases"
error_signature: null
context_key: "domain=python|knowledge_kind=causal_structure|target_performance=explain|prior_band=partial|task_difficulty=medium"
route_binding_id: "rb-demo-a17-function-baseline-v1"
elapsed_seconds: 330
attempts: 1
hint_count: 0
immediate_performance: 0.9
near_transfer: 0.85
delayed_retention: "not_tested"
response_correct: true
explanation_quality: "pass"
self_reported_effort: 3
retention_delay_days: 0
baseline_evidence_id: null
retention_task_id: null
scheduled_for: null
source_kind: "synthetic_demo"
observed_at: "2026-08-19T06:00:00Z"
created_at: "2026-09-03T11:16:49Z"
updated_at: "2026-09-03T11:16:49Z"
privacy: "sensitive"
tags: ["uc/evidence"]
field_bindings: {"activity": {"consumers": ["activity_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "answer_revealed_before_first_attempt": {"consumers": ["contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "assistance_level": {"consumers": ["activity_selection", "contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "attempts": {"consumers": ["activity_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "bound_verification_task_id": {"consumers": ["contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "carrier": {"consumers": ["activity_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "context_key": {"consumers": ["activity_selection", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "demonstrates": {"consumers": ["contract_recompute"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "elapsed_seconds": {"consumers": ["activity_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "explanation_quality": {"consumers": ["contract_recompute"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "hint_count": {"consumers": ["activity_selection", "contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "immediate_performance": {"consumers": ["activity_selection", "boundary_update", "contract_recompute"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "independence": {"consumers": ["activity_selection", "contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "mastery_eligible": {"consumers": ["derived_assertion_guard"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "near_transfer": {"consumers": ["activity_selection", "contract_recompute"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "observation_confidence": {"consumers": ["activity_selection", "boundary_update"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "observed_at": {"consumers": ["activity_selection", "boundary_update", "contract_recompute", "recovery"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "response_correct": {"consumers": ["activity_selection", "boundary_update", "contract_recompute"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "result": {"consumers": ["activity_selection", "boundary_update", "contract_recompute"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "route_id_at_observation": {"consumers": ["activity_selection", "contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "route_version_at_observation": {"consumers": ["activity_selection", "contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "self_reported_effort": {"consumers": ["activity_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "teaching_item_id": {"consumers": ["contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "verification_item_id": {"consumers": ["contract_recompute", "event_identity_guard", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "verification_task_id": {"consumers": ["contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}, "verification_unseen": {"consumers": ["contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-function", "contract_id": "mc-python-function-baseline", "contract_version": 1}, "observed_at": "2026-08-19T06:00:00Z", "validity": "valid"}}
observation_confidence: "high"
observation_confidence_basis: "qualified_independent_behavior"
---

# 证据：kc-python-function / independent_performance

独立定义并调用函数，能解释参数和返回值。

## Relations

- about: [[kc-python-function]]
- derived_from: [[ses-demo-a17-20260826t063000z]]
