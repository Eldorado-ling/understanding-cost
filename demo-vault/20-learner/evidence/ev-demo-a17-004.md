---
schema: "uc-demo/0.2"
id: "ev-demo-a17-004"
type: "evidence"
title: "证据：kc-python-recursion / diagnostic_probe"
learner_id: "demo-a17"
concept_id: "kc-python-recursion"
goal_id: "goal-demo-a17-recursion"
contract_id: "mc-python-recursion"
contract_version: 1
phase: "diagnostic"
carrier: "text_dialogue"
teaching_item_id: "probe-python-recursion-order-v1"
teaching_delivery_fingerprint_at_observation: null
verification_item_id: null
verification_unseen: false
answer_revealed_before_first_attempt: false
verification_task_id: null
bound_verification_task_id: null
route_id_at_observation: "route-demo-a17-recursion"
route_version_at_observation: 1
decision_fingerprint_at_observation: null
consumer_ids: ["boundary_update", "diagnostic_gate", "diagnostic_trace", "event_identity_guard"]
source_ref_ids: ["assets/demo-seed.json"]
observation_validity: "valid"
mastery_eligible: false
evidence_kind: "diagnostic_probe"
demonstrates: ["prediction"]
result: "fail"
independence: "independent"
assistance_level: "A0"
activity: "predict_explain"
error_signature: null
context_key: "domain=python|knowledge_kind=causal_structure|target_performance=predict|prior_band=none|task_difficulty=low"
route_binding_id: "rb-demo-a17-recursion-diagnostic-v1"
elapsed_seconds: 210
attempts: 1
hint_count: 0
immediate_performance: 0.3
near_transfer: "not_tested"
delayed_retention: "not_tested"
response_correct: false
explanation_quality: "fail"
self_reported_effort: 6
retention_delay_days: 0
baseline_evidence_id: null
retention_task_id: null
scheduled_for: null
source_kind: "synthetic_demo"
observed_at: "2026-08-26T06:30:00Z"
created_at: "2026-08-28T03:24:07Z"
updated_at: "2026-08-28T03:24:07Z"
privacy: "sensitive"
tags: ["uc/evidence"]
field_bindings: {"activity": {"consumers": ["diagnostic_gate", "diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "answer_revealed_before_first_attempt": {"consumers": ["diagnostic_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "assistance_level": {"consumers": ["diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "attempts": {"consumers": ["diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "carrier": {"consumers": ["diagnostic_gate", "diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "context_key": {"consumers": ["diagnostic_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "demonstrates": {"consumers": ["diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "elapsed_seconds": {"consumers": ["diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "explanation_quality": {"consumers": ["diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "hint_count": {"consumers": ["diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "immediate_performance": {"consumers": ["boundary_update", "diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "independence": {"consumers": ["diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "mastery_eligible": {"consumers": ["diagnostic_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "observation_confidence": {"consumers": ["boundary_update", "diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "observed_at": {"consumers": ["boundary_update", "diagnostic_gate", "diagnostic_trace", "event_identity_guard"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "response_correct": {"consumers": ["boundary_update", "diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "result": {"consumers": ["boundary_update", "diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "route_id_at_observation": {"consumers": ["diagnostic_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "route_version_at_observation": {"consumers": ["diagnostic_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "self_reported_effort": {"consumers": ["diagnostic_trace"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "teaching_item_id": {"consumers": ["diagnostic_gate", "diagnostic_trace", "event_identity_guard"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}, "verification_unseen": {"consumers": ["diagnostic_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-recursion", "contract_id": "mc-python-recursion", "contract_version": 1}, "observed_at": "2026-08-26T06:30:00Z", "validity": "valid"}}
observation_confidence: "medium"
observation_confidence_basis: "observed_process_or_diagnostic_behavior"
---

# 证据：kc-python-recursion / diagnostic_probe

未能独立预测递归展开顺序；因此记录 none，而非根据熟悉感推断掌握。

## Relations

- about: [[kc-python-recursion]]
- derived_from: [[ses-demo-a17-20260826t063000z]]
