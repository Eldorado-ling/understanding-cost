#!/usr/bin/env python3
"""Deterministic text-first teaching policy for the Understanding Cost Demo."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from math import isfinite
import re
from typing import Any
import unicodedata


TEXT_PROTOCOL_VERSION = "text-demo-v0.5"
RESPONSE_OBSERVATION_SCHEMA_VERSION = "response-observation-v1"
VERIFICATION_CONTENT_GUARD_SCHEMA_VERSION = "verification-content-guard-v1"
VERIFICATION_GUARD_NORMALIZATION = "unicode_nfkc_casefold_alnum_v1"
VERIFICATION_GUARD_NGRAM_SIZE = 8
VERIFICATION_GUARD_PROMPT_MIN_MATCHES = 2
VERIFICATION_GUARD_PROMPT_OVERLAP_RATIO = 0.35
VERIFICATION_GUARD_ANSWER_MIN_MATCHES = 1
VERIFICATION_GUARD_ANSWER_OVERLAP_RATIO = 0.25
REQUIRED_SCOPE_KEYS = (
    "learner_id",
    "goal_id",
    "concept_id",
    "contract_id",
    "contract_version",
)
TARGET_PERFORMANCE = {
    "recall",
    "explain",
    "discriminate",
    "predict",
    "execute",
    "diagnose",
    "transfer",
}
KNOWLEDGE_KINDS = {
    "declarative",
    "rule",
    "causal_structure",
    "symbolic_procedure",
    "diagnosis",
    "transfer",
    "motor_spatial",
}
TEXT_CARRIERS = {"text_document", "text_dialogue", "text_hybrid"}
NON_TEXT_CARRIERS = {"video", "interactive"}
CARRIERS = TEXT_CARRIERS | NON_TEXT_CARRIERS
TASK_DIFFICULTIES = {"low", "medium", "high"}
STATIC_VISUAL_KIND_BY_REASON = {
    "ownership_or_spatial_relation": "annotated_diagram",
    "multi_object_mapping": "annotated_diagram",
    "multi_state_comparison": "comparison_image",
    "interface_or_shape_judgment": "annotated_screenshot",
    "learner_reported_relational_complexity": "annotated_diagram",
}
ASSISTANCE_ORDER = {"A0": 0, "A1": 1, "A2": 2, "A3": 3, "A4": 4}
HARD_NON_TEXT_REASONS = {
    "continuous_motion_is_target",
    "spatial_temporal_change_required",
    "real_time_feedback_required",
    "accessibility_conflict",
    "user_explicit_medium_constraint",
}
AFFORDANCE_REASONS = {
    "video": {
        "continuous_motion_is_target",
        "spatial_temporal_change_required",
    },
    "interactive": {
        "real_time_feedback_required",
        "state_manipulation_required",
        "actual_execution_required",
    },
}
USER_DELIVERY_FIELDS = (
    "learning_objective",
    "method_label",
    "medium",
    "orientation",
    "term_grounding",
    "explanation",
    "example",
    "visual",
    "learner_task",
    "response_format",
    "feedback_rule",
    "verification_rule",
    "success_criteria",
    "next_step",
)
USER_FORBIDDEN_KEYS = {
    "activity_id",
    "assistance_level",
    "bound_verification_task_id",
    "comparison_gate",
    "cone_internal",
    "context_key",
    "consumer_ids",
    "concept_id",
    "concept_inventory",
    "contract_id",
    "contract_status",
    "contract_version",
    "debug_info",
    "cost_vector",
    "error_signature",
    "evidence_ref",
    "evidence_refs",
    "evidence_level",
    "focus_weights",
    "focus_z",
    "field_bindings",
    "goal_id",
    "goal_relevance",
    "input_confidence",
    "input_evidence_ids",
    "input_source_refs",
    "interest_evidence",
    "introduced_terms",
    "required_terms",
    "terms_to_ground",
    "learner_id",
    "mastery_eligible",
    "mastery_gate_derivation",
    "mastery_gate_met",
    "mastery_eligibility_failures",
    "next_step_id",
    "observation_confidence",
    "profile_actionability",
    "privacy",
    "probe_id",
    "ranking_status",
    "readiness",
    "reason_code",
    "reason_codes",
    "qualified_evidence_ids",
    "qualified_failure_evidence_ids",
    "qualified_observation_count",
    "response_profile_observations",
    "response_profile_refs",
    "route_id",
    "route_level",
    "route_version",
    "routing_action",
    "profile_selection",
    "pareto_status",
    "prepared_fields",
    "profile_selection_status",
    "profile_usage_status",
    "selection_consumer",
    "selection_basis",
    "selection_status",
    "scope",
    "schema_version",
    "source_context_key",
    "source_evidence_id",
    "source_refs",
    "snapshot_id",
    "state_id",
    "task_id",
    "time_scope",
    "trace_id",
    "user_visibility",
    "verification_task",
    "verification_task_id",
    "verification_content_guard",
    "teaching_basis",
    "verified_anchors",
    "verified_concept_ids",
    "focus_capabilities",
    "cost_inputs",
    "protected_content_fingerprints",
    "visual_support",
}
NEXT_STEP_SAFE_FIELDS = {"instruction", "when"}

DEFAULT_ACTIVITY: dict[str, tuple[str, str]] = {
    "recall": ("retrieval_prompt", "plain"),
    "discriminate": ("contrast_cases", "paired_cases"),
    "explain": ("predict_explain", "structured_steps"),
    "predict": ("predict_explain", "structured_steps"),
    "execute": ("worked_example_fading", "trace"),
    "diagnose": ("error_analysis", "trace"),
    "transfer": ("novel_case_application", "structured_steps"),
}
ACTIVITY_DEFAULT_FORMAT = {
    activity: text_format for activity, text_format in DEFAULT_ACTIVITY.values()
}
PROFILE_ACTIVITIES = set(ACTIVITY_DEFAULT_FORMAT)
TEXT_REPAIR_ORDER = {
    "predict_explain": ["contrast_cases", "worked_example_fading", "error_analysis"],
    "contrast_cases": ["predict_explain", "error_analysis", "worked_example_fading"],
    "retrieval_prompt": ["contrast_cases", "predict_explain", "worked_example_fading"],
    "worked_example_fading": ["predict_explain", "error_analysis", "contrast_cases"],
    "error_analysis": ["contrast_cases", "predict_explain", "worked_example_fading"],
    "novel_case_application": ["worked_example_fading", "contrast_cases", "predict_explain"],
}
PROFILE_ACTIVITY_SELECTION_FIELDS = {
    "activity",
    "carrier",
    "context_key",
    "observed_at",
    "observation_confidence",
    "immediate_performance",
    "elapsed_seconds",
    "attempts",
    "hint_count",
    "assistance_level",
}
PROFILE_SELECTION_STATUSES = {
    "no_observations",
    "no_qualified_observations",
    "insufficient_alternatives",
    "pareto_ambiguous",
    "tentative_exploration",
    "pareto_selected",
}
PROFILE_USAGE_STATUSES = {
    "default_text_policy",
    "activity_only",
    "activity_and_carrier",
    "exploration_only_threshold",
    "blocked_by_profile_threshold",
    "blocked_by_prerequisite",
    "overridden_by_hard_constraint",
    "overridden_by_text_repair_gate",
    "not_applicable_delivery_intent",
    "rejected_missing_affordance",
}

# Every persisted observation field has a finite, phase-specific downstream.
# These tables intentionally mirror vault_tool.py; the global map is vocabulary
# only and is never a phase fallback.
EVIDENCE_KIND_BY_PHASE: dict[str, set[str]] = {
    "diagnostic": {"diagnostic_probe"},
    "teaching_process": {"explanation", "prediction", "application", "teaching_attempt"},
    "verification": {"independent_performance"},
    "retention": {"delayed_transfer"},
}
_COMMON_EVIDENCE_ENVELOPE_GUARDS: dict[str, set[str]] = {
    "phase": {"phase_schema_guard"},
    "evidence_kind": {"phase_schema_guard"},
    "learner_id": {"scope_guard"},
    "goal_id": {"scope_guard"},
    "concept_id": {"scope_guard"},
    "contract_id": {"scope_guard"},
    "contract_version": {"scope_guard"},
    "source_kind": {"source_provenance_guard"},
    "source_ref_ids": {"source_provenance_guard"},
    "observation_validity": {"observation_validity_guard"},
}
EVIDENCE_ENVELOPE_GUARDS_BY_PHASE: dict[str, dict[str, set[str]]] = {
    "diagnostic": {
        **_COMMON_EVIDENCE_ENVELOPE_GUARDS,
        "route_binding_id": {"route_binding_guard", "diagnostic_gate"},
    },
    "teaching_process": {
        **_COMMON_EVIDENCE_ENVELOPE_GUARDS,
        "route_binding_id": {"route_binding_guard", "teaching_delivery_guard"},
    },
    "verification": {
        **_COMMON_EVIDENCE_ENVELOPE_GUARDS,
        "route_binding_id": {"route_binding_guard", "verification_gate"},
    },
    "retention": {
        **_COMMON_EVIDENCE_ENVELOPE_GUARDS,
        "route_binding_id": {
            "route_binding_guard",
            "verification_gate",
            "retention_recompute",
        },
    },
}
DIAGNOSTIC_FIELD_CONSUMER_ALLOWLIST: dict[str, set[str]] = {
    "activity": {"diagnostic_gate", "diagnostic_trace"},
    "carrier": {"diagnostic_gate", "diagnostic_trace"},
    "context_key": {"diagnostic_gate"},
    "teaching_item_id": {"diagnostic_gate", "diagnostic_trace", "event_identity_guard"},
    "route_id_at_observation": {"diagnostic_gate"},
    "route_version_at_observation": {"diagnostic_gate"},
    "verification_unseen": {"diagnostic_gate"},
    "answer_revealed_before_first_attempt": {"diagnostic_gate"},
    "result": {"boundary_update", "diagnostic_trace"},
    "demonstrates": {"diagnostic_trace"},
    "independence": {"diagnostic_trace"},
    "response_correct": {"boundary_update", "diagnostic_trace"},
    "immediate_performance": {"boundary_update", "diagnostic_trace"},
    "explanation_quality": {"diagnostic_trace"},
    "elapsed_seconds": {"diagnostic_trace"},
    "attempts": {"diagnostic_trace"},
    "hint_count": {"diagnostic_trace"},
    "assistance_level": {"diagnostic_trace"},
    "self_reported_effort": {"diagnostic_trace"},
    "observation_confidence": {"boundary_update", "diagnostic_trace"},
    "error_signature": {"boundary_update", "diagnostic_trace"},
    "mastery_eligible": {"diagnostic_gate"},
    "observed_at": {"diagnostic_gate", "boundary_update", "diagnostic_trace", "event_identity_guard"},
}
TEACHING_PROCESS_FIELD_CONSUMER_ALLOWLIST: dict[str, set[str]] = {
    "activity": {"activity_selection", "representation_selection", "feedback_selection", "teaching_delivery_guard"},
    "carrier": {"activity_selection", "representation_selection", "feedback_selection", "teaching_delivery_guard"},
    "context_key": {"verification_gate", "teaching_delivery_guard"},
    "teaching_item_id": {"process_trace", "teaching_delivery_guard"},
    "teaching_delivery_fingerprint_at_observation": {"teaching_delivery_guard"},
    "verification_task_id": {"verification_gate"},
    "bound_verification_task_id": {"verification_gate"},
    "route_id_at_observation": {"verification_gate", "teaching_delivery_guard"},
    "route_version_at_observation": {"verification_gate", "teaching_delivery_guard"},
    "decision_fingerprint_at_observation": {"verification_gate", "teaching_delivery_guard"},
    "verification_unseen": {"verification_gate"},
    "answer_revealed_before_first_attempt": {"verification_gate"},
    "result": {"verification_gate", "representation_selection", "feedback_selection"},
    "demonstrates": {"verification_gate", "representation_selection", "feedback_selection"},
    "response_correct": {"verification_gate", "representation_selection", "feedback_selection"},
    "immediate_performance": {"feedback_selection"},
    "explanation_quality": {"verification_gate", "representation_selection", "feedback_selection"},
    "elapsed_seconds": {"activity_selection"},
    "attempts": {"feedback_selection"},
    "hint_count": {"feedback_selection"},
    "assistance_level": {"activity_selection", "representation_selection"},
    "self_reported_effort": {"feedback_selection"},
    "error_signature": {"representation_selection", "feedback_selection"},
    "observation_confidence": {"process_evidence_gate", "representation_selection"},
    "mastery_eligible": {"verification_gate"},
    "observed_at": {"verification_gate", "feedback_selection", "activity_selection", "representation_selection", "teaching_delivery_guard", "event_identity_guard"},
}
VERIFICATION_FIELD_CONSUMER_ALLOWLIST: dict[str, set[str]] = {
    "activity": {"activity_selection"},
    "carrier": {"activity_selection"},
    "context_key": {"activity_selection", "verification_gate"},
    "teaching_item_id": {"verification_gate", "contract_recompute"},
    "verification_item_id": {"verification_gate", "contract_recompute", "event_identity_guard"},
    "verification_task_id": {"verification_gate", "contract_recompute"},
    "bound_verification_task_id": {"verification_gate", "contract_recompute"},
    "route_id_at_observation": {"verification_gate", "contract_recompute", "activity_selection"},
    "route_version_at_observation": {"verification_gate", "contract_recompute", "activity_selection"},
    "verification_unseen": {"verification_gate", "contract_recompute"},
    "answer_revealed_before_first_attempt": {"verification_gate", "contract_recompute"},
    "result": {"contract_recompute", "activity_selection", "boundary_update"},
    "demonstrates": {"contract_recompute"},
    "independence": {"verification_gate", "contract_recompute", "activity_selection"},
    "response_correct": {"contract_recompute", "activity_selection", "boundary_update"},
    "immediate_performance": {"contract_recompute", "activity_selection", "boundary_update"},
    "explanation_quality": {"contract_recompute"},
    "near_transfer": {"contract_recompute", "activity_selection"},
    "elapsed_seconds": {"activity_selection"},
    "attempts": {"activity_selection"},
    "hint_count": {"verification_gate", "contract_recompute", "activity_selection"},
    "assistance_level": {"verification_gate", "contract_recompute", "activity_selection"},
    "self_reported_effort": {"activity_selection"},
    "observation_confidence": {"activity_selection", "boundary_update"},
    "error_signature": {"boundary_update"},
    "mastery_eligible": {"derived_assertion_guard"},
    "observed_at": {"contract_recompute", "recovery", "activity_selection", "boundary_update"},
}
RETENTION_FIELD_CONSUMER_ALLOWLIST: dict[str, set[str]] = {
    **VERIFICATION_FIELD_CONSUMER_ALLOWLIST,
    "result": {"contract_recompute", "retention_recompute", "activity_selection", "boundary_update"},
    "demonstrates": {"contract_recompute", "retention_recompute"},
    "explanation_quality": set(),
    "near_transfer": set(),
    "delayed_retention": {"contract_recompute", "retention_recompute", "activity_selection"},
    "retention_delay_days": {"derived_assertion_guard"},
    "baseline_evidence_id": {"verification_gate", "contract_recompute", "retention_recompute"},
    "retention_task_id": {"verification_gate", "contract_recompute", "retention_recompute", "recovery"},
    "scheduled_for": {"verification_gate", "contract_recompute", "retention_recompute", "recovery"},
    "mastery_eligible": {"derived_assertion_guard"},
    "observed_at": {"contract_recompute", "retention_recompute", "recovery", "activity_selection", "boundary_update"},
}
PHASE_VAULT_FIELD_CONSUMERS = {
    "diagnostic": DIAGNOSTIC_FIELD_CONSUMER_ALLOWLIST,
    "teaching_process": TEACHING_PROCESS_FIELD_CONSUMER_ALLOWLIST,
    "verification": VERIFICATION_FIELD_CONSUMER_ALLOWLIST,
    "retention": RETENTION_FIELD_CONSUMER_ALLOWLIST,
}
VAULT_EVIDENCE_FIELD_NAMES = set().union(
    *(set(value) for value in PHASE_VAULT_FIELD_CONSUMERS.values())
)
VAULT_EVIDENCE_FIELD_CONSUMERS = {
    field: set().union(
        *(value.get(field, set()) for value in PHASE_VAULT_FIELD_CONSUMERS.values())
    )
    for field in VAULT_EVIDENCE_FIELD_NAMES
}
FIELD_CONSUMER_ALLOWLIST: dict[str, set[str]] = {
    **VAULT_EVIDENCE_FIELD_CONSUMERS,
    "learner_response_present": {"verification_gate"},
    "verification_assistance_level": {"verification_gate", "contract_recompute", "activity_selection"},
}
MEDIUM_LABELS = {
    "text_document": "文字文件",
    "text_dialogue": "文字对话",
    "text_hybrid": "文字文件＋对话",
    "video": "视频",
    "interactive": "交互",
}
TEXT_WITH_VISUAL_LABELS = {
    "text_document": "文字文件＋静态图示",
    "text_dialogue": "文字对话＋静态图示",
    "text_hybrid": "文字文件＋静态图示＋对话",
}
PROCESS_FEEDBACK_PUBLIC = {
    "ready_for_verification": "只确认本单元已达到进入独立验证的条件，不追加答案提示。",
    "repair_required": "只指出当前错误及其直接原因，不给完整答案；随后让学习者用新的文字方式再做一次。",
    "escalation_candidate": "先核对重复错误与已尝试的文字方式；只有媒介可供性匹配时才升级。",
}
PROCESS_NEXT_STEP_PUBLIC = {
    "ready_for_verification": "进入未见独立验证。",
    "repair_required": "先完成当前错误的最小修复，再做一个同目标的新练习。",
    "escalation_candidate": "复核媒介升级闸门；未满足时继续最小文字修复。",
}
PROCESS_FEEDBACK_RULE_PUBLIC = {
    "confirm_then_open_unseen_verification": "只确认本单元已达到进入独立验证的条件，不追加答案提示。",
    "correct_only_current_error_then_retry": "只指出当前错误及其直接原因，不给完整答案；随后让学习者用新的文字方式再做一次。",
    "reduce_information_then_correct_current_error": "先减少一次呈现的信息量，只纠正当前错误，再让学习者用更短的文字练习重做。",
    "evaluate_text_failure_escalation_gate": "先核对重复错误、实际帮助等级与已尝试的文字方式；只有媒介可供性匹配时才升级。",
}
PROCESS_NEXT_ACTION_PUBLIC = {
    "open_unseen_verification": "进入未见独立验证。",
    "text_repair": "先完成当前错误的最小修复，再做一个同目标的新练习。",
    "shorter_text_repair": "改用更短、负担更低的文字修复活动，再做一个同目标的新练习。",
    "evaluate_escalation_gate": "复核媒介升级闸门；未满足时继续最小文字修复。",
}
BEHAVIOR_SOURCE_KINDS = {
    "behavior_observation",
    "tool_observation",
}


def _mastery_source_is_authorized(
    evidence: dict[str, Any], *, allow_trusted_synthetic_demo: bool = False
) -> bool:
    source_kind = evidence.get("source_kind")
    return bool(
        source_kind in BEHAVIOR_SOURCE_KINDS
        or (allow_trusted_synthetic_demo and source_kind == "synthetic_demo")
    )


class TextPolicyError(ValueError):
    """Raised when the policy input would force an ambiguous or unsafe decision."""


def _enum(name: str, value: Any, allowed: set[str]) -> str:
    if value not in allowed:
        raise TextPolicyError(f"{name} 非法: {value!r}")
    return str(value)


def _nonempty_string(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TextPolicyError(f"{name} 必须是非空字符串")
    return value.strip()


def _unique_string_list(name: str, value: Any) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise TextPolicyError(f"{name} 必须是字符串数组")
    cleaned = [item.strip() for item in value]
    if len({item.casefold() for item in cleaned}) != len(cleaned):
        raise TextPolicyError(f"{name} 不得包含重复项")
    return cleaned


def _number(
    name: str,
    value: Any,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TextPolicyError(f"{name} 必须是数值")
    result = float(value)
    if not isfinite(result):
        raise TextPolicyError(f"{name} 必须是有限数值")
    if minimum is not None and result < minimum:
        raise TextPolicyError(f"{name} 不得小于 {minimum}")
    if maximum is not None and result > maximum:
        raise TextPolicyError(f"{name} 不得大于 {maximum}")
    return result


def _integer(name: str, value: Any, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise TextPolicyError(f"{name} 必须是大于等于 {minimum} 的整数")
    return value


def _aware_timestamp(name: str, value: Any) -> str:
    text = _nonempty_string(name, value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TextPolicyError(f"{name} 必须是 ISO 8601 时间") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TextPolicyError(f"{name} 必须包含时区")
    normalized = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return normalized


def _validated_scope(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TextPolicyError(f"{name} 必须是作用域对象")
    scope: dict[str, Any] = {}
    for key in REQUIRED_SCOPE_KEYS[:-1]:
        scope[key] = _nonempty_string(f"{name}.{key}", value.get(key))
    scope["contract_version"] = _integer(
        f"{name}.contract_version", value.get("contract_version"), minimum=1
    )
    return scope


def _validated_comparison_context(name: str, value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise TextPolicyError(f"{name} 必须是比较情境对象")
    _exact_keys(
        name,
        value,
        {
            "domain",
            "knowledge_kind",
            "target_performance",
            "prior_band",
            "task_difficulty",
        },
    )
    domain = _nonempty_string(f"{name}.domain", value.get("domain")).casefold()
    if "|" in domain or "=" in domain:
        raise TextPolicyError(f"{name}.domain 不得包含 | 或 =")
    return {
        "domain": domain,
        "knowledge_kind": _enum(
            f"{name}.knowledge_kind", value.get("knowledge_kind"), KNOWLEDGE_KINDS
        ),
        "target_performance": _enum(
            f"{name}.target_performance",
            value.get("target_performance"),
            TARGET_PERFORMANCE,
        ),
        "prior_band": _enum(
            f"{name}.prior_band",
            value.get("prior_band"),
            {"unknown", "none", "partial", "mastered"},
        ),
        "task_difficulty": _enum(
            f"{name}.task_difficulty",
            value.get("task_difficulty"),
            TASK_DIFFICULTIES,
        ),
    }


def _comparison_context_key(context: dict[str, str]) -> str:
    return "|".join(
        f"{field}={context[field]}"
        for field in (
            "domain",
            "knowledge_kind",
            "target_performance",
            "prior_band",
            "task_difficulty",
        )
    )


def _validated_comparison_gate(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TextPolicyError(f"{name} 必须是比较门对象")
    _exact_keys(name, value, {"retention_required", "task_difficulty"})
    if not isinstance(value.get("retention_required"), bool):
        raise TextPolicyError(f"{name}.retention_required 必须是布尔值")
    return {
        "retention_required": value["retention_required"],
        "task_difficulty": _enum(
            f"{name}.task_difficulty",
            value.get("task_difficulty"),
            TASK_DIFFICULTIES,
        ),
    }


def _optional_profile_metric(
    name: str,
    value: Any,
    *,
    minimum: float,
    maximum: float,
    markers: set[str],
) -> float | str:
    if isinstance(value, str) and value in markers:
        return value
    return _number(name, value, minimum=minimum, maximum=maximum)


def _exact_keys(name: str, value: dict[str, Any], expected: set[str]) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise TextPolicyError(f"{name} schema 不匹配: missing={missing}, extra={extra}")


def _verification_guard_normalize(value: str) -> str:
    """Canonicalize protected/user-visible text without retaining its raw form."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _verification_guard_hash(kind: str, unit: str, value: str) -> str:
    payload = (
        f"{VERIFICATION_CONTENT_GUARD_SCHEMA_VERSION}|{kind}|{unit}|{value}"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _verification_guard_sentences(value: str) -> list[str]:
    sentences = [
        _verification_guard_normalize(part)
        for part in re.split(r"[\r\n.!?。！？；;]+", value)
    ]
    return list(dict.fromkeys(item for item in sentences if item))


def _verification_guard_ngrams(value: str, size: int) -> set[str]:
    if not value:
        return set()
    actual_size = min(size, len(value))
    return {
        value[index : index + actual_size]
        for index in range(len(value) - actual_size + 1)
    }


def _protected_guard_source(kind: str, value: str) -> dict[str, Any]:
    raw = _nonempty_string(f"protected_{kind}", value)
    normalized = _verification_guard_normalize(raw)
    if not normalized:
        raise TextPolicyError(f"protected_{kind} 规范化后为空")
    if kind == "answer" and len(normalized) < 2:
        raise TextPolicyError(
            "受保护答案过短；请提供至少两个规范化字符的完整答案短语，而不是单字符标签"
        )
    ngram_size = min(VERIFICATION_GUARD_NGRAM_SIZE, len(normalized))
    sentences = _verification_guard_sentences(raw)
    return {
        "kind": kind,
        "normalized_length": len(normalized),
        "ngram_size": ngram_size,
        "full_hash": _verification_guard_hash(kind, "full", normalized),
        "sentence_hashes": sorted(
            _verification_guard_hash(kind, "sentence", sentence)
            for sentence in sentences
        ),
        "ngram_hashes": sorted(
            _verification_guard_hash(kind, "ngram", ngram)
            for ngram in _verification_guard_ngrams(normalized, ngram_size)
        ),
    }


def build_verification_content_guard(
    task_id: str,
    protected_prompt: str | list[str],
    protected_answers: str | list[str],
) -> dict[str, Any]:
    """Build an opaque no-leak guard from a bound Vault verification resource.

    The returned object contains only deterministic hashes and fixed thresholds;
    it is internal decision data and must never be projected to the learner.
    """

    bound_task_id = _nonempty_string("verification guard task_id", task_id)
    prompts = (
        [protected_prompt] if isinstance(protected_prompt, str) else protected_prompt
    )
    answers = (
        [protected_answers]
        if isinstance(protected_answers, str)
        else protected_answers
    )
    if not isinstance(prompts, list) or not prompts:
        raise TextPolicyError("protected_prompt 必须是非空字符串或非空字符串数组")
    if not isinstance(answers, list) or not answers:
        raise TextPolicyError("protected_answers 必须是非空字符串或非空字符串数组")
    prompt_sources = [_protected_guard_source("prompt", item) for item in prompts]
    answer_sources = [_protected_guard_source("answer", item) for item in answers]
    return {
        "schema_version": VERIFICATION_CONTENT_GUARD_SCHEMA_VERSION,
        "task_id": bound_task_id,
        "normalization": VERIFICATION_GUARD_NORMALIZATION,
        "thresholds": {
            "prompt_min_ngram_matches": VERIFICATION_GUARD_PROMPT_MIN_MATCHES,
            "prompt_overlap_ratio": VERIFICATION_GUARD_PROMPT_OVERLAP_RATIO,
            "answer_min_ngram_matches": VERIFICATION_GUARD_ANSWER_MIN_MATCHES,
            "answer_overlap_ratio": VERIFICATION_GUARD_ANSWER_OVERLAP_RATIO,
        },
        "protected_content_fingerprints": {
            "prompt": prompt_sources,
            "answer": answer_sources,
        },
    }


def _validated_guard_hashes(name: str, value: Any) -> list[str]:
    hashes = _unique_string_list(name, value)
    if not hashes or any(
        len(item) != 64 or any(character not in "0123456789abcdef" for character in item)
        for item in hashes
    ):
        raise TextPolicyError(f"{name} 必须是非空 SHA-256 十六进制数组")
    return sorted(hashes)


def _validated_guard_source(name: str, value: Any, expected_kind: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TextPolicyError(f"{name} 必须是对象")
    _exact_keys(
        name,
        value,
        {
            "kind",
            "normalized_length",
            "ngram_size",
            "full_hash",
            "sentence_hashes",
            "ngram_hashes",
        },
    )
    if value.get("kind") != expected_kind:
        raise TextPolicyError(f"{name}.kind 与分组不一致")
    length = _integer(f"{name}.normalized_length", value.get("normalized_length"), minimum=1)
    if expected_kind == "answer" and length < 2:
        raise TextPolicyError(f"{name} 的答案指纹过短")
    ngram_size = _integer(f"{name}.ngram_size", value.get("ngram_size"), minimum=1)
    if ngram_size != min(VERIFICATION_GUARD_NGRAM_SIZE, length):
        raise TextPolicyError(f"{name}.ngram_size 不是固定策略派生值")
    full_hash = _nonempty_string(f"{name}.full_hash", value.get("full_hash"))
    if len(full_hash) != 64 or any(
        character not in "0123456789abcdef" for character in full_hash
    ):
        raise TextPolicyError(f"{name}.full_hash 不是 SHA-256 十六进制")
    sentence_hashes = _validated_guard_hashes(
        f"{name}.sentence_hashes", value.get("sentence_hashes")
    )
    ngram_hashes = _validated_guard_hashes(
        f"{name}.ngram_hashes", value.get("ngram_hashes")
    )
    return {
        "kind": expected_kind,
        "normalized_length": length,
        "ngram_size": ngram_size,
        "full_hash": full_hash,
        "sentence_hashes": sentence_hashes,
        "ngram_hashes": ngram_hashes,
    }


def _validated_verification_content_guard(
    name: str, value: Any, bound_task_id: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TextPolicyError(f"{name} 必须是 build_verification_content_guard 的输出")
    _exact_keys(
        name,
        value,
        {
            "schema_version",
            "task_id",
            "normalization",
            "thresholds",
            "protected_content_fingerprints",
        },
    )
    if value.get("schema_version") != VERIFICATION_CONTENT_GUARD_SCHEMA_VERSION:
        raise TextPolicyError(f"{name}.schema_version 非法")
    task_id = _nonempty_string(f"{name}.task_id", value.get("task_id"))
    if task_id != bound_task_id:
        raise TextPolicyError(f"{name}.task_id 与 bound_verification_task_id 不一致")
    if value.get("normalization") != VERIFICATION_GUARD_NORMALIZATION:
        raise TextPolicyError(f"{name}.normalization 非法")
    thresholds = value.get("thresholds")
    if not isinstance(thresholds, dict):
        raise TextPolicyError(f"{name}.thresholds 必须是对象")
    expected_thresholds = {
        "prompt_min_ngram_matches": VERIFICATION_GUARD_PROMPT_MIN_MATCHES,
        "prompt_overlap_ratio": VERIFICATION_GUARD_PROMPT_OVERLAP_RATIO,
        "answer_min_ngram_matches": VERIFICATION_GUARD_ANSWER_MIN_MATCHES,
        "answer_overlap_ratio": VERIFICATION_GUARD_ANSWER_OVERLAP_RATIO,
    }
    _exact_keys(f"{name}.thresholds", thresholds, set(expected_thresholds))
    if any(thresholds.get(key) != expected for key, expected in expected_thresholds.items()):
        raise TextPolicyError(f"{name}.thresholds 不得由调用者放宽")
    fingerprints = value.get("protected_content_fingerprints")
    if not isinstance(fingerprints, dict):
        raise TextPolicyError(f"{name}.protected_content_fingerprints 必须是对象")
    _exact_keys(f"{name}.protected_content_fingerprints", fingerprints, {"prompt", "answer"})
    normalized_groups: dict[str, list[dict[str, Any]]] = {}
    for kind in ("prompt", "answer"):
        sources = fingerprints.get(kind)
        if not isinstance(sources, list) or not sources:
            raise TextPolicyError(f"{name}.protected_content_fingerprints.{kind} 不得为空")
        normalized_groups[kind] = [
            _validated_guard_source(
                f"{name}.protected_content_fingerprints.{kind}[{index}]",
                source,
                kind,
            )
            for index, source in enumerate(sources)
        ]
    return {
        "schema_version": VERIFICATION_CONTENT_GUARD_SCHEMA_VERSION,
        "task_id": task_id,
        "normalization": VERIFICATION_GUARD_NORMALIZATION,
        "thresholds": dict(expected_thresholds),
        "protected_content_fingerprints": normalized_groups,
    }


def _iter_user_visible_strings(value: Any, path: str = "delivery_plan"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _iter_user_visible_strings(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_user_visible_strings(item, f"{path}.{key}")


def _guard_source_overlaps_visible_text(
    source: dict[str, Any], visible_text: str, thresholds: dict[str, Any]
) -> bool:
    kind = source["kind"]
    normalized = _verification_guard_normalize(visible_text)
    if not normalized:
        return False
    source_length = source["normalized_length"]
    if len(normalized) >= source_length:
        for index in range(len(normalized) - source_length + 1):
            candidate = normalized[index : index + source_length]
            if _verification_guard_hash(kind, "full", candidate) == source["full_hash"]:
                return True
    visible_sentence_hashes = {
        _verification_guard_hash(kind, "sentence", sentence)
        for sentence in _verification_guard_sentences(visible_text)
    }
    if visible_sentence_hashes.intersection(source["sentence_hashes"]):
        return True
    visible_ngram_hashes = {
        _verification_guard_hash(kind, "ngram", ngram)
        for ngram in _verification_guard_ngrams(normalized, source["ngram_size"])
    }
    source_ngram_hashes = set(source["ngram_hashes"])
    matches = len(visible_ngram_hashes.intersection(source_ngram_hashes))
    denominator = min(len(visible_ngram_hashes), len(source_ngram_hashes))
    if denominator == 0:
        return False
    minimum_matches = thresholds[f"{kind}_min_ngram_matches"]
    overlap_ratio = thresholds[f"{kind}_overlap_ratio"]
    return matches >= minimum_matches and matches / denominator >= overlap_ratio


def _assert_no_reserved_verification_overlap(
    user_payload: dict[str, Any], guard: dict[str, Any]
) -> None:
    fingerprints = guard["protected_content_fingerprints"]
    thresholds = guard["thresholds"]
    visible_items = list(_iter_user_visible_strings(user_payload))
    for path, visible_text in visible_items:
        for kind in ("prompt", "answer"):
            if any(
                _guard_source_overlaps_visible_text(source, visible_text, thresholds)
                for source in fingerprints[kind]
            ):
                raise TextPolicyError(
                    f"初始 delivery_plan 的 {path} 与保留的未见验证{kind}内容重叠；请改写教学内容或更换验证任务"
                )
    # A protected phrase split over neighbouring fields/array items is still
    # visible to the learner as one reading stream.  Per-field scanning alone
    # would miss fragments shorter than the source n-gram size, so scan the
    # deterministic projection order again after concatenation.
    combined_visible_text = "".join(text for _path, text in visible_items)
    for kind in ("prompt", "answer"):
        if any(
            _guard_source_overlaps_visible_text(
                source, combined_visible_text, thresholds
            )
            for source in fingerprints[kind]
        ):
            raise TextPolicyError(
                f"初始 delivery_plan 的组合阅读流与保留的未见验证{kind}内容重叠；请重建教学内容"
            )


def _assert_revealed_prompt_matches_guard(
    verification_prompt: str, guard: dict[str, Any]
) -> None:
    normalized = _verification_guard_normalize(verification_prompt)
    candidate_hash = _verification_guard_hash("prompt", "full", normalized)
    if not any(
        source["normalized_length"] == len(normalized)
        and source["full_hash"] == candidate_hash
        for source in guard["protected_content_fingerprints"]["prompt"]
    ):
        raise TextPolicyError("公开验证题与当前绑定任务的 verification content guard 不一致")


def _validate_vault_evidence_envelope(
    label: str, evidence: dict[str, Any]
) -> str:
    """Validate record identity/provenance before reading outcome bindings."""

    if not isinstance(evidence, dict):
        raise TextPolicyError(f"{label} 必须是对象")
    phase = _enum(
        f"{label}.phase", evidence.get("phase"), set(EVIDENCE_ENVELOPE_GUARDS_BY_PHASE)
    )
    envelope_contract = EVIDENCE_ENVELOPE_GUARDS_BY_PHASE[phase]
    missing = sorted(field for field in envelope_contract if field not in evidence)
    if missing:
        raise TextPolicyError(f"{label} 缺少 evidence envelope 字段: {missing}")
    _validated_scope(f"{label}.scope", evidence)
    _nonempty_string(f"{label}.source_kind", evidence.get("source_kind"))
    source_refs = _unique_string_list(
        f"{label}.source_ref_ids", evidence.get("source_ref_ids")
    )
    if not source_refs:
        raise TextPolicyError(f"{label}.source_ref_ids 不得为空")
    _enum(
        f"{label}.observation_validity",
        evidence.get("observation_validity"),
        {"valid", "provisional", "stale"},
    )
    _nonempty_string(f"{label}.route_binding_id", evidence.get("route_binding_id"))
    _enum(
        f"{label}.evidence_kind",
        evidence.get("evidence_kind"),
        EVIDENCE_KIND_BY_PHASE[phase],
    )
    return phase


def _validate_vault_field_bindings(
    evidence: dict[str, Any],
    scope: dict[str, Any],
    source_refs: list[str],
    observed_at: str,
    validity: str,
) -> dict[str, set[str]]:
    """Validate every persisted field-level provenance/consumer contract we read."""

    field_bindings = evidence.get("field_bindings")
    if not isinstance(field_bindings, dict):
        raise TextPolicyError("vault_evidence.field_bindings 必须是对象")
    note_consumers = _unique_string_list(
        "vault_evidence.consumer_ids", evidence.get("consumer_ids")
    )
    if not note_consumers:
        raise TextPolicyError("vault_evidence.consumer_ids 不得为空")
    note_consumer_set = set(note_consumers)
    phase = evidence.get("phase")

    def allowed_for_phase(field: str) -> set[str]:
        phase_map = PHASE_VAULT_FIELD_CONSUMERS.get(str(phase))
        return phase_map.get(field, set()) if phase_map is not None else set()

    real_downstreams = set().union(
        *(allowed_for_phase(field) for field in VAULT_EVIDENCE_FIELD_CONSUMERS)
    )

    def actionable(field: str) -> bool:
        if field not in evidence or evidence.get(field) is None:
            return False
        if field in {"delayed_retention", "retention_delay_days"} and evidence.get(
            "phase"
        ) != "retention":
            return False
        if field in {
            "near_transfer",
            "delayed_retention",
            "self_reported_effort",
        } and evidence.get(field) in {
            "not_tested",
            "pending",
            "not_required",
            "not_collected",
        }:
            return False
        return True

    expected_binding_fields = {
        field
        for field in VAULT_EVIDENCE_FIELD_CONSUMERS
        if actionable(field)
        and allowed_for_phase(field)
        and allowed_for_phase(field).intersection(note_consumer_set)
    }
    actual_binding_fields = set(field_bindings)
    missing = sorted(expected_binding_fields - actual_binding_fields)
    unexpected = sorted(actual_binding_fields - expected_binding_fields)
    if missing:
        raise TextPolicyError(f"vault_evidence.field_bindings 缺少字段: {missing}")
    if unexpected:
        raise TextPolicyError(
            f"vault_evidence.field_bindings 含无实际消费者字段: {unexpected}"
        )

    validated_bindings: dict[str, set[str]] = {}
    for field, binding in field_bindings.items():
        path = f"vault_evidence.field_bindings.{field}"
        if field not in VAULT_EVIDENCE_FIELD_CONSUMERS:
            raise TextPolicyError(f"{path} 没有对应的 FIELD_CONSUMER_ALLOWLIST")
        if field not in evidence:
            raise TextPolicyError(f"{path} 绑定了 evidence 中不存在的字段")
        if not isinstance(binding, dict):
            raise TextPolicyError(f"{path} 必须是对象")
        _exact_keys(
            path,
            binding,
            {"consumers", "source_ref_ids", "scope", "observed_at", "validity"},
        )
        consumers = _unique_string_list(f"{path}.consumers", binding.get("consumers"))
        if not consumers:
            raise TextPolicyError(f"{path}.consumers 不得为空")
        consumer_set = set(consumers)
        if not consumer_set.issubset(allowed_for_phase(field)):
            raise TextPolicyError(f"{path}.consumers 不属于该字段的允许集合")
        if not consumer_set.issubset(note_consumer_set):
            raise TextPolicyError(f"{path}.consumers 未绑定到 evidence.consumer_ids")
        if not consumer_set.intersection(real_downstreams):
            raise TextPolicyError(f"{path}.consumers 没有真实下游")
        binding_sources = _unique_string_list(
            f"{path}.source_ref_ids", binding.get("source_ref_ids")
        )
        if not binding_sources or binding_sources != source_refs:
            raise TextPolicyError(f"{path}.source_ref_ids 非法或与 evidence 来源不一致")
        if _validated_scope(f"{path}.scope", binding.get("scope")) != scope:
            raise TextPolicyError(f"{path}.scope 与 evidence 完整作用域不一致")
        if _aware_timestamp(f"{path}.observed_at", binding.get("observed_at")) != observed_at:
            raise TextPolicyError(f"{path}.observed_at 与 evidence 不一致")
        binding_validity = _enum(
            f"{path}.validity",
            binding.get("validity"),
            {"valid", "provisional", "stale"},
        )
        if binding_validity != validity:
            raise TextPolicyError(f"{path}.validity 与 evidence 不一致")
        validated_bindings[field] = consumer_set
    return validated_bindings


def _vault_mastery_eligibility(
    evidence: dict[str, Any],
    binding_consumers: dict[str, set[str]],
    *,
    allow_trusted_synthetic_demo: bool = False,
) -> tuple[bool, list[str]]:
    """Mirror the Vault raw verification gate instead of trusting its label."""

    failures: list[str] = []
    if not _mastery_source_is_authorized(
        evidence,
        allow_trusted_synthetic_demo=allow_trusted_synthetic_demo,
    ):
        failures.append("source_not_behavior")
    phase = evidence.get("phase")
    if phase not in {"verification", "retention"}:
        failures.append("phase_not_verification")
    teaching_item_id = evidence.get("teaching_item_id")
    verification_item_id = evidence.get("verification_item_id")
    if not isinstance(teaching_item_id, str) or not teaching_item_id.strip():
        failures.append("missing_teaching_item_id")
    if not isinstance(verification_item_id, str) or not verification_item_id.strip():
        failures.append("missing_verification_item_id")
    elif verification_item_id.strip() == str(teaching_item_id).strip():
        failures.append("verification_item_reused")
    if evidence.get("verification_unseen") is not True:
        failures.append("verification_not_unseen")
    if evidence.get("answer_revealed_before_first_attempt") is not False:
        failures.append("answer_revealed_early")
    verification_task_id = evidence.get("verification_task_id")
    bound_verification_task_id = evidence.get("bound_verification_task_id")
    if not isinstance(verification_task_id, str) or not verification_task_id.strip():
        failures.append("verification_task_unbound")
    elif (
        not isinstance(bound_verification_task_id, str)
        or not bound_verification_task_id.strip()
        or verification_task_id.strip() != bound_verification_task_id.strip()
    ):
        failures.append("verification_task_binding_mismatch")
    if not isinstance(evidence.get("route_id_at_observation"), str) or not str(
        evidence.get("route_id_at_observation")
    ).strip():
        failures.append("verification_route_unbound")
    route_version = evidence.get("route_version_at_observation")
    if (
        not isinstance(route_version, int)
        or isinstance(route_version, bool)
        or route_version < 1
    ):
        failures.append("verification_route_version_unbound")
    if (
        evidence.get("assistance_level") != "A0"
        or evidence.get("independence") != "independent"
    ):
        failures.append("verification_not_independent")
    if evidence.get("hint_count") != 0:
        failures.append("verification_has_hint")
    consumers = evidence.get("consumer_ids")
    consumer_set = (
        {item for item in consumers if isinstance(item, str)}
        if isinstance(consumers, list)
        else set()
    )
    if not {"verification_gate", "contract_recompute"}.issubset(consumer_set):
        failures.append("missing_mastery_consumers")
    # Field bindings were already checked against the exact phase map above.
    # Eligibility is recomputed from raw values; a stored derived label must not
    # become an additional authority or a circular gate.
    if evidence.get("observation_validity") != "valid":
        failures.append("observation_not_valid")
    if phase == "retention":
        for field in ("baseline_evidence_id", "retention_task_id", "scheduled_for"):
            if not isinstance(evidence.get(field), str) or not str(
                evidence.get(field)
            ).strip():
                failures.append(f"missing_{field}")
        if evidence.get("retention_task_id") != verification_task_id:
            failures.append("retention_task_binding_mismatch")
        if "retention_recompute" not in consumer_set:
            failures.append("missing_retention_consumer")
    return not failures, list(dict.fromkeys(failures))


def _prepared_values_for_scope(
    prepared_update: dict[str, Any] | None,
    scope: dict[str, Any],
    expected_phase: str,
) -> dict[str, Any]:
    """Read prepare_observation_update output without introducing another schema."""

    if prepared_update is None:
        return {}
    if not isinstance(prepared_update, dict):
        raise TextPolicyError("prepared_update 必须是 prepare_observation_update 的输出")
    if prepared_update.get("protocol_version") != TEXT_PROTOCOL_VERSION:
        raise TextPolicyError("prepared_update.protocol_version 不匹配")
    if prepared_update.get("commit_allowed") is not True:
        raise TextPolicyError("prepared_update 没有可提交字段")
    phase = _enum(
        "prepared_update.phase",
        prepared_update.get("phase"),
        set(PHASE_VAULT_FIELD_CONSUMERS),
    )
    if phase != expected_phase:
        raise TextPolicyError("prepared_update.phase 与 evidence.phase 不一致")
    phase_field_consumers = PHASE_VAULT_FIELD_CONSUMERS[phase]
    prepared_fields = prepared_update.get("prepared_fields")
    if not isinstance(prepared_fields, dict) or not prepared_fields:
        raise TextPolicyError("prepared_update.prepared_fields 为空或非法")
    values: dict[str, Any] = {}
    for field, binding in prepared_fields.items():
        if field not in FIELD_CONSUMER_ALLOWLIST or not isinstance(binding, dict):
            raise TextPolicyError(f"prepared_update 含非法字段: {field}")
        allowed_consumers = (
            phase_field_consumers.get(field, set())
            if field in VAULT_EVIDENCE_FIELD_NAMES
            else FIELD_CONSUMER_ALLOWLIST[field]
        )
        if not allowed_consumers:
            raise TextPolicyError(f"prepared_update 字段不属于该 phase: {field}")
        if _validated_scope(f"prepared_fields.{field}.scope", binding.get("scope")) != scope:
            raise TextPolicyError(f"prepared_fields.{field}.scope 与 evidence 不一致")
        consumers = _unique_string_list(
            f"prepared_fields.{field}.consumers", binding.get("consumers")
        )
        if not consumers or not set(consumers).issubset(allowed_consumers):
            raise TextPolicyError(f"prepared_fields.{field}.consumers 非法")
        values[field] = _normalized_observation_field(field, binding.get("value"))
    return values


def _build_response_observation_from_validated_vault_inputs(
    source_evidence_id: str,
    vault_evidence: dict[str, Any],
    contract: dict[str, Any],
    scoped_evidence: list[tuple[str, dict[str, Any]]],
    comparison_context: dict[str, Any],
    *,
    state_context: dict[str, Any] | None = None,
    as_of: Any | None = None,
    prepared_update: dict[str, Any] | None = None,
    _allow_trusted_synthetic_demo: bool = False,
) -> dict[str, Any]:
    """Low-level adapter for inputs already resolved by validated Vault code.

    This private primitive still recomputes the contract and rejects claimed
    status/qualified IDs, but it does not prove where raw objects came from.
    Production callers must use vault_tool.build_response_observation_from_vault().
    """

    evidence_id = _nonempty_string("source_evidence_id", source_evidence_id)
    if not isinstance(vault_evidence, dict):
        raise TextPolicyError("vault_evidence 必须是对象")
    record_evidence_id = _nonempty_string("vault_evidence.id", vault_evidence.get("id"))
    if record_evidence_id != evidence_id:
        raise TextPolicyError("source_evidence_id 与 vault_evidence.id 不一致")
    scope = _validated_scope("vault_evidence.scope", vault_evidence)
    if not isinstance(contract, dict):
        raise TextPolicyError("contract 必须是 Vault mastery contract 对象")
    if (
        _nonempty_string("contract.id", contract.get("id")) != scope["contract_id"]
        or _integer("contract.version", contract.get("version"), minimum=1)
        != scope["contract_version"]
        or _nonempty_string("contract.concept_id", contract.get("concept_id"))
        != scope["concept_id"]
    ):
        raise TextPolicyError("contract id/version/concept 与目标 evidence 作用域不一致")
    if not isinstance(contract.get("requirements"), dict):
        raise TextPolicyError("contract.requirements 必须是对象")
    if not isinstance(scoped_evidence, list) or not scoped_evidence:
        raise TextPolicyError("scoped_evidence 必须是完整的非空同范围 evidence 数组")

    # Delayed import avoids a module cycle when vault_tool imports this policy.
    try:
        import vault_tool as vault_evaluator
    except ModuleNotFoundError:  # pragma: no cover - package-style embedding
        from . import vault_tool as vault_evaluator  # type: ignore

    normalized_scoped_evidence: list[tuple[str, dict[str, Any]]] = []
    seen_evidence_ids: set[str] = set()
    target_match_count = 0
    for index, entry in enumerate(scoped_evidence):
        path = f"scoped_evidence[{index}]"
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise TextPolicyError(f"{path} 必须是 (evidence_id, evidence) 二元组")
        scoped_id = _nonempty_string(f"{path}.evidence_id", entry[0])
        scoped_record = entry[1]
        if not isinstance(scoped_record, dict):
            raise TextPolicyError(f"{path}.evidence 必须是对象")
        _validate_vault_evidence_envelope(path, scoped_record)
        if _nonempty_string(f"{path}.evidence.id", scoped_record.get("id")) != scoped_id:
            raise TextPolicyError(f"{path} 的元组 ID 与 evidence.id 不一致")
        if scoped_id in seen_evidence_ids:
            raise TextPolicyError("scoped_evidence 不得包含重复 evidence ID")
        seen_evidence_ids.add(scoped_id)
        scoped_scope = _validated_scope(f"{path}.scope", scoped_record)
        if scoped_scope != scope:
            raise TextPolicyError(f"{path} 不属于目标 evidence 的完整合同作用域")
        scoped_sources = _unique_string_list(
            f"{path}.source_ref_ids", scoped_record.get("source_ref_ids")
        )
        if not scoped_sources:
            raise TextPolicyError(f"{path}.source_ref_ids 不得为空")
        scoped_validity = _enum(
            f"{path}.observation_validity",
            scoped_record.get("observation_validity"),
            {"valid", "provisional", "stale"},
        )
        scoped_observed_at = _aware_timestamp(
            f"{path}.observed_at", scoped_record.get("observed_at")
        )
        scoped_bindings = _validate_vault_field_bindings(
            scoped_record,
            scoped_scope,
            scoped_sources,
            scoped_observed_at,
            scoped_validity,
        )
        scoped_eligible, _scoped_failures = _vault_mastery_eligibility(
            scoped_record,
            scoped_bindings,
            allow_trusted_synthetic_demo=_allow_trusted_synthetic_demo,
        )
        if not isinstance(scoped_record.get("mastery_eligible"), bool):
            raise TextPolicyError(f"{path}.mastery_eligible 必须是布尔值")
        if scoped_record["mastery_eligible"] is not scoped_eligible:
            raise TextPolicyError(f"{path}.mastery_eligible 与原始字段推导结果不一致")
        expected_confidence, expected_confidence_basis = (
            vault_evaluator.derive_observation_confidence(
                scoped_record,
                derived_mastery_eligible=scoped_eligible,
                allow_synthetic_demo=_allow_trusted_synthetic_demo,
            )
        )
        if scoped_record.get("observation_confidence") != expected_confidence:
            raise TextPolicyError(f"{path}.observation_confidence 不是来源与资格推导值")
        if (
            scoped_record.get("observation_confidence_basis")
            != expected_confidence_basis
        ):
            raise TextPolicyError(f"{path}.observation_confidence_basis 不是推导值")
        if scoped_id == evidence_id:
            target_match_count += 1
            if scoped_record != vault_evidence:
                raise TextPolicyError("目标 vault_evidence 未原样存在于 scoped_evidence")
        normalized_scoped_evidence.append((scoped_id, scoped_record))
    if target_match_count != 1:
        raise TextPolicyError("目标 vault_evidence 必须在 scoped_evidence 中原样且唯一存在")
    if state_context is not None and not isinstance(state_context, dict):
        raise TextPolicyError("state_context 必须是对象或 null")
    normalized_as_of = (
        _aware_timestamp("as_of", as_of) if as_of is not None else None
    )

    contract_evaluation = vault_evaluator.evaluate_mastery_contract(
        contract,
        normalized_scoped_evidence,
        state_context=dict(state_context or {}),
        as_of=normalized_as_of,
        allow_synthetic_demo=_allow_trusted_synthetic_demo,
    )
    evaluation_scope = dict(scope)

    evidence = dict(vault_evidence)
    prepared_values = _prepared_values_for_scope(
        prepared_update, scope, str(vault_evidence.get("phase"))
    )
    for field, prepared_value in prepared_values.items():
        if field not in evidence or evidence[field] != prepared_value:
            raise TextPolicyError(
                f"prepared_update.{field} 与已提交 Vault evidence 不一致"
            )
    phase = _enum(
        "vault_evidence.phase",
        evidence.get("phase"),
        {"diagnostic", "teaching_process", "verification", "retention"},
    )
    result = _enum(
        "vault_evidence.result",
        evidence.get("result"),
        {"pass", "partial", "fail", "conflicted", "not_tested"},
    )
    if not isinstance(evidence.get("response_correct"), bool):
        raise TextPolicyError("vault_evidence.response_correct 必须是布尔值")
    source_refs = _unique_string_list(
        "vault_evidence.source_ref_ids", evidence.get("source_ref_ids")
    )
    if not source_refs:
        raise TextPolicyError("vault_evidence.source_ref_ids 不得为空")
    validity = _enum(
        "vault_evidence.observation_validity",
        evidence.get("observation_validity"),
        {"valid", "provisional", "stale"},
    )
    confidence = _enum(
        "vault_evidence.observation_confidence",
        evidence.get("observation_confidence"),
        {"low", "medium", "high"},
    )
    observed_at = _aware_timestamp(
        "vault_evidence.observed_at", evidence.get("observed_at")
    )
    if phase == "retention":
        _integer(
            "vault_evidence.retention_delay_days",
            evidence.get("retention_delay_days"),
            minimum=0,
        )
    binding_consumers = _validate_vault_field_bindings(
        evidence, scope, source_refs, observed_at, validity
    )
    comparison_context = _validated_comparison_context(
        "comparison_context", comparison_context
    )
    context_key = _comparison_context_key(comparison_context)
    comparison_gate = _validated_comparison_gate(
        "derived comparison_gate",
        {
            "retention_required": contract_evaluation.get("retention_required"),
            "task_difficulty": comparison_context["task_difficulty"],
        },
    )
    missing_profile_bindings = sorted(
        field
        for field in PROFILE_ACTIVITY_SELECTION_FIELDS
        if "activity_selection" not in binding_consumers.get(field, set())
    )
    profile_actionable = not missing_profile_bindings
    profile_bound = lambda field: "activity_selection" in binding_consumers.get(
        field, set()
    )
    source_context_key = (
        _nonempty_string(
            "vault_evidence.context_key", evidence.get("context_key")
        )
        if profile_bound("context_key")
        else None
    )
    if source_context_key is not None and source_context_key != context_key:
        raise TextPolicyError(
            "vault_evidence.context_key 与合同评估的 canonical comparison_context 不一致"
        )
    activity = (
        _enum("vault_evidence.activity", evidence.get("activity"), PROFILE_ACTIVITIES)
        if profile_bound("activity")
        else None
    )
    carrier = (
        _enum("vault_evidence.carrier", evidence.get("carrier"), CARRIERS)
        if profile_bound("carrier")
        else None
    )
    derived_eligible, eligibility_failures = _vault_mastery_eligibility(
        evidence,
        binding_consumers,
        allow_trusted_synthetic_demo=_allow_trusted_synthetic_demo,
    )
    if not isinstance(evidence.get("mastery_eligible"), bool):
        raise TextPolicyError("vault_evidence.mastery_eligible 必须是布尔值")
    if evidence["mastery_eligible"] is not derived_eligible:
        raise TextPolicyError("vault_evidence.mastery_eligible 与原始字段推导结果不一致")

    evaluation_status = _enum(
        "recomputed contract_evaluation.status",
        contract_evaluation.get("status"),
        {"not_tested", "in_progress", "not_met", "met"},
    )
    qualified_ids = _unique_string_list(
        "recomputed contract_evaluation.qualified_evidence_ids",
        contract_evaluation.get("qualified_evidence_ids"),
    )
    qualified_failure_ids = _unique_string_list(
        "recomputed contract_evaluation.qualified_failure_evidence_ids",
        contract_evaluation.get("qualified_failure_evidence_ids"),
    )
    if set(qualified_ids).intersection(qualified_failure_ids):
        raise TextPolicyError("同一 evidence 不得同时是 qualified pass 与 qualified fail")
    if evidence_id in qualified_ids and (
        not derived_eligible
        or result != "pass"
        or evidence.get("response_correct") is not True
    ):
        raise TextPolicyError("重算合同的 qualified evidence 与原始证据冲突")
    if evidence_id in qualified_failure_ids and (
        not derived_eligible
        or not (
            result in {"fail", "partial", "conflicted"}
            or evidence.get("response_correct") is False
        )
    ):
        raise TextPolicyError("重算合同的 qualified failure 与原始证据冲突")
    mastery_gate_met = (
        evaluation_status == "met"
        and derived_eligible
        and evidence_id in qualified_ids
        and result == "pass"
        and evidence.get("response_correct") is True
    )

    return {
        "schema_version": RESPONSE_OBSERVATION_SCHEMA_VERSION,
        "source": {
            "kind": "vault_evidence",
            "evidence_id": evidence_id,
            "source_refs": source_refs,
            "source_context_key": source_context_key,
            "phase": phase,
            "result": result,
            "response_correct": evidence["response_correct"],
            "derived_mastery_eligible": derived_eligible,
            "mastery_eligibility_failures": eligibility_failures,
        },
        "scope": scope,
        "context_key": context_key,
        "activity": activity,
        "carrier": carrier,
        "profile_actionability": {
            "status": "actionable" if profile_actionable else "not_actionable",
            "missing_field_bindings": missing_profile_bindings,
        },
        "comparison_gate": dict(comparison_gate),
        "mastery_gate_met": mastery_gate_met,
        "mastery_gate_derivation": {
            "method": "vault_tool_contract_recompute_and_evidence_membership",
            "evaluation_scope": evaluation_scope,
            "contract_status": evaluation_status,
            "qualified_evidence_ids": qualified_ids,
            "qualified_failure_evidence_ids": qualified_failure_ids,
            "comparison_gate": dict(comparison_gate),
        },
        "assistance_level": (
            _enum(
                "vault_evidence.assistance_level",
                evidence.get("assistance_level"),
                set(ASSISTANCE_ORDER),
            )
            if profile_bound("assistance_level")
            else None
        ),
        "elapsed_seconds": (
            _number(
                "vault_evidence.elapsed_seconds",
                evidence.get("elapsed_seconds"),
                minimum=0,
            )
            if profile_bound("elapsed_seconds")
            else None
        ),
        "attempts": (
            _integer("vault_evidence.attempts", evidence.get("attempts"), minimum=1)
            if profile_bound("attempts")
            else None
        ),
        "hint_count": (
            _integer("vault_evidence.hint_count", evidence.get("hint_count"), minimum=0)
            if profile_bound("hint_count")
            else None
        ),
        "immediate_performance": (
            _number(
                "vault_evidence.immediate_performance",
                evidence.get("immediate_performance"),
                minimum=0,
                maximum=1,
            )
            if profile_bound("immediate_performance")
            else None
        ),
        "near_transfer": (
            _optional_profile_metric(
                "vault_evidence.near_transfer",
                evidence.get("near_transfer", "not_required"),
                minimum=0,
                maximum=1,
                markers={"not_required", "pending", "not_tested"},
            )
            if profile_bound("near_transfer")
            else "not_tested"
        ),
        "delayed_retention": (
            _optional_profile_metric(
                "vault_evidence.delayed_retention",
                evidence.get("delayed_retention", "pending"),
                minimum=0,
                maximum=1,
                markers={"not_required", "pending", "not_tested"},
            )
            if profile_bound("delayed_retention")
            else "not_tested"
        ),
        "self_reported_effort": (
            _optional_profile_metric(
                "vault_evidence.self_reported_effort",
                evidence.get("self_reported_effort", "not_collected"),
                minimum=1,
                maximum=7,
                markers={"not_collected"},
            )
            if profile_bound("self_reported_effort")
            else "not_collected"
        ),
        "observed_at": observed_at if profile_bound("observed_at") else None,
        "validity": validity,
        "confidence": confidence,
    }


def _validate_profile_observations(
    expected_scope: dict[str, Any],
    context_key: str,
    current_comparison_gate: dict[str, Any],
    current_max_assistance: str,
    response_profile_refs: list[str],
    value: Any,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise TextPolicyError("response_profile_observations 必须是数组")
    observations: list[dict[str, Any]] = []
    expected_keys = {
        "schema_version",
        "source",
        "scope",
        "context_key",
        "activity",
        "carrier",
        "profile_actionability",
        "comparison_gate",
        "mastery_gate_met",
        "mastery_gate_derivation",
        "assistance_level",
        "elapsed_seconds",
        "attempts",
        "hint_count",
        "immediate_performance",
        "near_transfer",
        "delayed_retention",
        "self_reported_effort",
        "observed_at",
        "validity",
        "confidence",
    }
    source_keys = {
        "kind",
        "evidence_id",
        "source_refs",
        "source_context_key",
        "phase",
        "result",
        "response_correct",
        "derived_mastery_eligible",
        "mastery_eligibility_failures",
    }
    derivation_keys = {
        "method",
        "evaluation_scope",
        "contract_status",
        "qualified_evidence_ids",
        "qualified_failure_evidence_ids",
        "comparison_gate",
    }
    for index, item in enumerate(value):
        path = f"response_profile_observations[{index}]"
        if not isinstance(item, dict):
            raise TextPolicyError(f"{path} 必须是对象")
        _exact_keys(path, item, expected_keys)
        if item.get("schema_version") != RESPONSE_OBSERVATION_SCHEMA_VERSION:
            raise TextPolicyError(f"{path}.schema_version 非法")

        source = item.get("source")
        if not isinstance(source, dict):
            raise TextPolicyError(f"{path}.source 必须是对象")
        _exact_keys(f"{path}.source", source, source_keys)
        if source.get("kind") != "vault_evidence":
            raise TextPolicyError(f"{path}.source.kind 非法")
        source_ref = _nonempty_string(
            f"{path}.source.evidence_id", source.get("evidence_id")
        )
        source_refs = _unique_string_list(
            f"{path}.source.source_refs", source.get("source_refs")
        )
        if not source_refs:
            raise TextPolicyError(f"{path}.source.source_refs 不得为空")
        source_context_key = source.get("source_context_key")
        if source_context_key is not None:
            _nonempty_string(
                f"{path}.source.source_context_key", source_context_key
            )
        observed_scope = _validated_scope(f"{path}.scope", item.get("scope"))
        if observed_scope["learner_id"] != expected_scope["learner_id"]:
            raise TextPolicyError(f"{path}.scope 不属于当前 learner")
        observed_context = _nonempty_string(
            f"{path}.context_key", item.get("context_key")
        )
        if observed_context != context_key:
            raise TextPolicyError(f"{path}.context_key 与当前 context_key 不一致")

        derivation = item.get("mastery_gate_derivation")
        if not isinstance(derivation, dict):
            raise TextPolicyError(f"{path}.mastery_gate_derivation 必须是对象")
        _exact_keys(f"{path}.mastery_gate_derivation", derivation, derivation_keys)
        if (
            derivation.get("method")
            != "vault_tool_contract_recompute_and_evidence_membership"
        ):
            raise TextPolicyError(f"{path}.mastery_gate_derivation.method 非法")
        evaluation_scope = _validated_scope(
            f"{path}.mastery_gate_derivation.evaluation_scope",
            derivation.get("evaluation_scope"),
        )
        if evaluation_scope != observed_scope:
            raise TextPolicyError(f"{path} 的 scope 与其自身 contract evaluation 不一致")
        contract_status = _enum(
            f"{path}.mastery_gate_derivation.contract_status",
            derivation.get("contract_status"),
            {"not_tested", "in_progress", "not_met", "met"},
        )
        qualified_ids = _unique_string_list(
            f"{path}.mastery_gate_derivation.qualified_evidence_ids",
            derivation.get("qualified_evidence_ids"),
        )
        qualified_failure_ids = _unique_string_list(
            f"{path}.mastery_gate_derivation.qualified_failure_evidence_ids",
            derivation.get("qualified_failure_evidence_ids"),
        )
        if set(qualified_ids).intersection(qualified_failure_ids):
            raise TextPolicyError(f"{path} 的 qualified pass/fail evidence 重叠")
        derived_comparison_gate = _validated_comparison_gate(
            f"{path}.mastery_gate_derivation.comparison_gate",
            derivation.get("comparison_gate"),
        )

        _enum(
            f"{path}.source.phase",
            source.get("phase"),
            {"diagnostic", "teaching_process", "verification", "retention"},
        )
        source_result = _enum(
            f"{path}.source.result",
            source.get("result"),
            {"pass", "partial", "fail", "conflicted", "not_tested"},
        )
        if not isinstance(source.get("response_correct"), bool):
            raise TextPolicyError(f"{path}.source.response_correct 必须是布尔值")
        if not isinstance(source.get("derived_mastery_eligible"), bool):
            raise TextPolicyError(f"{path}.source.derived_mastery_eligible 必须是布尔值")
        eligibility_failures = _unique_string_list(
            f"{path}.source.mastery_eligibility_failures",
            source.get("mastery_eligibility_failures"),
        )
        if source["derived_mastery_eligible"] is not (not eligibility_failures):
            raise TextPolicyError(f"{path}.source 的 mastery eligibility 推导自相矛盾")
        if source_ref in qualified_ids and (
            source["derived_mastery_eligible"] is not True
            or source_result != "pass"
            or source["response_correct"] is not True
        ):
            raise TextPolicyError(f"{path} 的 qualified evidence 与来源状态冲突")
        if source_ref in qualified_failure_ids and (
            source["derived_mastery_eligible"] is not True
            or not (
                source_result in {"fail", "partial", "conflicted"}
                or source["response_correct"] is False
            )
        ):
            raise TextPolicyError(f"{path} 的 qualified failure 与来源状态冲突")
        derived_gate = (
            contract_status == "met"
            and source["derived_mastery_eligible"] is True
            and source_ref in qualified_ids
            and source_result == "pass"
            and source["response_correct"] is True
        )
        mastery_gate_met = item.get("mastery_gate_met")
        if not isinstance(mastery_gate_met, bool):
            raise TextPolicyError(f"{path}.mastery_gate_met 必须是布尔值")
        if mastery_gate_met is not derived_gate:
            raise TextPolicyError(f"{path}.mastery_gate_met 不是合同评估推导值")
        validity = _enum(
            f"{path}.validity",
            item.get("validity"),
            {"valid", "provisional", "stale"},
        )
        confidence = _enum(
            f"{path}.confidence", item.get("confidence"), {"low", "medium", "high"}
        )
        if mastery_gate_met and validity != "valid":
            raise TextPolicyError(f"{path} 非 valid observation 不得通过 mastery gate")

        actionability = item.get("profile_actionability")
        if not isinstance(actionability, dict):
            raise TextPolicyError(f"{path}.profile_actionability 必须是对象")
        _exact_keys(
            f"{path}.profile_actionability",
            actionability,
            {"status", "missing_field_bindings"},
        )
        actionability_status = _enum(
            f"{path}.profile_actionability.status",
            actionability.get("status"),
            {"actionable", "not_actionable"},
        )
        missing_bindings = _unique_string_list(
            f"{path}.profile_actionability.missing_field_bindings",
            actionability.get("missing_field_bindings"),
        )
        if not set(missing_bindings).issubset(PROFILE_ACTIVITY_SELECTION_FIELDS):
            raise TextPolicyError(
                f"{path}.profile_actionability 含未知画像 binding"
            )
        if actionability_status == "actionable" and missing_bindings:
            raise TextPolicyError(f"{path}.profile_actionability 自相矛盾")
        if actionability_status == "not_actionable" and not missing_bindings:
            raise TextPolicyError(f"{path}.profile_actionability 自相矛盾")
        if actionability_status == "actionable" and source_context_key != observed_context:
            raise TextPolicyError(
                f"{path}.source.source_context_key 未绑定 canonical context_key"
            )
        comparison_gate = _validated_comparison_gate(
            f"{path}.comparison_gate", item.get("comparison_gate")
        )
        if comparison_gate != derived_comparison_gate:
            raise TextPolicyError(f"{path}.comparison_gate 不是自身合同重算派生值")
        comparison_values_match = comparison_gate == current_comparison_gate

        raw_assistance = item.get("assistance_level")
        assistance_level = (
            _enum(f"{path}.assistance_level", raw_assistance, set(ASSISTANCE_ORDER))
            if raw_assistance is not None
            else None
        )
        assistance_within_limit = (
            assistance_level is not None
            and ASSISTANCE_ORDER[assistance_level]
            <= ASSISTANCE_ORDER[current_max_assistance]
        )
        comparison_gate_met = comparison_values_match and assistance_within_limit

        def optional_number(field: str, *, minimum: float, maximum: float | None = None) -> float | None:
            raw = item.get(field)
            if raw is None:
                return None
            return _number(f"{path}.{field}", raw, minimum=minimum, maximum=maximum)

        activity = (
            _enum(f"{path}.activity", item.get("activity"), PROFILE_ACTIVITIES)
            if item.get("activity") is not None
            else None
        )
        carrier = (
            _enum(f"{path}.carrier", item.get("carrier"), CARRIERS)
            if item.get("carrier") is not None
            else None
        )
        elapsed_seconds = optional_number("elapsed_seconds", minimum=0)
        attempts = (
            _integer(f"{path}.attempts", item.get("attempts"), minimum=1)
            if item.get("attempts") is not None
            else None
        )
        hint_count = (
            _integer(f"{path}.hint_count", item.get("hint_count"), minimum=0)
            if item.get("hint_count") is not None
            else None
        )
        immediate_performance = optional_number(
            "immediate_performance", minimum=0, maximum=1
        )
        observed_at = (
            _aware_timestamp(f"{path}.observed_at", item.get("observed_at"))
            if item.get("observed_at") is not None
            else None
        )
        if actionability_status == "actionable" and (
            activity is None
            or carrier is None
            or assistance_level is None
            or elapsed_seconds is None
            or attempts is None
            or hint_count is None
            or immediate_performance is None
            or observed_at is None
        ):
            raise TextPolicyError(f"{path} 标为 actionable 但画像必需值缺失")

        observations.append(
            {
                "source_evidence_id": source_ref,
                "source_refs": source_refs,
                "scope": observed_scope,
                "concept_id": observed_scope["concept_id"],
                "context_key": observed_context,
                "activity": activity,
                "carrier": carrier,
                "profile_actionable": actionability_status == "actionable",
                "comparison_gate_met": comparison_gate_met,
                "mastery_gate_met": mastery_gate_met,
                "validity": validity,
                "confidence": confidence,
                "assistance_level": assistance_level,
                "elapsed_seconds": elapsed_seconds,
                "attempts": attempts,
                "hint_count": hint_count,
                "immediate_performance": immediate_performance,
                "near_transfer": _optional_profile_metric(
                    f"{path}.near_transfer",
                    item.get("near_transfer"),
                    minimum=0,
                    maximum=1,
                    markers={"not_required", "pending", "not_tested"},
                ),
                "delayed_retention": _optional_profile_metric(
                    f"{path}.delayed_retention",
                    item.get("delayed_retention"),
                    minimum=0,
                    maximum=1,
                    markers={"not_required", "pending", "not_tested"},
                ),
                "self_reported_effort": _optional_profile_metric(
                    f"{path}.self_reported_effort",
                    item.get("self_reported_effort"),
                    minimum=1,
                    maximum=7,
                    markers={"not_collected"},
                ),
                "observed_at": observed_at,
            }
        )
    observed_refs = [item["source_evidence_id"] for item in observations]
    if len(set(observed_refs)) != len(observed_refs):
        raise TextPolicyError("response_profile_observations 的 source evidence 不得重复")
    if set(observed_refs) != set(response_profile_refs) or len(observed_refs) != len(
        response_profile_refs
    ):
        raise TextPolicyError(
            "response_profile_refs 必须与 response observation 的 evidence_id 一一对应"
        )
    return observations


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _pareto_profile_selection(observations: list[dict[str, Any]]) -> dict[str, Any]:
    required_directions = {
        "elapsed_seconds": "minimize",
        "attempts": "minimize",
        "hint_count": "minimize",
        "assistance_score": "minimize",
        "immediate_performance": "maximize",
    }
    required_metric_fields = {
        "elapsed_seconds",
        "attempts",
        "hint_count",
        "immediate_performance",
    }
    qualified = [
        item
        for item in observations
        if item["mastery_gate_met"]
        and item["profile_actionable"]
        and item["comparison_gate_met"]
        and item["confidence"] in {"medium", "high"}
        and item["activity"] is not None
        and item["carrier"] is not None
        and item["assistance_level"] is not None
        and all(isinstance(item[field], (int, float)) for field in required_metric_fields)
    ]
    qualified_refs = sorted(item["source_evidence_id"] for item in qualified)
    rejected_refs = sorted(
        item["source_evidence_id"]
        for item in observations
        if item not in qualified
    )
    pool_count = len(qualified)
    pool_concept_count = len({item["concept_id"] for item in qualified})
    pool_has_transfer_or_retention = any(
        isinstance(item["near_transfer"], float)
        or isinstance(item["delayed_retention"], float)
        for item in qualified
    )

    def threshold_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        count = len(items)
        concept_count = len({item["concept_id"] for item in items})
        has_transfer_or_retention = any(
            isinstance(item["near_transfer"], float)
            or isinstance(item["delayed_retention"], float)
            for item in items
        )
        if count == 0:
            level = "unknown"
        elif count >= 5 and concept_count >= 3 and has_transfer_or_retention:
            level = "supported"
        elif count >= 3 and concept_count >= 2:
            level = "emerging"
        else:
            level = "tentative"
        reasons: list[str] = []
        if level in {"unknown", "tentative"}:
            if count < 3:
                reasons.append("needs_three_qualified_observations")
            if concept_count < 2:
                reasons.append("needs_two_concepts_for_emerging")
        if level != "supported":
            if count < 5:
                reasons.append("needs_five_qualified_observations")
            if concept_count < 3:
                reasons.append("needs_three_concepts_for_supported")
            if not has_transfer_or_retention:
                reasons.append("needs_transfer_or_retention_evidence")
        return {
            "evidence_level": level,
            "qualified_observation_count": count,
            "distinct_concept_count": concept_count,
            "has_transfer_or_retention": has_transfer_or_retention,
            "threshold_reasons": list(dict.fromkeys(reasons)),
        }

    def selection_result(
        status: str,
        *,
        selected_option: dict[str, Any] | None = None,
        exploration_option: dict[str, Any] | None = None,
        frontier: list[str] | None = None,
        options: list[dict[str, Any]] | None = None,
        excluded_metrics: list[str] | None = None,
        directions: dict[str, str] | None = None,
        threshold_items: list[dict[str, Any]] | None = None,
        extra_threshold_reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        summary = threshold_summary(threshold_items or [])
        evidence_level = summary["evidence_level"]
        threshold_reasons = list(
            dict.fromkeys(
                summary["threshold_reasons"] + list(extra_threshold_reasons or [])
            )
        )
        return {
            "status": status,
            "evidence_level": evidence_level,
            # These three fields intentionally describe only the unique winning
            # option.  Pool totals are separate so they cannot inflate a winner.
            "qualified_observation_count": summary["qualified_observation_count"],
            "distinct_concept_count": summary["distinct_concept_count"],
            "has_transfer_or_retention": summary["has_transfer_or_retention"],
            "candidate_pool_observation_count": pool_count,
            "candidate_pool_distinct_concept_count": pool_concept_count,
            "candidate_pool_has_transfer_or_retention": pool_has_transfer_or_retention,
            "threshold_basis": (
                selected_option or exploration_option or {}
            ).get("option_id"),
            "direct_text_activity_override_allowed": evidence_level
            in {"emerging", "supported"},
            "strong_reuse_allowed": evidence_level == "supported",
            "nontext_override_allowed": evidence_level == "supported",
            "threshold_reasons": threshold_reasons,
            "selected_option": selected_option,
            "exploration_option": exploration_option,
            "pareto_frontier": frontier or [],
            "options": options or [],
            "excluded_metrics": excluded_metrics or [],
            "metric_directions": directions or required_directions,
            "qualified_observation_refs": qualified_refs,
            "rejected_observation_refs": rejected_refs,
        }

    if not observations:
        return selection_result("no_observations")
    if not qualified:
        return selection_result("no_qualified_observations")

    optional_metrics = {
        "near_transfer": "maximize",
        "delayed_retention": "maximize",
        "self_reported_effort": "minimize",
    }
    comparable_optional = {
        metric
        for metric in optional_metrics
        if all(isinstance(item[metric], float) for item in qualified)
    }
    excluded_metrics = sorted(set(optional_metrics) - comparable_optional)
    directions = {
        **required_directions,
        **{metric: optional_metrics[metric] for metric in comparable_optional},
    }

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in qualified:
        groups.setdefault((item["activity"], item["carrier"]), []).append(item)

    options: list[dict[str, Any]] = []
    for (activity, carrier), items in sorted(groups.items()):
        option_threshold = threshold_summary(items)
        metrics: dict[str, float] = {
            "elapsed_seconds": _mean([item["elapsed_seconds"] for item in items]),
            "attempts": _mean([float(item["attempts"]) for item in items]),
            "hint_count": _mean([float(item["hint_count"]) for item in items]),
            "assistance_score": _mean(
                [float(ASSISTANCE_ORDER[item["assistance_level"]]) for item in items]
            ),
            "immediate_performance": _mean(
                [item["immediate_performance"] for item in items]
            ),
        }
        for metric in comparable_optional:
            metrics[metric] = _mean([float(item[metric]) for item in items])
        options.append(
            {
                "option_id": f"{activity}|{carrier}",
                "activity": activity,
                "carrier": carrier,
                "sample_count": len(items),
                "distinct_concept_count": option_threshold["distinct_concept_count"],
                "has_transfer_or_retention": option_threshold[
                    "has_transfer_or_retention"
                ],
                "evidence_level": option_threshold["evidence_level"],
                "threshold_reasons": option_threshold["threshold_reasons"],
                "observation_refs": sorted(
                    item["source_evidence_id"] for item in items
                ),
                "metrics": metrics,
            }
        )

    if len(options) < 2:
        return selection_result(
            "insufficient_alternatives",
            frontier=[item["option_id"] for item in options],
            options=options,
            excluded_metrics=excluded_metrics,
            directions=directions,
            extra_threshold_reasons=["needs_comparable_alternative"],
        )

    def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
        no_worse = True
        strictly_better = False
        for metric, direction in directions.items():
            left_value = left["metrics"][metric]
            right_value = right["metrics"][metric]
            if direction == "minimize":
                if left_value > right_value:
                    no_worse = False
                    break
                strictly_better = strictly_better or left_value < right_value
            else:
                if left_value < right_value:
                    no_worse = False
                    break
                strictly_better = strictly_better or left_value > right_value
        return no_worse and strictly_better

    frontier = [
        option
        for option in options
        if not any(
            other is not option and dominates(other, option) for other in options
        )
    ]
    selected = frontier[0] if len(frontier) == 1 else None
    selected_items = (
        groups[(selected["activity"], selected["carrier"])]
        if selected is not None
        else []
    )
    selected_level = threshold_summary(selected_items)["evidence_level"]
    if selected is not None and selected_level not in {"emerging", "supported"}:
        status = "tentative_exploration"
        selected_option = None
        exploration_option = selected
    else:
        status = "pareto_selected" if selected else "pareto_ambiguous"
        selected_option = selected
        exploration_option = None
    return selection_result(
        status,
        selected_option=selected_option,
        exploration_option=exploration_option,
        frontier=[item["option_id"] for item in frontier],
        options=options,
        excluded_metrics=excluded_metrics,
        directions=directions,
        threshold_items=selected_items,
        extra_threshold_reasons=(
            [] if selected is not None else ["needs_unique_pareto_winner"]
        ),
    )


def _validate_user_value(value: Any, path: str) -> None:
    """Reject internal fields at any depth before building a user payload."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_user_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TextPolicyError(f"用户投影字段名必须是字符串: {path}")
            if key.casefold() in USER_FORBIDDEN_KEYS:
                raise TextPolicyError(f"用户投影包含内部字段: {path}.{key}")
            _validate_user_value(item, f"{path}.{key}")
        return
    raise TextPolicyError(f"用户投影包含不可序列化类型: {path}")


def _validated_next_step(value: Any) -> str | dict[str, str | None] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _nonempty_string("next_step", value)
    if not isinstance(value, dict):
        raise TextPolicyError("next_step 只能是字符串、null 或固定安全对象")
    _exact_keys("next_step", value, NEXT_STEP_SAFE_FIELDS)
    instruction = _nonempty_string("next_step.instruction", value.get("instruction"))
    when = value.get("when")
    if when is not None:
        when = _nonempty_string("next_step.when", when)
    return {"instruction": instruction, "when": when}


def decide_text_activity(context: dict[str, Any]) -> dict[str, Any]:
    """Choose an internal teaching activity while enforcing the text-first gate."""

    for derived_key in (
        "profile_selection_status",
        "profile_usage_status",
        "selection_consumer",
    ):
        if derived_key in context:
            raise TextPolicyError(f"{derived_key} 是派生输出，不得由调用者提供")
    legacy_profile_flags = {
        "historical_text_pareto_preferred",
        "historical_nontext_pareto_preferred",
    }
    if legacy_profile_flags.intersection(context):
        raise TextPolicyError(
            "historical_*_pareto_preferred 布尔值不再可信；请提供同情境结构化 observation"
        )

    learner_id = _nonempty_string("learner_id", context.get("learner_id"))
    goal_id = _nonempty_string("goal_id", context.get("goal_id"))
    concept_id = _nonempty_string("concept_id", context.get("concept_id"))
    contract_id = _nonempty_string("contract_id", context.get("contract_id"))
    contract_version = context.get("contract_version")
    if (
        not isinstance(contract_version, int)
        or isinstance(contract_version, bool)
        or contract_version < 1
    ):
        raise TextPolicyError("contract_version 必须是正整数")
    route_id = _nonempty_string("route_id", context.get("route_id"))
    route_version = _integer(
        "route_version", context.get("route_version"), minimum=1
    )
    bound_verification_task_id = _nonempty_string(
        "bound_verification_task_id", context.get("bound_verification_task_id")
    )
    verification_content_guard = _validated_verification_content_guard(
        "verification_content_guard",
        context.get("verification_content_guard"),
        bound_verification_task_id,
    )
    evidence_refs = context.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not all(
        isinstance(item, str) and item.strip() for item in evidence_refs
    ):
        raise TextPolicyError("evidence_refs 必须是字符串数组；无证据时使用 []")
    knowledge_kind = _enum(
        "knowledge_kind", context.get("knowledge_kind"), KNOWLEDGE_KINDS
    )
    target = _enum(
        "target_performance", context.get("target_performance"), TARGET_PERFORMANCE
    )
    prior = _enum(
        "prior_knowledge_band",
        context.get("prior_knowledge_band", "unknown"),
        {"unknown", "none", "partial", "mastered"},
    )
    domain = _nonempty_string("domain", context.get("domain")).casefold()
    task_difficulty = _enum(
        "task_difficulty", context.get("task_difficulty"), TASK_DIFFICULTIES
    )
    comparison_gate = _validated_comparison_gate(
        "comparison_gate", context.get("comparison_gate")
    )
    if comparison_gate["task_difficulty"] != task_difficulty:
        raise TextPolicyError("comparison_gate.task_difficulty 与当前任务难度不一致")
    comparison_context = _validated_comparison_context(
        "comparison_context",
        {
            "domain": domain,
            "knowledge_kind": knowledge_kind,
            "target_performance": target,
            "prior_band": prior,
            "task_difficulty": task_difficulty,
        },
    )
    canonical_context_key = _comparison_context_key(comparison_context)
    supplied_context_key = _nonempty_string(
        "context_key", context.get("context_key")
    )
    if supplied_context_key != canonical_context_key:
        raise TextPolicyError("context_key 不是当前比较维度的 canonical key")
    context_key = canonical_context_key
    assistance = _enum(
        "max_assistance_level",
        context.get("max_assistance_level", "A0"),
        set(ASSISTANCE_ORDER),
    )
    response_profile_refs = _unique_string_list(
        "response_profile_refs", context.get("response_profile_refs")
    )
    decision_scope = {
        "learner_id": learner_id,
        "goal_id": goal_id,
        "concept_id": concept_id,
        "contract_id": contract_id,
        "contract_version": contract_version,
    }
    response_profile_observations = _validate_profile_observations(
        decision_scope,
        context_key,
        comparison_gate,
        assistance,
        response_profile_refs,
        context.get("response_profile_observations"),
    )
    profile_selection = _pareto_profile_selection(response_profile_observations)
    if profile_selection["status"] not in PROFILE_SELECTION_STATUSES:
        raise TextPolicyError("profile_selection_status 非法")
    introduced_terms = _unique_string_list(
        "introduced_terms", context.get("introduced_terms", [])
    )
    static_visual_reason = context.get("static_visual_reason")
    if static_visual_reason is not None:
        static_visual_reason = _enum(
            "static_visual_reason",
            static_visual_reason,
            set(STATIC_VISUAL_KIND_BY_REASON),
        )
    intent = _enum(
        "delivery_intent",
        context.get("delivery_intent", "learn"),
        {"learn", "reference_only", "micro_diagnosis"},
    )
    text_sufficiency = _enum(
        "text_sufficiency",
        context.get("text_sufficiency", "unknown"),
        {"sufficient", "unknown", "insufficient"},
    )
    activity, text_format = DEFAULT_ACTIVITY[target]
    hard_constraints = list(context.get("hard_constraints", []))
    if any(item not in HARD_NON_TEXT_REASONS for item in hard_constraints):
        raise TextPolicyError("hard_constraints 包含未定义原因码")
    forced_carrier = context.get("forced_carrier")
    if forced_carrier is not None:
        forced_carrier = _enum("forced_carrier", forced_carrier, CARRIERS)
    if text_sufficiency == "insufficient" and not hard_constraints:
        raise TextPolicyError("text_sufficiency=insufficient 必须给出非文字硬需求")

    same_error_count = context.get("same_error_count", 0)
    variants_tried = context.get("text_variants_tried", 0)
    if not isinstance(same_error_count, int) or isinstance(same_error_count, bool) or same_error_count < 0:
        raise TextPolicyError("same_error_count 必须是非负整数")
    if not isinstance(variants_tried, int) or isinstance(variants_tried, bool) or variants_tried < 0:
        raise TextPolicyError("text_variants_tried 必须是非负整数")
    process_adaptation = context.get("process_adaptation")
    if process_adaptation is None:
        process_adaptation = {
            "schema": "uc-process-adaptation/0.1",
            "source_evidence_ids": [],
            "consumer_ids": [
                "feedback_selection",
                "activity_selection",
                "representation_selection",
            ],
            "cost_summary": {
                "practice_feedback_seconds": 0.0,
                "practice_feedback_minutes": 0.0,
                "total_attempts": 0,
                "total_hint_count": 0,
                "mean_self_reported_effort": None,
            },
            "latest_teaching_item_id": None,
            "max_observed_assistance_level": (
                assistance if same_error_count > 0 else None
            ),
            "support_load_status": "not_measured",
            "status": "no_process_evidence",
            "latest_evidence_id": None,
            "latest_activity": None,
            "latest_error_signature": None,
            "same_error_count": same_error_count,
            "text_variants_tried": variants_tried,
            "feedback_rule": "low_level_policy_input",
            "next_action": "policy_only",
        }
    if not isinstance(process_adaptation, dict):
        raise TextPolicyError("process_adaptation 必须是对象")
    _exact_keys(
        "process_adaptation",
        process_adaptation,
        {
            "schema",
            "source_evidence_ids",
            "consumer_ids",
            "cost_summary",
            "latest_teaching_item_id",
            "max_observed_assistance_level",
            "support_load_status",
            "status",
            "latest_evidence_id",
            "latest_activity",
            "latest_error_signature",
            "same_error_count",
            "text_variants_tried",
            "feedback_rule",
            "next_action",
        },
    )
    if process_adaptation.get("schema") != "uc-process-adaptation/0.1":
        raise TextPolicyError("process_adaptation.schema 非法")
    process_refs = _unique_string_list(
        "process_adaptation.source_evidence_ids",
        process_adaptation.get("source_evidence_ids"),
    )
    consumers = _unique_string_list(
        "process_adaptation.consumer_ids", process_adaptation.get("consumer_ids")
    )
    if set(consumers) != {
        "feedback_selection",
        "activity_selection",
        "representation_selection",
    }:
        raise TextPolicyError("process_adaptation.consumer_ids 非法")
    latest_teaching_item_id = process_adaptation.get("latest_teaching_item_id")
    if latest_teaching_item_id is not None:
        _nonempty_string(
            "process_adaptation.latest_teaching_item_id", latest_teaching_item_id
        )
    max_observed_assistance_level = process_adaptation.get(
        "max_observed_assistance_level"
    )
    if max_observed_assistance_level is not None:
        max_observed_assistance_level = _enum(
            "process_adaptation.max_observed_assistance_level",
            max_observed_assistance_level,
            set(ASSISTANCE_ORDER),
        )
    support_load_status = _enum(
        "process_adaptation.support_load_status",
        process_adaptation.get("support_load_status"),
        {"not_measured", "normal", "high"},
    )
    process_status = _enum(
        "process_adaptation.status",
        process_adaptation.get("status"),
        {
            "no_process_evidence",
            "ready_for_verification",
            "repair_required",
            "escalation_candidate",
        },
    )
    process_same_error_count = _integer(
        "process_adaptation.same_error_count",
        process_adaptation.get("same_error_count"),
        minimum=0,
    )
    process_variants_tried = _integer(
        "process_adaptation.text_variants_tried",
        process_adaptation.get("text_variants_tried"),
        minimum=0,
    )
    if process_same_error_count != same_error_count or process_variants_tried != variants_tried:
        raise TextPolicyError("过程修复计数必须来自 process_adaptation")
    latest_process_activity = process_adaptation.get("latest_activity")
    if latest_process_activity is not None:
        latest_process_activity = _enum(
            "process_adaptation.latest_activity",
            latest_process_activity,
            PROFILE_ACTIVITIES,
        )
    latest_error_signature = process_adaptation.get("latest_error_signature")
    if latest_error_signature is not None:
        _nonempty_string(
            "process_adaptation.latest_error_signature", latest_error_signature
        )
    latest_process_evidence_id = process_adaptation.get("latest_evidence_id")
    if latest_process_evidence_id is not None:
        latest_process_evidence_id = _nonempty_string(
            "process_adaptation.latest_evidence_id", latest_process_evidence_id
        )
        if latest_process_evidence_id not in process_refs:
            raise TextPolicyError("process_adaptation.latest_evidence_id 未在来源集合")
    for field in ("feedback_rule", "next_action"):
        _nonempty_string(
            f"process_adaptation.{field}", process_adaptation.get(field)
        )
    cost_summary = process_adaptation.get("cost_summary")
    if not isinstance(cost_summary, dict):
        raise TextPolicyError("process_adaptation.cost_summary 必须是对象")
    _exact_keys(
        "process_adaptation.cost_summary",
        cost_summary,
        {
            "practice_feedback_seconds",
            "practice_feedback_minutes",
            "total_attempts",
            "total_hint_count",
            "mean_self_reported_effort",
        },
    )
    _number(
        "process_adaptation.cost_summary.practice_feedback_seconds",
        cost_summary.get("practice_feedback_seconds"),
        minimum=0,
    )
    _number(
        "process_adaptation.cost_summary.practice_feedback_minutes",
        cost_summary.get("practice_feedback_minutes"),
        minimum=0,
    )
    _integer(
        "process_adaptation.cost_summary.total_attempts",
        cost_summary.get("total_attempts"),
        minimum=0,
    )
    _integer(
        "process_adaptation.cost_summary.total_hint_count",
        cost_summary.get("total_hint_count"),
        minimum=0,
    )
    if cost_summary.get("mean_self_reported_effort") is not None:
        _number(
            "process_adaptation.cost_summary.mean_self_reported_effort",
            cost_summary.get("mean_self_reported_effort"),
            minimum=1,
            maximum=7,
        )
    available_text_activities = _unique_string_list(
        "available_text_activities",
        context.get("available_text_activities", sorted(PROFILE_ACTIVITIES)),
    )
    if not available_text_activities or any(
        item not in PROFILE_ACTIVITIES for item in available_text_activities
    ):
        raise TextPolicyError("available_text_activities 非法或为空")
    available_text_activity_costs = context.get("available_text_activity_costs", {})
    if (
        not isinstance(available_text_activity_costs, dict)
        or set(available_text_activity_costs).difference(available_text_activities)
    ):
        raise TextPolicyError("available_text_activity_costs 必须只包含可用文字活动")
    normalized_activity_costs: dict[str, float] = {}
    for candidate_activity, raw_cost in available_text_activity_costs.items():
        if (
            not isinstance(candidate_activity, str)
            or not isinstance(raw_cost, (int, float))
            or isinstance(raw_cost, bool)
            or raw_cost < 0
        ):
            raise TextPolicyError("available_text_activity_costs 含非法成本")
        normalized_activity_costs[candidate_activity] = float(raw_cost)
    estimated_practice_feedback_minutes = _number(
        "estimated_practice_feedback_minutes",
        context.get("estimated_practice_feedback_minutes", 0),
        minimum=0,
    )
    measured_practice_feedback_minutes = float(
        cost_summary["practice_feedback_minutes"]
    )
    process_cost_over_estimate = bool(
        process_refs
        and measured_practice_feedback_minutes
        > float(estimated_practice_feedback_minutes)
    )
    prerequisite_gap = context.get("prerequisite_gap", False)
    if not isinstance(prerequisite_gap, bool):
        raise TextPolicyError("prerequisite_gap 必须是布尔值")
    affordance = context.get("matching_affordance")
    affordance_reason = context.get("matching_affordance_reason")
    if affordance is not None:
        affordance = _enum("matching_affordance", affordance, NON_TEXT_CARRIERS)
        affordance_reason = _enum(
            "matching_affordance_reason",
            affordance_reason,
            set().union(*AFFORDANCE_REASONS.values()),
        )
        if affordance_reason not in AFFORDANCE_REASONS[affordance]:
            raise TextPolicyError("matching_affordance 与 matching_affordance_reason 不一致")
    elif affordance_reason is not None:
        raise TextPolicyError("matching_affordance_reason 必须绑定 matching_affordance")

    carrier = "text_document" if intent == "reference_only" else "text_dialogue" if intent == "micro_diagnosis" else "text_hybrid"
    selection_status = "selected"
    escalation_status = "not_eligible"
    escalation_target = None
    reason_codes = ["text_can_represent_target", "text_default_low_coordination"]
    profile_usage_status = "default_text_policy"
    repair_selection_basis = None

    if prerequisite_gap:
        selection_status = "blocked"
        reason_codes = ["prerequisite_gap"]
        profile_usage_status = "blocked_by_prerequisite"
    elif hard_constraints:
        profile_usage_status = "overridden_by_hard_constraint"
        if forced_carrier is None:
            if "real_time_feedback_required" in hard_constraints:
                forced_carrier = "interactive"
            elif {
                "continuous_motion_is_target",
                "spatial_temporal_change_required",
            }.intersection(hard_constraints):
                forced_carrier = "video"
            else:
                raise TextPolicyError("accessibility/user constraint 必须指定 forced_carrier")
        carrier = forced_carrier
        selection_status = "escalation_required" if carrier in NON_TEXT_CARRIERS else "selected"
        escalation_status = "selected" if carrier in NON_TEXT_CARRIERS else "not_applicable"
        escalation_target = carrier if carrier in NON_TEXT_CARRIERS else None
        reason_codes = hard_constraints
    else:
        repeated_gate = (
            same_error_count >= 2
            and variants_tried >= 2
            and max_observed_assistance_level is not None
            and ASSISTANCE_ORDER[max_observed_assistance_level]
            >= ASSISTANCE_ORDER["A2"]
            and affordance in NON_TEXT_CARRIERS
        )
        if repeated_gate:
            carrier = str(affordance)
            selection_status = "escalation_required"
            escalation_status = "selected"
            escalation_target = carrier
            reason_codes = ["same_error_repeated", "text_representation_exhausted"]
            profile_usage_status = "overridden_by_text_repair_gate"
        elif same_error_count >= 1:
            selection_status = "repair_selected"
            escalation_status = "text_repair_required"
            selected_profile = profile_selection.get("selected_option")
            profile_alternative = (
                selected_profile.get("activity")
                if isinstance(selected_profile, dict)
                and selected_profile.get("carrier") in TEXT_CARRIERS
                else None
            )
            cost_candidates = [
                item
                for item in available_text_activities
                if item != latest_process_activity and item in normalized_activity_costs
            ]
            if process_cost_over_estimate and cost_candidates:
                activity = min(
                    cost_candidates,
                    key=lambda item: (normalized_activity_costs[item], item),
                )
                repair_selection_basis = "measured_cost_alternative"
            elif (
                profile_alternative in available_text_activities
                and profile_alternative != latest_process_activity
            ):
                activity = str(profile_alternative)
                repair_selection_basis = "profile_alternative"
            else:
                alternatives = [
                    item
                    for item in TEXT_REPAIR_ORDER.get(
                        str(latest_process_activity), sorted(PROFILE_ACTIVITIES)
                    )
                    if item in available_text_activities
                    and item != latest_process_activity
                ]
                if alternatives:
                    activity = alternatives[0]
                    repair_selection_basis = "available_text_alternative"
                else:
                    repair_selection_basis = "no_alternative_resource"
            text_format = ACTIVITY_DEFAULT_FORMAT[activity]
            reason_codes = [
                "text_repair_required",
                "process_evidence_triggered_repair",
                "text_can_represent_target",
            ]
            if repair_selection_basis == "measured_cost_alternative":
                reason_codes.append("process_cost_exceeded_estimate")
            profile_usage_status = "overridden_by_text_repair_gate"
        elif profile_selection["status"] == "tentative_exploration":
            profile_usage_status = "exploration_only_threshold"
            reason_codes.append("response_profile_exploration")
        elif profile_selection["status"] == "pareto_selected":
            selected_profile = profile_selection["selected_option"]
            if not isinstance(selected_profile, dict):
                raise TextPolicyError("pareto_selected 缺少 selected_option")
            selected_activity = selected_profile["activity"]
            selected_carrier = selected_profile["carrier"]
            evidence_level = profile_selection["evidence_level"]
            if intent != "learn":
                profile_usage_status = "not_applicable_delivery_intent"
            elif selected_carrier in NON_TEXT_CARRIERS:
                if not profile_selection["nontext_override_allowed"]:
                    profile_usage_status = "blocked_by_profile_threshold"
                    reason_codes.append("response_profile_exploration")
                elif affordance == selected_carrier:
                    activity = selected_activity
                    carrier = selected_carrier
                    text_format = None
                    selection_status = "escalation_required"
                    escalation_status = "selected"
                    escalation_target = carrier
                    reason_codes = ["nontext_supported_pareto_dominance"]
                    profile_usage_status = "activity_and_carrier"
                else:
                    profile_usage_status = "rejected_missing_affordance"
                    reason_codes.append("no_context_evidence")
            else:
                activity = selected_activity
                text_format = ACTIVITY_DEFAULT_FORMAT[activity]
                reason_codes = ["historical_text_pareto_preferred"]
                if evidence_level == "supported":
                    carrier = selected_carrier
                    profile_usage_status = "activity_and_carrier"
                else:
                    # Emerging evidence may change the text mechanism, not the
                    # carrier; stronger cross-concept reuse requires supported.
                    profile_usage_status = "activity_only"
        else:
            if (
                profile_selection["evidence_level"] == "tentative"
                and profile_selection["qualified_observation_count"] > 0
            ):
                profile_usage_status = "exploration_only_threshold"
                reason_codes.append("response_profile_exploration")
            elif (
                response_profile_observations
                and profile_selection["status"] == "no_qualified_observations"
            ):
                profile_usage_status = "blocked_by_profile_threshold"
            reason_codes.append("no_context_evidence")

    if profile_usage_status not in PROFILE_USAGE_STATUSES:
        raise TextPolicyError("profile_usage_status 非法")
    selection_consumer = "activity_selection"
    profile_selection = {
        **profile_selection,
        "consumer": selection_consumer,
        "usage_status": profile_usage_status,
        "context_key": context_key,
        "response_profile_refs": list(response_profile_refs),
    }

    return {
        "protocol_version": TEXT_PROTOCOL_VERSION,
        "scope": dict(decision_scope),
        "learner_id": learner_id,
        "goal_id": goal_id,
        "concept_id": concept_id,
        "contract_id": contract_id,
        "contract_version": contract_version,
        "route_id": route_id,
        "route_version": route_version,
        "bound_verification_task_id": bound_verification_task_id,
        "verification_content_guard": verification_content_guard,
        "evidence_refs": list(evidence_refs),
        "domain": domain,
        "context_key": context_key,
        "comparison_gate": dict(comparison_gate),
        "task_difficulty": task_difficulty,
        "response_profile_refs": list(response_profile_refs),
        "profile_selection_status": profile_selection["status"],
        "profile_usage_status": profile_usage_status,
        "selection_consumer": selection_consumer,
        "profile_selection": profile_selection,
        "process_adaptation": process_adaptation,
        "process_cost_selection": {
            "status": (
                "over_estimate"
                if process_cost_over_estimate
                else "within_estimate"
                if process_refs
                else "not_measured"
            ),
            "estimated_minutes": float(estimated_practice_feedback_minutes),
            "measured_minutes": measured_practice_feedback_minutes,
            "selected_by_cost": repair_selection_basis == "measured_cost_alternative",
            "consumer": "activity_selection",
        },
        "repair_selection_basis": repair_selection_basis,
        "introduced_terms": introduced_terms,
        "knowledge_kind": knowledge_kind,
        "target_performance": target,
        "prior_knowledge_band": prior,
        "text_policy": "preferred_default",
        "text_sufficiency": text_sufficiency,
        "selection_status": selection_status,
        "activity": activity,
        "carrier": carrier,
        "text_format": text_format if carrier in TEXT_CARRIERS else None,
        "assistance_level": assistance,
        "reason_codes": reason_codes,
        "escalation": {
            "status": escalation_status,
            "target_medium": escalation_target,
            "affordance_reason": affordance_reason if escalation_status == "selected" else None,
        },
        "visual_support": {
            "status": "selected" if static_visual_reason is not None else "not_selected",
            "kind": (
                STATIC_VISUAL_KIND_BY_REASON[static_visual_reason]
                if static_visual_reason is not None
                else None
            ),
            "reason": static_visual_reason,
        },
    }


_GROUNDING_PLACEHOLDERS = {
    "", "todo", "tbd", "placeholder", "unknown", "idontknow", "idon'tknow",
    "不知道", "不清楚", "待解释", "待补充", "待填写", "待确认", "待完善",
    "稍后解释", "稍后补充", "未说明", "暂无",
}


def _grounding_text_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[\"'`“”‘’]", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip(
        " \t\r\n.,;:!?。，；：！？…()（）[]【】<>"
    )


def _validate_grounding_meaning(item: dict[str, str], index: int) -> None:
    """Reject a finite set of obvious non-definitions, not semantic inadequacy.

No minimum length is imposed. Passing this check does not establish that a
definition is true, sufficient, non-circular in general, or understood.
"""
    for field in ("what_it_is", "owner_scope", "role_here", "relation_direction"):
        key = _grounding_text_key(item[field])
        if key.replace(" ", "") in _GROUNDING_PLACEHOLDERS:
            raise TextPolicyError(f"term_grounding[{index}].{field} 不能用占位或未解释说明代替具体含义")
    term = _grounding_text_key(item["term"])
    definition = _grounding_text_key(item["what_it_is"])
    if not term:
        return
    escaped = re.escape(term)
    repetition_patterns = (
        escaped,
        rf"(?:所谓(?:的)?\s*)?{escaped}\s*[,，]?\s*(?:就是|是|即|指的是|指的就是|指|的意思是)\s*(?:一个|一种)?\s*{escaped}",
        rf"(?:(?:a|an|the) )?{escaped}\s+(?:is|means|refers to|is defined as)\s+(?:(?:a|an|the) )?{escaped}",
    )
    if any(re.fullmatch(pattern, definition) for pattern in repetition_patterns):
        raise TextPolicyError(f"term_grounding[{index}].what_it_is 不能只把术语重复为其自身；请说明具体含义")


def _validate_term_grounding(
    introduced_terms: list[str], value: Any
) -> list[dict[str, str]]:
    if not introduced_terms:
        if value not in (None, []):
            raise TextPolicyError("term_grounding 存在时必须在 introduced_terms 声明术语")
        return []
    if not isinstance(value, list):
        raise TextPolicyError("存在新术语时必须提供 term_grounding")
    grounded: list[dict[str, str]] = []
    required = ("term", "what_it_is", "owner_scope", "role_here", "relation_direction")
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise TextPolicyError(f"term_grounding[{index}] 必须是对象")
        grounded.append(
            {
                key: _nonempty_string(f"term_grounding[{index}].{key}", item.get(key))
                for key in required
            }
        )
    actual = [item["term"].casefold() for item in grounded]
    expected = [item.casefold() for item in introduced_terms]
    if sorted(actual) != sorted(expected) or len(actual) != len(expected):
        raise TextPolicyError("term_grounding 必须逐项覆盖 introduced_terms，且不得多出术语")
    for index, item in enumerate(grounded):
        _validate_grounding_meaning(item, index)
    # A declared new term cannot be explained using another declared term that
    # appears only later. This is a literal dependency check, not NLP mastery.
    for index, item in enumerate(grounded):
        definitions = " ".join(item[key] for key in required if key != "term").casefold()
        for later in grounded[index + 1:]:
            term = later["term"].casefold()
            pattern = re.escape(term)
            if term.isascii():
                pattern = r"(?<![A-Za-z0-9_])" + pattern + r"(?![A-Za-z0-9_])"
            if re.search(pattern, definitions):
                raise TextPolicyError(
                    f"术语 {item['term']} 的解释依赖尚未落地的 {later['term']}；先解释依赖或改用已知语言"
                )
    return grounded


def _validate_visual(decision: dict[str, Any], value: Any) -> dict[str, Any] | None:
    visual_support = decision.get("visual_support")
    if not isinstance(visual_support, dict):
        raise TextPolicyError("decision 缺少 visual_support")
    status = visual_support.get("status")
    if status == "not_selected":
        if value not in (None, {}):
            raise TextPolicyError("提供静态图示前必须声明 static_visual_reason")
        return None
    if status != "selected":
        raise TextPolicyError("visual_support.status 非法")
    if not isinstance(value, dict):
        raise TextPolicyError("已选择静态视觉支持，但没有提供具体 visual")
    expected_kind = _nonempty_string("visual_support.kind", visual_support.get("kind"))
    kind = _nonempty_string("visual.kind", value.get("kind"))
    if kind != expected_kind:
        raise TextPolicyError("visual.kind 与 visual_support.kind 不一致")
    if value.get("labels_grounded") is not True:
        raise TextPolicyError("visual 必须确认所有标签均已落地")
    if value.get("relation_direction_marked") is not True:
        raise TextPolicyError("visual 必须明确标出关系或变化方向")
    asset = _nonempty_string("visual.asset", value.get("asset"))
    if asset.casefold() in {"见下图", "待生成", "todo", "placeholder", "占位图"}:
        raise TextPolicyError("visual.asset 不能是占位说明，必须提供实际可呈现内容")
    return {
        "kind": kind,
        "asset": asset,
        "observation_focus": _nonempty_string(
            "visual.observation_focus", value.get("observation_focus")
        ),
        "text_equivalent": _nonempty_string(
            "visual.text_equivalent", value.get("text_equivalent")
        ),
        "learner_reading_task": _nonempty_string(
            "visual.learner_reading_task", value.get("learner_reading_task")
        ),
    }


def project_delivery_plan(decision: dict[str, Any], content: dict[str, Any]) -> dict[str, Any]:
    """Build the user object from an allowlist; never serialize the decision wholesale."""

    if not isinstance(decision, dict) or decision.get("protocol_version") != TEXT_PROTOCOL_VERSION:
        raise TextPolicyError("decision 不是当前文字协议的决策")
    bound_task_id = _nonempty_string(
        "decision.bound_verification_task_id",
        decision.get("bound_verification_task_id"),
    )
    verification_guard = _validated_verification_content_guard(
        "decision.verification_content_guard",
        decision.get("verification_content_guard"),
        bound_task_id,
    )
    if not isinstance(content, dict):
        raise TextPolicyError("delivery content 必须是对象")
    if "verification_task" in content:
        raise TextPolicyError(
            "初始 delivery_plan 不得包含未见验证题；请使用 verification_rule，教学过程后再投影题面"
        )
    carrier = _enum("carrier", decision.get("carrier"), CARRIERS)
    introduced_terms = _unique_string_list(
        "decision.introduced_terms", decision.get("introduced_terms", [])
    )
    term_grounding = _validate_term_grounding(
        introduced_terms, content.get("term_grounding")
    )
    visual = _validate_visual(decision, content.get("visual"))
    medium = (
        TEXT_WITH_VISUAL_LABELS[carrier]
        if visual is not None and carrier in TEXT_CARRIERS
        else MEDIUM_LABELS[carrier]
    )
    process_adaptation = decision.get("process_adaptation")
    process_status = (
        process_adaptation.get("status")
        if isinstance(process_adaptation, dict)
        else "no_process_evidence"
    )
    feedback_rule = content.get("feedback_rule")
    next_step = _validated_next_step(content.get("next_step"))
    process_feedback_code = (
        process_adaptation.get("feedback_rule")
        if isinstance(process_adaptation, dict)
        else None
    )
    process_next_action = (
        process_adaptation.get("next_action")
        if isinstance(process_adaptation, dict)
        else None
    )
    if (
        process_feedback_code in PROCESS_FEEDBACK_RULE_PUBLIC
        and process_next_action in PROCESS_NEXT_ACTION_PUBLIC
    ):
        feedback_rule = PROCESS_FEEDBACK_RULE_PUBLIC[process_feedback_code]
        next_step = {
            "instruction": PROCESS_NEXT_ACTION_PUBLIC[process_next_action],
            "when": None,
        }
    elif process_status in PROCESS_FEEDBACK_PUBLIC:
        feedback_rule = PROCESS_FEEDBACK_PUBLIC[process_status]
        next_step = {
            "instruction": PROCESS_NEXT_STEP_PUBLIC[process_status],
            "when": None,
        }
    projected = {
        "learning_objective": content.get("learning_objective"),
        "method_label": content.get("method_label"),
        "medium": medium,
        "orientation": content.get("orientation"),
        "term_grounding": term_grounding,
        "explanation": content.get("explanation"),
        "example": content.get("example"),
        "visual": visual,
        "learner_task": content.get("learner_task"),
        "response_format": content.get("response_format"),
        "feedback_rule": feedback_rule,
        "verification_rule": content.get("verification_rule"),
        "success_criteria": content.get("success_criteria"),
        "next_step": next_step,
    }
    for key, value in projected.items():
        _validate_user_value(value, key)
    required_strings = (
        "learning_objective",
        "method_label",
        "orientation",
        "explanation",
        "example",
        "learner_task",
        "response_format",
        "feedback_rule",
        "verification_rule",
        "success_criteria",
    )
    for key in required_strings:
        _nonempty_string(key, projected[key])
    _assert_no_reserved_verification_overlap(projected, verification_guard)
    return {key: projected[key] for key in USER_DELIVERY_FIELDS}


def _project_verification_task_from_committed_process(
    decision: dict[str, Any],
    process_evaluation: dict[str, Any],
    content: dict[str, Any],
) -> dict[str, str]:
    """Low-level projection primitive for vault_tool's committed-evidence gate.

    This private helper does not prove persistence.  Production callers must
    use vault_tool.project_verification_task_from_vault(), which resolves the
    process evidence from a validated Vault before reaching this primitive.
    """

    if not isinstance(decision, dict) or decision.get("protocol_version") != TEXT_PROTOCOL_VERSION:
        raise TextPolicyError("decision 不是当前文字协议的决策")
    if not isinstance(process_evaluation, dict):
        raise TextPolicyError("process_evaluation 必须是 evaluate_text_unit 的输出")
    required_process_values = {
        "protocol_version": TEXT_PROTOCOL_VERSION,
        "observation_kind": "teaching_process",
        "evidence_class": "teaching_process",
        "qualification_status": "teaching_process_recorded",
        "unit_status": "teaching_process",
        "mastery_eligible": False,
        "mastery_update_allowed": False,
        "next_action": "continue_to_unseen_verification",
    }
    for field, expected in required_process_values.items():
        if process_evaluation.get(field) != expected:
            raise TextPolicyError("只有教学过程 evidence 已接受后才能公开验证题")
    decision_scope = _validated_scope("decision.scope", decision)
    process_scope = _validated_scope(
        "process_evaluation.scope", process_evaluation.get("scope")
    )
    if process_scope != decision_scope:
        raise TextPolicyError("教学过程 evidence 与当前教学决策作用域不一致")
    decision_route_id = _nonempty_string("decision.route_id", decision.get("route_id"))
    decision_route_version = _integer(
        "decision.route_version", decision.get("route_version"), minimum=1
    )
    process_route = process_evaluation.get("route_binding")
    if not isinstance(process_route, dict):
        raise TextPolicyError("教学过程 evidence 缺少 route_binding")
    _exact_keys("process_evaluation.route_binding", process_route, {"route_id", "route_version"})
    if (
        _nonempty_string("process route_id", process_route.get("route_id"))
        != decision_route_id
        or _integer(
            "process route_version", process_route.get("route_version"), minimum=1
        )
        != decision_route_version
    ):
        raise TextPolicyError("教学过程 evidence 与当前 candidate_step route/version 不一致")
    if process_evaluation.get("failures") != []:
        raise TextPolicyError("教学过程 evidence 仍有资格错误，不能公开验证题")
    if decision.get("selection_status") == "blocked":
        raise TextPolicyError("当前教学决策被先修阻塞，不能公开验证题")
    if not isinstance(content, dict):
        raise TextPolicyError("verification content 必须是对象")
    _exact_keys(
        "verification content",
        content,
        {"task_id", "verification_task", "response_format", "success_criteria"},
    )
    task_id = _nonempty_string("verification.task_id", content.get("task_id"))
    bound_task_id = _nonempty_string(
        "decision.bound_verification_task_id",
        decision.get("bound_verification_task_id"),
    )
    verification_guard = _validated_verification_content_guard(
        "decision.verification_content_guard",
        decision.get("verification_content_guard"),
        bound_task_id,
    )
    if task_id != bound_task_id:
        raise TextPolicyError("验证题 task_id 与 candidate_step 绑定任务不一致")
    projected = {
        "verification_task": _nonempty_string(
            "verification_task", content.get("verification_task")
        ),
        "response_format": _nonempty_string(
            "verification.response_format", content.get("response_format")
        ),
        "success_criteria": _nonempty_string(
            "verification.success_criteria", content.get("success_criteria")
        ),
    }
    _assert_revealed_prompt_matches_guard(
        projected["verification_task"], verification_guard
    )
    for key, value in projected.items():
        _validate_user_value(value, key)
    return projected


def _normalized_observation_field(field: str, value: Any) -> Any:
    if field == "result":
        return _enum(
            field,
            value,
            {"pass", "partial", "fail", "conflicted", "not_tested"},
        )
    if field in {"observed_at", "scheduled_for"}:
        return _aware_timestamp(field, value)
    if field in {
        "learner_response_present",
        "verification_unseen",
        "answer_revealed_before_first_attempt",
        "response_correct",
        "mastery_eligible",
    }:
        if not isinstance(value, bool):
            raise TextPolicyError(f"{field} 必须是布尔值")
        return value
    if field in {
        "teaching_item_id",
        "verification_item_id",
        "verification_task_id",
        "bound_verification_task_id",
        "route_id_at_observation",
        "context_key",
        "decision_fingerprint_at_observation",
        "teaching_delivery_fingerprint_at_observation",
        "baseline_evidence_id",
        "retention_task_id",
        "error_signature",
    }:
        normalized = _nonempty_string(field, value)
        if field == "teaching_delivery_fingerprint_at_observation" and not re.fullmatch(
            r"[0-9a-f]{64}", normalized
        ):
            raise TextPolicyError(f"{field} 必须是 64 位小写 SHA-256")
        return normalized
    if field == "activity":
        return _enum(field, value, PROFILE_ACTIVITIES)
    if field == "carrier":
        return _enum(field, value, CARRIERS)
    if field in {"assistance_level", "verification_assistance_level"}:
        return _enum(field, value, set(ASSISTANCE_ORDER))
    if field == "independence":
        return _enum(field, value, {"independent", "hinted", "guided", "not_observed"})
    if field == "demonstrates":
        return _unique_string_list(field, value)
    if field == "observation_confidence":
        return _enum(field, value, {"low", "medium", "high"})
    if field == "explanation_quality":
        return _enum(
            field, value, {"pass", "partial", "fail", "conflicted", "not_tested"}
        )
    if field in {
        "immediate_performance",
        "near_transfer",
        "delayed_retention",
    }:
        return _number(field, value, minimum=0, maximum=1)
    if field in {"elapsed_seconds"}:
        return _number(field, value, minimum=0)
    if field in {"attempts"}:
        return _integer(field, value, minimum=1)
    if field == "route_version_at_observation":
        return _integer(field, value, minimum=1)
    if field in {"hint_count", "retention_delay_days"}:
        return _integer(field, value, minimum=0)
    if field == "self_reported_effort":
        return _number(field, value, minimum=1, maximum=7)
    raise TextPolicyError(f"未定义 observation 字段: {field}")


def prepare_observation_update(observation: dict[str, Any]) -> dict[str, Any]:
    """Allow only traceable fields with an explicit, field-specific consumer."""

    if not isinstance(observation, dict):
        raise TextPolicyError("observation 必须是对象")
    fields = observation.get("fields")
    if not isinstance(fields, dict):
        raise TextPolicyError("observation.fields 必须是对象")
    expected_scope = _validated_scope("observation.scope", observation.get("scope"))
    phase = _enum(
        "observation.phase",
        observation.get("phase"),
        set(PHASE_VAULT_FIELD_CONSUMERS),
    )
    phase_field_consumers = PHASE_VAULT_FIELD_CONSUMERS[phase]

    prepared: dict[str, dict[str, Any]] = {}
    dropped: list[dict[str, str]] = []
    consumer_index: dict[str, list[str]] = {}
    for field, binding in fields.items():
        if not isinstance(field, str):
            dropped.append({"field": str(field), "reason": "field_name_invalid"})
            continue
        if field not in FIELD_CONSUMER_ALLOWLIST:
            dropped.append({"field": field, "reason": "field_not_allowlisted"})
            continue
        allowed_consumers = (
            phase_field_consumers.get(field, set())
            if field in VAULT_EVIDENCE_FIELD_NAMES
            else FIELD_CONSUMER_ALLOWLIST[field]
        )
        if not allowed_consumers:
            dropped.append({"field": field, "reason": "field_not_used_in_phase"})
            continue
        if not isinstance(binding, dict) or "value" not in binding:
            dropped.append({"field": field, "reason": "binding_invalid"})
            continue
        try:
            consumers = _unique_string_list(
                f"fields.{field}.consumers", binding.get("consumers")
            )
            if not consumers or not set(consumers).issubset(allowed_consumers):
                raise TextPolicyError("consumer_not_allowed")
            scope = _validated_scope(
                f"fields.{field}.scope",
                binding.get("scope", observation.get("scope")),
            )
            if scope != expected_scope:
                raise TextPolicyError("scope_mismatch")
            source_refs = _unique_string_list(
                f"fields.{field}.source_refs",
                binding.get("source_refs", observation.get("source_refs")),
            )
            if not source_refs:
                raise TextPolicyError("source_refs_empty")
            observed_at = _aware_timestamp(
                f"fields.{field}.observed_at",
                binding.get("observed_at", observation.get("observed_at")),
            )
            validity = _enum(
                f"fields.{field}.validity",
                binding.get("validity", observation.get("validity")),
                {"valid", "provisional", "stale"},
            )
            if validity == "stale":
                raise TextPolicyError("stale_not_committable")
            confidence_value = binding.get(
                "confidence", observation.get("confidence", "not_estimated")
            )
            confidence: float | str
            if confidence_value == "not_estimated":
                confidence = "not_estimated"
            else:
                confidence = _number(
                    f"fields.{field}.confidence",
                    confidence_value,
                    minimum=0,
                    maximum=1,
                )
            if validity != "valid" and {
                "verification_gate",
                "contract_recompute",
                "retention_recompute",
            }.intersection(consumers):
                raise TextPolicyError("validity_insufficient_for_mastery_consumer")
            normalized = _normalized_observation_field(field, binding["value"])
        except TextPolicyError as exc:
            dropped.append({"field": field, "reason": str(exc)})
            continue
        prepared[field] = {
            "value": normalized,
            "consumers": consumers,
            "scope": scope,
            "source_refs": source_refs,
            "observed_at": observed_at,
            "validity": validity,
            "confidence": confidence,
        }
        for consumer in consumers:
            consumer_index.setdefault(consumer, []).append(field)

    for consumer in consumer_index:
        consumer_index[consumer].sort()
    return {
        "protocol_version": TEXT_PROTOCOL_VERSION,
        "phase": phase,
        "commit_status": "ready" if prepared else "nothing_to_commit",
        "commit_allowed": bool(prepared),
        "prepared_fields": prepared,
        "consumer_index": dict(sorted(consumer_index.items())),
        "dropped_fields": dropped,
    }


def evaluate_text_unit(
    record: dict[str, Any], decision: dict[str, Any]
) -> dict[str, Any]:
    """Classify process evidence and qualified unseen A0 verification evidence."""

    if not isinstance(record, dict):
        raise TextPolicyError("record 必须是对象")
    if (
        not isinstance(decision, dict)
        or decision.get("protocol_version") != TEXT_PROTOCOL_VERSION
    ):
        raise TextPolicyError("decision 不是当前文字协议的决策")
    decision_scope = _validated_scope("decision.scope", decision)
    decision_route_id = _nonempty_string(
        "decision.route_id", decision.get("route_id")
    )
    decision_route_version = _integer(
        "decision.route_version", decision.get("route_version"), minimum=1
    )
    decision_verification_task_id = _nonempty_string(
        "decision.bound_verification_task_id",
        decision.get("bound_verification_task_id"),
    )
    observation_kind = _enum(
        "observation_kind",
        record.get("observation_kind"),
        {"teaching_process", "verification"},
    )
    qualification_failures: list[str] = []
    performance_failures: list[str] = []
    scope: dict[str, Any] | None = None

    try:
        scope = _validated_scope("scope", record.get("scope"))
        evidence_scope = _validated_scope(
            "evidence_scope", record.get("evidence_scope")
        )
        if any(scope[key] != evidence_scope[key] for key in REQUIRED_SCOPE_KEYS):
            qualification_failures.append("evidence_scope_mismatch")
        if any(scope[key] != decision_scope[key] for key in REQUIRED_SCOPE_KEYS):
            qualification_failures.append("current_decision_scope_mismatch")
    except TextPolicyError:
        qualification_failures.append("evidence_scope_mismatch")

    route_binding: dict[str, Any] | None = None
    route_id_at_observation = record.get("route_id_at_observation")
    route_version_at_observation = record.get("route_version_at_observation")
    bound_route_id = record.get("bound_route_id")
    bound_route_version = record.get("bound_route_version")
    route_values_valid = (
        isinstance(route_id_at_observation, str)
        and bool(route_id_at_observation.strip())
        and isinstance(bound_route_id, str)
        and bool(bound_route_id.strip())
        and isinstance(route_version_at_observation, int)
        and not isinstance(route_version_at_observation, bool)
        and route_version_at_observation >= 1
        and isinstance(bound_route_version, int)
        and not isinstance(bound_route_version, bool)
        and bound_route_version >= 1
    )
    if not route_values_valid:
        qualification_failures.append("verification_route_unbound")
    elif (
        route_id_at_observation.strip() != decision_route_id
        or route_version_at_observation != decision_route_version
        or bound_route_id.strip() != decision_route_id
        or bound_route_version != decision_route_version
    ):
        qualification_failures.append("verification_route_binding_mismatch")
    else:
        route_binding = {
            "route_id": decision_route_id,
            "route_version": decision_route_version,
        }

    if observation_kind == "teaching_process":
        failures = list(dict.fromkeys(qualification_failures))
        accepted = not failures
        return {
            "protocol_version": TEXT_PROTOCOL_VERSION,
            "scope": scope if accepted else None,
            "route_binding": route_binding if accepted else None,
            "observation_kind": "teaching_process",
            "evidence_class": "teaching_process",
            "qualification_status": (
                "teaching_process_recorded" if accepted else "teaching_process_rejected"
            ),
            "verification_outcome": "not_applicable",
            "unit_status": "teaching_process" if accepted else "not_passed",
            "qualification_failures": failures,
            "performance_failures": [],
            "failures": failures,
            "mastery_eligible": False,
            "mastery_update_allowed": False,
            "next_action": (
                "continue_to_unseen_verification" if accepted else "repair_or_replan"
            ),
        }

    if record.get("learner_response_present") is not True:
        qualification_failures.append("missing_independent_response")
    teaching_item_id = record.get("teaching_item_id")
    verification_item_id = record.get("verification_item_id")
    if not isinstance(teaching_item_id, str) or not teaching_item_id.strip():
        qualification_failures.append("missing_teaching_item_id")
    if not isinstance(verification_item_id, str) or not verification_item_id.strip():
        qualification_failures.append("missing_verification_item_id")
    if (
        isinstance(teaching_item_id, str)
        and isinstance(verification_item_id, str)
        and teaching_item_id.strip()
        and teaching_item_id.strip() == verification_item_id.strip()
    ):
        qualification_failures.append("verification_item_reused")
    if record.get("verification_unseen") is not True:
        qualification_failures.append("verification_not_unseen")
    if record.get("answer_revealed_before_first_attempt") is not False:
        qualification_failures.append("answer_revealed_early")
    if record.get("verification_assistance_level") != "A0":
        qualification_failures.append("verification_not_independent")
    verification_task_id = record.get("verification_task_id")
    bound_verification_task_id = record.get("bound_verification_task_id")
    if not isinstance(verification_task_id, str) or not verification_task_id.strip():
        qualification_failures.append("verification_task_unbound")
    elif (
        not isinstance(bound_verification_task_id, str)
        or not bound_verification_task_id.strip()
        or verification_task_id.strip() != decision_verification_task_id
        or bound_verification_task_id.strip() != decision_verification_task_id
    ):
        qualification_failures.append("verification_task_binding_mismatch")

    required_capabilities: list[str] = []
    demonstrated_capabilities: list[str] = []
    try:
        required_capabilities = _unique_string_list(
            "required_capabilities", record.get("required_capabilities")
        )
        demonstrated_capabilities = _unique_string_list(
            "demonstrated_capabilities", record.get("demonstrated_capabilities")
        )
        if not required_capabilities:
            raise TextPolicyError("required_capabilities_empty")
    except TextPolicyError:
        qualification_failures.append("contract_capability_binding_invalid")
    else:
        if not set(required_capabilities).issubset(demonstrated_capabilities):
            performance_failures.append("contract_capability_not_covered")

    response_correct = record.get("response_correct")
    if not isinstance(response_correct, bool):
        qualification_failures.append("verification_result_invalid")
    elif response_correct is False:
        performance_failures.append("verification_incorrect")

    explanation_required = record.get("explanation_required", False)
    if not isinstance(explanation_required, bool):
        qualification_failures.append("explanation_requirement_invalid")
    elif explanation_required and record.get("explanation_quality") != "pass":
        performance_failures.append("explanation_not_passed")

    near_transfer_required = record.get("near_transfer_required", False)
    if not isinstance(near_transfer_required, bool):
        qualification_failures.append("near_transfer_requirement_invalid")
    elif near_transfer_required:
        score = record.get("near_transfer")
        threshold = record.get("near_transfer_threshold")
        if (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not isinstance(threshold, (int, float))
            or isinstance(threshold, bool)
            or not 0 <= float(score) <= 1
            or not 0 <= float(threshold) <= 1
            or float(score) < float(threshold)
        ):
            performance_failures.append("near_transfer_not_passed")

    qualification_failures = list(dict.fromkeys(qualification_failures))
    performance_failures = list(dict.fromkeys(performance_failures))
    mastery_eligible = not qualification_failures
    if not mastery_eligible:
        verification_outcome = "unqualified"
        next_action = "repeat_independent_verification_or_repair"
    elif performance_failures:
        verification_outcome = "qualified_fail"
        next_action = "evaluate_mastery_contract_then_repair"
    else:
        verification_outcome = "qualified_pass"
        next_action = "evaluate_mastery_contract"
    failures = qualification_failures + performance_failures
    evidence_class = (
        "qualified_unseen_a0_verification"
        if mastery_eligible
        else "unqualified_verification"
    )
    return {
        "protocol_version": TEXT_PROTOCOL_VERSION,
        "scope": scope if mastery_eligible else None,
        "route_binding": route_binding if mastery_eligible else None,
        "observation_kind": "verification",
        "evidence_class": evidence_class,
        "qualification_status": evidence_class,
        "verification_outcome": verification_outcome,
        "unit_status": "passed" if verification_outcome == "qualified_pass" else "not_passed",
        "qualification_failures": qualification_failures,
        "performance_failures": performance_failures,
        "failures": failures,
        "mastery_eligible": mastery_eligible,
        "mastery_update_allowed": False,
        "next_action": next_action,
    }
