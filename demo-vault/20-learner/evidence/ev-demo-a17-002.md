---
schema: "uc-demo/0.2"
id: "ev-demo-a17-002"
type: "evidence"
title: "证据：kc-python-iteration / delayed_transfer"
learner_id: "demo-a17"
concept_id: "kc-python-iteration"
goal_id: "goal-demo-a17-recursion"
contract_id: "mc-python-iteration-baseline"
contract_version: 1
phase: "retention"
carrier: "text_dialogue"
teaching_item_id: "teach-python-iteration-contrast-v1"
teaching_delivery_fingerprint_at_observation: null
verification_item_id: "retain-python-iteration-unseen-v1"
verification_unseen: true
answer_revealed_before_first_attempt: false
verification_task_id: "retain-python-iteration-unseen-v1"
bound_verification_task_id: "retain-python-iteration-unseen-v1"
route_id_at_observation: "route-python-iteration-retention-v1"
route_version_at_observation: 1
decision_fingerprint_at_observation: null
consumer_ids: ["activity_selection", "boundary_update", "contract_recompute", "derived_assertion_guard", "event_identity_guard", "recovery", "retention_recompute", "verification_gate"]
source_ref_ids: ["assets/demo-seed.json"]
observation_validity: "valid"
mastery_eligible: true
evidence_kind: "delayed_transfer"
demonstrates: ["delayed_retention"]
result: "pass"
independence: "independent"
assistance_level: "A0"
activity: "retrieval_prompt"
error_signature: null
context_key: "domain=python|knowledge_kind=causal_structure|target_performance=explain|prior_band=partial|task_difficulty=medium"
route_binding_id: "rb-demo-a17-iteration-retention-v1"
elapsed_seconds: 360
attempts: 1
hint_count: 0
immediate_performance: 0.82
near_transfer: "not_tested"
delayed_retention: 0.82
response_correct: true
explanation_quality: "not_tested"
self_reported_effort: 3
retention_delay_days: 7
baseline_evidence_id: "ev-demo-a17-002-baseline"
retention_task_id: "retain-python-iteration-unseen-v1"
scheduled_for: "2026-08-26T06:10:00Z"
source_kind: "synthetic_demo"
observed_at: "2026-08-26T06:10:00Z"
created_at: "2026-08-28T03:24:07Z"
updated_at: "2026-08-28T03:24:07Z"
privacy: "sensitive"
tags: ["uc/evidence"]
field_bindings: {"activity": {"consumers": ["activity_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "answer_revealed_before_first_attempt": {"consumers": ["contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "assistance_level": {"consumers": ["activity_selection", "contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "attempts": {"consumers": ["activity_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "baseline_evidence_id": {"consumers": ["contract_recompute", "retention_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "bound_verification_task_id": {"consumers": ["contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "carrier": {"consumers": ["activity_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "context_key": {"consumers": ["activity_selection", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "delayed_retention": {"consumers": ["activity_selection", "contract_recompute", "retention_recompute"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "demonstrates": {"consumers": ["contract_recompute", "retention_recompute"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "elapsed_seconds": {"consumers": ["activity_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "hint_count": {"consumers": ["activity_selection", "contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "immediate_performance": {"consumers": ["activity_selection", "boundary_update", "contract_recompute"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "independence": {"consumers": ["activity_selection", "contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "mastery_eligible": {"consumers": ["derived_assertion_guard"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "observation_confidence": {"consumers": ["activity_selection", "boundary_update"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "observed_at": {"consumers": ["activity_selection", "boundary_update", "contract_recompute", "recovery", "retention_recompute"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "response_correct": {"consumers": ["activity_selection", "boundary_update", "contract_recompute"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "result": {"consumers": ["activity_selection", "boundary_update", "contract_recompute", "retention_recompute"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "retention_delay_days": {"consumers": ["derived_assertion_guard"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "retention_task_id": {"consumers": ["contract_recompute", "recovery", "retention_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "route_id_at_observation": {"consumers": ["activity_selection", "contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "route_version_at_observation": {"consumers": ["activity_selection", "contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "scheduled_for": {"consumers": ["contract_recompute", "recovery", "retention_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "self_reported_effort": {"consumers": ["activity_selection"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "teaching_item_id": {"consumers": ["contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "verification_item_id": {"consumers": ["contract_recompute", "event_identity_guard", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "verification_task_id": {"consumers": ["contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}, "verification_unseen": {"consumers": ["contract_recompute", "verification_gate"], "source_ref_ids": ["assets/demo-seed.json"], "scope": {"learner_id": "demo-a17", "goal_id": "goal-demo-a17-recursion", "concept_id": "kc-python-iteration", "contract_id": "mc-python-iteration-baseline", "contract_version": 1}, "observed_at": "2026-08-26T06:10:00Z", "validity": "valid"}}
observation_confidence: "high"
observation_confidence_basis: "qualified_independent_behavior"
---

# 证据：kc-python-iteration / delayed_transfer

在基线验证七个完整日后独立完成另一道未见变式。

## Relations

- about: [[kc-python-iteration]]
- derived_from: [[ses-demo-a17-20260826t063000z]]
