#!/usr/bin/env python3
"""Create, validate, recover, and visualize an Understanding Cost demo Vault.

The tool intentionally uses only the Python standard library. It treats Markdown
notes and append-only evidence as facts; index.json and focus_z are rebuildable
derived data.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


SCHEMA = "uc-demo/0.2"
ROUTE_FILE = ".understanding-cost-route.json"
MANIFEST_REL = Path("00-system/manifest.json")
INDEX_REL = Path("00-system/index.json")
ROUTER_REL = Path("00-system/ROUTER.md")
ROUTE_BINDINGS_REL = Path("00-system/route-bindings.json")
ROUTE_BINDING_SCHEMA = "uc-route-bindings/0.2"
TEACHING_RESOLUTION_SCHEMA = "uc-active-teaching-resolution/0.2"
TEACHING_DELIVERY_SCHEMA = "uc-teaching-delivery/0.1"
RETENTION_SCHEDULE_SCHEMA = "uc-retention-schedule/0.1"
VERIFICATION_OPEN_SCHEMA = "uc-verification-open/0.1"
FOCUS_SNAPSHOT_SCHEMA = "uc-focus-snapshot/0.4"
VAULT_LOCK_TIMEOUT_ENV = "UNDERSTANDING_COST_LOCK_TIMEOUT_SECONDS"
DEFAULT_VAULT_LOCK_TIMEOUT_SECONDS = 10.0
MAX_VAULT_LOCK_TIMEOUT_SECONDS = 60.0
COST_DIMENSIONS = (
    "diagnosis",
    "prerequisites",
    "core_learning",
    "practice_feedback",
    "verification",
    "maintenance_relearning",
)
PROCESS_REFRESH_FIELDS = (
    "resolved_process_refs",
    "resolved_process_status",
    "resolved_process_feedback_rule",
    "resolved_process_next_action",
    "resolved_process_cost",
    "resolved_process_cost_selection",
    "resolved_cost_vector",
    "resolved_cost_basis",
    "resolved_same_error_count",
    "resolved_text_variants_tried",
    "resolved_latest_teaching_item_id",
    "resolved_max_observed_assistance_level",
    "resolved_process_support_load",
)
SEED_PATH = Path(__file__).resolve().parent.parent / "assets" / "demo-seed.json"
ROUTE_TRUST_LEVEL_VALUES = {
    "local_chain_only",
    "trusted_seed_source",
    "trusted_seed_prefix_local_extension",
}

NODE_TYPES = {
    "domain",
    "concept",
    "learner",
    "state",
    "goal",
    "session",
    "evidence",
    "resource",
    "intervention",
    "teaching_delivery",
    "retention_schedule",
    "verification_open",
    "focus_snapshot",
    "router",
}
RELATION_TYPES = {
    "requires",
    "part_of",
    "related_to",
    "contrasts_with",
    "targets",
    "about",
    "supported_by",
    "for_learner",
    "for_goal",
    "implements",
    "uses",
    "generated",
    "derived_from",
    "supersedes",
    "teaches",
    "scheduled_by",
}
RELATION_SIGNATURES: dict[str, tuple[set[str], set[str]]] = {
    "requires": ({"concept", "resource"}, {"concept"}),
    "part_of": ({"concept"}, {"concept", "domain"}),
    "related_to": ({"concept"}, {"concept"}),
    "contrasts_with": ({"concept"}, {"concept"}),
    "targets": ({"goal"}, {"concept"}),
    "about": (
        {
            "state",
            "evidence",
            "focus_snapshot",
            "teaching_delivery",
            "retention_schedule",
            "verification_open",
        },
        {"concept"},
    ),
    "supported_by": ({"state"}, {"evidence"}),
    "for_learner": (
        {
            "state",
            "goal",
            "intervention",
            "session",
            "focus_snapshot",
            "teaching_delivery",
            "retention_schedule",
            "verification_open",
        },
        {"learner"},
    ),
    "for_goal": (
        {
            "state",
            "session",
            "focus_snapshot",
            "teaching_delivery",
            "retention_schedule",
            "verification_open",
        },
        {"goal"},
    ),
    "implements": ({"intervention"}, {"goal"}),
    "uses": ({"intervention", "teaching_delivery", "verification_open"}, {"resource"}),
    "teaches": ({"resource"}, {"concept"}),
    "generated": ({"session"}, {"evidence"}),
    "derived_from": (NODE_TYPES, {"session", "evidence"}),
    "supersedes": (NODE_TYPES, NODE_TYPES),
    "scheduled_by": ({"verification_open"}, {"retention_schedule"}),
}
MASTERY_VALUES = {"unknown", "none", "partial", "mastered"}
BOUNDARY_VALUES = {
    "interior",
    "inner_fringe",
    "outer_fringe",
    "blocked",
    "out_of_domain",
    "unknown",
}
CONFIDENCE_VALUES = {"low", "medium", "high"}
OBSERVATION_VALIDITY_VALUES = {"valid", "provisional", "stale"}
PRIVACY_VALUES = {"shared", "private", "sensitive"}
ASSISTANCE_VALUES = {"A0", "A1", "A2", "A3", "A4"}
KNOWLEDGE_KIND_VALUES = {
    "declarative",
    "rule",
    "causal_structure",
    "symbolic_procedure",
    "diagnosis",
    "transfer",
    "motor_spatial",
}
TEXT_PROTOCOL_VERSION = "text-demo-v0.5"
ROUTE_STATUS_VALUES = {"active", "paused", "completed", "superseded", "abandoned"}
EVIDENCE_RESULT_VALUES = {"pass", "partial", "fail", "conflicted", "not_tested"}
INDEPENDENCE_VALUES = {"independent", "hinted", "guided", "not_observed"}
EXPLANATION_QUALITY_VALUES = {"pass", "partial", "fail", "conflicted", "not_tested"}
MEASUREMENT_PENDING_VALUES = {"not_required", "pending", "not_tested"}
EVIDENCE_PHASE_VALUES = {"diagnostic", "teaching_process", "verification", "retention"}
IMMEDIATE_CONTRACT_STATUS_VALUES = {"not_tested", "in_progress", "not_met", "met"}
CONTRACT_STATUS_VALUES = {"not_tested", "in_progress", "not_met", "met"}
RETENTION_STATUS_VALUES = {
    "not_required",
    "not_started",
    "pending",
    "due",
    "failed",
    "conflicted",
    "invalid_contract",
}
STATE_NEXT_ACTION_VALUES = {
    "collect_immediate_verification",
    "immediate_repair",
    "schedule_retention",
    "wait_until_scheduled_for",
    "issue_delayed_verification",
    "retention_repair",
    "none",
}
CARRIER_VALUES = {"text_document", "text_dialogue", "text_hybrid", "video", "interactive"}
VALUE_CONSUMER_VALUES = {
    "boundary_update",
    "route_selection",
    "anchor_selection",
    "activity_selection",
    "representation_selection",
    "feedback_selection",
    "verification_gate",
    "contract_recompute",
    "retention_recompute",
    "recovery",
    "inspect_view",
    "focus_priority",
    "experiment_evaluation",
    "event_identity_guard",
    "process_trace",
    "process_evidence_gate",
    "diagnostic_gate",
    "diagnostic_trace",
    "teaching_delivery_guard",
    "derived_assertion_guard",
}
EVIDENCE_KIND_BY_PHASE: dict[str, set[str]] = {
    "diagnostic": {"diagnostic_probe"},
    "teaching_process": {"explanation", "prediction", "application", "teaching_attempt"},
    "verification": {"independent_performance"},
    "retention": {"delayed_transfer"},
}

# Evidence identity/provenance fields are record-level gates, not learning
# outcomes.  Keep them separate from field_bindings so an envelope value cannot
# masquerade as a measured result while still making every persisted metadata
# field's real validator explicit.
EVIDENCE_ENVELOPE_GUARD_VALUES = {
    "phase_schema_guard",
    "scope_guard",
    "source_provenance_guard",
    "observation_validity_guard",
    "route_binding_guard",
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
EVIDENCE_ENVELOPE_FIELDS = set().union(
    *(set(value) for value in EVIDENCE_ENVELOPE_GUARDS_BY_PHASE.values())
)

# These are executable phase contracts, not documentation labels.  A value is
# persisted only when this exact phase has a real downstream reader for it.
DIAGNOSTIC_FIELD_CONSUMERS: dict[str, set[str]] = {
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

TEACHING_PROCESS_FIELD_CONSUMERS: dict[str, set[str]] = {
    "activity": {
        "activity_selection",
        "representation_selection",
        "feedback_selection",
        "teaching_delivery_guard",
    },
    "carrier": {
        "activity_selection",
        "representation_selection",
        "feedback_selection",
        "teaching_delivery_guard",
    },
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
    "observed_at": {
        "verification_gate",
        "feedback_selection",
        "activity_selection",
        "representation_selection",
        "teaching_delivery_guard",
        "event_identity_guard",
    },
}

VERIFICATION_FIELD_CONSUMERS: dict[str, set[str]] = {
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

RETENTION_FIELD_CONSUMERS: dict[str, set[str]] = {
    **VERIFICATION_FIELD_CONSUMERS,
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
    "observed_at": {
        "contract_recompute",
        "retention_recompute",
        "recovery",
        "activity_selection",
        "boundary_update",
    },
}

PHASE_FIELD_CONSUMERS: dict[str, dict[str, set[str]]] = {
    "diagnostic": DIAGNOSTIC_FIELD_CONSUMERS,
    "teaching_process": TEACHING_PROCESS_FIELD_CONSUMERS,
    "verification": VERIFICATION_FIELD_CONSUMERS,
    "retention": RETENTION_FIELD_CONSUMERS,
}
EVIDENCE_FIELD_CONSUMERS: dict[str, set[str]] = {
    field: set().union(
        *(phase_map.get(field, set()) for phase_map in PHASE_FIELD_CONSUMERS.values())
    )
    for field in sorted(
        set().union(*(set(phase_map) for phase_map in PHASE_FIELD_CONSUMERS.values()))
    )
}
EVIDENCE_BINDING_FIELDS = set(EVIDENCE_FIELD_CONSUMERS)

# ``append-evidence`` accepts only observations and explicit event bindings.
# Authority/cache fields (schema, provenance, route binding, confidence,
# mastery eligibility, consumers and field bindings) are always derived from
# the validated Vault and therefore cannot be supplied by a caller.
APPEND_EVIDENCE_RAW_FIELDS = {
    "id",
    "summary",
    "learner_id",
    "goal_id",
    "concept_id",
    "contract_id",
    "contract_version",
    "phase",
    "carrier",
    "teaching_item_id",
    "teaching_delivery_fingerprint_at_observation",
    "verification_item_id",
    "verification_unseen",
    "answer_revealed_before_first_attempt",
    "verification_task_id",
    "bound_verification_task_id",
    "route_id_at_observation",
    "route_version_at_observation",
    "decision_fingerprint_at_observation",
    "observation_validity",
    "evidence_kind",
    "demonstrates",
    "result",
    "independence",
    "assistance_level",
    "activity",
    "error_signature",
    "elapsed_seconds",
    "attempts",
    "hint_count",
    "immediate_performance",
    "near_transfer",
    "delayed_retention",
    "response_correct",
    "explanation_quality",
    "self_reported_effort",
    "baseline_evidence_id",
    "retention_task_id",
    "scheduled_for",
    "observed_at",
}
FOCUS_MODEL_VERSION = "focus-cone-agent-v0.3"
FOCUS_PURPOSE_VALUES = {"residual_candidate_order", "inspect_view", "experiment_evaluation"}
FOCUS_SELECTION_BASIS_VALUES = {
    "focus",
    "route_default",
    "diagnose_information_gain",
    "cost_unresolved",
    "stable_tie_break",
    "not_used",
}
SKIP_DIRS = {".git", ".obsidian", "node_modules", "__pycache__", ".venv", "venv"}

FRONTMATTER_RE = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", re.DOTALL)
RELATION_RE = re.compile(
    r"^\s*-\s*([a-z_]+):\s*\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]\s*$",
    re.MULTILINE,
)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")


class VaultError(RuntimeError):
    """A user-actionable vault error."""


_VAULT_THREAD_LOCKS_GUARD = threading.Lock()
_VAULT_THREAD_LOCKS: dict[str, threading.RLock] = {}
_VAULT_LOCK_DEPTH = threading.local()


def canonical_vault_path(vault: Path) -> str:
    """Return one process- and platform-stable identity for a Vault path."""

    return os.path.normcase(str(Path(vault).expanduser().resolve(strict=False)))


def vault_lock_path(vault: Path) -> Path:
    """Return the external lock file for a canonical Vault identity."""

    identity = canonical_vault_path(vault)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / "understanding-cost-vault-locks" / f"{digest}.lock"


def configured_vault_lock_timeout() -> float:
    raw = os.environ.get(VAULT_LOCK_TIMEOUT_ENV)
    if raw is None:
        return DEFAULT_VAULT_LOCK_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise VaultError(
            f"{VAULT_LOCK_TIMEOUT_ENV} 必须是 0–{MAX_VAULT_LOCK_TIMEOUT_SECONDS:g} 秒的有限数值"
        ) from exc
    if not math.isfinite(value) or value < 0 or value > MAX_VAULT_LOCK_TIMEOUT_SECONDS:
        raise VaultError(
            f"{VAULT_LOCK_TIMEOUT_ENV} 必须是 0–{MAX_VAULT_LOCK_TIMEOUT_SECONDS:g} 秒的有限数值"
        )
    return value


def _try_acquire_process_lock(handle: Any) -> bool:
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _release_process_lock(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def vault_transaction_lock(
    vault: Path, *, timeout_seconds: float | None = None
) -> Iterable[Path]:
    """Hold an exclusive, re-entrant, cross-process lock outside the Vault."""

    identity = canonical_vault_path(vault)
    timeout = (
        configured_vault_lock_timeout()
        if timeout_seconds is None
        else float(timeout_seconds)
    )
    if not math.isfinite(timeout) or timeout < 0 or timeout > MAX_VAULT_LOCK_TIMEOUT_SECONDS:
        raise VaultError(
            f"Vault 事务锁 timeout 必须是 0–{MAX_VAULT_LOCK_TIMEOUT_SECONDS:g} 秒的有限数值"
        )
    deadline = time.monotonic() + timeout
    with _VAULT_THREAD_LOCKS_GUARD:
        thread_lock = _VAULT_THREAD_LOCKS.setdefault(identity, threading.RLock())
    if not thread_lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
        raise VaultError(f"Vault 事务锁超时，未写入任何数据: {identity}")

    depths = getattr(_VAULT_LOCK_DEPTH, "depths", None)
    if depths is None:
        depths = {}
        _VAULT_LOCK_DEPTH.depths = depths
    if depths.get(identity, 0) > 0:
        depths[identity] += 1
        try:
            yield vault_lock_path(vault)
        finally:
            depths[identity] -= 1
            thread_lock.release()
        return

    lock_file = vault_lock_path(vault)
    handle = None
    acquired = False
    try:
        try:
            lock_file.parent.mkdir(parents=True, exist_ok=True)
            handle = lock_file.open("a+b", buffering=0)
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
        except OSError as exc:
            raise VaultError(f"Vault 事务锁无法创建，未写入任何数据: {exc}") from exc
        while True:
            acquired = _try_acquire_process_lock(handle)
            if acquired:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise VaultError(f"Vault 事务锁超时，未写入任何数据: {identity}")
            time.sleep(min(0.05, remaining))
        depths[identity] = 1
        try:
            yield lock_file
        finally:
            depths.pop(identity, None)
            try:
                _release_process_lock(handle)
            finally:
                acquired = False
    finally:
        if acquired and handle is not None:
            _release_process_lock(handle)
        if handle is not None:
            handle.close()
        thread_lock.release()


def vault_transaction_writer(function: Any) -> Any:
    """Wrap a production Vault writer in the canonical transaction lock."""

    @functools.wraps(function)
    def locked(vault: Path, *args: Any, **kwargs: Any) -> Any:
        with vault_transaction_lock(Path(vault)):
            return function(vault, *args, **kwargs)

    return locked


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now_precise() -> str:
    """Return real wall-clock UTC without fabricating a future sequence value."""

    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def parse_iso_instant(value: Any) -> datetime:
    """Parse an ISO-8601 timestamp as one absolute UTC instant."""

    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def is_unit_interval(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= float(value) <= 1


BEHAVIOR_SOURCE_KINDS = {
    "behavior_observation",
    "tool_observation",
}


def mastery_source_is_authorized(
    meta: dict[str, Any], *, allow_synthetic_demo: bool = False
) -> bool:
    source_kind = meta.get("source_kind")
    return bool(
        source_kind in BEHAVIOR_SOURCE_KINDS
        or (allow_synthetic_demo and source_kind == "synthetic_demo")
    )


def evidence_mastery_eligibility(
    meta: dict[str, Any], *, allow_synthetic_demo: bool = False
) -> tuple[bool, list[str]]:
    """Recompute mastery eligibility from raw verification fields.

    Correctness is intentionally not part of this gate: an eligible failed
    verification must still participate in latest-failure handling.
    """

    failures: list[str] = []
    if meta.get("observation_validity") != "valid":
        failures.append("observation_not_valid")
    source_ref_ids = meta.get("source_ref_ids")
    if (
        not isinstance(source_ref_ids, list)
        or not source_ref_ids
        or any(not isinstance(item, str) or not item.strip() for item in source_ref_ids)
    ):
        failures.append("missing_source_refs")
    if not mastery_source_is_authorized(
        meta, allow_synthetic_demo=allow_synthetic_demo
    ):
        failures.append("source_not_behavior")
    phase = meta.get("phase")
    if phase not in {"verification", "retention"}:
        failures.append("phase_not_verification")
    teaching_item_id = meta.get("teaching_item_id")
    verification_item_id = meta.get("verification_item_id")
    if not isinstance(teaching_item_id, str) or not teaching_item_id.strip():
        failures.append("missing_teaching_item_id")
    if not isinstance(verification_item_id, str) or not verification_item_id.strip():
        failures.append("missing_verification_item_id")
    elif verification_item_id == teaching_item_id:
        failures.append("verification_item_reused")
    if meta.get("verification_unseen") is not True:
        failures.append("verification_not_unseen")
    if meta.get("answer_revealed_before_first_attempt") is not False:
        failures.append("answer_revealed_early")
    verification_task_id = meta.get("verification_task_id")
    bound_verification_task_id = meta.get("bound_verification_task_id")
    if not isinstance(verification_task_id, str) or not verification_task_id.strip():
        failures.append("verification_task_unbound")
    elif (
        not isinstance(bound_verification_task_id, str)
        or not bound_verification_task_id.strip()
        or verification_task_id != bound_verification_task_id
    ):
        failures.append("verification_task_binding_mismatch")
    if not isinstance(meta.get("route_id_at_observation"), str) or not str(
        meta.get("route_id_at_observation")
    ).strip():
        failures.append("verification_route_unbound")
    route_version = meta.get("route_version_at_observation")
    if (
        not isinstance(route_version, int)
        or isinstance(route_version, bool)
        or route_version < 1
    ):
        failures.append("verification_route_version_unbound")
    if meta.get("assistance_level") != "A0" or meta.get("independence") != "independent":
        failures.append("verification_not_independent")
    if meta.get("hint_count") != 0:
        failures.append("verification_has_hint")
    consumers = meta.get("consumer_ids")
    consumer_set = (
        {item for item in consumers if isinstance(item, str)}
        if isinstance(consumers, list)
        else set()
    )
    if not isinstance(consumers, list) or not {
        "verification_gate",
        "contract_recompute",
    }.issubset(consumer_set):
        failures.append("missing_mastery_consumers")
    if phase == "retention":
        if not isinstance(meta.get("baseline_evidence_id"), str) or not str(
            meta.get("baseline_evidence_id")
        ).strip():
            failures.append("missing_retention_baseline")
        if not isinstance(meta.get("retention_task_id"), str) or not str(
            meta.get("retention_task_id")
        ).strip():
            failures.append("missing_retention_task")
        elif meta.get("retention_task_id") != meta.get("verification_task_id"):
            failures.append("retention_task_binding_mismatch")
        if not isinstance(meta.get("scheduled_for"), str) or not str(meta.get("scheduled_for")).strip():
            failures.append("missing_retention_schedule")
        if "retention_recompute" not in consumer_set:
            failures.append("missing_retention_consumer")
    return not failures, failures


def derive_observation_confidence(
    meta: dict[str, Any], *, derived_mastery_eligible: bool | None = None,
    allow_synthetic_demo: bool = False,
) -> tuple[str, str]:
    """Derive trust in an observation, never trust a caller-selected level."""

    validity = meta.get("observation_validity")
    source_kind = meta.get("source_kind")
    phase = meta.get("phase")
    if validity != "valid":
        return "low", "nonvalid_record"
    if not mastery_source_is_authorized(
        meta, allow_synthetic_demo=allow_synthetic_demo
    ):
        return "low", "nonbehavior_source_cap"
    if derived_mastery_eligible is None:
        derived_mastery_eligible, _failures = evidence_mastery_eligibility(
            meta, allow_synthetic_demo=allow_synthetic_demo
        )
    if derived_mastery_eligible:
        return "high", "qualified_independent_behavior"
    if phase in {"diagnostic", "teaching_process"} and meta.get("result") != "not_tested":
        return "medium", "observed_process_or_diagnostic_behavior"
    return "low", "insufficient_behavior_provenance"


def build_evidence_field_bindings(meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Bind critical persisted observations to their actual downstream consumers.

    This is deliberately field-level rather than a generic note-level label: a
    stored result without source, scope, observation time, validity, and a real
    consumer is not actionable evidence.
    """

    scope = {
        "learner_id": meta.get("learner_id"),
        "goal_id": meta.get("goal_id"),
        "concept_id": meta.get("concept_id"),
        "contract_id": meta.get("contract_id"),
        "contract_version": meta.get("contract_version"),
    }
    record_consumers = [
        item for item in meta.get("consumer_ids", []) if isinstance(item, str)
    ]
    sources = list(meta.get("source_ref_ids", []))
    bindings: dict[str, dict[str, Any]] = {}
    for field in sorted(EVIDENCE_FIELD_CONSUMERS):
        allowed_consumers = evidence_field_consumers_for_phase(meta, field)
        if not allowed_consumers:
            continue
        if not evidence_field_is_actionable(meta, field):
            continue
        field_consumers = [
            consumer for consumer in record_consumers if consumer in allowed_consumers
        ]
        if not field_consumers:
            continue
        bindings[field] = {
            "consumers": field_consumers,
            "source_ref_ids": sources,
            "scope": dict(scope),
            "observed_at": meta.get("observed_at"),
            "validity": meta.get("observation_validity"),
        }
    return bindings


def evidence_field_consumers_for_phase(
    meta: dict[str, Any], field: str
) -> set[str]:
    """Return real consumers for this evidence phase, not the global union."""

    phase_map = PHASE_FIELD_CONSUMERS.get(str(meta.get("phase")))
    return phase_map.get(field, set()) if phase_map is not None else set()


def evidence_field_is_actionable(meta: dict[str, Any], field: str) -> bool:
    """Return whether a persisted value is meaningful in this evidence phase."""

    if field not in meta or meta.get(field) is None:
        return False
    if field in {"delayed_retention", "retention_delay_days"} and meta.get(
        "phase"
    ) != "retention":
        return False
    if field in {"near_transfer", "delayed_retention", "self_reported_effort"} and meta.get(
        field
    ) in {"not_tested", "pending", "not_required", "not_collected"}:
        return False
    return True


def derive_diagnostic_snapshot(
    evidence_records: list[tuple[str, dict[str, Any]]], *, as_of: Any | None = None
) -> dict[str, Any] | None:
    """Return the latest trusted diagnostic trace consumed by boundary updates.

    Keeping the complete trace in the state makes every collected diagnostic
    value auditable and prevents a field from being stored merely because it
    appeared on a form.  It is formative only and never grants mastery.
    """

    try:
        cutoff = parse_iso_instant(as_of if as_of is not None else utc_now())
    except (TypeError, ValueError):
        return None
    eligible: list[tuple[str, dict[str, Any]]] = []
    for evidence_id, meta in evidence_records:
        if (
            meta.get("phase") == "diagnostic"
            and meta.get("observation_validity") == "valid"
            and meta.get("observation_confidence") in {"medium", "high"}
        ):
            try:
                observed = parse_iso_instant(meta.get("observed_at"))
            except (TypeError, ValueError):
                continue
            if observed > cutoff:
                continue
            eligible.append((evidence_id, meta))
    if not eligible:
        return None
    evidence_id, latest = max(
        eligible,
        key=lambda item: (parse_iso_instant(item[1]["observed_at"]), item[0]),
    )
    elapsed = latest.get("elapsed_seconds")
    diagnosis_minutes = (
        round(float(elapsed) / 60.0, 3)
        if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool)
        else None
    )
    return {
        "schema": "uc-diagnostic-snapshot/0.1",
        "source_evidence_id": evidence_id,
        "teaching_item_id": latest.get("teaching_item_id"),
        "activity": latest.get("activity"),
        "carrier": latest.get("carrier"),
        "result": latest.get("result"),
        "demonstrates": list(latest.get("demonstrates", [])),
        "independence": latest.get("independence"),
        "assistance_level": latest.get("assistance_level"),
        "response_correct": latest.get("response_correct"),
        "immediate_performance": latest.get("immediate_performance"),
        "explanation_quality": latest.get("explanation_quality"),
        "elapsed_seconds": latest.get("elapsed_seconds"),
        "diagnosis_minutes": diagnosis_minutes,
        "attempts": latest.get("attempts"),
        "hint_count": latest.get("hint_count"),
        "self_reported_effort": latest.get("self_reported_effort"),
        "error_signature": latest.get("error_signature"),
        "observation_confidence": latest.get("observation_confidence"),
        "observed_at": latest.get("observed_at"),
    }


def derive_state_knowledge_status(
    contract_evaluation: dict[str, Any],
    evidence_records: list[tuple[str, dict[str, Any]]],
    *,
    as_of: Any | None = None,
) -> dict[str, Any]:
    """Derive mastery band, confidence and active misconceptions.

    Only a met mastery contract yields ``mastered``.  Diagnostic and process
    observations can locate ``none``/``partial`` boundaries but cannot cross
    the mastery gate.
    """

    try:
        cutoff = parse_iso_instant(as_of if as_of is not None else utc_now())
    except (TypeError, ValueError):
        cutoff = datetime.min.replace(tzinfo=timezone.utc)
    if contract_evaluation.get("status") == "met":
        mastery = "mastered"
        confidence = "high"
    else:
        usable: list[tuple[str, dict[str, Any]]] = []
        for evidence_id, meta in evidence_records:
            if (
                meta.get("phase") in {"diagnostic", "verification", "retention"}
                and meta.get("observation_validity") == "valid"
                and meta.get("observation_confidence") in {"medium", "high"}
                and meta.get("result") != "not_tested"
            ):
                try:
                    observed = parse_iso_instant(meta.get("observed_at"))
                except (TypeError, ValueError):
                    continue
                if observed > cutoff:
                    continue
                usable.append((evidence_id, meta))
        latest = (
            max(usable, key=lambda item: (parse_iso_instant(item[1]["observed_at"]), item[0]))[1]
            if usable
            else None
        )
        if latest is None:
            mastery, confidence = "unknown", "low"
        else:
            result = latest.get("result")
            performance = latest.get("immediate_performance")
            positive_formative = bool(
                result == "pass"
                and latest.get("response_correct") is True
                or result == "partial"
                or (
                    isinstance(performance, (int, float))
                    and not isinstance(performance, bool)
                    and float(performance) >= 0.5
                )
            )
            mastery = "partial" if positive_formative else "none"
            confidence = (
                "high"
                if latest.get("phase") in {"verification", "retention"}
                and latest.get("observation_confidence") == "high"
                else "medium"
            )
    misconception_values: set[str] = set()
    for _evidence_id, meta in evidence_records:
        try:
            observed = parse_iso_instant(meta.get("observed_at"))
        except (TypeError, ValueError):
            continue
        if (
            observed <= cutoff
            and meta.get("phase") in {"diagnostic", "verification", "retention"}
            and meta.get("observation_validity") == "valid"
            and meta.get("observation_confidence") in {"medium", "high"}
            and meta.get("result") != "pass"
            and isinstance(meta.get("error_signature"), str)
            and str(meta.get("error_signature")).strip()
        ):
            misconception_values.add(str(meta["error_signature"]))
    misconception_flags = sorted(misconception_values)
    return {
        "mastery": mastery,
        "mastery_confidence": confidence,
        "misconception_flags": misconception_flags,
        "diagnostic_snapshot": derive_diagnostic_snapshot(
            evidence_records, as_of=cutoff
        ),
    }


def derive_boundary_positions(
    concept_relations: dict[str, list[dict[str, str]]],
    mastery_by_concept: dict[str, str],
) -> dict[str, str]:
    """Derive graph boundary from mastered prerequisites and contrasts."""

    positions: dict[str, str] = {}
    for concept_id, mastery in mastery_by_concept.items():
        relations = concept_relations.get(concept_id, [])
        requires = [item["target"] for item in relations if item.get("type") == "requires"]
        contrasts = [
            item["target"] for item in relations if item.get("type") == "contrasts_with"
        ]
        if mastery == "mastered":
            positions[concept_id] = (
                "inner_fringe"
                if any(mastery_by_concept.get(target) != "mastered" for target in contrasts)
                else "interior"
            )
        elif all(mastery_by_concept.get(target) == "mastered" for target in requires):
            positions[concept_id] = "outer_fringe"
        else:
            positions[concept_id] = "blocked"
    return positions


def derived_retention_delay_days(
    evidence_meta: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]
) -> int | None:
    """Derive completed 24-hour periods from a scoped baseline evidence."""

    baseline_id = evidence_meta.get("baseline_evidence_id")
    baseline = evidence_by_id.get(str(baseline_id)) if baseline_id else None
    if not baseline:
        return None
    scope_fields = ("learner_id", "goal_id", "concept_id", "contract_id", "contract_version")
    if any(baseline.get(field) != evidence_meta.get(field) for field in scope_fields):
        return None
    try:
        baseline_at = parse_iso_instant(baseline.get("observed_at"))
        observed_at = parse_iso_instant(evidence_meta.get("observed_at"))
    except ValueError:
        return None
    elapsed_seconds = (observed_at - baseline_at).total_seconds()
    if elapsed_seconds < 0:
        return None
    return int(elapsed_seconds // 86400)


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Atomically restore an exact previous file image during rollback."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json_dump(value))


COMPARISON_CONTEXT_FIELDS = (
    "domain",
    "knowledge_kind",
    "target_performance",
    "prior_band",
    "task_difficulty",
)
TARGET_PERFORMANCE_VALUES = {
    "recall",
    "explain",
    "discriminate",
    "predict",
    "execute",
    "diagnose",
    "transfer",
}
TASK_DIFFICULTY_VALUES = {"low", "medium", "high"}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def canonical_comparison_context(value: Any, *, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != set(COMPARISON_CONTEXT_FIELDS):
        raise VaultError(f"{label} 必须且只能包含 {','.join(COMPARISON_CONTEXT_FIELDS)}")
    normalized = {field: str(value.get(field, "")).strip().casefold() for field in COMPARISON_CONTEXT_FIELDS}
    if any(not item or "|" in item or "=" in item for item in normalized.values()):
        raise VaultError(f"{label} 含空值或保留字符 |/=")
    if normalized["knowledge_kind"] not in KNOWLEDGE_KIND_VALUES:
        raise VaultError(f"{label}.knowledge_kind 非法")
    if normalized["target_performance"] not in TARGET_PERFORMANCE_VALUES:
        raise VaultError(f"{label}.target_performance 非法")
    if normalized["prior_band"] not in MASTERY_VALUES:
        raise VaultError(f"{label}.prior_band 非法")
    if normalized["task_difficulty"] not in TASK_DIFFICULTY_VALUES:
        raise VaultError(f"{label}.task_difficulty 非法")
    return normalized


def comparison_context_key(value: dict[str, str]) -> str:
    return "|".join(f"{field}={value[field]}" for field in COMPARISON_CONTEXT_FIELDS)


def canonical_cost_vector(value: Any, *, label: str) -> dict[str, float] | None:
    """Validate an optional six-dimensional, directly traceable cost vector."""

    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != set(COST_DIMENSIONS):
        raise VaultError(
            f"{label} 必须精确包含 {','.join(COST_DIMENSIONS)}，或省略/null"
        )
    normalized: dict[str, float] = {}
    for dimension in COST_DIMENSIONS:
        item = value.get(dimension)
        if (
            not isinstance(item, (int, float))
            or isinstance(item, bool)
            or not math.isfinite(float(item))
            or float(item) < 0
        ):
            raise VaultError(f"{label}.{dimension} 必须是有限非负数")
        normalized[dimension] = float(item)
    return normalized


def route_chain_anchor(manifest: dict[str, Any]) -> str:
    return sha256_fingerprint(
        {
            "kind": "understanding_cost_route_chain_genesis",
            "vault_id": manifest.get("vault_id"),
            "created_at": manifest.get("created_at"),
        }
    )


def normalized_resource_snapshot(resource: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(resource, dict):
        raise VaultError(f"{label} 必须是 resource 对象")
    resource_id = resource.get("id")
    carrier = resource.get("carrier")
    activities = resource.get("supported_activities")
    if not isinstance(resource_id, str) or not resource_id.strip():
        raise VaultError(f"{label}.id 缺失")
    if carrier not in CARRIER_VALUES:
        raise VaultError(f"{label}.carrier 非法")
    if (
        not isinstance(activities, list)
        or not activities
        or any(not isinstance(item, str) or not item.strip() for item in activities)
        or len(activities) != len(set(activities))
    ):
        raise VaultError(f"{label}.supported_activities 必须是非空唯一字符串数组")
    probe = resource.get("diagnostic_probe")
    task = resource.get("verification_task")
    for task_label, task_value in (("diagnostic_probe", probe), ("verification_task", task)):
        if not isinstance(task_value, dict) or not all(
            isinstance(task_value.get(key), str) and task_value[key].strip()
            for key in ("id", "prompt", "success_criteria")
        ):
            raise VaultError(f"{label}.{task_label} 非法")
    protected_answers = task.get("protected_answers")
    if not (
        isinstance(protected_answers, str)
        and protected_answers.strip()
        or isinstance(protected_answers, list)
        and protected_answers
        and all(isinstance(item, str) and item.strip() for item in protected_answers)
    ):
        raise VaultError(f"{label}.verification_task.protected_answers 非法")
    duration_minutes = resource.get("duration_minutes")
    if (
        not isinstance(duration_minutes, (int, float))
        or isinstance(duration_minutes, bool)
        or duration_minutes < 0
    ):
        raise VaultError(f"{label}.duration_minutes 必须是非负数值")
    normalized = {
        "id": resource_id,
        "carrier": carrier,
        "supported_activities": sorted(activities),
        "protocol_version": resource.get("protocol_version"),
        "diagnostic_probe": dict(probe),
        "verification_task": dict(task),
        "teaches": sorted(resource.get("teaches", [])),
        "requires": sorted(resource.get("requires", [])),
        "duration_minutes": float(duration_minutes),
    }
    cost_vector = canonical_cost_vector(
        resource.get("cost_vector"), label=f"{label}.cost_vector"
    )
    if cost_vector is not None:
        normalized["cost_vector"] = cost_vector
    return normalized


def normalized_intervention_snapshot(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VaultError(f"{label} 必须是 intervention 对象")
    required_strings = ("id", "route_id", "goal_id", "current_checkpoint")
    if any(not isinstance(value.get(field), str) or not value[field].strip() for field in required_strings):
        raise VaultError(f"{label} 缺少 id/route_id/goal_id/current_checkpoint")
    route_version = value.get("route_version")
    resource_ids = value.get("resource_ids")
    if not isinstance(route_version, int) or isinstance(route_version, bool) or route_version < 1:
        raise VaultError(f"{label}.route_version 必须是正整数")
    if (
        not isinstance(resource_ids, list)
        or not resource_ids
        or any(not isinstance(item, str) or not item.strip() for item in resource_ids)
        or len(resource_ids) != len(set(resource_ids))
    ):
        raise VaultError(f"{label}.resource_ids 必须是非空唯一字符串数组")
    return {
        "id": value["id"],
        "route_id": value["route_id"],
        "route_version": route_version,
        "goal_id": value["goal_id"],
        "current_checkpoint": value["current_checkpoint"],
        "resource_ids": sorted(resource_ids),
    }


def seed_resources(seed: dict[str, Any]) -> list[dict[str, Any]]:
    resources = seed.get("resources")
    if resources is None and isinstance(seed.get("resource"), dict):
        resources = [seed["resource"]]
    if not isinstance(resources, list) or not resources:
        raise VaultError("Demo seed 必须包含非空 resources 数组")
    if any(not isinstance(item, dict) for item in resources):
        raise VaultError("Demo seed resources 每项必须是对象")
    return resources


def binding_seed_snapshot(seed: dict[str, Any], binding: dict[str, Any], *, label: str) -> dict[str, Any]:
    supplied = binding.get("issuance_snapshot")
    if supplied is not None:
        if not isinstance(supplied, dict):
            raise VaultError(f"{label}.issuance_snapshot 必须是对象")
        resources = supplied.get("resources")
        intervention = supplied.get("intervention")
    else:
        intervention_seed = seed.get("intervention")
        if not isinstance(intervention_seed, dict) or (
            intervention_seed.get("route_id") != binding.get("route_id")
            or intervention_seed.get("route_version") != binding.get("route_version")
        ):
            raise VaultError(f"{label} 是历史路线，必须提供 issuance_snapshot")
        use_ids = intervention_seed.get("uses_resource_ids")
        if use_ids is None and isinstance(intervention_seed.get("current_activity_id"), str):
            use_ids = [intervention_seed["current_activity_id"]]
        resource_by_id = {str(item.get("id")): item for item in seed_resources(seed)}
        if not isinstance(use_ids, list) or any(item not in resource_by_id for item in use_ids):
            raise VaultError(f"{label} 当前路线 uses_resource_ids 无法解析")
        resources = [resource_by_id[item] for item in use_ids]
        intervention = {
            "id": intervention_seed.get("id"),
            "route_id": intervention_seed.get("route_id"),
            "route_version": intervention_seed.get("route_version"),
            "goal_id": intervention_seed.get("goal_id"),
            "current_checkpoint": intervention_seed.get("current_checkpoint"),
            "resource_ids": list(use_ids),
        }
    if not isinstance(resources, list) or not resources:
        raise VaultError(f"{label}.issuance_snapshot.resources 必须是非空数组")
    normalized_resources = sorted(
        (
            normalized_resource_snapshot(item, label=f"{label}.issuance_snapshot.resources")
            for item in resources
        ),
        key=lambda item: item["id"],
    )
    normalized_intervention = normalized_intervention_snapshot(
        intervention, label=f"{label}.issuance_snapshot.intervention"
    )
    resource_ids = [item["id"] for item in normalized_resources]
    if resource_ids != normalized_intervention["resource_ids"]:
        raise VaultError(f"{label} resource snapshot 与 intervention.resource_ids 不一致")
    task_ids = {item["verification_task"]["id"] for item in normalized_resources}
    if task_ids != {binding.get("verification_task_id")}:
        raise VaultError(f"{label} resource verification_task 与 binding 不一致")
    return {"resources": normalized_resources, "intervention": normalized_intervention}


def build_route_binding_document(
    seed: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    bindings = seed.get("route_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise VaultError("Demo seed 必须提供非空 route_bindings 签发序列")
    anchor = route_chain_anchor(manifest)
    previous_hash = anchor
    events: list[dict[str, Any]] = []
    for sequence, binding in enumerate(bindings, start=1):
        label = f"route_bindings[{sequence - 1}]"
        if not isinstance(binding, dict):
            raise VaultError(f"{label} 必须是对象")
        context = canonical_comparison_context(binding.get("comparison_context"), label=f"{label}.comparison_context")
        snapshot = binding_seed_snapshot(seed, binding, label=label)
        task = snapshot["resources"][0]["verification_task"]
        event = {
            key: binding.get(key)
            for key in (
                "binding_id",
                "learner_id",
                "goal_id",
                "concept_id",
                "contract_id",
                "contract_version",
                "route_id",
                "route_version",
                "verification_task_id",
                "issued_at",
                "immutable",
                "source_ref_ids",
            )
        }
        event.update(
            {
                "event_kind": "route_issued",
                "sequence": sequence,
                "previous_hash": previous_hash,
                "comparison_context": context,
                "context_key": comparison_context_key(context),
                "resource_fingerprint": sha256_fingerprint(snapshot["resources"]),
                "intervention_fingerprint": sha256_fingerprint(snapshot["intervention"]),
                "verification_task_fingerprint": sha256_fingerprint(task),
                "issuance_snapshot": snapshot,
            }
        )
        event["event_hash"] = sha256_fingerprint(event)
        previous_hash = event["event_hash"]
        events.append(event)
    return {
        "schema": ROUTE_BINDING_SCHEMA,
        "source": "assets/demo-seed.json#route_bindings",
        "chain_anchor": anchor,
        "head_sequence": len(events),
        "head_hash": previous_hash,
        "events": events,
    }


def load_route_binding_registry(
    vault: Path, manifest: dict[str, Any]
) -> tuple[
    dict[tuple[str, str, str, str, int, str, int], dict[str, Any]],
    list[dict[str, Any]],
    list[str],
]:
    """Validate the append-only issuance chain before returning any binding.

    The hash chain is not treated as external notarisation. Its purpose is to
    make edits, truncation, reordering, and cross-Vault transplantation
    detectable against the manifest anchor/head before an evidence record can
    consume a route context or task.
    """

    errors: list[str] = []
    validation_now = datetime.now(timezone.utc)
    registry: dict[tuple[str, str, str, str, int, str, int], dict[str, Any]] = {}
    path = vault / ROUTE_BINDINGS_REL
    if not path.is_file():
        if any(
            manifest.get(field) is not None
            for field in (
                "route_binding_chain_anchor",
                "route_binding_chain_head",
                "route_binding_chain_length",
            )
        ):
            errors.append("manifest 声明 route binding chain 但账本文件不存在")
        return registry, [], errors
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return registry, [], [f"route binding registry 无法解析: {exc}"]
    if document.get("schema") != ROUTE_BINDING_SCHEMA:
        errors.append(f"route binding registry schema 应为 {ROUTE_BINDING_SCHEMA}")
    if not isinstance(document.get("source"), str) or not document["source"].strip():
        errors.append("route binding registry 缺少独立 source")
    expected_anchor = route_chain_anchor(manifest)
    anchor = document.get("chain_anchor")
    if anchor != expected_anchor or manifest.get("route_binding_chain_anchor") != expected_anchor:
        errors.append("route binding chain anchor 与 manifest/Vault 身份不一致")
    events = document.get("events")
    if not isinstance(events, list) or not events:
        errors.append("route binding registry events 必须是非空数组")
        events = []
    binding_ids: set[str] = set()
    sequences: set[int] = set()
    previous_hash = expected_anchor
    validated_events: list[dict[str, Any]] = []
    for position, event in enumerate(events, start=1):
        label = f"route binding registry.events[{position - 1}]"
        if not isinstance(event, dict):
            errors.append(f"{label} 必须是对象")
            continue
        event_errors_before = len(errors)
        if event.get("event_kind") != "route_issued":
            errors.append(f"{label}.event_kind 必须是 route_issued")
        sequence = event.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            errors.append(f"{label}.sequence 必须是正整数")
        else:
            if sequence in sequences:
                errors.append(f"route binding sequence 重复: {sequence}")
            sequences.add(sequence)
            if sequence != position:
                errors.append(f"route binding sequence 必须连续且等于文件顺序: expected={position} stored={sequence}")
        if event.get("previous_hash") != previous_hash:
            errors.append(f"{label}.previous_hash 断链")
        stored_hash = event.get("event_hash")
        event_payload = dict(event)
        event_payload.pop("event_hash", None)
        calculated_hash = sha256_fingerprint(event_payload)
        if stored_hash != calculated_hash:
            errors.append(f"{label}.event_hash 与内容不一致")
        previous_hash = str(stored_hash) if isinstance(stored_hash, str) else calculated_hash

        binding_id = event.get("binding_id")
        if not isinstance(binding_id, str) or not binding_id.strip():
            errors.append(f"{label} 缺少 binding_id")
        elif binding_id in binding_ids:
            errors.append(f"route binding binding_id 重复: {binding_id}")
        else:
            binding_ids.add(binding_id)
        string_fields = (
            "learner_id",
            "goal_id",
            "concept_id",
            "contract_id",
            "route_id",
            "verification_task_id",
            "issued_at",
            "context_key",
            "resource_fingerprint",
            "intervention_fingerprint",
            "verification_task_fingerprint",
        )
        if any(not isinstance(event.get(field), str) or not event[field].strip() for field in string_fields):
            errors.append(f"{label} 缺少非空作用域/task/context/fingerprint 字段")
        contract_version = event.get("contract_version")
        route_version = event.get("route_version")
        if (
            not isinstance(contract_version, int)
            or isinstance(contract_version, bool)
            or contract_version < 1
            or not isinstance(route_version, int)
            or isinstance(route_version, bool)
            or route_version < 1
        ):
            errors.append(f"{label} contract_version/route_version 必须是正整数")
        if event.get("immutable") is not True:
            errors.append(f"{label} 必须声明 immutable=true")
        route_purpose = event.get("route_purpose")
        legacy_seed_event = _is_legacy_trusted_seed_route_event(event, manifest)
        if route_purpose not in {"learning", "retention"} and not legacy_seed_event:
            errors.append(
                f"{label}.route_purpose 必须是 learning/retention；"
                "缺失仅兼容可信 seed 前缀"
            )
        source_refs = event.get("source_ref_ids")
        if (
            not isinstance(source_refs, list)
            or not source_refs
            or any(not isinstance(item, str) or not item.strip() for item in source_refs)
            or len(source_refs) != len(set(source_refs))
        ):
            errors.append(f"{label}.source_ref_ids 必须是非空唯一字符串数组")
        if not legacy_seed_event:
            baseline_evidence_id = event.get("baseline_evidence_id")
            if route_purpose == "learning" and baseline_evidence_id is not None:
                errors.append(f"{label}.learning baseline_evidence_id 必须为 null")
            if route_purpose == "retention" and (
                not isinstance(baseline_evidence_id, str)
                or not baseline_evidence_id.strip()
                or baseline_evidence_id not in (source_refs or [])
            ):
                errors.append(
                    f"{label}.retention baseline_evidence_id 必须非空且属于 source_ref_ids"
                )
            selection_decision = event.get("selection_decision")
            expected_selection_fields = {
                "selection_basis",
                "user_cost_priority",
                "user_cost_priority_status",
                "focus_decision_id",
                "focus_time_scope",
                "candidate_costs",
            }
            if (
                not isinstance(selection_decision, dict)
                or set(selection_decision) != expected_selection_fields
            ):
                errors.append(f"{label}.selection_decision 字段合同非法")
            else:
                selection_basis = selection_decision.get("selection_basis")
                priority = selection_decision.get("user_cost_priority")
                priority_status = selection_decision.get("user_cost_priority_status")
                focus_decision_id = selection_decision.get("focus_decision_id")
                focus_time_scope = selection_decision.get("focus_time_scope")
                candidate_costs = selection_decision.get("candidate_costs")
                valid_priority = priority is None or (
                    isinstance(priority, list)
                    and bool(priority)
                    and all(item in COST_DIMENSIONS for item in priority)
                    and len(priority) == len(set(priority))
                )
                if not valid_priority:
                    errors.append(f"{label}.selection_decision user_cost_priority 非法")
                if route_purpose == "retention":
                    if selection_decision != {
                        "selection_basis": "retention_contract",
                        "user_cost_priority": None,
                        "user_cost_priority_status": "not_applicable",
                        "focus_decision_id": None,
                        "focus_time_scope": None,
                        "candidate_costs": [],
                    }:
                        errors.append(
                            f"{label}.retention selection_decision 必须是 canonical not_applicable"
                        )
                elif route_purpose == "learning":
                    valid_cost_sources = {
                        "resource.cost_vector",
                        "intervention.cost_vector+resource.duration_minutes:fallback_estimate",
                    }
                    if not isinstance(candidate_costs, list) or not candidate_costs:
                        errors.append(f"{label}.candidate_costs 必须是非空数组")
                        candidate_costs = []
                    cost_identities: set[tuple[str, str]] = set()
                    selected_costs: list[dict[str, Any]] = []
                    canonical_candidate_costs = sorted(
                        candidate_costs,
                        key=lambda item: (
                            str(item.get("concept_id"))
                            if isinstance(item, dict)
                            else "",
                            str(item.get("resource_id"))
                            if isinstance(item, dict)
                            else "",
                        ),
                    )
                    if candidate_costs != canonical_candidate_costs:
                        errors.append(f"{label}.candidate_costs 必须 canonical 排序")
                    for candidate_cost in candidate_costs:
                        expected_cost_fields = {
                            "concept_id",
                            "resource_id",
                            "resource_fingerprint",
                            "cost_vector",
                            "fallback_cost_estimate",
                            "cost_vector_source",
                            "selected",
                        }
                        if (
                            not isinstance(candidate_cost, dict)
                            or set(candidate_cost) != expected_cost_fields
                        ):
                            errors.append(f"{label}.candidate_costs 项字段合同非法")
                            continue
                        identity = (
                            str(candidate_cost.get("concept_id")),
                            str(candidate_cost.get("resource_id")),
                        )
                        if (
                            not all(identity)
                            or identity in cost_identities
                            or not re.fullmatch(
                                r"[0-9a-f]{64}",
                                str(candidate_cost.get("resource_fingerprint")),
                            )
                            or candidate_cost.get("cost_vector_source")
                            not in valid_cost_sources
                            or not isinstance(candidate_cost.get("selected"), bool)
                        ):
                            errors.append(f"{label}.candidate_costs 项值非法")
                        cost_identities.add(identity)
                        try:
                            normalized_candidate_cost = canonical_cost_vector(
                                candidate_cost.get("cost_vector"),
                                label=f"{label}.candidate_costs.cost_vector",
                            )
                            normalized_fallback = canonical_cost_vector(
                                candidate_cost.get("fallback_cost_estimate"),
                                label=(
                                    f"{label}.candidate_costs.fallback_cost_estimate"
                                ),
                            )
                            if candidate_cost.get("cost_vector_source") == "resource.cost_vector":
                                if normalized_candidate_cost is None or normalized_fallback is not None:
                                    errors.append(
                                        f"{label}.resource cost 必须有真实 vector 且无 fallback"
                                    )
                            elif (
                                normalized_candidate_cost is not None
                                or normalized_fallback is None
                            ):
                                errors.append(
                                    f"{label}.fallback candidate 不得冒充可比较 cost_vector"
                                )
                        except VaultError as exc:
                            errors.append(str(exc))
                        if candidate_cost.get("selected") is True:
                            selected_costs.append(candidate_cost)
                    if len(selected_costs) != 1:
                        errors.append(f"{label}.candidate_costs 必须且只能标记一个 selected")
                    if selection_basis not in {
                        "active_route",
                        "route_default",
                        "cost_pareto",
                        "user_cost_priority",
                        "focus",
                        "stable_tie_break",
                    }:
                        errors.append(f"{label}.selection_basis 非法")
                    if priority_status not in {
                        "not_provided",
                        "not_needed",
                        "applied",
                    }:
                        errors.append(f"{label}.user_cost_priority_status 非法")
                    if priority_status == "not_provided" and priority is not None:
                        errors.append(f"{label}.not_provided 必须对应 null priority")
                    if priority_status in {"not_needed", "applied"} and not isinstance(
                        priority, list
                    ):
                        errors.append(f"{label}.{priority_status} 必须保存 priority 维度")
                    if (selection_basis == "user_cost_priority") != (
                        priority_status == "applied"
                    ):
                        errors.append(f"{label}.priority selection basis/status 不一致")
                    focus_used = selection_basis in {"focus", "stable_tie_break"}
                    if focus_used:
                        if (
                            not isinstance(focus_decision_id, str)
                            or not focus_decision_id.strip()
                            or focus_time_scope
                            != f"route-chain-head:{event.get('previous_hash')}"
                        ):
                            errors.append(f"{label}.Focus decision/time scope 绑定非法")
                    elif focus_decision_id is not None or focus_time_scope is not None:
                        errors.append(f"{label}.未消费 Focus 时不得保存 Focus batch")
        try:
            issued_instant = parse_iso_instant(event.get("issued_at"))
            if issued_instant > validation_now:
                errors.append(f"{label}.issued_at 不得位于未来")
        except (TypeError, ValueError):
            errors.append(f"{label}.issued_at 必须是带时区 ISO 时间")
        try:
            context = canonical_comparison_context(
                event.get("comparison_context"), label=f"{label}.comparison_context"
            )
            if event.get("context_key") != comparison_context_key(context):
                errors.append(f"{label}.context_key 不是 comparison_context 的规范派生值")
        except VaultError as exc:
            errors.append(str(exc))

        snapshot = event.get("issuance_snapshot")
        try:
            if not isinstance(snapshot, dict):
                raise VaultError(f"{label}.issuance_snapshot 必须是对象")
            raw_resources = snapshot.get("resources")
            if not isinstance(raw_resources, list) or not raw_resources:
                raise VaultError(f"{label}.issuance_snapshot.resources 必须是非空数组")
            resources = sorted(
                (
                    normalized_resource_snapshot(item, label=f"{label}.issuance_snapshot.resources")
                    for item in raw_resources
                ),
                key=lambda item: item["id"],
            )
            intervention = normalized_intervention_snapshot(
                snapshot.get("intervention"), label=f"{label}.issuance_snapshot.intervention"
            )
            if snapshot != {"resources": resources, "intervention": intervention}:
                raise VaultError(f"{label}.issuance_snapshot 不是规范化快照")
            if intervention["resource_ids"] != [item["id"] for item in resources]:
                raise VaultError(f"{label} resource/intervention 快照不一致")
            if (
                intervention["route_id"] != event.get("route_id")
                or intervention["route_version"] != event.get("route_version")
                or intervention["goal_id"] != event.get("goal_id")
                or intervention["current_checkpoint"] != event.get("concept_id")
            ):
                raise VaultError(f"{label} intervention 快照与 route scope 不一致")
            tasks = [item["verification_task"] for item in resources]
            if any(task["id"] != event.get("verification_task_id") for task in tasks):
                raise VaultError(f"{label} resource verification_task id 与发行记录不一致")
            task_fingerprints = {sha256_fingerprint(task) for task in tasks}
            if len(task_fingerprints) != 1:
                raise VaultError(f"{label} 同一路线候选资源的 verification_task 内容不一致")
            if event.get("resource_fingerprint") != sha256_fingerprint(resources):
                raise VaultError(f"{label}.resource_fingerprint 不一致")
            if event.get("intervention_fingerprint") != sha256_fingerprint(intervention):
                raise VaultError(f"{label}.intervention_fingerprint 不一致")
            if event.get("verification_task_fingerprint") not in task_fingerprints:
                raise VaultError(f"{label}.verification_task_fingerprint 不一致")
            if not legacy_seed_event:
                selection_decision = event.get("selection_decision", {})
                selected_costs = [
                    item
                    for item in selection_decision.get("candidate_costs", [])
                    if isinstance(item, dict) and item.get("selected") is True
                ]
                if route_purpose == "learning" and (
                    len(resources) != 1
                    or len(selected_costs) != 1
                    or selected_costs[0].get("concept_id")
                    != event.get("concept_id")
                    or selected_costs[0].get("resource_id")
                    != resources[0].get("id")
                    or selected_costs[0].get("resource_fingerprint")
                    != sha256_fingerprint(resources[0])
                    or (
                        selected_costs[0].get("cost_vector_source")
                        == "resource.cost_vector"
                        and selected_costs[0].get("cost_vector")
                        != resources[0].get("cost_vector")
                    )
                    or (
                        selected_costs[0].get("cost_vector_source")
                        != "resource.cost_vector"
                        and resources[0].get("cost_vector") is not None
                    )
                ):
                    raise VaultError(
                        f"{label}.selected candidate cost 未精确绑定 issuance resource"
                    )
        except VaultError as exc:
            errors.append(str(exc))

        if len(errors) == event_errors_before and isinstance(contract_version, int) and isinstance(route_version, int):
            key = (
                str(event.get("learner_id")),
                str(event.get("goal_id")),
                str(event.get("concept_id")),
                str(event.get("contract_id")),
                contract_version,
                str(event.get("route_id")),
                route_version,
            )
            if key in registry:
                errors.append(f"route binding registry 作用域/version 重复: {key}")
            else:
                registry[key] = event
                validated_events.append(event)

    expected_head_sequence = len(events)
    if document.get("head_sequence") != expected_head_sequence:
        errors.append("route binding chain head_sequence 与事件数不一致")
    if document.get("head_hash") != previous_hash:
        errors.append("route binding chain head_hash 与末事件不一致")
    if manifest.get("route_binding_chain_length") != expected_head_sequence:
        errors.append("manifest route_binding_chain_length 与账本不一致")
    if manifest.get("route_binding_chain_head") != previous_hash:
        errors.append("manifest route_binding_chain_head 与账本不一致")
    return registry, validated_events, errors


def validate_route_binding_authority(
    vault: Path, manifest: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Validate the declared route-ledger trust boundary.

    A local hash chain detects ordinary edits, truncation, and reordering, but a
    writer that can replace both the ledger and its manifest head can recompute
    every unkeyed hash. The synthetic Demo therefore compares its full ledger
    with the Skill-owned seed outside the Vault. Generic Vaults remain
    ``local_chain_only`` until the host supplies an external receipt/signature.
    """

    errors: list[str] = []
    warnings: list[str] = []
    ledger_path = vault / ROUTE_BINDINGS_REL
    trust_level = manifest.get("route_trust_level")

    if not ledger_path.is_file():
        if trust_level not in {None, "local_chain_only"}:
            errors.append("没有 route binding 账本时 route_trust_level 只能是 local_chain_only")
        return errors, warnings

    if trust_level not in ROUTE_TRUST_LEVEL_VALUES:
        errors.append(
            "route binding 账本必须声明 route_trust_level="
            "local_chain_only、trusted_seed_source 或 "
            "trusted_seed_prefix_local_extension"
        )
        return errors, warnings

    if manifest.get("reconstruction_status") == "synthetic_demo" and trust_level not in {
        "trusted_seed_source",
        "trusted_seed_prefix_local_extension",
    }:
        errors.append("synthetic_demo 不得把 route trust 降级为 local_chain_only")

    if trust_level == "local_chain_only":
        warnings.append(
            "route trust=local_chain_only：哈希链只检测非协同漂移；"
            "同一写权限可协同重算账本与 manifest，不具备外部防伪能力"
        )
        return errors, warnings

    if manifest.get("seed_source") != "assets/demo-seed.json":
        errors.append("trusted_seed_source 必须指向 assets/demo-seed.json")
        return errors, warnings
    try:
        trusted_seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        expected_vault_id = trusted_seed["vault"]["id"]
        if manifest.get("vault_id") != expected_vault_id:
            errors.append("trusted seed 的 vault_id 与 manifest 不一致")
        expected_document = build_route_binding_document(trusted_seed, manifest)
        actual_document = json.loads(ledger_path.read_text(encoding="utf-8"))
        expected_events = expected_document.get("events", [])
        actual_events = actual_document.get("events", [])
        if (
            not isinstance(actual_events, list)
            or len(actual_events) < len(expected_events)
            or actual_events[: len(expected_events)] != expected_events
            or actual_document.get("schema") != expected_document.get("schema")
            or actual_document.get("source") != expected_document.get("source")
            or actual_document.get("chain_anchor")
            != expected_document.get("chain_anchor")
        ):
            errors.append("route binding 账本的 Vault 外 trusted seed 前缀不一致")
        elif len(actual_events) > len(expected_events):
            expected_extension_sequence = len(expected_events) + 1
            if trust_level != "trusted_seed_prefix_local_extension":
                errors.append(
                    "trusted seed 后存在本地追加事件时必须声明 "
                    "route_trust_level=trusted_seed_prefix_local_extension"
                )
            if (
                actual_document.get("local_extension_from_sequence")
                != expected_extension_sequence
                or manifest.get("route_local_extension_from_sequence")
                != expected_extension_sequence
            ):
                errors.append(
                    "trusted seed 后的本地追加段必须在 ledger/manifest 明确声明起始 sequence"
                )
            warnings.append(
                "trusted_seed_source 仅为固定 seed 前缀提供外部权威；"
                "后续生产 route issuance 是本地哈希链事件"
            )
        else:
            if trust_level != "trusted_seed_source":
                errors.append("没有本地追加事件时 trust 必须是 trusted_seed_source")
            if (
                actual_document.get("local_extension_from_sequence") is not None
                or manifest.get("route_local_extension_from_sequence") is not None
            ):
                errors.append("没有本地追加事件时不得声明 route local extension")
    except (OSError, json.JSONDecodeError, KeyError, VaultError) as exc:
        errors.append(f"无法校验 Vault 外 route authority: {exc}")
    return errors, warnings


def trusted_synthetic_demo_authorized(
    vault: Path, manifest: dict[str, Any]
) -> bool:
    """Allow synthetic mastery only for the externally anchored bundled Demo."""

    if (
        manifest.get("reconstruction_status") != "synthetic_demo"
        or manifest.get("route_trust_level")
        not in {"trusted_seed_source", "trusted_seed_prefix_local_extension"}
        or manifest.get("seed_source") != "assets/demo-seed.json"
    ):
        return False
    authority_errors, _warnings = validate_route_binding_authority(vault, manifest)
    return not authority_errors


def yaml_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_frontmatter(meta: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in meta.items():
        lines.append(f"{key}: {yaml_value(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def write_note(vault: Path, relative_path: str | Path, meta: dict[str, Any], body: str) -> None:
    target = vault / relative_path
    if target.exists():
        raise VaultError(f"拒绝覆盖现有笔记: {target}")
    content = render_frontmatter(meta) + "\n" + body.rstrip() + "\n"
    atomic_write_text(target, content)


def replace_note_meta(path: Path, meta: dict[str, Any], body: str) -> None:
    content = render_frontmatter(meta) + "\n" + body.lstrip("\r\n").rstrip() + "\n"
    atomic_write_text(path, content)


def load_text_learning_policy() -> Any:
    module_path = Path(__file__).resolve().with_name("text_learning.py")
    spec = importlib.util.spec_from_file_location("understanding_cost_text_learning", module_path)
    if spec is None or spec.loader is None:
        raise VaultError(f"无法加载文字教学决策器: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _adapt_profile_observation_from_validated_context(
    policy: Any,
    evidence_id: str,
    evidence: dict[str, Any],
    contract: dict[str, Any],
    scoped_evidence: list[tuple[str, dict[str, Any]]],
    comparison_context: dict[str, str],
    state_context: dict[str, Any],
    *,
    as_of: str,
    allow_trusted_synthetic_demo: bool = False,
) -> dict[str, Any]:
    """Single integration seam for the text policy's trusted Vault adapter."""

    return policy._build_response_observation_from_validated_vault_inputs(
        evidence_id,
        evidence,
        contract,
        scoped_evidence,
        comparison_context,
        state_context=state_context,
        as_of=as_of,
        _allow_trusted_synthetic_demo=allow_trusted_synthetic_demo,
    )


def build_response_observation_from_vault(
    vault: Path, evidence_id: str, *, as_of: str | None = None
) -> dict[str, Any]:
    """Resolve canonical contract/window/context from a validated Vault."""

    errors, _warnings, _summary = validate_vault(
        vault,
        allow_unresolved_teaching=True,
    )
    if errors:
        raise VaultError(
            "Vault 校验失败，不能构造响应观察:\n- " + "\n- ".join(errors)
        )
    index, index_errors = build_index(vault)
    if index_errors:
        raise VaultError("图谱存在错误，不能构造响应观察: " + "; ".join(index_errors))
    evidence_node = index.get("nodes", {}).get(evidence_id)
    if not isinstance(evidence_node, dict) or evidence_node.get("type") != "evidence":
        raise VaultError("evidence_id 不存在或不是 evidence")
    all_meta = {
        node_id: parse_note(vault / node["path"])[0]
        for node_id, node in index["nodes"].items()
    }
    evidence = all_meta[evidence_id]
    scope = (
        str(evidence.get("learner_id")),
        str(evidence.get("goal_id")),
        str(evidence.get("concept_id")),
        str(evidence.get("contract_id")),
        evidence.get("contract_version"),
    )
    state_matches = [
        (node_id, meta)
        for node_id, meta in all_meta.items()
        if meta.get("type") == "state"
        and (
            str(meta.get("learner_id")),
            str(meta.get("goal_id")),
            str(meta.get("concept_id")),
            str(meta.get("contract_id")),
            meta.get("contract_version"),
        )
        == scope
    ]
    if len(state_matches) != 1:
        raise VaultError("evidence 无唯一同 scope state")
    state_id, state = state_matches[0]
    supported_ids = [
        str(relation["target"])
        for relation in index["nodes"][state_id].get("relations", [])
        if relation.get("type") == "supported_by"
    ]
    if evidence_id not in supported_ids:
        raise VaultError("目标 evidence 未进入 state 的 canonical supported_by 窗口")
    scoped_evidence = [
        (item_id, all_meta[item_id])
        for item_id in supported_ids
        if item_id in all_meta and all_meta[item_id].get("type") == "evidence"
    ]
    goal = all_meta.get(scope[1], {})
    contracts = [
        item
        for item in goal.get("mastery_contracts", [])
        if isinstance(item, dict)
        and str(item.get("id")) == scope[3]
        and item.get("version") == scope[4]
        and str(item.get("concept_id")) == scope[2]
    ]
    if len(contracts) != 1:
        raise VaultError("evidence 无唯一 canonical mastery contract")
    manifest = json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))
    allow_synthetic_demo = trusted_synthetic_demo_authorized(vault, manifest)
    registry, _events, registry_errors = load_route_binding_registry(vault, manifest)
    if registry_errors:
        raise VaultError("route issuance 校验失败: " + "; ".join(registry_errors))
    issuance_key = (
        scope[0],
        scope[1],
        scope[2],
        scope[3],
        scope[4],
        str(evidence.get("route_id_at_observation")),
        evidence.get("route_version_at_observation"),
    )
    issuance = registry.get(issuance_key)
    if issuance is None or evidence.get("route_binding_id") != issuance.get("binding_id"):
        raise VaultError("evidence 无有效 canonical route issuance")
    policy = load_text_learning_policy()
    return _adapt_profile_observation_from_validated_context(
        policy,
        evidence_id,
        evidence,
        contracts[0],
        scoped_evidence,
        dict(issuance["comparison_context"]),
        state,
        as_of=as_of or utc_now(),
        allow_trusted_synthetic_demo=allow_synthetic_demo,
    )


def parse_scalar(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def parse_note(path: Path) -> tuple[dict[str, Any], str, list[str]]:
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {}, "", [f"不是 UTF-8: {path}"]
    match = FRONTMATTER_RE.search(text)
    if not match:
        return {}, text, [f"缺少 frontmatter: {path}"]
    meta: dict[str, Any] = {}
    for line_number, line in enumerate(match.group(1).splitlines(), start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) or ":" not in line:
            errors.append(f"不支持的 frontmatter 行 {path}:{line_number}: {line}")
            continue
        key, raw = line.split(":", 1)
        meta[key.strip()] = parse_scalar(raw)
    return meta, text[match.end() :], errors


def normalized_link_target(raw: str) -> str:
    return Path(raw.strip().replace("\\", "/")).name


def relation_lines(relations: Iterable[dict[str, str]]) -> str:
    lines = ["## Relations", ""]
    for relation in relations:
        lines.append(f"- {relation['type']}: [[{relation['target']}]]")
    if len(lines) == 2:
        lines.append("- none")
    return "\n".join(lines)


def ensure_empty_target(path: Path) -> None:
    resolved = path.resolve()
    if resolved == Path(resolved.anchor):
        raise VaultError("拒绝把磁盘根目录作为 Vault")
    if resolved.exists():
        if not resolved.is_dir():
            raise VaultError(f"目标不是目录: {resolved}")
        if any(resolved.iterdir()):
            raise VaultError(f"目标目录不是空目录，拒绝覆盖: {resolved}")
    else:
        resolved.mkdir(parents=True, exist_ok=False)


def base_directories(vault: Path) -> None:
    for relative in (
        "00-system",
        "10-domain",
        "20-learner/states",
        "20-learner/goals",
        "20-learner/sessions",
        "20-learner/evidence",
        "30-learning/resources",
        "30-learning/interventions",
        "30-learning/retention-schedules",
        "30-learning/verification-opens",
        "30-learning/visuals",
        "30-learning/visuals/snapshots",
        "90-templates",
    ):
        (vault / relative).mkdir(parents=True, exist_ok=True)


def write_route_marker(vault: Path) -> None:
    marker = {
        "schema": SCHEMA,
        "manifest": MANIFEST_REL.as_posix(),
        "vault_id": json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))["vault_id"],
    }
    write_json(vault / ROUTE_FILE, marker)


def router_body(manifest: dict[str, Any]) -> str:
    links: list[tuple[str, str | None]] = [
        ("learner", manifest.get("active_learner_id")),
        ("goal", manifest.get("active_goal_id")),
        ("session", manifest.get("last_session_id")),
        ("domain", manifest.get("active_domain_id")),
    ]
    body = ["# 理解成本导航入口", "", "## Active links", ""]
    for label, target in links:
        if target:
            body.append(f"- {label} → [[{target}]]")
    body.extend(
        [
            "",
            "## Recovery rule",
            "",
            "路由丢失时先校验 manifest 和现有证据；未找到时询问用户，不得静默创建新画像。",
        ]
    )
    return "\n".join(body)


def write_router(vault: Path, manifest: dict[str, Any]) -> None:
    meta = {
        "schema": SCHEMA,
        "id": "sys-router",
        "type": "router",
        "title": "理解成本导航入口",
        "active_learner_id": manifest.get("active_learner_id"),
        "active_goal_id": manifest.get("active_goal_id"),
        "last_session_id": manifest.get("last_session_id"),
        "active_domain_id": manifest.get("active_domain_id"),
        "updated_at": utc_now(),
        "privacy": "private",
        "tags": ["uc/system"],
    }
    write_note(vault, ROUTER_REL, meta, router_body(manifest))


@vault_transaction_writer
def initialize_vault(vault: Path, learner_id: str) -> None:
    ensure_empty_target(vault)
    base_directories(vault)
    now = utc_now()
    learner_node_id = f"usr-{learner_id}"
    manifest = {
        "schema": SCHEMA,
        "vault_id": f"vault-{learner_id}",
        "title": f"理解成本 Vault {learner_id}",
        "created_at": now,
        "updated_at": now,
        "active_learner_id": learner_node_id,
        "active_domain_id": None,
        "active_goal_id": None,
        "last_session_id": None,
        "reconstruction_status": "original",
        "route_trust_level": "local_chain_only",
    }
    write_json(vault / MANIFEST_REL, manifest)
    write_route_marker(vault)
    profile_meta = {
        "schema": SCHEMA,
        "id": learner_node_id,
        "type": "learner",
        "title": f"匿名学习者 {learner_id}",
        "learner_id": learner_id,
        "created_at": now,
        "updated_at": now,
        "privacy": "private",
        "tags": ["uc/learner"],
    }
    body = "# 匿名学习者画像\n\n## Stable constraints\n\n- 尚未采集\n\n## Preferences\n\n- 尚未采集；偏好与效果分开\n\n## Adaptation hypotheses\n\n- 当前证据不足"
    write_note(vault, f"20-learner/{learner_node_id}.md", profile_meta, body)
    write_router(vault, manifest)
    index, _ = build_index(vault)
    write_json(vault / INDEX_REL, index)


@vault_transaction_writer
def seed_demo(vault: Path) -> None:
    ensure_empty_target(vault)
    base_directories(vault)
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    now = utc_now()
    vault_data = seed["vault"]
    manifest = {
        "schema": SCHEMA,
        "vault_id": vault_data["id"],
        "title": vault_data["title"],
        "created_at": now,
        "updated_at": now,
        "active_learner_id": vault_data["learner_node_id"],
        "active_domain_id": vault_data["domain_id"],
        "active_goal_id": vault_data["active_goal_id"],
        "last_session_id": vault_data["last_session_id"],
        "reconstruction_status": "synthetic_demo",
        "seed_source": "assets/demo-seed.json",
        "route_trust_level": "trusted_seed_source",
    }
    route_binding_document = build_route_binding_document(seed, manifest)
    manifest.update(
        {
            "route_binding_chain_anchor": route_binding_document["chain_anchor"],
            "route_binding_chain_head": route_binding_document["head_hash"],
            "route_binding_chain_length": route_binding_document["head_sequence"],
        }
    )
    write_json(vault / MANIFEST_REL, manifest)
    write_route_marker(vault)
    write_json(vault / ROUTE_BINDINGS_REL, route_binding_document)

    route_binding_registry = {
        (
            event["learner_id"],
            event["goal_id"],
            event["concept_id"],
            event["contract_id"],
            event["contract_version"],
            event["route_id"],
            event["route_version"],
        ): event
        for event in route_binding_document["events"]
    }

    domain = seed["domain"]
    write_note(
        vault,
        f"10-domain/python/{domain['id']}.md",
        {
            "schema": SCHEMA,
            "id": domain["id"],
            "type": "domain",
            "title": domain["title"],
            "created_at": now,
            "updated_at": now,
            "privacy": "shared",
            "tags": ["uc/domain", "domain/python"],
        },
        f"# {domain['title']}\n\n{domain['description']}\n\n" + relation_lines([]),
    )

    for concept in seed["concepts"]:
        meta = {
            "schema": SCHEMA,
            "id": concept["id"],
            "type": "concept",
            "title": concept["title"],
            "domain_id": domain["id"],
            "knowledge_kind": concept["knowledge_kind"],
            "difficulty": concept["difficulty"],
            "graph_x": concept["graph_x"],
            "graph_y": concept["graph_y"],
            "content_provenance": "synthetic_authored_demo",
            "created_at": now,
            "updated_at": now,
            "privacy": "shared",
            "tags": ["uc/concept", "domain/python"],
        }
        body = (
            f"# {concept['title']}\n\n"
            "> 合成领域节点。学习者状态和 Focus 派生量保存在独立私有节点中。\n\n"
            + relation_lines(concept["relations"])
        )
        write_note(vault, f"10-domain/python/{concept['id']}.md", meta, body)

    learner = seed["learner"]
    profile_meta = {
        "schema": SCHEMA,
        "id": learner["id"],
        "type": "learner",
        "title": learner["title"],
        "learner_id": learner["learner_id"],
        "language": learner["language"],
        "created_at": now,
        "updated_at": now,
        "privacy": "private",
        "tags": ["uc/learner"],
    }
    profile_lines = [
        f"# {learner['title']}",
        "",
        "> 合成 Demo，不包含真实用户资料。偏好与实测效果严格分开。",
        "",
        "## Stable constraints",
        "",
    ]
    profile_lines.extend(f"- {item}" for item in learner["constraints"])
    profile_lines.extend(["", "## Preferences (self-report)", ""])
    profile_lines.extend(f"- {item}" for item in learner["preferences"])
    profile_lines.extend(
        [
            "",
            "## Adaptation hypotheses",
            "",
            "| 条件 | 当前候选活动 | 依据 | 置信度 | 证据 |",
            "|---|---|---|---|---|",
        ]
    )
    for hypothesis in learner["adaptation_hypotheses"]:
        links = "、".join(f"[[{item}]]" for item in hypothesis["evidence_ids"])
        profile_lines.append(
            f"| {hypothesis['condition']} | {hypothesis['activity']} | {hypothesis['basis']} | {hypothesis['confidence']} | {links} |"
        )
    write_note(vault, f"20-learner/{learner['id']}.md", profile_meta, "\n".join(profile_lines))

    evidence_ids: list[str] = []
    seed_evidence_by_id = {item["id"]: item for item in seed["evidence"]}
    generated_evidence_meta_by_id: dict[str, dict[str, Any]] = {}
    seed_delivery_records: list[dict[str, Any]] = []
    for evidence in seed["evidence"]:
        if evidence.get("phase") != "teaching_process":
            evidence["teaching_delivery_fingerprint_at_observation"] = None
            continue
        delivery_key = (
            learner["learner_id"],
            evidence["goal_id"],
            evidence["about"],
            evidence["contract_id"],
            evidence["contract_version"],
            evidence.get("route_id_at_observation"),
            evidence.get("route_version_at_observation"),
        )
        issued_binding = route_binding_registry.get(delivery_key)
        if issued_binding is None:
            raise VaultError(
                f"Demo teaching process 无法解析 delivery route issuance: {evidence['id']}"
            )
        # The bundled process observation represents a historical, already
        # issued teaching decision.  Hydrate the immutable task binding and a
        # deterministic historical decision epoch instead of relying on the
        # former null-compatible validator behavior.
        evidence["verification_task_id"] = issued_binding["verification_task_id"]
        evidence["bound_verification_task_id"] = issued_binding[
            "verification_task_id"
        ]
        evidence["decision_fingerprint_at_observation"] = sha256_fingerprint(
            {
                "kind": "trusted_seed_teaching_decision",
                "evidence_id": evidence["id"],
                "route_binding_id": issued_binding["binding_id"],
                "verification_task_id": issued_binding["verification_task_id"],
            }
        )
        matching_resources = [
            item
            for item in issued_binding.get("issuance_snapshot", {}).get(
                "resources", []
            )
            if isinstance(item, dict)
            and item.get("carrier") == evidence.get("carrier")
            and evidence.get("activity") in item.get("supported_activities", [])
            and evidence.get("about") in item.get("teaches", [])
        ]
        if len(matching_resources) != 1:
            raise VaultError(
                f"Demo teaching process 必须唯一解析教学资源: {evidence['id']} "
                f"matches={len(matching_resources)}"
            )
        issued_at = (
            parse_iso_instant(evidence["observed_at"]) - timedelta(minutes=1)
        ).isoformat().replace("+00:00", "Z")
        delivery_plan = {
            "learning_objective": "区分调用展开顺序与返回顺序，并能用自己的话解释。",
            "method_label": "预测后解释",
            "medium": "文字文件＋对话",
            "orientation": "先看清每一步是谁调用谁，再单独追踪返回方向。",
            "term_grounding": [],
            "explanation": "调用发生时先进入下一层；到达停止条件后，结果才按相反方向逐层返回。",
            "example": "像叠放便签：新便签压在上面，处理完最上层后再依次取下。",
            "visual": None,
            "learner_task": "不运行代码，写出两层调用的进入顺序和返回顺序，并说明两者为何相反。",
            "response_format": "先写调用顺序，再写返回顺序，最后用一句话解释。",
            "feedback_rule": "只纠正当前混淆的一步，不提前给完整轨迹。",
            "verification_rule": "教学任务完成后再发一个未见例子，独立作答且不使用提示。",
            "success_criteria": "能够正确区分进入与返回方向，并给出因果解释。",
            "next_step": {
                "instruction": "完成当前预测后，根据错误只修正一处再重做。",
                "when": None,
            },
        }
        fingerprint = sha256_fingerprint(delivery_plan)
        evidence["teaching_delivery_fingerprint_at_observation"] = fingerprint
        resource = matching_resources[0]
        seed_delivery_records.append(
            {
                "id": evidence["teaching_item_id"],
                "title": f"教学签发：{evidence['about']}",
                "learner_id": learner["learner_id"],
                "goal_id": evidence["goal_id"],
                "concept_id": evidence["about"],
                "contract_id": evidence["contract_id"],
                "contract_version": evidence["contract_version"],
                "route_id": evidence["route_id_at_observation"],
                "route_version": evidence["route_version_at_observation"],
                "route_binding_id": issued_binding["binding_id"],
                "context_key": issued_binding["context_key"],
                "decision_fingerprint": evidence.get(
                    "decision_fingerprint_at_observation"
                ),
                "resource_id": resource["id"],
                "activity": evidence["activity"],
                "carrier": evidence["carrier"],
                "delivery_plan": delivery_plan,
                "delivery_plan_fingerprint": fingerprint,
                "issued_at": issued_at,
                "source_kind": "synthetic_demo",
                "source_ref_ids": ["assets/demo-seed.json"],
            }
        )
    for evidence in seed["evidence"]:
        evidence_ids.append(evidence["id"])
        binding_key = (
            learner["learner_id"],
            evidence["goal_id"],
            evidence["about"],
            evidence["contract_id"],
            evidence["contract_version"],
            evidence.get("route_id_at_observation"),
            evidence.get("route_version_at_observation"),
        )
        issued_binding = route_binding_registry.get(binding_key)
        if issued_binding is None:
            raise VaultError(
                f"Demo evidence 无法解析到 route issuance: {evidence['id']} / {binding_key}"
            )
        derived_context_key = issued_binding["context_key"]
        supplied_context_key = evidence.get("context_key")
        if supplied_context_key is not None and supplied_context_key != derived_context_key:
            raise VaultError(
                f"Demo evidence context_key 与 route issuance 不一致: {evidence['id']}"
            )
        meta = {
            "schema": SCHEMA,
            "id": evidence["id"],
            "type": "evidence",
            "title": f"证据：{evidence['about']} / {evidence['evidence_kind']}",
            "learner_id": learner["learner_id"],
            "concept_id": evidence["about"],
            "goal_id": evidence["goal_id"],
            "contract_id": evidence["contract_id"],
            "contract_version": evidence["contract_version"],
            "phase": evidence["phase"],
            "carrier": evidence["carrier"],
            "teaching_item_id": evidence.get("teaching_item_id"),
            "teaching_delivery_fingerprint_at_observation": evidence.get(
                "teaching_delivery_fingerprint_at_observation"
            ),
            "verification_item_id": evidence.get("verification_item_id"),
            "verification_unseen": evidence["verification_unseen"],
            "answer_revealed_before_first_attempt": evidence[
                "answer_revealed_before_first_attempt"
            ],
            "verification_task_id": evidence.get("verification_task_id"),
            "bound_verification_task_id": evidence.get("bound_verification_task_id"),
            "route_id_at_observation": evidence.get("route_id_at_observation"),
            "route_version_at_observation": evidence.get("route_version_at_observation"),
            "decision_fingerprint_at_observation": evidence.get(
                "decision_fingerprint_at_observation"
            ),
            "consumer_ids": [],
            "source_ref_ids": evidence["source_ref_ids"],
            "observation_validity": evidence["observation_validity"],
            "mastery_eligible": evidence["mastery_eligible"],
            "evidence_kind": evidence["evidence_kind"],
            "demonstrates": evidence["demonstrates"],
            "result": evidence["result"],
            "independence": evidence["independence"],
            "assistance_level": evidence["assistance_level"],
            "activity": evidence["activity"],
            "error_signature": evidence.get("error_signature"),
            "context_key": derived_context_key,
            "route_binding_id": issued_binding["binding_id"],
            "elapsed_seconds": evidence["elapsed_seconds"],
            "attempts": evidence["attempts"],
            "hint_count": evidence["hint_count"],
            "immediate_performance": evidence["immediate_performance"],
            "near_transfer": evidence["near_transfer"],
            "delayed_retention": evidence["delayed_retention"],
            "response_correct": evidence["response_correct"],
            "explanation_quality": evidence["explanation_quality"],
            "self_reported_effort": evidence.get("self_reported_effort", "not_collected"),
            "retention_delay_days": evidence.get("retention_delay_days", 0),
            "baseline_evidence_id": evidence.get("baseline_evidence_id"),
            "retention_task_id": evidence.get("retention_task_id"),
            "scheduled_for": evidence.get("scheduled_for"),
            "source_kind": "synthetic_demo",
            "observed_at": evidence["observed_at"],
            "created_at": now,
            "updated_at": now,
            "privacy": "sensitive",
            "tags": ["uc/evidence"],
        }
        meta["consumer_ids"] = sorted(
            {
                consumer
                for field in EVIDENCE_FIELD_CONSUMERS
                if evidence_field_is_actionable(meta, field)
                for consumer in evidence_field_consumers_for_phase(meta, field)
            }
        )
        meta["field_bindings"] = build_evidence_field_bindings(meta)
        derived_eligible, _eligibility_failures = evidence_mastery_eligibility(
            meta, allow_synthetic_demo=True
        )
        (
            meta["observation_confidence"],
            meta["observation_confidence_basis"],
        ) = derive_observation_confidence(
            meta,
            derived_mastery_eligible=derived_eligible,
            allow_synthetic_demo=True,
        )
        meta["consumer_ids"] = sorted(
            {
                consumer
                for field in EVIDENCE_FIELD_CONSUMERS
                if evidence_field_is_actionable(meta, field)
                for consumer in evidence_field_consumers_for_phase(meta, field)
            }
        )
        meta["field_bindings"] = build_evidence_field_bindings(meta)
        generated_evidence_meta_by_id[evidence["id"]] = dict(meta)
        body = (
            f"# {meta['title']}\n\n{evidence['summary']}\n\n"
            + relation_lines(
                [
                    {"type": "about", "target": evidence["about"]},
                    {"type": "derived_from", "target": seed["session"]["id"]},
                ]
            )
        )
        write_note(vault, f"20-learner/evidence/{evidence['id']}.md", meta, body)

    for delivery in seed_delivery_records:
        delivery_meta = {
            "schema": SCHEMA,
            "delivery_contract": TEACHING_DELIVERY_SCHEMA,
            "type": "teaching_delivery",
            **delivery,
            "created_at": now,
            "updated_at": now,
            "privacy": "sensitive",
            "tags": ["uc/teaching-delivery", "uc/append-only"],
        }
        delivery_relations = [
            {"type": "for_learner", "target": learner["id"]},
            {"type": "for_goal", "target": delivery["goal_id"]},
            {"type": "about", "target": delivery["concept_id"]},
            {"type": "uses", "target": delivery["resource_id"]},
        ]
        write_note(
            vault,
            f"30-learning/deliveries/{delivery['id']}.md",
            delivery_meta,
            "# 已发行教学项\n\n"
            "> 追加记录：保存实际用户白名单投影及其指纹；过程作答必须引用本记录。\n\n"
            + relation_lines(delivery_relations),
        )

    state_by_concept: dict[str, str] = {}
    state_seed_by_concept: dict[str, dict[str, Any]] = {}
    state_derivations: dict[str, dict[str, Any]] = {}
    for state in seed["states"]:
        state_contract = next(
            (
                contract
                for contract in seed["goal"]["mastery_contracts"]
                if contract.get("id") == state.get("contract_id")
                and contract.get("version") == state.get("contract_version")
            ),
            None,
        )
        if state_contract is None:
            raise VaultError(
                f"Demo state 找不到 mastery contract: {state['concept_id']}/{state['contract_id']}"
            )
        state_records = [
            (evidence_id, generated_evidence_meta_by_id[evidence_id])
            for evidence_id in state["supported_by"]
            if evidence_id in generated_evidence_meta_by_id
        ]
        evaluation = evaluate_mastery_contract(
            state_contract,
            state_records,
            state_context=state,
            as_of=now,
            allow_synthetic_demo=True,
        )
        state_derivations[state["concept_id"]] = {
            "evaluation": evaluation,
            "knowledge": derive_state_knowledge_status(
                evaluation, state_records, as_of=now
            ),
        }
    concept_relations = {
        concept["id"]: list(concept.get("relations", [])) for concept in seed["concepts"]
    }
    derived_boundaries = derive_boundary_positions(
        concept_relations,
        {
            concept_id: derived["knowledge"]["mastery"]
            for concept_id, derived in state_derivations.items()
        },
    )
    for state in seed["states"]:
        state_id = f"ks-{learner['learner_id']}-{state['concept_id']}"
        state_by_concept[state["concept_id"]] = state_id
        state_seed_by_concept[state["concept_id"]] = state
        supported_seed_evidence = [
            seed_evidence_by_id[evidence_id]
            for evidence_id in state["supported_by"]
            if evidence_id in seed_evidence_by_id
        ]
        try:
            latest_supported = max(
                supported_seed_evidence,
                key=lambda item: parse_iso_instant(item["observed_at"]),
                default=None,
            )
            independent_seed_evidence = [
                item
                for item in supported_seed_evidence
                if item.get("independence") == "independent"
                and item.get("assistance_level") == "A0"
            ]
            latest_independent = max(
                independent_seed_evidence,
                key=lambda item: parse_iso_instant(item["observed_at"]),
                default=None,
            )
        except (KeyError, ValueError) as exc:
            raise VaultError(f"Demo evidence observed_at 非法，无法派生 state 时间: {exc}") from exc
        state_observed_at = latest_supported["observed_at"] if latest_supported else None
        independent_observed_at = (
            latest_independent["observed_at"] if latest_independent else None
        )
        state_evaluation = state_derivations[state["concept_id"]]["evaluation"]
        knowledge = state_derivations[state["concept_id"]]["knowledge"]
        meta = {
            "schema": SCHEMA,
            "id": state_id,
            "type": "state",
            "title": f"状态：{state['concept_id']}",
            "learner_id": learner["learner_id"],
            "concept_id": state["concept_id"],
            "goal_id": seed["goal"]["id"],
            "contract_id": state["contract_id"],
            "contract_version": state["contract_version"],
            "mastery": knowledge["mastery"],
            "mastery_confidence": knowledge["mastery_confidence"],
            "boundary_position": derived_boundaries[state["concept_id"]],
            "immediate_contract_status": state["immediate_contract_status"],
            "contract_status": state["contract_status"],
            "retention_status": state["retention_status"],
            "next_action": state_evaluation["next_action"],
            "valid_context": state["valid_context"],
            "as_of": state_observed_at,
            "evaluated_at": now,
            "last_independent_evidence_at": independent_observed_at,
            "boundary_derived_at": state_observed_at,
            "last_assessed_at": state_observed_at,
            "misconception_flags": knowledge["misconception_flags"],
            "diagnostic_snapshot": knowledge["diagnostic_snapshot"],
            "created_at": now,
            "updated_at": now,
            "privacy": "private",
            "tags": ["uc/state", f"uc/state/{knowledge['mastery']}"],
        }
        relations = [
            {"type": "for_learner", "target": learner["id"]},
            {"type": "for_goal", "target": seed["goal"]["id"]},
            {"type": "about", "target": state["concept_id"]},
        ]
        relations.extend({"type": "supported_by", "target": evidence_id} for evidence_id in state["supported_by"])
        body = (
            f"# 状态：{state['concept_id']}\n\n"
            "> 这是由证据重算的当前快照；原始证据不会被覆盖。\n\n"
            + relation_lines(relations)
        )
        write_note(vault, f"20-learner/states/{state_id}.md", meta, body)

    goal = seed["goal"]
    goal_meta = {
        "schema": SCHEMA,
        "id": goal["id"],
        "type": "goal",
        "title": goal["title"],
        "learner_id": learner["learner_id"],
        "status": "active",
        "source_question": goal["source_question"],
        "desired_outcome": goal["desired_outcome"],
        "retention_check_days": goal["retention_check_days"],
        "mastery_contracts": goal["mastery_contracts"],
        "created_at": now,
        "updated_at": now,
        "privacy": "private",
        "tags": ["uc/goal"],
    }
    goal_relations = [{"type": "for_learner", "target": learner["id"]}]
    goal_relations.extend({"type": "targets", "target": target} for target in goal["targets"])
    goal_lines = [f"# {goal['title']}", "", f"> 原问题：{goal['source_question']}", "", relation_lines(goal_relations), "", "## Mastery contract", ""]
    goal_lines.extend(f"- {item}" for item in goal["mastery_contract"])
    goal_lines.extend(["", "## Structured contracts", ""])
    for contract in goal["mastery_contracts"]:
        requirements = contract["requirements"]
        retention = requirements["delayed_retention"]
        goal_lines.extend(
            [
                f"### {contract['id']}",
                "",
                f"- contract version: {contract['version']}",
                f"- 合同知识点：[[{contract['concept_id']}]]",
                f"- minimum qualified evidence: {requirements['minimum_qualified_evidence']}",
                f"- required capabilities: {', '.join(requirements['required_capabilities'])}",
                f"- minimum near transfer: {requirements['min_near_transfer']}",
                f"- delayed retention required: {str(retention['required']).lower()}",
                f"- delayed threshold: {retention['min_score']} after {retention['min_delay_days']} days",
                "",
            ]
        )
    write_note(vault, f"20-learner/goals/{goal['id']}.md", goal_meta, "\n".join(goal_lines))

    weights = {"goal": 0.4, "interest": 0.3, "readiness": 0.3}
    focus_stamp = re.sub(r"[^0-9A-Za-z]", "", now).lower()
    for concept in seed["concepts"]:
        focus_id = f"focus-{learner['learner_id']}-{goal['id']}-{concept['id']}-{focus_stamp}"
        state_seed = state_seed_by_concept[concept["id"]]
        state_id = state_by_concept[concept["id"]]
        focus_z = round(
            weights["goal"] * concept["goal_relevance"]
            + weights["interest"] * concept["interest_evidence"]
            + weights["readiness"] * concept["readiness"],
            4,
        )
        focus_meta = {
            "schema": SCHEMA,
            "focus_snapshot_contract": FOCUS_SNAPSHOT_SCHEMA,
            "id": focus_id,
            "type": "focus_snapshot",
            "title": f"Focus：{concept['title']}",
            "learner_id": learner["learner_id"],
            "goal_id": goal["id"],
            "concept_id": concept["id"],
            "state_id": state_id,
            "contract_id": state_seed["contract_id"],
            "contract_version": state_seed["contract_version"],
            "route_id": seed["intervention"]["route_id"],
            "route_version": seed["intervention"]["route_version"],
            "time_scope": f"route-chain-head:{route_binding_document['head_hash']}",
            "decision_id": "dec-demo-a17-focus-inspect",
            "goal_relevance": concept["goal_relevance"],
            "goal_relevance_status": "derived",
            "interest_evidence": concept["interest_evidence"],
            "interest_evidence_status": "derived",
            "interest_evidence_kind": "synthetic_demo",
            "readiness": concept["readiness"],
            "readiness_status": "derived",
            "focus_model": FOCUS_MODEL_VERSION,
            "focus_weights": weights,
            "focus_z": focus_z,
            "ranking_status": "complete",
            "calculation_purpose": "inspect_view",
            "consumer_ids": ["inspect_view"],
            "used_in_decision": False,
            "selection_basis": "not_used",
            "score_kind": "heuristic_cone_coordinate",
            "causal_status": "not_established",
            "decision_role": "experimental_priority",
            "input_evidence_ids": state_seed["supported_by"],
            "input_source_refs": [state_id, goal["id"], "assets/demo-seed.json"],
            "input_confidence": {
                "goal_relevance": "high",
                "interest_evidence": "low",
                "readiness": "medium",
            },
            "calculated_at": now,
            "validity": "valid",
            "audience": "agent_internal",
            "user_visibility": "hidden_by_default",
            "export_policy": "explicit_inspect_or_debug",
            "authoritative": False,
            "derived": True,
            "rebuildable": True,
            "created_at": now,
            "updated_at": now,
            "privacy": "private",
            "tags": ["uc/focus", "uc/derived"],
        }
        focus_relations = [
            {"type": "for_learner", "target": learner["id"]},
            {"type": "for_goal", "target": goal["id"]},
            {"type": "about", "target": concept["id"]},
        ]
        write_note(
            vault,
            f"30-learning/visuals/snapshots/{focus_id}.md",
            focus_meta,
            f"# Agent 内部 Focus：{concept['title']}\n\n> 默认不进入学习者输出；它是可删除、可重算、非权威的决策缓存，不是掌握证据。\n\n"
            + relation_lines(focus_relations),
        )

    resources = seed_resources(seed)
    resource_by_id = {resource["id"]: resource for resource in resources}
    if len(resource_by_id) != len(resources):
        raise VaultError("Demo resources id 重复")
    for resource in resources:
        supported_activities = resource.get("supported_activities")
        if (
            not isinstance(supported_activities, list)
            or not supported_activities
            or any(not isinstance(item, str) or not item.strip() for item in supported_activities)
            or len(supported_activities) != len(set(supported_activities))
        ):
            raise VaultError(f"resource supported_activities 非法: {resource.get('id')}")
        resource_meta = {
            "schema": SCHEMA,
            "id": resource["id"],
            "type": "resource",
            "title": resource["title"],
            "modality": resource["modality"],
            "carrier": resource["carrier"],
            "text_format": resource["text_format"],
            "activity": resource.get("activity", supported_activities[0]),
            "supported_activities": supported_activities,
            "protocol_version": resource["protocol_version"],
            "verification_required": resource["verification_required"],
            "diagnostic_probe": resource["diagnostic_probe"],
            "verification_task": resource["verification_task"],
            "duration_minutes": resource["duration_minutes"],
            "difficulty": resource["difficulty"],
            "language": "zh-CN",
            "created_at": now,
            "updated_at": now,
            "privacy": "private",
            "tags": ["uc/resource"],
        }
        explicit_cost_vector = canonical_cost_vector(
            resource.get("cost_vector"),
            label=f"resource {resource.get('id')}.cost_vector",
        )
        if explicit_cost_vector is not None:
            resource_meta["cost_vector"] = explicit_cost_vector
        resource_relations = [{"type": "teaches", "target": item} for item in resource["teaches"]]
        resource_relations.extend({"type": "requires", "target": item} for item in resource["requires"])
        write_note(
            vault,
            f"30-learning/resources/{resource['id']}.md",
            resource_meta,
            f"# {resource['title']}\n\n> Agent 内部教学资源规格；验证题与保护答案不得直接进入学习者材料。实际交付必须经过文字协议白名单和 verification content guard。\n\n"
            + relation_lines(resource_relations),
        )

    intervention = seed["intervention"]
    used_resource_ids = intervention.get("uses_resource_ids")
    if used_resource_ids is None:
        used_resource_ids = [intervention["current_activity_id"]]
    if (
        not isinstance(used_resource_ids, list)
        or not used_resource_ids
        or any(item not in resource_by_id for item in used_resource_ids)
        or len(used_resource_ids) != len(set(used_resource_ids))
    ):
        raise VaultError("intervention uses_resource_ids 必须解析到唯一 resource")
    intervention_meta = {
        "schema": SCHEMA,
        "id": intervention["id"],
        "type": "intervention",
        "title": intervention["title"],
        "learner_id": learner["learner_id"],
        "status": "active",
        "strategy": intervention["strategy"],
        "medium_policy": intervention["medium_policy"],
        "carrier": intervention["carrier"],
        "estimated_minutes": intervention["estimated_minutes"],
        "cost_vector": intervention.get("cost_vector"),
        "adaptation_confidence": intervention["adaptation_confidence"],
        "teaching_decision_inputs": intervention.get("teaching_decision_inputs", {}),
        "route_id": intervention["route_id"],
        "route_version": intervention["route_version"],
        "goal_id": intervention["goal_id"],
        "current_checkpoint": intervention["current_checkpoint"],
        "current_activity_id": intervention["current_activity_id"],
        "current_probe_id": intervention["current_probe_id"],
        "current_verification_task_id": intervention["current_verification_task_id"],
        "completed_step_evidence_ids": intervention["completed_step_evidence_ids"],
        "parent_route_id": intervention["parent_route_id"],
        "return_checkpoint": intervention["return_checkpoint"],
        "recovery_status": intervention["recovery_status"],
        "recovered_from": intervention["recovered_from"],
        "path": intervention["path"],
        "created_at": now,
        "updated_at": now,
        "privacy": "private",
        "tags": ["uc/intervention"],
    }
    intervention_relations = [
        {"type": "for_learner", "target": learner["id"]},
        {"type": "implements", "target": goal["id"]},
    ]
    intervention_relations.extend({"type": "uses", "target": item} for item in used_resource_ids)
    intervention_lines = [
        f"# {intervention['title']}",
        "",
        intervention["rationale"],
        "",
        relation_lines(intervention_relations),
        "",
        "## Path",
        "",
    ]
    intervention_lines.extend(f"{number}. [[{concept_id}]]" for number, concept_id in enumerate(intervention["path"], start=1))
    write_note(
        vault,
        f"30-learning/interventions/{intervention['id']}.md",
        intervention_meta,
        "\n".join(intervention_lines),
    )

    session = seed["session"]
    session_meta = {
        "schema": SCHEMA,
        "id": session["id"],
        "type": "session",
        "title": session["title"],
        "learner_id": learner["learner_id"],
        "goal_id": goal["id"],
        "source_kind": session["source_kind"],
        "source_ref": session["source_ref"],
        "started_at": now,
        "created_at": now,
        "updated_at": now,
        "privacy": "private",
        "tags": ["uc/session"],
    }
    session_relations = [
        {"type": "for_learner", "target": learner["id"]},
        {"type": "for_goal", "target": goal["id"]},
    ]
    session_relations.extend({"type": "generated", "target": item} for item in evidence_ids)
    write_note(
        vault,
        f"20-learner/sessions/{session['id']}.md",
        session_meta,
        f"# {session['title']}\n\n{session['summary']}\n\n" + relation_lines(session_relations),
    )

    write_router(vault, manifest)
    index, _ = build_index(vault)
    write_json(vault / INDEX_REL, index)
    resolve_active_teaching(vault, write=True)


def build_index(vault: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    nodes: dict[str, dict[str, Any]] = {}
    id_paths: dict[str, str] = {}
    stem_ids: dict[str, list[str]] = {}
    notes: list[tuple[Path, dict[str, Any], str]] = []

    for path in sorted(vault.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.relative_to(vault).parts):
            continue
        meta, body, parse_errors = parse_note(path)
        errors.extend(parse_errors)
        relative = path.relative_to(vault).as_posix()
        note_id = str(meta.get("id", ""))
        if not note_id:
            errors.append(f"缺少 id: {relative}")
            continue
        if note_id in id_paths:
            errors.append(f"重复 id {note_id}: {id_paths[note_id]} 与 {relative}")
        else:
            id_paths[note_id] = relative
        stem_ids.setdefault(path.stem, []).append(note_id)
        notes.append((path, meta, body))

    for stem, ids in stem_ids.items():
        if len(ids) > 1:
            paths = [id_paths.get(item, item) for item in ids]
            errors.append(f"Wikilink stem 歧义 {stem}: {'、'.join(paths)}")

    def resolve_target(raw_target: str, relative: str) -> str | None:
        target = normalized_link_target(raw_target)
        if target in id_paths:
            return target
        candidates = stem_ids.get(target, [])
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            errors.append(f"Wikilink 目标歧义 {target}: {relative}")
        else:
            errors.append(f"断开的 Wikilink {target}: {relative}")
        return None

    for path, meta, body in notes:
        relative = path.relative_to(vault).as_posix()
        note_id = str(meta["id"])
        relations: list[dict[str, str]] = []
        for relation_type, raw_target in RELATION_RE.findall(body):
            if relation_type not in RELATION_TYPES:
                errors.append(f"未知关系 {relation_type}: {relative}")
            target_id = resolve_target(raw_target, relative)
            if target_id:
                relations.append({"type": relation_type, "target": target_id})
        wikilinks: list[str] = []
        for raw_target in WIKILINK_RE.findall(body):
            target_id = resolve_target(raw_target, relative)
            if target_id and target_id not in wikilinks:
                wikilinks.append(target_id)
        node_type = meta.get("type")
        if node_type not in NODE_TYPES:
            errors.append(f"未知节点类型 {node_type}: {relative}")
        nodes[note_id] = {
            "path": relative,
            "type": node_type,
            "title": meta.get("title", note_id),
            "relations": relations,
            "wikilinks": wikilinks,
        }

    index = {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "source": "markdown_notes",
        "node_count": len(nodes),
        "nodes": nodes,
        "errors": sorted(set(errors)),
    }
    return index, sorted(set(errors))


def validate_vault(
    vault: Path,
    *,
    allow_route_marker_issue: bool = False,
    allow_active_route_ambiguity: bool = False,
    allow_unresolved_teaching: bool = False,
) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    validation_now = datetime.now(timezone.utc)
    # Persisted clocks are authority inputs.  A future grace window would let
    # an observation, state evaluation or decision affect the system before it
    # actually occurred, so validation uses the real wall clock with no
    # fabricated +N minute tolerance.
    maximum_observation_time = validation_now
    if not vault.is_dir():
        return [f"Vault 不存在: {vault}"], warnings, {}

    manifest_path = vault / MANIFEST_REL
    if not manifest_path.is_file():
        errors.append(f"缺少 manifest: {manifest_path}")
        manifest: dict[str, Any] = {}
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"manifest 无法解析: {exc}")
            manifest = {}
        if manifest.get("schema") != SCHEMA:
            errors.append(f"manifest schema 应为 {SCHEMA}")

    marker_issues: list[str] = []
    marker_path = vault / ROUTE_FILE
    if not marker_path.is_file():
        warnings.append("Vault 入口 marker 丢失；数据可能仍完整，可用 recover-route --repair 修复")
    else:
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            if marker.get("schema") != SCHEMA:
                marker_issues.append("入口 marker schema 不匹配")
            if marker.get("manifest") != MANIFEST_REL.as_posix():
                marker_issues.append("入口 marker 的 manifest 路径不正确")
            if manifest and marker.get("vault_id") != manifest.get("vault_id"):
                marker_issues.append("入口 marker 的 vault_id 与 manifest 不一致")
        except (OSError, json.JSONDecodeError) as exc:
            marker_issues.append(f"入口 marker 无法解析: {exc}")
    if marker_issues:
        (warnings if allow_route_marker_issue else errors).extend(marker_issues)

    route_binding_registry, route_issuance_events, binding_errors = load_route_binding_registry(
        vault, manifest
    )
    errors.extend(binding_errors)
    authority_errors, authority_warnings = validate_route_binding_authority(vault, manifest)
    errors.extend(authority_errors)
    warnings.extend(authority_warnings)
    allow_synthetic_demo = (
        not binding_errors
        and not authority_errors
        and trusted_synthetic_demo_authorized(vault, manifest)
    )
    local_task_ids: dict[tuple[str, str, str, str, int, str], str] = {}
    local_task_fingerprints: dict[
        tuple[str, str, str, str, int, str], str
    ] = {}
    for event in route_issuance_events:
        if event.get("route_purpose") not in {"learning", "retention"}:
            continue
        scope = (
            str(event.get("learner_id")),
            str(event.get("goal_id")),
            str(event.get("concept_id")),
            str(event.get("contract_id")),
            event.get("contract_version")
            if isinstance(event.get("contract_version"), int)
            else -1,
        )
        for value, owners, label in (
            (
                str(event.get("verification_task_id")),
                local_task_ids,
                "verification_task_id",
            ),
            (
                str(event.get("verification_task_fingerprint")),
                local_task_fingerprints,
                "verification_task_fingerprint",
            ),
        ):
            identity = (*scope, value)
            prior = owners.get(identity)
            if prior is not None and prior != event.get("binding_id"):
                errors.append(
                    f"同 scope 本地 route issuance 重复 {label}: {prior}/{event.get('binding_id')}"
                )
            else:
                owners[identity] = str(event.get("binding_id"))

    index, index_errors = build_index(vault)
    errors.extend(index_errors)
    node_meta: dict[str, dict[str, Any]] = {}
    node_body: dict[str, str] = {}
    state_keys: dict[tuple[str, str, str], str] = {}
    focus_keys: dict[tuple[str, str, str, str], str] = {}
    goal_contracts: dict[str, dict[tuple[str, int], dict[str, Any]]] = {}

    for node_id, node in index.get("nodes", {}).items():
        path = vault / node["path"]
        meta, body, _ = parse_note(path)
        node_meta[node_id] = meta
        node_body[node_id] = body
        if meta.get("schema") != SCHEMA:
            errors.append(f"schema 不匹配: {node['path']}")
        if meta.get("privacy") not in PRIVACY_VALUES:
            errors.append(f"privacy 非法: {node['path']}")

        node_type = meta.get("type")
        if node_type == "concept":
            for key in ("goal_relevance", "interest_evidence", "readiness", "focus_z"):
                if key in meta:
                    errors.append(f"学习者/目标派生字段 {key} 不得写入共享 concept: {node['path']}")
            if not meta.get("content_provenance"):
                warnings.append(f"concept 缺少 content_provenance: {node['path']}")
            if meta.get("knowledge_kind") not in KNOWLEDGE_KIND_VALUES:
                errors.append(f"concept knowledge_kind 非法: {node['path']}")

        if node_type == "state":
            for required in ("misconception_flags", "diagnostic_snapshot"):
                if required not in meta:
                    errors.append(f"state 缺少派生字段 {required}: {node['path']}")
            if not isinstance(meta.get("misconception_flags"), list) or any(
                not isinstance(item, str) or not item.strip()
                for item in meta.get("misconception_flags", [])
            ):
                errors.append(f"state misconception_flags 非法: {node['path']}")
            diagnostic_snapshot = meta.get("diagnostic_snapshot")
            if diagnostic_snapshot is not None and (
                not isinstance(diagnostic_snapshot, dict)
                or diagnostic_snapshot.get("schema") != "uc-diagnostic-snapshot/0.1"
            ):
                errors.append(f"state diagnostic_snapshot 非法: {node['path']}")
            if meta.get("mastery") not in MASTERY_VALUES:
                errors.append(f"mastery 非法: {node['path']}")
            if meta.get("boundary_position") not in BOUNDARY_VALUES:
                errors.append(f"boundary_position 非法: {node['path']}")
            if meta.get("mastery_confidence") not in CONFIDENCE_VALUES:
                errors.append(f"mastery_confidence 非法: {node['path']}")
            if meta.get("immediate_contract_status") not in IMMEDIATE_CONTRACT_STATUS_VALUES:
                errors.append(f"immediate_contract_status 非法: {node['path']}")
            if meta.get("contract_status") not in CONTRACT_STATUS_VALUES:
                errors.append(f"contract_status 非法: {node['path']}")
            retention_status = meta.get("retention_status")
            if retention_status not in RETENTION_STATUS_VALUES and not re.fullmatch(
                r"passed_\d+d", str(retention_status)
            ):
                errors.append(f"retention_status 非法: {node['path']}")
            legacy_schedule_cache_fields = (
                "baseline_evidence_id",
                "retention_task_id",
                "retention_route_binding_id",
                "scheduled_for",
            )
            if any(field in meta for field in legacy_schedule_cache_fields):
                errors.append(
                    "state 不得复制 retention schedule 内容，只能引用 "
                    f"current_retention_schedule_id: {node['path']}"
                )
            current_schedule_id = meta.get("current_retention_schedule_id")
            if current_schedule_id is not None and (
                not isinstance(current_schedule_id, str)
                or not current_schedule_id.strip()
            ):
                errors.append(
                    f"state current_retention_schedule_id 非法: {node['path']}"
                )
            if retention_status in {"pending", "due", "failed", "conflicted"} and not (
                isinstance(current_schedule_id, str) and current_schedule_id.strip()
            ):
                errors.append(
                    f"state {retention_status} 缺少 current_retention_schedule_id: {node['path']}"
                )
            if meta.get("next_action") not in STATE_NEXT_ACTION_VALUES:
                errors.append(f"state next_action 非法: {node['path']}")
            try:
                evaluated_instant = parse_iso_instant(meta.get("evaluated_at"))
                if evaluated_instant > maximum_observation_time:
                    errors.append(
                        f"state evaluated_at 不得位于未来: {node['path']}"
                    )
            except (TypeError, ValueError):
                errors.append(f"state evaluated_at 必须是带时区 ISO 时间: {node['path']}")
            if meta.get("concept_id") not in index.get("nodes", {}):
                errors.append(f"state concept_id 不存在: {node['path']}")
            for required in ("goal_id", "contract_id", "contract_version"):
                if not meta.get(required):
                    errors.append(f"state 缺少 {required}: {node['path']}")
            if not isinstance(meta.get("contract_version"), int) or isinstance(meta.get("contract_version"), bool):
                errors.append(f"state contract_version 非法: {node['path']}")
            key = (
                str(meta.get("learner_id")),
                str(meta.get("goal_id")),
                str(meta.get("concept_id")),
            )
            if key in state_keys:
                errors.append(f"同一学习者/目标/知识点存在重复 state: {state_keys[key]} 与 {node_id}")
            state_keys[key] = node_id

        if node_type == "evidence":
            if meta.get("assistance_level") not in ASSISTANCE_VALUES:
                errors.append(f"assistance_level 非法: {node['path']}")
            for required in (
                *sorted(EVIDENCE_ENVELOPE_FIELDS),
                "carrier",
                "teaching_item_id",
                "teaching_delivery_fingerprint_at_observation",
                "verification_item_id",
                "verification_unseen",
                "answer_revealed_before_first_attempt",
                "verification_task_id",
                "bound_verification_task_id",
                "route_id_at_observation",
                "route_version_at_observation",
                "decision_fingerprint_at_observation",
                "consumer_ids",
                "observation_confidence",
                "observation_confidence_basis",
                "error_signature",
                "mastery_eligible",
                "evidence_kind",
                "result",
                "independence",
                "assistance_level",
                "demonstrates",
                "elapsed_seconds",
                "attempts",
                "hint_count",
                "immediate_performance",
                "near_transfer",
                "delayed_retention",
                "retention_delay_days",
                "response_correct",
                "explanation_quality",
                "observed_at",
                "self_reported_effort",
                "field_bindings",
            ):
                if required not in meta:
                    errors.append(f"evidence 缺少 {required}: {node['path']}")
            if meta.get("phase") not in EVIDENCE_PHASE_VALUES:
                errors.append(f"evidence phase 非法: {node['path']}")
            elif meta.get("evidence_kind") not in EVIDENCE_KIND_BY_PHASE.get(
                str(meta.get("phase")), set()
            ):
                errors.append(
                    f"evidence_kind 与 phase 不一致: {node['path']} "
                    f"phase={meta.get('phase')} kind={meta.get('evidence_kind')}"
                )
            envelope_contract = EVIDENCE_ENVELOPE_GUARDS_BY_PHASE.get(
                str(meta.get("phase")), {}
            )
            if any(
                not guards
                or not guards.issubset(EVIDENCE_ENVELOPE_GUARD_VALUES.union(VALUE_CONSUMER_VALUES))
                for guards in envelope_contract.values()
            ):
                errors.append(f"evidence envelope guard contract 非法: {node['path']}")
            if not isinstance(meta.get("source_kind"), str) or not str(
                meta.get("source_kind")
            ).strip():
                errors.append(f"evidence source_kind 必须为非空字符串: {node['path']}")
            if meta.get("carrier") not in CARRIER_VALUES:
                errors.append(f"evidence carrier 非法: {node['path']}")
            for field in (
                "teaching_item_id",
                "teaching_delivery_fingerprint_at_observation",
                "verification_item_id",
                "verification_task_id",
                "bound_verification_task_id",
                "route_id_at_observation",
                "route_binding_id",
                "decision_fingerprint_at_observation",
                "error_signature",
            ):
                value = meta.get(field)
                if value is not None and (not isinstance(value, str) or not value.strip()):
                    errors.append(f"evidence {field} 必须为非空字符串或 null: {node['path']}")
            route_version_at_observation = meta.get("route_version_at_observation")
            if route_version_at_observation is not None and (
                not isinstance(route_version_at_observation, int)
                or isinstance(route_version_at_observation, bool)
                or route_version_at_observation < 1
            ):
                errors.append(
                    f"evidence route_version_at_observation 必须为正整数或 null: {node['path']}"
                )
            verification_task_id = meta.get("verification_task_id")
            bound_verification_task_id = meta.get("bound_verification_task_id")
            if verification_task_id != bound_verification_task_id:
                errors.append(
                    f"evidence verification_task_id 与 bound_verification_task_id 不一致: "
                    f"{node['path']} stored={verification_task_id} bound={bound_verification_task_id}"
                )
            phase = meta.get("phase")
            if phase in {
                "teaching_process",
                "verification",
                "retention",
            } and (
                not isinstance(verification_task_id, str)
                or not verification_task_id.strip()
                or not isinstance(bound_verification_task_id, str)
                or not bound_verification_task_id.strip()
            ):
                errors.append(
                    "teaching_process/verification/retention evidence 必须绑定验证任务: "
                    f"{node['path']}"
                )
            if not isinstance(meta.get("verification_unseen"), bool):
                errors.append(f"evidence verification_unseen 必须是布尔值: {node['path']}")
            if not isinstance(meta.get("answer_revealed_before_first_attempt"), bool):
                errors.append(
                    f"evidence answer_revealed_before_first_attempt 必须是布尔值: {node['path']}"
                )
            if meta.get("phase") == "teaching_process":
                if meta.get("verification_unseen") is not False:
                    errors.append(
                        f"teaching_process verification_unseen 必须为 false: {node['path']}"
                    )
                if meta.get("answer_revealed_before_first_attempt") is not False:
                    errors.append(
                        "teaching_process 不得把提前泄露答案的记录作为可继续过程: "
                        f"{node['path']}"
                    )
                process_sentinels = {
                    "verification_item_id": None,
                    "independence": "not_observed",
                    "near_transfer": "not_tested",
                    "delayed_retention": "not_tested",
                    "retention_delay_days": 0,
                }
                for field, expected in process_sentinels.items():
                    if meta.get(field) != expected:
                        errors.append(
                            "teaching_process 不得保存本阶段未测的具体表现值: "
                            f"{node['path']}/{field} expected={expected!r}"
                        )
                delivery_fingerprint = meta.get(
                    "teaching_delivery_fingerprint_at_observation"
                )
                if (
                    not isinstance(delivery_fingerprint, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", delivery_fingerprint)
                ):
                    errors.append(
                        "teaching_process 必须绑定已发行教学内容的 SHA-256 指纹: "
                        f"{node['path']}"
                    )
                decision_fingerprint = meta.get(
                    "decision_fingerprint_at_observation"
                )
                if (
                    not isinstance(decision_fingerprint, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", decision_fingerprint)
                ):
                    errors.append(
                        "teaching_process 必须绑定教学决策 epoch 的 SHA-256 指纹: "
                        f"{node['path']}"
                    )
            elif meta.get("teaching_delivery_fingerprint_at_observation") is not None:
                errors.append(
                    "非 teaching_process evidence 的 teaching delivery 指纹必须为 null: "
                    f"{node['path']}"
                )
            if meta.get("phase") == "diagnostic":
                diagnostic_sentinels = {
                    "verification_item_id": None,
                    "verification_task_id": None,
                    "bound_verification_task_id": None,
                    "decision_fingerprint_at_observation": None,
                    "verification_unseen": False,
                    "answer_revealed_before_first_attempt": False,
                    "near_transfer": "not_tested",
                    "delayed_retention": "not_tested",
                    "retention_delay_days": 0,
                    "mastery_eligible": False,
                }
                for field, expected in diagnostic_sentinels.items():
                    if meta.get(field) != expected:
                        errors.append(
                            "diagnostic 不得保存其他阶段字段: "
                            f"{node['path']}/{field} expected={expected!r}"
                        )
            if meta.get("phase") in {"verification", "retention"} and meta.get(
                "decision_fingerprint_at_observation"
            ) is not None:
                errors.append(
                    "verification/retention 只绑定 route issuance，不得自填 teaching decision fingerprint: "
                    f"{node['path']}"
                )
            if meta.get("phase") == "verification":
                verification_sentinels = {
                    "delayed_retention": "not_tested",
                    "retention_delay_days": 0,
                    "baseline_evidence_id": None,
                    "retention_task_id": None,
                    "scheduled_for": None,
                }
                for field, expected in verification_sentinels.items():
                    if meta.get(field) != expected:
                        errors.append(
                            "verification 不得保存 retention 阶段值: "
                            f"{node['path']}/{field} expected={expected!r}"
                        )
            if meta.get("phase") == "retention":
                if meta.get("near_transfer") != "not_tested":
                    errors.append(
                        f"retention near_transfer 必须为 not_tested: {node['path']}"
                    )
                if meta.get("explanation_quality") != "not_tested":
                    errors.append(
                        f"retention explanation_quality 必须为 not_tested: {node['path']}"
                    )
                if "delayed_retention" not in meta.get("demonstrates", []):
                    errors.append(
                        f"retention demonstrates 必须声明 delayed_retention: {node['path']}"
                    )
            consumer_ids = meta.get("consumer_ids")
            if (
                not isinstance(consumer_ids, list)
                or not consumer_ids
                or any(item not in VALUE_CONSUMER_VALUES for item in consumer_ids)
                or len(consumer_ids) != len(set(consumer_ids))
            ):
                errors.append(f"evidence consumer_ids 非法或为空: {node['path']}")
            source_ref_ids = meta.get("source_ref_ids")
            if (
                not isinstance(source_ref_ids, list)
                or not source_ref_ids
                or any(not isinstance(item, str) or not item.strip() for item in source_ref_ids)
                or len(source_ref_ids) != len(set(source_ref_ids))
            ):
                errors.append(f"evidence source_ref_ids 非法或为空: {node['path']}")
            derived_session_ids = [
                relation.get("target")
                for relation in node.get("relations", [])
                if relation.get("type") == "derived_from"
                and index.get("nodes", {})
                .get(str(relation.get("target")), {})
                .get("type")
                == "session"
            ]
            canonical_source_refs: list[str] = []
            if len(derived_session_ids) != 1:
                errors.append(
                    f"evidence 必须唯一 derived_from 一个 canonical session: {node['path']}"
                )
            else:
                source_session_id = str(derived_session_ids[0])
                source_session = node_meta.get(source_session_id)
                if source_session is None:
                    source_session_node = index.get("nodes", {}).get(
                        source_session_id, {}
                    )
                    source_session = (
                        parse_note(vault / source_session_node["path"])[0]
                        if source_session_node.get("path")
                        else {}
                    )
                if meta.get("source_kind") != source_session.get("source_kind"):
                    errors.append(
                        f"evidence source_kind 必须从 canonical session 派生: {node['path']}"
                    )
                session_source_ref = source_session.get("source_ref")
                if (
                    not isinstance(session_source_ref, str)
                    or not session_source_ref.strip()
                ):
                    errors.append(
                        f"canonical session.source_ref 非法: {node['path']}"
                    )
                else:
                    canonical_source_refs = [session_source_ref]
                    if source_ref_ids != canonical_source_refs:
                        errors.append(
                            "evidence source_ref_ids 必须严格等于 canonical "
                            f"session.source_ref: {node['path']}"
                        )
            field_bindings = meta.get("field_bindings")
            if not isinstance(field_bindings, dict):
                errors.append(f"evidence field_bindings 必须是对象: {node['path']}")
                field_bindings = {}
            valid_record_consumers = {
                item
                for item in consumer_ids
                if isinstance(consumer_ids, list)
                and isinstance(item, str)
                and item in VALUE_CONSUMER_VALUES
            }
            expected_binding_fields = {
                field
                for field in EVIDENCE_FIELD_CONSUMERS
                if evidence_field_is_actionable(meta, field)
                and evidence_field_consumers_for_phase(meta, field)
            }
            missing_bindings = sorted(expected_binding_fields.difference(field_bindings))
            if missing_bindings:
                errors.append(
                    f"evidence 关键结果字段缺少 field_bindings: {node['path']} "
                    f"fields={','.join(missing_bindings)}"
                )
            unexpected_bindings = sorted(set(field_bindings).difference(expected_binding_fields))
            if unexpected_bindings:
                errors.append(
                    f"evidence field_bindings 含无实际消费者字段: {node['path']} "
                    f"fields={','.join(unexpected_bindings)}"
                )
            expected_scope = {
                "learner_id": meta.get("learner_id"),
                "goal_id": meta.get("goal_id"),
                "concept_id": meta.get("concept_id"),
                "contract_id": meta.get("contract_id"),
                "contract_version": meta.get("contract_version"),
            }
            bound_consumer_union: set[str] = set()
            for field in sorted(set(field_bindings).intersection(EVIDENCE_FIELD_CONSUMERS)):
                binding = field_bindings.get(field)
                if not isinstance(binding, dict):
                    errors.append(f"evidence field_binding 不是对象: {node['path']}/{field}")
                    continue
                binding_consumers = binding.get("consumers")
                if (
                    not isinstance(binding_consumers, list)
                    or not binding_consumers
                    or any(
                        not isinstance(item, str) or item not in VALUE_CONSUMER_VALUES
                        for item in binding_consumers
                    )
                    or len(binding_consumers) != len(set(binding_consumers))
                    or not set(binding_consumers).issubset(
                        evidence_field_consumers_for_phase(meta, field)
                    )
                    or not isinstance(consumer_ids, list)
                    or any(not isinstance(item, str) for item in consumer_ids)
                    or not set(binding_consumers).issubset(set(consumer_ids))
                ):
                    errors.append(
                        f"evidence field_binding consumers 未绑定到 note consumers: "
                        f"{node['path']}/{field}"
                    )
                else:
                    bound_consumer_union.update(binding_consumers)
                binding_sources = binding.get("source_ref_ids")
                if (
                    not isinstance(binding_sources, list)
                    or not binding_sources
                    or any(not isinstance(item, str) or not item.strip() for item in binding_sources)
                    or len(binding_sources) != len(set(binding_sources))
                    or not isinstance(source_ref_ids, list)
                    or any(not isinstance(item, str) for item in source_ref_ids)
                    or binding_sources != canonical_source_refs
                ):
                    errors.append(
                        f"evidence field_binding source_ref_ids 非法: {node['path']}/{field}"
                    )
                if binding.get("scope") != expected_scope:
                    errors.append(f"evidence field_binding scope 不一致: {node['path']}/{field}")
                if binding.get("observed_at") != meta.get("observed_at"):
                    errors.append(f"evidence field_binding observed_at 不一致: {node['path']}/{field}")
                if binding.get("validity") != meta.get("observation_validity"):
                    errors.append(f"evidence field_binding validity 不一致: {node['path']}/{field}")
            if bound_consumer_union != valid_record_consumers:
                errors.append(
                    f"evidence consumer_ids 必须等于字段消费者并集: {node['path']} "
                    f"record={','.join(sorted(valid_record_consumers))} "
                    f"field_union={','.join(sorted(bound_consumer_union))}"
                )
            if meta.get("observation_validity") not in OBSERVATION_VALIDITY_VALUES:
                errors.append(f"evidence observation_validity 非法: {node['path']}")
            if meta.get("observation_confidence") not in CONFIDENCE_VALUES:
                errors.append(f"evidence observation_confidence 非法: {node['path']}")
            derived_eligible_for_confidence, _confidence_eligibility_failures = (
                evidence_mastery_eligibility(
                    meta, allow_synthetic_demo=allow_synthetic_demo
                )
            )
            expected_confidence, expected_confidence_basis = derive_observation_confidence(
                meta,
                derived_mastery_eligible=derived_eligible_for_confidence,
                allow_synthetic_demo=allow_synthetic_demo,
            )
            if meta.get("observation_confidence") != expected_confidence:
                errors.append(
                    f"evidence observation_confidence 不是来源与资格推导值: {node['path']} "
                    f"stored={meta.get('observation_confidence')} derived={expected_confidence}"
                )
            if meta.get("observation_confidence_basis") != expected_confidence_basis:
                errors.append(
                    f"evidence observation_confidence_basis 不是推导值: {node['path']}"
                )
            consumer_set = (
                {item for item in consumer_ids if isinstance(item, str)}
                if isinstance(consumer_ids, list)
                else set()
            )
            if meta.get("observation_validity") != "valid" and {
                "verification_gate",
                "contract_recompute",
                "retention_recompute",
            }.intersection(consumer_set):
                errors.append(f"evidence 非 valid 时不得进入 mastery 消费者: {node['path']}")
            derived_eligible, eligibility_failures = evidence_mastery_eligibility(
                meta, allow_synthetic_demo=allow_synthetic_demo
            )
            if not isinstance(meta.get("mastery_eligible"), bool):
                errors.append(f"evidence mastery_eligible 必须是布尔值: {node['path']}")
            elif meta.get("mastery_eligible") is not derived_eligible:
                errors.append(
                    f"evidence mastery_eligible 不是原始字段推导值: {node['path']} "
                    f"stored={meta.get('mastery_eligible')} derived={derived_eligible} "
                    f"reasons={','.join(eligibility_failures)}"
                )
            if meta.get("phase") in {"diagnostic", "teaching_process"} and meta.get(
                "mastery_eligible"
            ) is not False:
                errors.append(f"过程或诊断 evidence 不得满足 mastery: {node['path']}")
            demonstrates = meta.get("demonstrates")
            if (
                not isinstance(demonstrates, list)
                or not demonstrates
                or not all(isinstance(item, str) and item for item in demonstrates)
            ):
                errors.append(f"evidence demonstrates 必须是非空字符串数组: {node['path']}")
                demonstrates = []
            if meta.get("result") not in EVIDENCE_RESULT_VALUES:
                errors.append(f"evidence result 非法: {node['path']}")
            if meta.get("independence") not in INDEPENDENCE_VALUES:
                errors.append(f"evidence independence 非法: {node['path']}")
            if meta.get("explanation_quality") not in EXPLANATION_QUALITY_VALUES:
                errors.append(f"evidence explanation_quality 非法: {node['path']}")
            if not isinstance(meta.get("response_correct"), bool):
                errors.append(f"evidence response_correct 必须是布尔值: {node['path']}")
            elapsed_seconds = meta.get("elapsed_seconds")
            if (
                not isinstance(elapsed_seconds, (int, float))
                or isinstance(elapsed_seconds, bool)
                or elapsed_seconds < 0
            ):
                errors.append(f"evidence elapsed_seconds 必须是非负数: {node['path']}")
            attempts = meta.get("attempts")
            hint_count = meta.get("hint_count")
            if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
                errors.append(f"evidence attempts 必须是正整数: {node['path']}")
            if not isinstance(hint_count, int) or isinstance(hint_count, bool) or hint_count < 0:
                errors.append(f"evidence hint_count 必须是非负整数: {node['path']}")
            effort = meta.get("self_reported_effort")
            if effort != "not_collected" and (
                not isinstance(effort, int) or isinstance(effort, bool) or not 1 <= effort <= 7
            ):
                errors.append(f"evidence self_reported_effort 必须为 1..7 或 not_collected: {node['path']}")
            if not is_unit_interval(meta.get("immediate_performance")):
                errors.append(f"evidence immediate_performance 必须在 0..1: {node['path']}")
            near_transfer = meta.get("near_transfer")
            near_state = isinstance(near_transfer, str) and near_transfer in {"not_tested", "pending"}
            if not is_unit_interval(near_transfer) and not near_state:
                errors.append(f"evidence near_transfer 必须在 0..1 或为未测状态: {node['path']}")
            delayed_retention = meta.get("delayed_retention")
            retention_state = (
                isinstance(delayed_retention, str) and delayed_retention in MEASUREMENT_PENDING_VALUES
            )
            if not is_unit_interval(delayed_retention) and not retention_state:
                errors.append(f"evidence delayed_retention 必须在 0..1 或为状态枚举: {node['path']}")
            retention_delay_days = meta.get("retention_delay_days")
            if (
                not isinstance(retention_delay_days, int)
                or isinstance(retention_delay_days, bool)
                or retention_delay_days < 0
            ):
                errors.append(f"evidence retention_delay_days 必须是非负整数: {node['path']}")
            if meta.get("phase") == "retention":
                for field in ("baseline_evidence_id", "retention_task_id", "scheduled_for"):
                    if not isinstance(meta.get(field), str) or not str(meta.get(field)).strip():
                        errors.append(f"retention evidence 缺少 {field}: {node['path']}")
                if meta.get("retention_task_id") != meta.get("verification_task_id"):
                    errors.append(
                        f"retention_task_id 与 verification_task_id 不一致: {node['path']}"
                    )
                try:
                    scheduled_for = parse_iso_instant(meta.get("scheduled_for"))
                    observed_at = parse_iso_instant(meta.get("observed_at"))
                    if observed_at < scheduled_for:
                        errors.append(f"retention evidence observed_at 早于 scheduled_for: {node['path']}")
                except ValueError:
                    errors.append(f"retention evidence scheduled_for 必须是带时区 ISO 时间: {node['path']}")
            elif retention_delay_days != 0:
                errors.append(f"非 retention evidence 的 retention_delay_days 必须为 0: {node['path']}")
            if meta.get("result") == "pass" and meta.get("response_correct") is not True:
                errors.append(f"evidence pass 与 response_correct 冲突: {node['path']}")
            if meta.get("assistance_level") == "A0" and hint_count != 0:
                errors.append(f"evidence A0 与 hint_count 冲突: {node['path']}")
            if meta.get("independence") == "independent" and meta.get("assistance_level") != "A0":
                errors.append(f"evidence independent 与 assistance_level 冲突: {node['path']}")
            if (
                meta.get("result") == "pass"
                and "explanation" in demonstrates
                and meta.get("explanation_quality") != "pass"
            ):
                errors.append(f"evidence pass 的 explanation 声明与 explanation_quality 冲突: {node['path']}")
            if "near_transfer" in demonstrates and not is_unit_interval(near_transfer):
                errors.append(f"evidence 声明 near_transfer 但没有数值观测: {node['path']}")
            if "delayed_retention" in demonstrates and (
                not is_unit_interval(delayed_retention)
                or not isinstance(retention_delay_days, int)
                or retention_delay_days < 1
            ):
                errors.append(f"evidence 声明 delayed_retention 但没有有效延迟观测: {node['path']}")
            if not isinstance(meta.get("contract_version"), int) or isinstance(meta.get("contract_version"), bool):
                errors.append(f"evidence contract_version 非法: {node['path']}")
            try:
                observed_instant = parse_iso_instant(meta.get("observed_at"))
                if observed_instant > maximum_observation_time:
                    errors.append(
                        f"evidence observed_at 不得位于未来: {node['path']}"
                    )
            except (TypeError, ValueError):
                errors.append(f"evidence observed_at 必须是带时区的 ISO 时间: {node['path']}")

        if node_type == "goal":
            contracts = meta.get("mastery_contracts")
            if not isinstance(contracts, list) or not contracts:
                errors.append(f"goal 缺少结构化 mastery_contracts: {node['path']}")
                contracts = []
            by_id: dict[tuple[str, int], dict[str, Any]] = {}
            for contract in contracts:
                if not isinstance(contract, dict):
                    errors.append(f"goal mastery_contract 不是对象: {node['path']}")
                    continue
                contract_id = contract.get("id")
                contract_version = contract.get("version")
                concept_id = contract.get("concept_id")
                requirements_meta = contract.get("requirements")
                if not isinstance(contract_id, str) or not contract_id:
                    errors.append(f"goal mastery_contract 缺少 id: {node['path']}")
                    continue
                if not isinstance(contract_version, int) or isinstance(contract_version, bool) or contract_version < 1:
                    errors.append(f"goal mastery_contract version 非法: {node_id}/{contract_id}")
                    continue
                contract_key = (contract_id, contract_version)
                if contract_key in by_id:
                    errors.append(f"goal mastery_contract id/version 重复: {node_id}/{contract_id}/v{contract_version}")
                if concept_id not in index.get("nodes", {}) or index["nodes"].get(concept_id, {}).get("type") != "concept":
                    errors.append(f"goal mastery_contract concept_id 非法: {node_id}/{contract_id}")
                if not isinstance(requirements_meta, dict):
                    errors.append(f"goal mastery_contract requirements 非法: {node_id}/{contract_id}")
                else:
                    minimum = requirements_meta.get("minimum_qualified_evidence")
                    capabilities = requirements_meta.get("required_capabilities")
                    transfer = requirements_meta.get("min_near_transfer")
                    retention = requirements_meta.get("delayed_retention")
                    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
                        errors.append(f"mastery_contract minimum_qualified_evidence 非法: {node_id}/{contract_id}")
                    if not isinstance(capabilities, list) or not capabilities or not all(isinstance(item, str) and item for item in capabilities):
                        errors.append(f"mastery_contract required_capabilities 非法: {node_id}/{contract_id}")
                    if "min_near_transfer" not in requirements_meta:
                        errors.append(f"mastery_contract 缺少 min_near_transfer: {node_id}/{contract_id}")
                    elif transfer is not None and (
                        not isinstance(transfer, (int, float))
                        or isinstance(transfer, bool)
                        or not 0 <= float(transfer) <= 1
                    ):
                        errors.append(f"mastery_contract min_near_transfer 非法: {node_id}/{contract_id}")
                    if not isinstance(retention, dict) or not isinstance(retention.get("required"), bool):
                        errors.append(f"mastery_contract delayed_retention 非法: {node_id}/{contract_id}")
                    elif retention.get("required"):
                        score = retention.get("min_score")
                        days = retention.get("min_delay_days")
                        if (
                            not isinstance(score, (int, float))
                            or isinstance(score, bool)
                            or not 0 <= float(score) <= 1
                            or not isinstance(days, int)
                            or isinstance(days, bool)
                            or days < 1
                        ):
                            errors.append(f"mastery_contract 延迟阈值非法: {node_id}/{contract_id}")
                by_id[contract_key] = contract
            goal_contracts[node_id] = by_id

        if node_type == "resource":
            carrier = meta.get("carrier")
            supported_activities = meta.get("supported_activities")
            try:
                canonical_cost_vector(
                    meta.get("cost_vector"),
                    label=f"resource {node_id}.cost_vector",
                )
            except VaultError as exc:
                errors.append(str(exc))
            if (
                not isinstance(supported_activities, list)
                or not supported_activities
                or any(not isinstance(item, str) or not item.strip() for item in supported_activities)
                or len(supported_activities) != len(set(supported_activities))
            ):
                errors.append(f"resource supported_activities 非法: {node['path']}")
            elif meta.get("activity") not in supported_activities:
                errors.append(f"resource activity 不在 supported_activities: {node['path']}")
            if meta.get("modality") == "text":
                if carrier not in {"text_document", "text_dialogue", "text_hybrid"}:
                    errors.append(f"文字 resource carrier 非法: {node['path']}")
                if meta.get("protocol_version") != TEXT_PROTOCOL_VERSION:
                    errors.append(f"文字 resource protocol_version 非法: {node['path']}")
                if meta.get("verification_required") is not True:
                    errors.append(f"文字 resource 必须要求独立验证: {node['path']}")
                if not meta.get("text_format"):
                    errors.append(f"文字 resource 缺少 text_format: {node['path']}")
                for task_key in ("diagnostic_probe", "verification_task"):
                    task = meta.get(task_key)
                    if not isinstance(task, dict) or not all(
                        isinstance(task.get(key), str) and task[key].strip()
                        for key in ("id", "prompt", "success_criteria")
                    ):
                        errors.append(f"文字 resource {task_key} 非法: {node['path']}")
                verification_task = meta.get("verification_task")
                protected_answers = (
                    verification_task.get("protected_answers")
                    if isinstance(verification_task, dict)
                    else None
                )
                if not (
                    isinstance(protected_answers, str)
                    and protected_answers.strip()
                    or isinstance(protected_answers, list)
                    and protected_answers
                    and all(isinstance(item, str) and item.strip() for item in protected_answers)
                ):
                    errors.append(
                        f"文字 resource verification_task.protected_answers 非法: {node['path']}"
                    )

        if node_type == "teaching_delivery":
            required_delivery_fields = (
                "delivery_contract",
                "learner_id",
                "goal_id",
                "concept_id",
                "contract_id",
                "contract_version",
                "route_id",
                "route_version",
                "route_binding_id",
                "context_key",
                "decision_fingerprint",
                "resource_id",
                "activity",
                "carrier",
                "delivery_plan",
                "delivery_plan_fingerprint",
                "issued_at",
                "source_kind",
                "source_ref_ids",
            )
            for required in required_delivery_fields:
                if required not in meta:
                    errors.append(
                        f"teaching_delivery 缺少 {required}: {node['path']}"
                    )
            if meta.get("delivery_contract") != TEACHING_DELIVERY_SCHEMA:
                errors.append(f"teaching_delivery contract 非法: {node['path']}")
            for field in (
                "learner_id",
                "goal_id",
                "concept_id",
                "contract_id",
                "route_id",
                "route_binding_id",
                "context_key",
                "resource_id",
                "activity",
            ):
                if not isinstance(meta.get(field), str) or not str(meta[field]).strip():
                    errors.append(f"teaching_delivery {field} 非法: {node['path']}")
            for field in ("contract_version", "route_version"):
                value = meta.get(field)
                if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                    errors.append(f"teaching_delivery {field} 非法: {node['path']}")
            if meta.get("carrier") not in CARRIER_VALUES:
                errors.append(f"teaching_delivery carrier 非法: {node['path']}")
            decision_fingerprint = meta.get("decision_fingerprint")
            if (
                not isinstance(decision_fingerprint, str)
                or not re.fullmatch(r"[0-9a-f]{64}", decision_fingerprint)
            ):
                errors.append(
                    f"teaching_delivery decision_fingerprint 非法: {node['path']}"
                )
            delivery_plan = meta.get("delivery_plan")
            delivery_fingerprint = meta.get("delivery_plan_fingerprint")
            if not isinstance(delivery_plan, dict):
                errors.append(f"teaching_delivery delivery_plan 必须是对象: {node['path']}")
            elif delivery_fingerprint != sha256_fingerprint(delivery_plan):
                errors.append(
                    f"teaching_delivery delivery_plan_fingerprint 与实际投影不一致: {node['path']}"
                )
            else:
                try:
                    policy = load_text_learning_policy()
                    if set(delivery_plan) != set(policy.USER_DELIVERY_FIELDS):
                        raise ValueError("delivery fields mismatch")
                    for field, value in delivery_plan.items():
                        policy._validate_user_value(value, field)
                except (ValueError, TypeError, AttributeError) as exc:
                    errors.append(
                        f"teaching_delivery 不是合法用户白名单投影: {node['path']} ({exc})"
                    )
            try:
                delivery_instant = parse_iso_instant(meta.get("issued_at"))
                if delivery_instant > validation_now:
                    errors.append(
                        f"teaching_delivery issued_at 不得位于未来: {node['path']}"
                    )
            except (TypeError, ValueError):
                errors.append(f"teaching_delivery issued_at 非法: {node['path']}")
            if meta.get("source_kind") not in {"agent_projection", "synthetic_demo"}:
                errors.append(f"teaching_delivery source_kind 非法: {node['path']}")
            if (
                not isinstance(meta.get("source_ref_ids"), list)
                or not meta.get("source_ref_ids")
                or any(
                    not isinstance(item, str) or not item.strip()
                    for item in meta.get("source_ref_ids", [])
                )
            ):
                errors.append(f"teaching_delivery source_ref_ids 非法: {node['path']}")

        if node_type == "retention_schedule":
            if set(meta) != set(RETENTION_SCHEDULE_METADATA_FIELDS):
                errors.append(
                    "retention_schedule metadata 字段必须精确匹配合同"
                    f"（missing={sorted(RETENTION_SCHEDULE_METADATA_FIELDS.difference(meta))},"
                    f" unknown={sorted(set(meta).difference(RETENTION_SCHEDULE_METADATA_FIELDS))}）: "
                    f"{node['path']}"
                )
            required_schedule_fields = (
                "schedule_contract",
                *RETENTION_SCOPE_FIELDS,
                "baseline_evidence_id",
                "retention_task_id",
                "route_binding_id",
                "route_id",
                "route_version",
                "context_key",
                "verification_task_fingerprint",
                "not_before",
                "scheduled_for",
                "supersedes_schedule_id",
                "scheduled_at",
                "receipt_fingerprint",
                "immutable",
            )
            for field in required_schedule_fields:
                if field not in meta:
                    errors.append(f"retention_schedule 缺少 {field}: {node['path']}")
            if meta.get("schedule_contract") != RETENTION_SCHEDULE_SCHEMA:
                errors.append(f"retention_schedule contract 非法: {node['path']}")
            for field in (
                "learner_id",
                "goal_id",
                "concept_id",
                "contract_id",
                "baseline_evidence_id",
                "retention_task_id",
                "route_binding_id",
                "route_id",
                "context_key",
            ):
                if not isinstance(meta.get(field), str) or not str(meta[field]).strip():
                    errors.append(f"retention_schedule {field} 非法: {node['path']}")
            for field in ("contract_version", "route_version"):
                value = meta.get(field)
                if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                    errors.append(f"retention_schedule {field} 非法: {node['path']}")
            if meta.get("immutable") is not True:
                errors.append(f"retention_schedule 必须 immutable=true: {node['path']}")
            if not (
                meta.get("created_at")
                == meta.get("updated_at")
                == meta.get("scheduled_at")
            ):
                errors.append(
                    f"retention_schedule created/updated/scheduled_at 必须一致: {node['path']}"
                )
            if meta.get("privacy") != "sensitive":
                errors.append(f"retention_schedule 必须 privacy=sensitive: {node['path']}")
            if "protected_answers" in json.dumps(meta, ensure_ascii=False):
                errors.append(f"retention_schedule 不得保存 protected_answers: {node['path']}")
            for field in ("scheduled_at", "scheduled_for"):
                try:
                    instant = parse_iso_instant(meta.get(field))
                    if field == "scheduled_at" and instant > maximum_observation_time:
                        errors.append(f"retention_schedule scheduled_at 不得位于未来: {node['path']}")
                except (TypeError, ValueError):
                    errors.append(f"retention_schedule {field} 非法: {node['path']}")
            not_before = meta.get("not_before")
            if not_before is not None:
                try:
                    parse_iso_instant(not_before)
                except (TypeError, ValueError):
                    errors.append(f"retention_schedule not_before 非法: {node['path']}")
            supersedes_schedule_id = meta.get("supersedes_schedule_id")
            if supersedes_schedule_id is not None and (
                not isinstance(supersedes_schedule_id, str)
                or not supersedes_schedule_id.strip()
            ):
                errors.append(f"retention_schedule supersedes_schedule_id 非法: {node['path']}")
            if meta.get("id") != retention_schedule_id(
                route_binding_id=str(meta.get("route_binding_id")),
                baseline_evidence_id=str(meta.get("baseline_evidence_id")),
                scheduled_for=str(meta.get("scheduled_for")),
            ):
                errors.append(f"retention_schedule id 不是规范派生值: {node['path']}")
            fingerprint = meta.get("receipt_fingerprint")
            if (
                not isinstance(fingerprint, str)
                or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
                or fingerprint != sha256_fingerprint(_schedule_fingerprint_payload(meta))
            ):
                errors.append(f"retention_schedule receipt_fingerprint 非法: {node['path']}")

        if node_type == "verification_open":
            if set(meta) != set(VERIFICATION_OPEN_METADATA_FIELDS):
                errors.append(
                    "verification_open metadata 字段必须精确匹配合同"
                    f"（missing={sorted(VERIFICATION_OPEN_METADATA_FIELDS.difference(meta))},"
                    f" unknown={sorted(set(meta).difference(VERIFICATION_OPEN_METADATA_FIELDS))}）: "
                    f"{node['path']}"
                )
            required_open_fields = (
                "open_contract",
                *RETENTION_SCOPE_FIELDS,
                "retention_schedule_id",
                "baseline_evidence_id",
                "retention_task_id",
                "route_binding_id",
                "route_id",
                "route_version",
                "context_key",
                "verification_task_fingerprint",
                "schedule_fingerprint",
                "resource_id",
                "activity",
                "carrier",
                "scheduled_for",
                "opened_at",
                "receipt_fingerprint",
                "immutable",
            )
            for field in required_open_fields:
                if field not in meta:
                    errors.append(f"verification_open 缺少 {field}: {node['path']}")
            if meta.get("open_contract") != VERIFICATION_OPEN_SCHEMA:
                errors.append(f"verification_open contract 非法: {node['path']}")
            for field in (
                "learner_id",
                "goal_id",
                "concept_id",
                "contract_id",
                "retention_schedule_id",
                "baseline_evidence_id",
                "retention_task_id",
                "route_binding_id",
                "route_id",
                "context_key",
                "verification_task_fingerprint",
                "schedule_fingerprint",
                "resource_id",
                "activity",
                "carrier",
            ):
                if not isinstance(meta.get(field), str) or not str(meta[field]).strip():
                    errors.append(f"verification_open {field} 非法: {node['path']}")
            if meta.get("carrier") not in CARRIER_VALUES:
                errors.append(f"verification_open carrier 非法: {node['path']}")
            for field in ("contract_version", "route_version"):
                value = meta.get(field)
                if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                    errors.append(f"verification_open {field} 非法: {node['path']}")
            if meta.get("immutable") is not True or meta.get("privacy") != "sensitive":
                errors.append(f"verification_open 必须 immutable + sensitive: {node['path']}")
            if not (
                meta.get("created_at")
                == meta.get("updated_at")
                == meta.get("opened_at")
            ):
                errors.append(
                    f"verification_open created/updated/opened_at 必须一致: {node['path']}"
                )
            if "protected_answers" in json.dumps(meta, ensure_ascii=False):
                errors.append(f"verification_open 不得保存 protected_answers: {node['path']}")
            for field in ("scheduled_for", "opened_at"):
                try:
                    instant = parse_iso_instant(meta.get(field))
                    if field == "opened_at" and instant > maximum_observation_time:
                        errors.append(f"verification_open opened_at 不得位于未来: {node['path']}")
                except (TypeError, ValueError):
                    errors.append(f"verification_open {field} 非法: {node['path']}")
            if meta.get("id") != verification_open_id(
                str(meta.get("retention_schedule_id"))
            ):
                errors.append(f"verification_open id 不是规范派生值: {node['path']}")
            fingerprint = meta.get("receipt_fingerprint")
            if (
                not isinstance(fingerprint, str)
                or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
                or fingerprint != sha256_fingerprint(_open_fingerprint_payload(meta))
            ):
                errors.append(f"verification_open receipt_fingerprint 非法: {node['path']}")

        if node_type == "intervention":
            if meta.get("adaptation_confidence") not in {"unknown", "tentative", "emerging", "supported"}:
                errors.append(f"adaptation_confidence 非法: {node['path']}")
            for required in ("status", "route_id", "route_version", "goal_id", "current_checkpoint", "current_activity_id", "current_probe_id", "current_verification_task_id", "completed_step_evidence_ids", "recovery_status", "recovered_from", "path", "medium_policy", "carrier"):
                if required not in meta:
                    errors.append(f"intervention 缺少 {required}: {node['path']}")
            for required in ("current_activity_id", "current_probe_id", "current_verification_task_id"):
                if required in meta and (
                    not isinstance(meta.get(required), str) or not meta[required].strip()
                ):
                    errors.append(f"intervention {required} 非法: {node['path']}")
            if meta.get("status") not in ROUTE_STATUS_VALUES:
                errors.append(f"intervention status 非法: {node['path']}")
            if meta.get("medium_policy") == "text_preferred" and meta.get("carrier") not in {
                "text_document",
                "text_dialogue",
                "text_hybrid",
            }:
                errors.append(f"text_preferred intervention carrier 非法: {node['path']}")
            used_resource_ids = [
                relation["target"]
                for relation in node.get("relations", [])
                if relation.get("type") == "uses"
            ]
            activity_id = meta.get("current_activity_id")
            if activity_id not in used_resource_ids:
                errors.append(f"intervention current_activity_id 未由 uses 绑定: {node['path']}")
            elif activity_id in index.get("nodes", {}):
                resource_node = index["nodes"][activity_id]
                resource_meta, _, resource_parse_errors = parse_note(vault / resource_node["path"])
                if resource_parse_errors or resource_node.get("type") != "resource":
                    errors.append(f"intervention current_activity_id 不是有效 resource: {node['path']}")
                else:
                    probe = resource_meta.get("diagnostic_probe")
                    verification = resource_meta.get("verification_task")
                    if not isinstance(probe, dict) or probe.get("id") != meta.get("current_probe_id"):
                        errors.append(f"intervention current_probe_id 与 resource 不一致: {node['path']}")
                    if (
                        not isinstance(verification, dict)
                        or verification.get("id") != meta.get("current_verification_task_id")
                    ):
                        errors.append(
                            f"intervention current_verification_task_id 与 resource 不一致: {node['path']}"
                        )
                    taught_ids = {
                        relation["target"]
                        for relation in resource_node.get("relations", [])
                        if relation.get("type") == "teaches"
                    }
                    if meta.get("current_checkpoint") not in taught_ids:
                        errors.append(f"current activity 未 teaches 当前 checkpoint: {node['path']}")
            resolution_fields = (
                "teaching_resolution_schema",
                "resolved_activity",
                "resolved_carrier",
                "resolved_resource_id",
                "resolved_profile_refs",
                "resolved_profile_level",
                "resolved_profile_usage",
                "resolved_process_refs",
                "resolved_process_status",
                "resolved_process_feedback_rule",
                "resolved_process_next_action",
                "resolved_process_cost",
                "resolved_process_cost_selection",
                "resolved_cost_vector",
                "resolved_cost_basis",
                "resolved_same_error_count",
                "resolved_text_variants_tried",
                "resolved_latest_teaching_item_id",
                "resolved_max_observed_assistance_level",
                "resolved_process_support_load",
                "resolved_route_binding_id",
                "resolved_context_key",
                "resolved_at",
                "process_refreshed_at",
                "resolved_decision_fingerprint",
            )
            has_resolution = any(field in meta for field in resolution_fields)
            if meta.get("status") == "active" and not has_resolution and not allow_unresolved_teaching:
                errors.append(f"active intervention 尚未落盘教学决策: {node['path']}")
            if has_resolution:
                if any(field not in meta for field in resolution_fields):
                    errors.append(f"intervention 教学决策字段不完整: {node['path']}")
                if meta.get("teaching_resolution_schema") != TEACHING_RESOLUTION_SCHEMA:
                    errors.append(f"intervention teaching_resolution_schema 非法: {node['path']}")
                if meta.get("resolved_resource_id") != meta.get("current_activity_id"):
                    errors.append(f"intervention resolved_resource_id 与 current_activity_id 不一致: {node['path']}")
                if meta.get("resolved_carrier") != meta.get("carrier"):
                    errors.append(f"intervention resolved_carrier 与 carrier 不一致: {node['path']}")
                profile_refs = meta.get("resolved_profile_refs")
                if not isinstance(profile_refs, list) or any(
                    not isinstance(item, str) or not item.strip() for item in profile_refs
                ):
                    errors.append(f"intervention resolved_profile_refs 非法: {node['path']}")
                process_refs = meta.get("resolved_process_refs")
                if not isinstance(process_refs, list) or any(
                    not isinstance(item, str) or not item.strip() for item in process_refs
                ):
                    errors.append(f"intervention resolved_process_refs 非法: {node['path']}")
                if meta.get("resolved_process_status") not in {
                    "no_process_evidence",
                    "ready_for_verification",
                    "repair_required",
                    "escalation_candidate",
                }:
                    errors.append(f"intervention resolved_process_status 非法: {node['path']}")
                for field in (
                    "resolved_process_feedback_rule",
                    "resolved_process_next_action",
                ):
                    if not isinstance(meta.get(field), str) or not meta[field].strip():
                        errors.append(f"intervention {field} 非法: {node['path']}")
                process_cost = meta.get("resolved_process_cost")
                if not isinstance(process_cost, dict) or set(process_cost) != {
                    "practice_feedback_seconds",
                    "practice_feedback_minutes",
                    "total_attempts",
                    "total_hint_count",
                    "mean_self_reported_effort",
                }:
                    errors.append(f"intervention resolved_process_cost 非法: {node['path']}")
                process_cost_selection = meta.get("resolved_process_cost_selection")
                if (
                    not isinstance(process_cost_selection, dict)
                    or set(process_cost_selection)
                    != {
                        "status",
                        "estimated_minutes",
                        "measured_minutes",
                        "selected_by_cost",
                        "consumer",
                    }
                    or process_cost_selection.get("status")
                    not in {"not_measured", "within_estimate", "over_estimate"}
                    or not isinstance(
                        process_cost_selection.get("estimated_minutes"), (int, float)
                    )
                    or isinstance(
                        process_cost_selection.get("estimated_minutes"), bool
                    )
                    or process_cost_selection.get("estimated_minutes", -1) < 0
                    or not isinstance(
                        process_cost_selection.get("measured_minutes"), (int, float)
                    )
                    or isinstance(process_cost_selection.get("measured_minutes"), bool)
                    or process_cost_selection.get("measured_minutes", -1) < 0
                    or not isinstance(
                        process_cost_selection.get("selected_by_cost"), bool
                    )
                    or process_cost_selection.get("consumer") != "activity_selection"
                ):
                    errors.append(
                        f"intervention resolved_process_cost_selection 非法: {node['path']}"
                    )
                resolved_cost_vector = meta.get("resolved_cost_vector")
                if (
                    not isinstance(resolved_cost_vector, dict)
                    or set(resolved_cost_vector)
                    != {
                        "diagnosis",
                        "prerequisites",
                        "core_learning",
                        "practice_feedback",
                        "verification",
                        "maintenance_relearning",
                    }
                    or _complete_cost_vector({"cost_vector": resolved_cost_vector}) is None
                ):
                    errors.append(f"intervention resolved_cost_vector 非法: {node['path']}")
                if meta.get("resolved_cost_basis") not in {
                    "measured_process_evidence",
                    "route_estimate_no_process_measurement",
                }:
                    errors.append(f"intervention resolved_cost_basis 非法: {node['path']}")
                for field in ("resolved_same_error_count", "resolved_text_variants_tried"):
                    value = meta.get(field)
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        errors.append(f"intervention {field} 非法: {node['path']}")
                latest_teaching_item_id = meta.get(
                    "resolved_latest_teaching_item_id"
                )
                if latest_teaching_item_id is not None and (
                    not isinstance(latest_teaching_item_id, str)
                    or not latest_teaching_item_id.strip()
                ):
                    errors.append(
                        f"intervention resolved_latest_teaching_item_id 非法: {node['path']}"
                    )
                if meta.get("resolved_max_observed_assistance_level") not in (
                    ASSISTANCE_VALUES | {None}
                ):
                    errors.append(
                        f"intervention resolved_max_observed_assistance_level 非法: {node['path']}"
                    )
                if meta.get("resolved_process_support_load") not in {
                    "not_measured",
                    "normal",
                    "high",
                }:
                    errors.append(
                        f"intervention resolved_process_support_load 非法: {node['path']}"
                    )
                if meta.get("resolved_profile_level") not in {
                    "unknown",
                    "tentative",
                    "emerging",
                    "supported",
                }:
                    errors.append(f"intervention resolved_profile_level 非法: {node['path']}")
                for field in (
                    "resolved_activity",
                    "resolved_profile_usage",
                    "resolved_route_binding_id",
                    "resolved_context_key",
                    "resolved_decision_fingerprint",
                ):
                    if not isinstance(meta.get(field), str) or not meta[field].strip():
                        errors.append(f"intervention {field} 非法: {node['path']}")
                try:
                    resolved_instant = parse_iso_instant(meta.get("resolved_at"))
                    if resolved_instant > maximum_observation_time:
                        errors.append(
                            f"intervention resolved_at 不得位于未来: {node['path']}"
                        )
                except (TypeError, ValueError):
                    errors.append(f"intervention resolved_at 非法: {node['path']}")
                    resolved_instant = None
                try:
                    process_refreshed_instant = parse_iso_instant(
                        meta.get("process_refreshed_at")
                    )
                    if process_refreshed_instant > maximum_observation_time:
                        errors.append(
                            f"intervention process_refreshed_at 不得位于未来: {node['path']}"
                        )
                    if (
                        resolved_instant is not None
                        and process_refreshed_instant < resolved_instant
                    ):
                        errors.append(
                            f"intervention process_refreshed_at 不得早于 resolved_at: {node['path']}"
                        )
                except (TypeError, ValueError):
                    errors.append(
                        f"intervention process_refreshed_at 非法: {node['path']}"
                    )
                selected_resource_id = str(meta.get("current_activity_id"))
                selected_resource_meta = node_meta.get(selected_resource_id, {})
                selected_resource_node = index.get("nodes", {}).get(selected_resource_id)
                if not selected_resource_meta and isinstance(selected_resource_node, dict):
                    selected_resource_meta, _, _ = parse_note(
                        vault / selected_resource_node["path"]
                    )
                if meta.get("resolved_activity") not in selected_resource_meta.get(
                    "supported_activities", []
                ):
                    errors.append(f"resolved_activity 不受 current resource 支持: {node['path']}")
                if meta.get("resolved_carrier") != selected_resource_meta.get("carrier"):
                    errors.append(f"resolved_carrier 与 current resource 不一致: {node['path']}")

        if node_type == "focus_snapshot":
            key = (
                str(meta.get("learner_id")),
                str(meta.get("goal_id")),
                str(meta.get("concept_id")),
                str(meta.get("calculated_at")),
            )
            if key in focus_keys:
                errors.append(f"重复 focus snapshot: {focus_keys[key]} 与 {node_id}")
            focus_keys[key] = node_id
            for required in (
                "focus_snapshot_contract",
                "learner_id",
                "goal_id",
                "concept_id",
                "state_id",
                "contract_id",
                "contract_version",
                "route_id",
                "route_version",
                "time_scope",
                "decision_id",
                "calculated_at",
                "focus_model",
                "calculation_purpose",
                "consumer_ids",
                "used_in_decision",
                "selection_basis",
                "score_kind",
                "causal_status",
                "decision_role",
                "audience",
                "user_visibility",
                "export_policy",
                "validity",
            ):
                if required not in meta or meta.get(required) is None:
                    errors.append(f"focus snapshot 缺少 {required}: {node['path']}")
            if meta.get("focus_model") != FOCUS_MODEL_VERSION:
                errors.append(f"focus snapshot focus_model 应为 {FOCUS_MODEL_VERSION}: {node['path']}")
            if meta.get("focus_snapshot_contract") != FOCUS_SNAPSHOT_SCHEMA:
                errors.append(
                    f"focus snapshot contract 应为 {FOCUS_SNAPSHOT_SCHEMA}: {node['path']}"
                )
            if meta.get("validity") not in OBSERVATION_VALIDITY_VALUES:
                errors.append(f"focus snapshot validity 非法: {node['path']}")
            route_version = meta.get("route_version")
            if not isinstance(route_version, int) or isinstance(route_version, bool) or route_version < 1:
                errors.append(f"focus snapshot route_version 非法: {node['path']}")
            if not isinstance(meta.get("route_id"), str) or not str(meta.get("route_id")).strip():
                errors.append(f"focus snapshot route_id 非法: {node['path']}")
            if not re.fullmatch(
                r"route-chain-head:[0-9a-f]{64}", str(meta.get("time_scope"))
            ):
                errors.append(f"focus snapshot time_scope 非法: {node['path']}")
            if not isinstance(meta.get("decision_id"), str) or not str(meta.get("decision_id")).strip():
                errors.append(f"focus snapshot decision_id 非法: {node['path']}")
            calculation_purpose = meta.get("calculation_purpose")
            if calculation_purpose not in FOCUS_PURPOSE_VALUES:
                errors.append(f"focus snapshot calculation_purpose 非法: {node['path']}")
            focus_consumers = meta.get("consumer_ids")
            if (
                not isinstance(focus_consumers, list)
                or not focus_consumers
                or any(
                    item not in {"focus_priority", "inspect_view", "experiment_evaluation"}
                    for item in focus_consumers
                )
                or len(focus_consumers) != len(set(focus_consumers))
            ):
                errors.append(f"focus snapshot consumer_ids 非法或为空: {node['path']}")
            expected_consumer = {
                "residual_candidate_order": "focus_priority",
                "inspect_view": "inspect_view",
                "experiment_evaluation": "experiment_evaluation",
            }.get(str(calculation_purpose))
            if expected_consumer and expected_consumer not in set(focus_consumers or []):
                errors.append(f"focus snapshot purpose 没有对应消费者: {node['path']}")
            if not isinstance(meta.get("used_in_decision"), bool):
                errors.append(f"focus snapshot used_in_decision 必须是布尔值: {node['path']}")
            if meta.get("selection_basis") not in FOCUS_SELECTION_BASIS_VALUES:
                errors.append(f"focus snapshot selection_basis 非法: {node['path']}")
            if calculation_purpose == "inspect_view" and (
                meta.get("used_in_decision") is not False or meta.get("selection_basis") != "not_used"
            ):
                errors.append(f"inspect focus snapshot 不得冒充真实决策: {node['path']}")
            try:
                calculated_instant = parse_iso_instant(meta.get("calculated_at"))
                if calculated_instant > validation_now:
                    errors.append(
                        f"focus snapshot calculated_at 不得位于未来: {node['path']}"
                    )
            except (TypeError, ValueError):
                errors.append(f"focus snapshot calculated_at 必须是带时区的 ISO 时间: {node['path']}")
            if meta.get("privacy") != "private" or meta.get("derived") is not True or meta.get("rebuildable") is not True:
                errors.append(f"focus snapshot 必须 private + derived + rebuildable: {node['path']}")
            if meta.get("authoritative") is not False:
                errors.append(f"focus snapshot 必须声明 authoritative: false: {node['path']}")
            if (
                meta.get("audience") != "agent_internal"
                or meta.get("user_visibility") != "hidden_by_default"
                or meta.get("export_policy") != "explicit_inspect_or_debug"
            ):
                errors.append(f"focus snapshot 必须是默认隐藏的 Agent 内部数据: {node['path']}")
            if (
                meta.get("score_kind") != "heuristic_cone_coordinate"
                or meta.get("causal_status") != "not_established"
                or meta.get("decision_role") != "experimental_priority"
            ):
                errors.append(f"focus snapshot 分数语义必须是非因果、非权威的启发式坐标: {node['path']}")

            component_statuses: dict[str, str] = {}
            for field in ("goal_relevance", "interest_evidence", "readiness"):
                status_field = f"{field}_status"
                status = meta.get(status_field)
                component_statuses[field] = str(status)
                value = meta.get(field)
                if status == "derived":
                    if not is_unit_interval(value):
                        errors.append(f"focus snapshot 的 {field} 在 derived 时必须为 0..1: {node['path']}")
                elif status in {"unknown", "not_applicable"}:
                    if value is not None:
                        errors.append(f"focus snapshot 的 {field} 在 {status} 时必须为 null: {node['path']}")
                else:
                    errors.append(f"focus snapshot 的 {status_field} 非法: {node['path']}")

            input_confidence = meta.get("input_confidence")
            if not isinstance(input_confidence, dict) or set(input_confidence) != {
                "goal_relevance",
                "interest_evidence",
                "readiness",
            } or any(value not in CONFIDENCE_VALUES for value in input_confidence.values()):
                errors.append(f"focus snapshot input_confidence 非法: {node['path']}")
            input_evidence_ids = meta.get("input_evidence_ids")
            if not isinstance(input_evidence_ids, list) or any(not isinstance(item, str) for item in input_evidence_ids):
                errors.append(f"focus snapshot input_evidence_ids 必须是字符串数组: {node['path']}")
            input_source_refs = meta.get("input_source_refs")
            if (
                not isinstance(input_source_refs, list)
                or not input_source_refs
                or any(not isinstance(item, str) or not item for item in input_source_refs)
            ):
                errors.append(f"focus snapshot input_source_refs 必须是非空字符串数组: {node['path']}")

            weights = meta.get("focus_weights")
            if not isinstance(weights, dict) or set(weights) != {"goal", "interest", "readiness"} or not all(
                is_unit_interval(weights.get(item)) for item in ("goal", "interest", "readiness")
            ):
                errors.append(f"focus_weights 非法: {node['path']}")
            else:
                if not math.isclose(sum(float(weights[item]) for item in ("goal", "interest", "readiness")), 1.0, abs_tol=0.0002):
                    errors.append(f"focus_weights 之和必须为 1: {node['path']}")
                ranking_status = meta.get("ranking_status")
                all_derived = all(status == "derived" for status in component_statuses.values())
                if ranking_status == "complete":
                    if not all_derived or not is_unit_interval(meta.get("focus_z")):
                        errors.append(f"focus snapshot complete 排名必须具备全部分量与 0..1 focus_z: {node['path']}")
                    elif meta.get("validity") != "valid":
                        errors.append(
                            f"focus snapshot complete 排名只允许消费 validity=valid: {node['path']}"
                        )
                    else:
                        expected = (
                            float(weights["goal"]) * float(meta["goal_relevance"])
                            + float(weights["interest"]) * float(meta["interest_evidence"])
                            + float(weights["readiness"]) * float(meta["readiness"])
                        )
                        if not math.isclose(float(meta["focus_z"]), expected, abs_tol=0.0002):
                            errors.append(f"focus_z 与分量/权重不一致: {node['path']}")
                elif ranking_status == "incomplete":
                    if all_derived or meta.get("focus_z") is not None:
                        errors.append(f"focus snapshot incomplete 排名必须至少一项未知且 focus_z 为 null: {node['path']}")
                elif ranking_status in {"not_needed", "stale"}:
                    if meta.get("focus_z") is not None:
                        errors.append(f"focus snapshot {ranking_status} 时 focus_z 必须为 null: {node['path']}")
                else:
                    errors.append(f"focus snapshot ranking_status 非法: {node['path']}")

    # Relation endpoints are validated after every node type is known.
    for source_id, node in index.get("nodes", {}).items():
        source_type = node.get("type")
        for relation in node.get("relations", []):
            target_id = relation["target"]
            target_type = index["nodes"].get(target_id, {}).get("type")
            signature = RELATION_SIGNATURES.get(relation["type"])
            if signature and (source_type not in signature[0] or target_type not in signature[1]):
                errors.append(
                    f"关系端点类型非法: {source_id}({source_type}) -{relation['type']}-> {target_id}({target_type})"
                )

    expected_active_types = {
        "active_learner_id": "learner",
        "active_domain_id": "domain",
        "active_goal_id": "goal",
        "last_session_id": "session",
    }
    for key, expected_type in expected_active_types.items():
        value = manifest.get(key)
        if value and value not in index.get("nodes", {}):
            errors.append(f"manifest {key} 指向不存在的 id: {value}")
        elif value and index["nodes"][value]["type"] != expected_type:
            errors.append(f"manifest {key} 应指向 {expected_type}: {value}")

    router_meta = node_meta.get("sys-router")
    if not router_meta:
        errors.append("缺少 sys-router 笔记")
    else:
        for key in expected_active_types:
            if router_meta.get(key) != manifest.get(key):
                errors.append(f"ROUTER 与 manifest 的 {key} 不一致")

    # Boundary is a deterministic graph projection of the current mastery
    # bands.  This exact check prevents a diagnostic update from being stored
    # while the route-facing boundary cache remains stale.
    requirements: dict[str, set[str]] = {}
    concept_relation_map: dict[str, list[dict[str, str]]] = {}
    for concept_id, node in index.get("nodes", {}).items():
        if node.get("type") == "concept":
            concept_relation_map[concept_id] = list(node.get("relations", []))
            requirements[concept_id] = {
                relation["target"] for relation in node["relations"] if relation["type"] == "requires"
            }
    state_groups: dict[tuple[str, str], dict[str, str]] = {}
    for (learner_id, goal_id, concept_id), state_id in state_keys.items():
        state_groups.setdefault((learner_id, goal_id), {})[concept_id] = str(
            node_meta[state_id].get("mastery")
        )
    for (learner_id, goal_id), mastery_by_concept in state_groups.items():
        expected_boundaries = derive_boundary_positions(
            concept_relation_map, mastery_by_concept
        )
        for concept_id, expected_boundary in expected_boundaries.items():
            state_id = state_keys[(learner_id, goal_id, concept_id)]
            stored_boundary = node_meta[state_id].get("boundary_position")
            if stored_boundary != expected_boundary:
                errors.append(
                    f"state boundary_position 不是图谱与 mastery 推导值: {state_id} "
                    f"stored={stored_boundary} derived={expected_boundary}"
                )

    learner_node_by_id = {
        str(meta.get("learner_id")): node_id
        for node_id, meta in node_meta.items()
        if meta.get("type") == "learner" and meta.get("learner_id")
    }
    target_subgraphs = {
        goal_id: target_subgraph_for_goal(index, goal_id, requirements)
        for goal_id, meta in node_meta.items()
        if meta.get("type") == "goal"
    }

    schedule_receipts = {
        node_id: meta
        for node_id, meta in node_meta.items()
        if meta.get("type") == "retention_schedule"
    }
    open_receipts = {
        node_id: meta
        for node_id, meta in node_meta.items()
        if meta.get("type") == "verification_open"
    }
    issuance_by_binding_id = {
        str(event.get("binding_id")): event for event in route_issuance_events
    }
    schedules_by_scope: dict[tuple[str, str, str, str, int], list[str]] = {}
    schedule_binding_owners: dict[str, str] = {}
    for schedule_id, schedule in schedule_receipts.items():
        scope_key = (
            str(schedule.get("learner_id")),
            str(schedule.get("goal_id")),
            str(schedule.get("concept_id")),
            str(schedule.get("contract_id")),
            schedule.get("contract_version")
            if isinstance(schedule.get("contract_version"), int)
            and not isinstance(schedule.get("contract_version"), bool)
            else -1,
        )
        schedules_by_scope.setdefault(scope_key, []).append(schedule_id)
        state_id = state_keys.get(scope_key[:3])
        state = node_meta.get(str(state_id), {})
        if (
            state.get("type") != "state"
            or state.get("contract_id") != schedule.get("contract_id")
            or state.get("contract_version") != schedule.get("contract_version")
        ):
            errors.append(f"retention_schedule 无唯一同 scope state: {schedule_id}")
        baseline_id = str(schedule.get("baseline_evidence_id"))
        baseline = node_meta.get(baseline_id, {})
        supported_ids = {
            relation["target"]
            for relation in index.get("nodes", {}).get(str(state_id), {}).get(
                "relations", []
            )
            if relation.get("type") == "supported_by"
        }
        if (
            not _qualified_verification_baseline(
                baseline, state, allow_synthetic_demo=allow_synthetic_demo
            )
            or baseline_id not in supported_ids
        ):
            errors.append(
                f"retention_schedule baseline 不是 state 支持的合格 verification: {schedule_id}"
            )
        binding_id = str(schedule.get("route_binding_id"))
        issuance = issuance_by_binding_id.get(binding_id)
        if issuance is None:
            errors.append(f"retention_schedule 无唯一 route issuance: {schedule_id}")
        else:
            if (
                issuance.get("route_purpose") != "retention"
                or issuance.get("baseline_evidence_id") != baseline_id
                or issuance.get("verification_task_id")
                != schedule.get("retention_task_id")
                or issuance.get("route_id") != schedule.get("route_id")
                or issuance.get("route_version") != schedule.get("route_version")
                or issuance.get("context_key") != schedule.get("context_key")
                or issuance.get("verification_task_fingerprint")
                != schedule.get("verification_task_fingerprint")
                or any(
                    issuance.get(field) != schedule.get(field)
                    for field in RETENTION_SCOPE_FIELDS
                )
            ):
                errors.append(
                    f"retention_schedule 与 retention issuance 不一致: {schedule_id}"
                )
            try:
                if parse_iso_instant(issuance.get("issued_at")) > parse_iso_instant(
                    schedule.get("scheduled_at")
                ):
                    errors.append(
                        f"retention_schedule 早于 route issuance: {schedule_id}"
                    )
            except (TypeError, ValueError):
                pass
        prior_owner = schedule_binding_owners.get(binding_id)
        if prior_owner is not None and prior_owner != schedule_id:
            errors.append(
                f"retention route binding 被多个 schedule 消费: {prior_owner}/{schedule_id}"
            )
        schedule_binding_owners[binding_id] = schedule_id
        contract = goal_contracts.get(str(schedule.get("goal_id")), {}).get(
            (
                str(schedule.get("contract_id")),
                schedule.get("contract_version")
                if isinstance(schedule.get("contract_version"), int)
                else -1,
            )
        )
        try:
            minimum_days = contract.get("requirements", {}).get(
                "delayed_retention", {}
            ).get("min_delay_days") if isinstance(contract, dict) else None
            if (
                not isinstance(minimum_days, int)
                or isinstance(minimum_days, bool)
                or minimum_days < 1
            ):
                raise ValueError("invalid min_delay_days")
            earliest = parse_iso_instant(baseline.get("observed_at")) + timedelta(
                days=minimum_days
            )
            if schedule.get("not_before") is not None:
                earliest = max(earliest, parse_iso_instant(schedule.get("not_before")))
            if parse_iso_instant(schedule.get("scheduled_for")) != earliest:
                errors.append(
                    f"retention_schedule scheduled_for 不是 baseline/delay/not_before 规范派生值: {schedule_id}"
                )
        except (TypeError, ValueError):
            errors.append(f"retention_schedule 无法验证最小延迟: {schedule_id}")
        if schedule.get("retention_task_id") == baseline.get("verification_item_id"):
            errors.append(f"retention_schedule task 与 baseline item 相同: {schedule_id}")
        relations = index.get("nodes", {}).get(schedule_id, {}).get("relations", [])
        expected_relations = {
            "for_learner": learner_node_by_id.get(str(schedule.get("learner_id"))),
            "for_goal": str(schedule.get("goal_id")),
            "about": str(schedule.get("concept_id")),
            "derived_from": baseline_id,
        }
        for relation_type, expected_target in expected_relations.items():
            targets = [
                relation["target"]
                for relation in relations
                if relation.get("type") == relation_type
            ]
            if targets != [expected_target]:
                errors.append(
                    f"retention_schedule {relation_type} 关系不一致: {schedule_id}"
                )
        learner_node_id = learner_node_by_id.get(str(schedule.get("learner_id")))
        if learner_node_id is None or node_body.get(schedule_id) != _stored_note_body(
            _canonical_retention_schedule_body(schedule, str(learner_node_id))
        ):
            errors.append(
                f"retention_schedule 正文必须精确等于 canonical receipt body: {schedule_id}"
            )

    for scope_key, schedule_ids in schedules_by_scope.items():
        def schedule_order_key(item: str) -> tuple[datetime, str]:
            try:
                instant = parse_iso_instant(
                    schedule_receipts[item].get("scheduled_at")
                )
            except (TypeError, ValueError):
                instant = datetime.min.replace(tzinfo=timezone.utc)
            return instant, item

        ordered = sorted(
            schedule_ids,
            key=schedule_order_key,
        )
        for position, schedule_id in enumerate(ordered):
            schedule = schedule_receipts[schedule_id]
            expected_previous = ordered[position - 1] if position else None
            if schedule.get("supersedes_schedule_id") != expected_previous:
                errors.append(
                    f"retention_schedule supersedes 链不连续: {schedule_id}"
                )
            supersedes_targets = [
                relation["target"]
                for relation in index.get("nodes", {}).get(schedule_id, {}).get(
                    "relations", []
                )
                if relation.get("type") == "supersedes"
            ]
            if supersedes_targets != ([expected_previous] if expected_previous else []):
                errors.append(
                    f"retention_schedule supersedes 关系不一致: {schedule_id}"
                )
            if expected_previous:
                previous = schedule_receipts[expected_previous]
                try:
                    latest_adverse = _latest_adverse_retention_instant(
                        (node_id, meta)
                        for node_id, meta in node_meta.items()
                        if meta.get("type") == "evidence"
                        and all(
                            meta.get(field) == schedule.get(field)
                            for field in RETENTION_SCOPE_FIELDS
                        )
                    )
                    if latest_adverse is None or parse_iso_instant(
                        node_meta[str(schedule.get("baseline_evidence_id"))].get(
                            "observed_at"
                        )
                    ) <= latest_adverse:
                        errors.append(
                            f"retention reschedule 缺少晚于失败的新 verification baseline: {schedule_id}"
                        )
                except (TypeError, ValueError, KeyError):
                    errors.append(
                        f"retention reschedule baseline 时间链非法: {schedule_id}"
                    )
                if (
                    schedule.get("route_binding_id") == previous.get("route_binding_id")
                    or schedule.get("retention_task_id")
                    == previous.get("retention_task_id")
                    or schedule.get("verification_task_fingerprint")
                    == previous.get("verification_task_fingerprint")
                ):
                    errors.append(
                        f"retention reschedule 必须使用新 binding/task/fingerprint: {schedule_id}"
                    )

    open_by_schedule: dict[str, str] = {}
    for open_id, opened in open_receipts.items():
        schedule_id = str(opened.get("retention_schedule_id"))
        schedule = schedule_receipts.get(schedule_id)
        if schedule is None:
            errors.append(f"verification_open schedule 不存在: {open_id}/{schedule_id}")
            continue
        if schedule_id in open_by_schedule:
            errors.append(
                f"同一 retention schedule 存在多个 verification_open: {schedule_id}"
            )
        else:
            open_by_schedule[schedule_id] = open_id
        copied_fields = (
            *RETENTION_SCOPE_FIELDS,
            "baseline_evidence_id",
            "retention_task_id",
            "route_binding_id",
            "route_id",
            "route_version",
            "context_key",
            "verification_task_fingerprint",
            "scheduled_for",
        )
        if (
            any(opened.get(field) != schedule.get(field) for field in copied_fields)
            or opened.get("schedule_fingerprint")
            != schedule.get("receipt_fingerprint")
        ):
            errors.append(f"verification_open 未精确复制 schedule binding: {open_id}")
        issuance = issuance_by_binding_id.get(str(schedule.get("route_binding_id")), {})
        matching_resources = [
            resource
            for resource in issuance.get("issuance_snapshot", {}).get(
                "resources", []
            )
            if isinstance(resource, dict)
            and resource.get("id") == opened.get("resource_id")
            and isinstance(resource.get("verification_task"), dict)
            and resource["verification_task"].get("id")
            == opened.get("retention_task_id")
            and resource.get("carrier") == opened.get("carrier")
            and opened.get("activity")
            in resource.get("supported_activities", [])
        ]
        if len(matching_resources) != 1:
            errors.append(
                f"verification_open resource/activity/carrier 未由 issuance 唯一签发: {open_id}"
            )
        try:
            opened_instant = parse_iso_instant(opened.get("opened_at"))
            if opened_instant < parse_iso_instant(schedule.get("scheduled_for")):
                errors.append(f"verification_open 早于 scheduled_for: {open_id}")
            if opened_instant < parse_iso_instant(schedule.get("scheduled_at")):
                errors.append(f"verification_open 早于 schedule.scheduled_at: {open_id}")
        except (TypeError, ValueError):
            pass
        relations = index.get("nodes", {}).get(open_id, {}).get("relations", [])
        expected_relations = {
            "for_learner": learner_node_by_id.get(str(opened.get("learner_id"))),
            "for_goal": str(opened.get("goal_id")),
            "about": str(opened.get("concept_id")),
            "scheduled_by": schedule_id,
            "uses": str(opened.get("resource_id")),
        }
        for relation_type, expected_target in expected_relations.items():
            targets = [
                relation["target"]
                for relation in relations
                if relation.get("type") == relation_type
            ]
            if targets != [expected_target]:
                errors.append(
                    f"verification_open {relation_type} 关系不一致: {open_id}"
                )
        learner_node_id = learner_node_by_id.get(str(opened.get("learner_id")))
        if learner_node_id is None or node_body.get(open_id) != _stored_note_body(
            _canonical_verification_open_body(opened, str(learner_node_id))
        ):
            errors.append(
                f"verification_open 正文必须精确等于 canonical receipt body: {open_id}"
            )

    # A state is scoped to one learner, goal, concept, and embedded contract.
    for state_id in state_keys.values():
        meta = node_meta[state_id]
        goal_id = str(meta.get("goal_id"))
        contract_id = str(meta.get("contract_id"))
        relations = index["nodes"][state_id]["relations"]
        for_goal_targets = [item["target"] for item in relations if item["type"] == "for_goal"]
        for_learner_targets = [item["target"] for item in relations if item["type"] == "for_learner"]
        expected_learner_node = learner_node_by_id.get(str(meta.get("learner_id")))
        if for_goal_targets != [goal_id]:
            errors.append(f"state goal_id 与 for_goal 不一致: {state_id}")
        if not expected_learner_node or for_learner_targets != [expected_learner_node]:
            errors.append(f"state learner_id 与 for_learner 不一致: {state_id}")
        contract_version = meta.get("contract_version")
        contract_key = (contract_id, contract_version) if isinstance(contract_version, int) else (contract_id, -1)
        contract = goal_contracts.get(goal_id, {}).get(contract_key)
        if not contract:
            errors.append(f"state contract_id/version 未在 goal 定义: {state_id}/{contract_id}/v{contract_version}")
        elif contract.get("concept_id") != meta.get("concept_id"):
            errors.append(f"state contract 与 concept_id 不一致: {state_id}/{contract_id}")

        current_schedule_id = meta.get("current_retention_schedule_id")
        if current_schedule_id is not None:
            schedule = schedule_receipts.get(str(current_schedule_id))
            if schedule is None:
                errors.append(
                    f"state current_retention_schedule_id 不存在: {state_id}/{current_schedule_id}"
                )
            elif any(
                schedule.get(field) != meta.get(field)
                for field in RETENTION_SCOPE_FIELDS
            ):
                errors.append(
                    f"state current retention schedule scope 不一致: {state_id}"
                )
            else:
                scope_key = (
                    str(meta.get("learner_id")),
                    str(meta.get("goal_id")),
                    str(meta.get("concept_id")),
                    str(meta.get("contract_id")),
                    meta.get("contract_version")
                    if isinstance(meta.get("contract_version"), int)
                    else -1,
                )
                scoped_schedule_ids = schedules_by_scope.get(scope_key, [])
                if scoped_schedule_ids:
                    latest_schedule_id = max(
                        scoped_schedule_ids,
                        key=schedule_order_key,
                    )
                    if current_schedule_id != latest_schedule_id:
                        errors.append(
                            f"state 必须指向同 scope 最新 schedule receipt: {state_id}"
                        )

    valid_focus_chain_heads = {
        str(route_chain_anchor(manifest)),
        *(
            str(event.get("event_hash"))
            for event in route_issuance_events
            if isinstance(event.get("event_hash"), str)
        ),
    }
    for node_id, meta in node_meta.items():
        if meta.get("type") != "focus_snapshot":
            continue
        learner_id = str(meta.get("learner_id"))
        goal_id = str(meta.get("goal_id"))
        concept_id = str(meta.get("concept_id"))
        relations = index["nodes"][node_id]["relations"]
        expected_learner_node = learner_node_by_id.get(learner_id)
        if [item["target"] for item in relations if item["type"] == "for_learner"] != [expected_learner_node]:
            errors.append(f"focus snapshot learner_id 与 for_learner 不一致: {node_id}")
        if [item["target"] for item in relations if item["type"] == "for_goal"] != [goal_id]:
            errors.append(f"focus snapshot goal_id 与 for_goal 不一致: {node_id}")
        if [item["target"] for item in relations if item["type"] == "about"] != [concept_id]:
            errors.append(f"focus snapshot concept_id 与 about 不一致: {node_id}")
        goal_meta = node_meta.get(goal_id, {})
        if goal_meta.get("type") != "goal" or str(goal_meta.get("learner_id")) != learner_id:
            errors.append(f"focus snapshot 的 learner/goal 范围不一致: {node_id}")
        matching_route_events = [
            event
            for event in route_issuance_events
            if event.get("learner_id") == learner_id
            and event.get("goal_id") == goal_id
            and event.get("route_id") == meta.get("route_id")
            and event.get("route_version") == meta.get("route_version")
        ]
        if not matching_route_events:
            errors.append(f"focus snapshot route_id/version 无历史发行依据: {node_id}")
        time_scope = str(meta.get("time_scope"))
        if (
            not time_scope.startswith("route-chain-head:")
            or time_scope.removeprefix("route-chain-head:")
            not in valid_focus_chain_heads
        ):
            errors.append(f"focus snapshot time_scope 不在 route chain 历史中: {node_id}")
        state_id = str(meta.get("state_id"))
        state_meta = node_meta.get(state_id, {})
        if state_meta.get("type") != "state":
            errors.append(f"focus snapshot state_id 不存在或不是 state: {node_id}/{state_id}")
        else:
            exact_scope = (
                str(state_meta.get("learner_id")) == learner_id
                and str(state_meta.get("goal_id")) == goal_id
                and str(state_meta.get("concept_id")) == concept_id
                and str(state_meta.get("contract_id")) == str(meta.get("contract_id"))
                and state_meta.get("contract_version") == meta.get("contract_version")
            )
            if not exact_scope:
                errors.append(f"focus snapshot 与 state/contract 作用域不一致: {node_id}/{state_id}")
        for evidence_id in meta.get("input_evidence_ids", []):
            evidence_meta = node_meta.get(str(evidence_id), {})
            if evidence_meta.get("type") != "evidence":
                errors.append(f"focus snapshot 输入 evidence 不存在或类型错误: {node_id}/{evidence_id}")
            elif (
                str(evidence_meta.get("learner_id")) != learner_id
                or str(evidence_meta.get("goal_id")) != goal_id
            ):
                errors.append(f"focus snapshot 输入 evidence 跨 learner/goal: {node_id}/{evidence_id}")

    residual_batch_decisions: dict[tuple[Any, ...], set[str]] = {}
    residual_batch_bases: dict[tuple[Any, ...], dict[str, set[str]]] = {}
    for meta in node_meta.values():
        if (
            meta.get("type") != "focus_snapshot"
            or meta.get("calculation_purpose") != "residual_candidate_order"
            or meta.get("used_in_decision") is not True
        ):
            continue
        batch_key = (
            meta.get("learner_id"),
            meta.get("goal_id"),
            meta.get("route_id"),
            meta.get("route_version"),
            meta.get("time_scope"),
            meta.get("calculation_purpose"),
            meta.get("used_in_decision"),
        )
        decision_id = str(meta.get("decision_id"))
        residual_batch_decisions.setdefault(batch_key, set()).add(decision_id)
        residual_batch_bases.setdefault(batch_key, {}).setdefault(
            decision_id, set()
        ).add(str(meta.get("selection_basis")))
    for batch_key, decision_ids in residual_batch_decisions.items():
        if len(decision_ids) > 1:
            errors.append(
                "同一 current residual Focus batch 不得混用多个 decision_id: "
                f"batch={batch_key}, decisions={sorted(decision_ids)}"
            )
        bases_by_decision = residual_batch_bases.get(batch_key, {})
        allowed_bases = {"focus", "stable_tie_break", "route_default"}
        invalid_bases = sorted(
            {
                basis
                for bases in bases_by_decision.values()
                for basis in bases
                if basis not in allowed_bases
            }
        )
        if invalid_bases:
            errors.append(
                "current residual Focus batch 的 selection_basis 只能是 "
                "focus/stable_tie_break/route_default: "
                f"batch={batch_key}, invalid={invalid_bases}"
            )
        for decision_id, selection_bases in sorted(bases_by_decision.items()):
            if len(selection_bases) != 1:
                errors.append(
                    "同一 current residual Focus decision batch 的 "
                    "selection_basis 必须唯一一致: "
                    f"batch={batch_key}, decision_id={decision_id}, "
                    f"selection_bases={sorted(selection_bases)}"
                )

    teaching_deliveries: dict[str, dict[str, Any]] = {}
    for delivery_id, delivery in node_meta.items():
        if delivery.get("type") != "teaching_delivery":
            continue
        teaching_deliveries[delivery_id] = delivery
        delivery_key = (
            str(delivery.get("learner_id")),
            str(delivery.get("goal_id")),
            str(delivery.get("concept_id")),
            str(delivery.get("contract_id")),
            delivery.get("contract_version")
            if isinstance(delivery.get("contract_version"), int)
            else -1,
            str(delivery.get("route_id")),
            delivery.get("route_version")
            if isinstance(delivery.get("route_version"), int)
            else -1,
        )
        issued_binding = route_binding_registry.get(delivery_key)
        if issued_binding is None:
            errors.append(
                f"teaching_delivery 无有效 route issuance: {delivery_id}"
            )
            continue
        if (
            delivery.get("route_binding_id") != issued_binding.get("binding_id")
            or delivery.get("context_key") != issued_binding.get("context_key")
        ):
            errors.append(
                f"teaching_delivery route binding/context 不一致: {delivery_id}"
            )
        resource_id = str(delivery.get("resource_id"))
        issued_resources = {
            str(item.get("id")): item
            for item in issued_binding.get("issuance_snapshot", {}).get("resources", [])
            if isinstance(item, dict)
        }
        issued_resource = issued_resources.get(resource_id)
        resource_meta = node_meta.get(resource_id, {})
        if issued_resource is None or resource_meta.get("type") != "resource":
            errors.append(
                f"teaching_delivery resource 未被该 route 签发或不存在: {delivery_id}/{resource_id}"
            )
        else:
            if (
                delivery.get("carrier") != issued_resource.get("carrier")
                or delivery.get("carrier") != resource_meta.get("carrier")
                or delivery.get("activity")
                not in issued_resource.get("supported_activities", [])
                or delivery.get("activity")
                not in resource_meta.get("supported_activities", [])
            ):
                errors.append(
                    f"teaching_delivery activity/carrier 未由已签发 resource 支持: {delivery_id}"
                )
            verification_task = issued_resource.get("verification_task")
            if not isinstance(verification_task, dict):
                errors.append(
                    f"teaching_delivery 已签发 resource 缺少验证任务: {delivery_id}"
                )
            elif isinstance(delivery.get("delivery_plan"), dict):
                try:
                    policy = load_text_learning_policy()
                    guard = policy.build_verification_content_guard(
                        str(verification_task.get("id")),
                        str(verification_task.get("prompt")),
                        verification_task.get("protected_answers"),
                    )
                    policy._assert_no_reserved_verification_overlap(
                        delivery["delivery_plan"], guard
                    )
                except Exception as exc:
                    if exc.__class__.__name__ == "TextPolicyError":
                        errors.append(
                            "teaching_delivery 含保留的未见验证题或答案内容: "
                            f"{delivery_id} ({exc})"
                        )
                    else:
                        raise
        relations = index.get("nodes", {}).get(delivery_id, {}).get("relations", [])
        expected_learner_node = learner_node_by_id.get(str(delivery.get("learner_id")))
        relation_expectations = {
            "for_learner": expected_learner_node,
            "for_goal": str(delivery.get("goal_id")),
            "about": str(delivery.get("concept_id")),
            "uses": resource_id,
        }
        for relation_type, expected_target in relation_expectations.items():
            targets = [
                item["target"] for item in relations if item.get("type") == relation_type
            ]
            if targets != [expected_target]:
                errors.append(
                    f"teaching_delivery {relation_type} 关系不一致: {delivery_id}"
                )
        try:
            if parse_iso_instant(delivery.get("issued_at")) < parse_iso_instant(
                issued_binding.get("issued_at")
            ):
                errors.append(
                    f"teaching_delivery 早于 route issuance: {delivery_id}"
                )
        except (TypeError, ValueError):
            pass

    independently_bound_evidence_ids: set[str] = set()
    for node_id, meta in node_meta.items():
        if meta.get("type") != "evidence":
            continue
        learner_id = str(meta.get("learner_id"))
        goal_id = str(meta.get("goal_id"))
        contract_id = str(meta.get("contract_id"))
        contract_version = meta.get("contract_version")
        contract_key = (contract_id, contract_version) if isinstance(contract_version, int) else (contract_id, -1)
        goal_meta = node_meta.get(goal_id, {})
        contract = goal_contracts.get(goal_id, {}).get(contract_key)
        if goal_meta.get("type") != "goal" or str(goal_meta.get("learner_id")) != learner_id:
            errors.append(f"evidence 的 learner/goal 范围不一致: {node_id}")
        if not contract:
            errors.append(f"evidence contract_id/version 未在 goal 定义: {node_id}/{contract_id}/v{contract_version}")
        elif contract.get("concept_id") != meta.get("concept_id"):
            errors.append(f"evidence contract 与 concept_id 不一致: {node_id}/{contract_id}")
        route_version = meta.get("route_version_at_observation")
        binding_key = (
            learner_id,
            goal_id,
            str(meta.get("concept_id")),
            contract_id,
            contract_version if isinstance(contract_version, int) else -1,
            str(meta.get("route_id_at_observation")),
            route_version if isinstance(route_version, int) else -1,
        )
        issued_binding = route_binding_registry.get(binding_key)
        binding_valid = issued_binding is not None
        if issued_binding is None:
            errors.append(
                f"evidence route/context 无有效签发事件: {node_id} "
                f"route={meta.get('route_id_at_observation')}@{route_version}"
            )
        else:
            if meta.get("route_binding_id") != issued_binding.get("binding_id"):
                binding_valid = False
                errors.append(f"evidence route_binding_id 与签发事件不一致: {node_id}")
            if meta.get("context_key") != issued_binding.get("context_key"):
                binding_valid = False
                errors.append(f"evidence context_key 不是已验证 route issuance 的派生值: {node_id}")
            try:
                if parse_iso_instant(issued_binding.get("issued_at")) > parse_iso_instant(
                    meta.get("observed_at")
                ):
                    binding_valid = False
                    errors.append(f"evidence observed_at 早于 route issuance issued_at: {node_id}")
            except (TypeError, ValueError):
                binding_valid = False
            phase = meta.get("phase")
            expected_route_purpose = (
                "retention" if phase == "retention" else "learning"
            )
            legacy_seed_binding = bool(
                allow_synthetic_demo
                and _is_legacy_trusted_seed_route_event(
                    issued_binding, manifest
                )
            )
            if (
                issued_binding.get("route_purpose") != expected_route_purpose
                and not legacy_seed_binding
            ):
                binding_valid = False
                errors.append(
                    "evidence phase 与 route_purpose 不一致: "
                    f"{node_id} phase={phase} purpose={issued_binding.get('route_purpose')}"
                )
            if phase in {
                "teaching_process",
                "verification",
                "retention",
            }:
                issued_task = issued_binding.get("verification_task_id")
                if issued_task != meta.get("verification_task_id") or issued_task != meta.get(
                    "bound_verification_task_id"
                ):
                    binding_valid = False
                    errors.append(
                        f"evidence task 与 route issuance 不一致: {node_id} "
                        f"issued={issued_task} evidence={meta.get('verification_task_id')}"
                    )
            if phase in {"verification", "retention"}:
                issued_task = issued_binding.get("verification_task_id")
                if meta.get("verification_item_id") != issued_task:
                    binding_valid = False
                    errors.append(
                        f"verification/retention item 必须等于已签发 task: {node_id} "
                        f"issued={issued_task} item={meta.get('verification_item_id')}"
                    )
            elif phase == "diagnostic":
                matching_probes = [
                    item
                    for item in issued_binding.get("issuance_snapshot", {}).get(
                        "resources", []
                    )
                    if isinstance(item, dict)
                    and isinstance(item.get("diagnostic_probe"), dict)
                    and item["diagnostic_probe"].get("id")
                    == meta.get("teaching_item_id")
                    and item.get("carrier") == meta.get("carrier")
                    and meta.get("activity") in item.get("supported_activities", [])
                ]
                if len(matching_probes) != 1:
                    binding_valid = False
                    errors.append(
                        "diagnostic teaching_item_id 必须唯一绑定已签发 resource 的 probe: "
                        f"{node_id} matches={len(matching_probes)}"
                    )
            elif phase == "teaching_process":
                delivery = teaching_deliveries.get(str(meta.get("teaching_item_id")))
                if delivery is None:
                    binding_valid = False
                    errors.append(
                        f"teaching_process 引用了未发行的教学项: {node_id}"
                    )
                else:
                    delivery_matches = bool(
                        delivery.get("learner_id") == meta.get("learner_id")
                        and delivery.get("goal_id") == meta.get("goal_id")
                        and delivery.get("concept_id") == meta.get("concept_id")
                        and delivery.get("contract_id") == meta.get("contract_id")
                        and delivery.get("contract_version")
                        == meta.get("contract_version")
                        and delivery.get("route_id")
                        == meta.get("route_id_at_observation")
                        and delivery.get("route_version")
                        == meta.get("route_version_at_observation")
                        and delivery.get("route_binding_id")
                        == meta.get("route_binding_id")
                        and delivery.get("context_key") == meta.get("context_key")
                        and delivery.get("decision_fingerprint")
                        == meta.get("decision_fingerprint_at_observation")
                        and delivery.get("activity") == meta.get("activity")
                        and delivery.get("carrier") == meta.get("carrier")
                        and delivery.get("delivery_plan_fingerprint")
                        == meta.get(
                            "teaching_delivery_fingerprint_at_observation"
                        )
                    )
                    try:
                        issued_before_response = parse_iso_instant(
                            delivery.get("issued_at")
                        ) < parse_iso_instant(meta.get("observed_at"))
                    except (TypeError, ValueError):
                        issued_before_response = False
                    if not delivery_matches or not issued_before_response:
                        binding_valid = False
                        errors.append(
                            "teaching_process 未精确绑定先发行的教学项/内容/decision epoch: "
                            f"{node_id}"
                        )
        if binding_valid and meta.get("phase") in {"verification", "retention"}:
            independently_bound_evidence_ids.add(node_id)
        if meta.get("phase") == "retention":
            baseline_id = str(meta.get("baseline_evidence_id"))
            baseline = node_meta.get(baseline_id, {})
            if baseline.get("type") != "evidence":
                errors.append(f"retention baseline_evidence_id 不存在: {node_id}/{baseline_id}")
            else:
                baseline_eligible, _baseline_failures = evidence_mastery_eligibility(
                    baseline, allow_synthetic_demo=allow_synthetic_demo
                )
                if baseline.get("phase") != "verification" or not baseline_eligible:
                    errors.append(f"retention baseline 必须是合格 verification: {node_id}/{baseline_id}")
                if baseline.get("verification_item_id") == meta.get("verification_item_id"):
                    errors.append(f"retention 必须使用不同于 baseline 的未见 item: {node_id}/{baseline_id}")
            if issued_binding is not None and issued_binding.get(
                "route_purpose"
            ) == "retention":
                open_id = str(meta.get("teaching_item_id"))
                opened = open_receipts.get(open_id)
                if opened is None:
                    errors.append(
                        f"本地 retention evidence 必须引用 verification_open receipt: {node_id}"
                    )
                else:
                    schedule = schedule_receipts.get(
                        str(opened.get("retention_schedule_id")), {}
                    )
                    copied_fields = (
                        *RETENTION_SCOPE_FIELDS,
                        "baseline_evidence_id",
                        "retention_task_id",
                        "scheduled_for",
                    )
                    if (
                        any(opened.get(field) != meta.get(field) for field in copied_fields)
                        or opened.get("route_binding_id")
                        != meta.get("route_binding_id")
                        or opened.get("route_id")
                        != meta.get("route_id_at_observation")
                        or opened.get("route_version")
                        != meta.get("route_version_at_observation")
                        or opened.get("context_key") != meta.get("context_key")
                        or opened.get("activity") != meta.get("activity")
                        or opened.get("carrier") != meta.get("carrier")
                        or opened.get("retention_task_id")
                        != meta.get("verification_item_id")
                        or schedule.get("id")
                        != opened.get("retention_schedule_id")
                    ):
                        errors.append(
                            f"retention evidence 未精确绑定 open→schedule receipt: {node_id}"
                        )
                    try:
                        if parse_iso_instant(opened.get("opened_at")) >= parse_iso_instant(
                            meta.get("observed_at")
                        ):
                            errors.append(
                                f"retention evidence observed_at 必须晚于 open receipt: {node_id}"
                            )
                    except (TypeError, ValueError):
                        errors.append(
                            f"retention evidence/open 时间链非法: {node_id}"
                        )
            derived_delay = derived_retention_delay_days(meta, node_meta)
            if derived_delay is None:
                errors.append(f"retention_delay_days 无法由同范围 baseline 时间推导: {node_id}")
            elif meta.get("retention_delay_days") != derived_delay:
                errors.append(
                    f"retention_delay_days 不是时间链推导值: {node_id} "
                    f"stored={meta.get('retention_delay_days')} derived={derived_delay}"
                )

    # Validate route scope, path order, checkpoint eligibility, and evidence ownership.
    route_identity: dict[tuple[str, str, str, int], str] = {}
    route_task_by_identity: dict[tuple[str, str, str, int], str] = {}
    active_routes_by_scope: dict[tuple[str, str], list[str]] = {}
    for node_id, meta in node_meta.items():
        if meta.get("type") != "intervention":
            continue
        learner_id = str(meta.get("learner_id"))
        goal_id = str(meta.get("goal_id"))
        relations = index["nodes"][node_id]["relations"]
        implements_targets = [item["target"] for item in relations if item["type"] == "implements"]
        learner_targets = [item["target"] for item in relations if item["type"] == "for_learner"]
        expected_learner_node = learner_node_by_id.get(learner_id)
        if implements_targets != [goal_id]:
            errors.append(f"intervention goal_id 与 implements 不一致: {node_id}")
        if not expected_learner_node or learner_targets != [expected_learner_node]:
            errors.append(f"intervention learner_id 与 for_learner 不一致: {node_id}")
        goal_meta = node_meta.get(goal_id, {})
        if goal_meta.get("type") != "goal" or str(goal_meta.get("learner_id")) != learner_id:
            errors.append(f"intervention 的 goal/learner 范围不一致: {node_id}")

        path = meta.get("path")
        if not isinstance(path, list) or not path or not all(isinstance(item, str) for item in path):
            errors.append(f"intervention path 必须是非空 concept id 数组: {node_id}")
            path = []
        if len(path) != len(set(path)):
            errors.append(f"intervention path 含重复 concept: {node_id}")
        subgraph = target_subgraphs.get(goal_id, set())
        if any(index.get("nodes", {}).get(item, {}).get("type") != "concept" for item in path):
            errors.append(f"intervention path 含非 concept 或不存在节点: {node_id}")
        if any(item not in subgraph for item in path):
            errors.append(f"intervention path 超出 goal 的目标/先修子图: {node_id}")

        states_for_learner = {
            concept_id: node_meta[state_id]
            for (state_learner_id, state_goal_id, concept_id), state_id in state_keys.items()
            if state_learner_id == learner_id and state_goal_id == goal_id
        }
        seen_path: set[str] = set()
        for concept_id in path:
            unmet = [
                prerequisite
                for prerequisite in requirements.get(concept_id, set())
                if states_for_learner.get(prerequisite, {}).get("mastery") != "mastered"
                and prerequisite not in seen_path
            ]
            if unmet:
                errors.append(f"intervention path 前置顺序断裂: {node_id}/{concept_id} <- {','.join(sorted(unmet))}")
            seen_path.add(concept_id)

        checkpoint = meta.get("current_checkpoint")
        if meta.get("status") == "active":
            if checkpoint not in path:
                errors.append(f"active intervention checkpoint 不在 path: {node_id}")
            elif not is_eligible_teaching_candidate(str(checkpoint), subgraph, states_for_learner):
                checkpoint_state = states_for_learner.get(str(checkpoint), {})
                remaining_eligible = any(
                    candidate_id != str(checkpoint)
                    and is_eligible_teaching_candidate(
                        candidate_id, subgraph, states_for_learner
                    )
                    for candidate_id in path
                )
                target_ids = {
                    relation["target"]
                    for relation in index.get("nodes", {}).get(goal_id, {}).get(
                        "relations", []
                    )
                    if relation.get("type") == "targets"
                }
                all_targets_complete = bool(target_ids) and all(
                    states_for_learner.get(target_id, {}).get("mastery")
                    == "mastered"
                    and states_for_learner.get(target_id, {}).get(
                        "contract_status"
                    )
                    == "met"
                    for target_id in target_ids
                )
                completed_transition = bool(
                    checkpoint_state.get("mastery") == "mastered"
                    and checkpoint_state.get("contract_status") == "met"
                    and (remaining_eligible or all_targets_complete)
                )
                if not completed_transition:
                    errors.append(
                        f"active intervention checkpoint 不是可学 outer_fringe: {node_id}/{checkpoint}"
                    )
            active_routes_by_scope.setdefault((learner_id, goal_id), []).append(node_id)
        elif checkpoint is not None and checkpoint not in path:
            errors.append(f"intervention checkpoint 不在 path: {node_id}")

        completed = meta.get("completed_step_evidence_ids")
        if not isinstance(completed, list) or not all(isinstance(item, str) for item in completed):
            errors.append(f"intervention completed_step_evidence_ids 非法: {node_id}")
        else:
            for evidence_id in completed:
                evidence_meta = node_meta.get(evidence_id, {})
                if evidence_meta.get("type") != "evidence":
                    errors.append(f"intervention completed evidence 不存在: {node_id}/{evidence_id}")
                elif str(evidence_meta.get("learner_id")) != learner_id:
                    errors.append(f"intervention completed evidence 属于其他学习者: {node_id}/{evidence_id}")
                elif str(evidence_meta.get("goal_id")) != goal_id:
                    errors.append(f"intervention completed evidence 属于其他目标: {node_id}/{evidence_id}")
                else:
                    evidence_concept = str(evidence_meta.get("concept_id"))
                    completed_state = states_for_learner.get(evidence_concept)
                    state_node_id = state_keys.get((learner_id, goal_id, evidence_concept))
                    supported_targets = {
                        relation["target"]
                        for relation in index.get("nodes", {}).get(state_node_id, {}).get("relations", [])
                        if relation.get("type") == "supported_by"
                    }
                    if not completed_state or not state_node_id:
                        errors.append(f"intervention completed evidence 没有同范围 state: {node_id}/{evidence_id}")
                    elif (
                        completed_state.get("contract_id") != evidence_meta.get("contract_id")
                        or completed_state.get("contract_version") != evidence_meta.get("contract_version")
                    ):
                        errors.append(f"intervention completed evidence 与 state 合同不一致: {node_id}/{evidence_id}")
                    elif evidence_id not in supported_targets:
                        errors.append(f"intervention completed evidence 未被同范围 state 支持: {node_id}/{evidence_id}")
                    elif completed_state.get("mastery") != "mastered" or completed_state.get("contract_status") != "met":
                        errors.append(f"intervention completed evidence 对应 state 尚未完成: {node_id}/{evidence_id}")

        route_id = meta.get("route_id")
        route_version = meta.get("route_version")
        if not isinstance(route_id, str) or not route_id:
            errors.append(f"intervention route_id 非法: {node_id}")
        if not isinstance(route_version, int) or isinstance(route_version, bool) or route_version < 1:
            errors.append(f"intervention route_version 非法: {node_id}")
        else:
            identity = (learner_id, goal_id, str(route_id), route_version)
            if identity in route_identity:
                errors.append(f"intervention route_id/version 重复: {route_identity[identity]} 与 {node_id}")
            route_identity[identity] = node_id
            current_task = meta.get("current_verification_task_id")
            if isinstance(current_task, str) and current_task.strip():
                route_task_by_identity[identity] = current_task

    for scope, route_nodes in active_routes_by_scope.items():
        if len(route_nodes) > 1:
            message = (
                f"同一 learner+goal 有多个 active route，恢复时必须让用户选择: "
                f"{scope[0]}/{scope[1]} -> {','.join(sorted(route_nodes))}"
            )
            (warnings if allow_active_route_ambiguity else errors).append(message)

    # The active route must still resolve to the exact resource set and task
    # that were frozen in its append-only issuance event. Historical events are
    # self-contained snapshots; active events additionally match live nodes.
    for route_nodes in active_routes_by_scope.values():
        if len(route_nodes) != 1:
            continue
        route_node_id = route_nodes[0]
        route_meta = node_meta[route_node_id]
        checkpoint = str(route_meta.get("current_checkpoint"))
        state_id = state_keys.get(
            (str(route_meta.get("learner_id")), str(route_meta.get("goal_id")), checkpoint)
        )
        state_meta = node_meta.get(str(state_id), {})
        binding_key = (
            str(route_meta.get("learner_id")),
            str(route_meta.get("goal_id")),
            checkpoint,
            str(state_meta.get("contract_id")),
            state_meta.get("contract_version") if isinstance(state_meta.get("contract_version"), int) else -1,
            str(route_meta.get("route_id")),
            route_meta.get("route_version") if isinstance(route_meta.get("route_version"), int) else -1,
        )
        issued = route_binding_registry.get(binding_key)
        if issued is None:
            errors.append(f"active intervention 无匹配 route issuance: {route_node_id}")
            continue
        uses_ids = sorted(
            relation["target"]
            for relation in index["nodes"][route_node_id]["relations"]
            if relation.get("type") == "uses"
        )
        actual_resources: list[dict[str, Any]] = []
        try:
            for resource_id in uses_ids:
                resource_meta = dict(node_meta.get(resource_id, {}))
                resource_relations = index.get("nodes", {}).get(resource_id, {}).get("relations", [])
                resource_meta["teaches"] = [
                    item["target"] for item in resource_relations if item.get("type") == "teaches"
                ]
                resource_meta["requires"] = [
                    item["target"] for item in resource_relations if item.get("type") == "requires"
                ]
                actual_resources.append(
                    normalized_resource_snapshot(resource_meta, label=f"resource {resource_id}")
                )
            actual_resources.sort(key=lambda item: item["id"])
            actual_intervention = normalized_intervention_snapshot(
                {
                    "id": route_node_id,
                    "route_id": route_meta.get("route_id"),
                    "route_version": route_meta.get("route_version"),
                    "goal_id": route_meta.get("goal_id"),
                    "current_checkpoint": route_meta.get("current_checkpoint"),
                    "resource_ids": uses_ids,
                },
                label=f"intervention {route_node_id}",
            )
        except VaultError as exc:
            errors.append(str(exc))
            continue
        actual_snapshot = {"resources": actual_resources, "intervention": actual_intervention}
        if actual_snapshot != issued.get("issuance_snapshot"):
            errors.append(f"active intervention/resource 已偏离 route issuance 快照: {route_node_id}")
        if route_meta.get("current_verification_task_id") != issued.get("verification_task_id"):
            errors.append(f"active intervention task 与 route issuance 不一致: {route_node_id}")
        if route_meta.get("resolved_route_binding_id") not in {None, issued.get("binding_id")}:
            errors.append(f"active intervention resolved_route_binding_id 与 route issuance 不一致: {route_node_id}")
        if route_meta.get("resolved_context_key") not in {None, issued.get("context_key")}:
            errors.append(f"active intervention resolved_context_key 与 route issuance 不一致: {route_node_id}")

    # Active/current intervention routes get an additional task consistency
    # check here. Historical process/verification/retention evidence has already been
    # required above to match the independent immutable route-binding registry.
    for evidence_id, meta in node_meta.items():
        if meta.get("type") != "evidence" or meta.get("phase") not in {
            "teaching_process",
            "verification",
            "retention",
        }:
            continue
        route_version = meta.get("route_version_at_observation")
        if not isinstance(route_version, int) or isinstance(route_version, bool):
            continue
        identity = (
            str(meta.get("learner_id")),
            str(meta.get("goal_id")),
            str(meta.get("route_id_at_observation")),
            route_version,
        )
        expected_task = route_task_by_identity.get(identity)
        bound_task = meta.get("bound_verification_task_id")
        if expected_task is not None and bound_task != expected_task:
            errors.append(
                f"evidence 验证任务与 route version 绑定不一致: {evidence_id} "
                f"route_task={expected_task} evidence_task={bound_task}"
            )

    # Detect cycles in concept prerequisite relations.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(concept_id: str, trail: list[str]) -> None:
        if concept_id in visiting:
            cycle = trail[trail.index(concept_id) :] + [concept_id]
            errors.append(f"requires 存在环: {' -> '.join(cycle)}")
            return
        if concept_id in visited:
            return
        visiting.add(concept_id)
        for prerequisite in requirements.get(concept_id, set()):
            visit(prerequisite, trail + [prerequisite])
        visiting.remove(concept_id)
        visited.add(concept_id)

    for concept_id in requirements:
        visit(concept_id, [concept_id])

    # Recompute every state contract from its canonical supported evidence;
    # labels and unlinked evidence files are not trusted profile observations.
    canonical_observation_owners: dict[tuple[Any, ...], str] = {}
    canonical_evidence_owner_counts: dict[str, int] = {}
    derived_knowledge_by_state: dict[str, dict[str, Any]] = {}
    for node_id, meta in node_meta.items():
        if meta.get("type") != "state":
            continue
        relations = index["nodes"][node_id]["relations"]
        evidence_targets = [item["target"] for item in relations if item["type"] == "supported_by"]
        if len(evidence_targets) != len(set(evidence_targets)):
            errors.append(f"state supported_by 重复引用同一 evidence: {node_id}")
        evidence_targets = list(dict.fromkeys(evidence_targets))
        for target in evidence_targets:
            target_meta = node_meta.get(target, {})
            canonical_evidence_owner_counts[target] = (
                canonical_evidence_owner_counts.get(target, 0) + 1
            )
            if target_meta.get("type") != "evidence":
                errors.append(f"supported_by 目标不是 evidence: {node_id} -> {target}")
            elif target_meta.get("concept_id") != meta.get("concept_id"):
                errors.append(f"state 与 evidence 的 concept_id 不一致: {node_id} -> {target}")
            elif str(target_meta.get("learner_id")) != str(meta.get("learner_id")):
                errors.append(f"state 与 evidence 的 learner_id 不一致: {node_id} -> {target}")
            elif (
                str(target_meta.get("goal_id")) != str(meta.get("goal_id"))
                or str(target_meta.get("contract_id")) != str(meta.get("contract_id"))
                or target_meta.get("contract_version") != meta.get("contract_version")
            ):
                errors.append(f"state 与 evidence 的 goal/contract/version 不一致: {node_id} -> {target}")
            else:
                phase = str(target_meta.get("phase"))
                item_id = (
                    target_meta.get("verification_item_id")
                    if phase in {"verification", "retention"}
                    else target_meta.get("teaching_item_id")
                )
                if not isinstance(item_id, str) or not item_id.strip():
                    errors.append(f"canonical evidence 缺少可去重的 item identity: {node_id} -> {target}")
                elif phase in {"verification", "retention"}:
                    identity = (
                        str(target_meta.get("learner_id")),
                        str(target_meta.get("goal_id")),
                        str(target_meta.get("concept_id")),
                        str(target_meta.get("contract_id")),
                        target_meta.get("contract_version")
                        if isinstance(target_meta.get("contract_version"), int)
                        and not isinstance(target_meta.get("contract_version"), bool)
                        else -1,
                        str(target_meta.get("route_binding_id")),
                        phase,
                        item_id,
                    )
                    prior_owner = canonical_observation_owners.get(identity)
                    if prior_owner is not None and prior_owner != target:
                        errors.append(
                            "canonical supported evidence 重复 observation identity: "
                            f"{prior_owner} 与 {target}"
                        )
                    else:
                        canonical_observation_owners[identity] = target
                elif phase in {"diagnostic", "teaching_process"}:
                    try:
                        observed_identity = parse_iso_instant(
                            target_meta.get("observed_at")
                        ).isoformat()
                    except (TypeError, ValueError):
                        observed_identity = str(target_meta.get("observed_at"))
                    identity_base = (
                        str(target_meta.get("learner_id")),
                        str(target_meta.get("goal_id")),
                        str(target_meta.get("concept_id")),
                        str(target_meta.get("contract_id")),
                        target_meta.get("contract_version")
                        if isinstance(target_meta.get("contract_version"), int)
                        and not isinstance(target_meta.get("contract_version"), bool)
                        else -1,
                        str(target_meta.get("route_binding_id")),
                        phase,
                        observed_identity,
                    )
                    # A process event needs a unique timestamp within one
                    # scoped decision stream.  Otherwise an arbitrary evidence
                    # filename would decide which same-time record is "latest".
                    # Diagnostics retain item identity because independent
                    # probes may legitimately be captured together.
                    identity = (
                        identity_base
                        if phase == "teaching_process"
                        else (*identity_base, item_id)
                    )
                    prior_owner = canonical_observation_owners.get(identity)
                    if prior_owner is not None and prior_owner != target:
                        errors.append(
                            "canonical supported evidence 重放同一 observation event: "
                            f"{prior_owner} 与 {target}"
                        )
                    else:
                        canonical_observation_owners[identity] = target

        goal_id = str(meta.get("goal_id"))
        contract_id = str(meta.get("contract_id"))
        contract_version = meta.get("contract_version")
        contract_key = (contract_id, contract_version) if isinstance(contract_version, int) else (contract_id, -1)
        contract = goal_contracts.get(goal_id, {}).get(contract_key)
        if not contract:
            continue
        evidence_records = [
            (target, node_meta[target])
            for target in evidence_targets
            if node_meta.get(target, {}).get("type") == "evidence"
            and node_meta[target].get("concept_id") == meta.get("concept_id")
            and str(node_meta[target].get("learner_id")) == str(meta.get("learner_id"))
            and str(node_meta[target].get("goal_id")) == goal_id
            and str(node_meta[target].get("contract_id")) == contract_id
            and node_meta[target].get("contract_version") == contract_version
            and (
                node_meta[target].get("phase") not in {"verification", "retention"}
                or target in independently_bound_evidence_ids
            )
        ]
        evaluation = evaluate_mastery_contract(
            contract,
            evidence_records,
            state_context=state_context_with_current_schedule(
                meta, node_meta, strict=True
            ),
            as_of=meta.get("evaluated_at"),
            allow_synthetic_demo=allow_synthetic_demo,
        )
        derived_knowledge = derive_state_knowledge_status(
            evaluation, evidence_records, as_of=meta.get("evaluated_at")
        )
        derived_knowledge_by_state[node_id] = derived_knowledge
        for field in (
            "mastery",
            "mastery_confidence",
            "misconception_flags",
            "diagnostic_snapshot",
        ):
            if meta.get(field) != derived_knowledge[field]:
                errors.append(
                    f"state {field} 不是 canonical evidence 推导值: {node_id} "
                    f"stored={meta.get(field)!r} derived={derived_knowledge[field]!r}"
                )
        if meta.get("immediate_contract_status") != evaluation[
            "immediate_contract_status"
        ]:
            errors.append(
                f"state immediate_contract_status 不是证据推导值: {node_id} "
                f"stored={meta.get('immediate_contract_status')} "
                f"derived={evaluation['immediate_contract_status']}"
            )
        if meta.get("contract_status") != evaluation["status"]:
            errors.append(
                f"state contract_status 不是证据推导值: {node_id} "
                f"stored={meta.get('contract_status')} derived={evaluation['status']}"
            )
        if meta.get("retention_status") != evaluation["retention_status"]:
            errors.append(
                f"state retention_status 不是证据/计划时间推导值: {node_id} "
                f"stored={meta.get('retention_status')} derived={evaluation['retention_status']}"
            )
        if meta.get("next_action") != evaluation["next_action"]:
            errors.append(
                f"state next_action 不是当前三段状态推导值: {node_id} "
                f"stored={meta.get('next_action')} derived={evaluation['next_action']}"
            )
        live_evaluation = evaluate_mastery_contract(
            contract,
            evidence_records,
            state_context=state_context_with_current_schedule(
                meta, node_meta, strict=True
            ),
            as_of=utc_now(),
            allow_synthetic_demo=allow_synthetic_demo,
        )
        if (
            meta.get("retention_status") == "pending"
            and live_evaluation["retention_status"] == "due"
        ):
            warnings.append(
                f"state retention 已到期；continue/recover 应重算为 due 并执行 "
                f"issue_delayed_verification: {node_id}"
            )
        mastery = meta.get("mastery")
        if meta.get("contract_status") == "met" and mastery != "mastered":
            errors.append(
                f"state contract_status=met 但 mastery 不是 mastered，且无合法解释状态: {node_id}"
            )
        if evaluation["status"] == "met" and mastery != "mastered":
            errors.append(
                f"state 已满足全部合同但 mastery 未更新为 mastered: {node_id}"
            )
        if (
            evaluation["immediate_contract_status"] == "met"
            and evaluation["retention_status"] in {"not_started", "pending", "due"}
            and mastery == "mastered"
        ):
            errors.append(
                f"即时合同已过但延迟保持仍待完成，不得标记 mastered: {node_id}"
            )

        supported_with_times: list[tuple[str, dict[str, Any], datetime]] = []
        for evidence_id, evidence_meta in evidence_records:
            try:
                supported_with_times.append(
                    (evidence_id, evidence_meta, parse_iso_instant(evidence_meta.get("observed_at")))
                )
            except (TypeError, ValueError):
                continue
        latest_supported_at = (
            max(item[2] for item in supported_with_times) if supported_with_times else None
        )
        try:
            state_evaluated_instant = parse_iso_instant(meta.get("evaluated_at"))
        except (TypeError, ValueError):
            state_evaluated_instant = None
        if (
            latest_supported_at is not None
            and state_evaluated_instant is not None
            and state_evaluated_instant < latest_supported_at
        ):
            errors.append(
                f"state evaluated_at 早于最新 canonical evidence: {node_id}"
            )
        independent_times = [
            instant
            for _evidence_id, evidence_meta, instant in supported_with_times
            if evidence_meta.get("independence") == "independent"
            and evidence_meta.get("assistance_level") == "A0"
        ]
        latest_independent_at = max(independent_times) if independent_times else None

        def state_time_matches(field: str, expected: datetime | None) -> bool:
            stored = meta.get(field)
            if expected is None:
                return stored is None
            try:
                return parse_iso_instant(stored) == expected
            except (TypeError, ValueError):
                return False

        for field in ("as_of", "boundary_derived_at", "last_assessed_at"):
            if not state_time_matches(field, latest_supported_at):
                expected_text = latest_supported_at.isoformat() if latest_supported_at else None
                errors.append(
                    f"state {field} 不是 supported evidence 时间推导值: {node_id} "
                    f"stored={meta.get(field)} expected={expected_text}"
                )
        if not state_time_matches("last_independent_evidence_at", latest_independent_at):
            expected_text = latest_independent_at.isoformat() if latest_independent_at else None
            errors.append(
                f"state last_independent_evidence_at 不是独立 evidence 时间推导值: {node_id} "
                f"stored={meta.get('last_independent_evidence_at')} expected={expected_text}"
            )

        if mastery != "mastered":
            continue
        if evaluation["status"] != "met":
            errors.append(
                f"mastered 状态未满足结构化合同: {node_id}; missing={','.join(evaluation['missing'])}"
            )
        if evaluation["retention_required"]:
            if not re.fullmatch(r"passed_\d+d", evaluation["retention_status"]):
                errors.append(f"mastered 状态缺少合同要求的延迟保持证据: {node_id}")
            if evaluation["retention_status"] in {"failed", "conflicted"}:
                errors.append(
                    f"mastered 状态存在更新的延迟保持负面证据，必须 retention_repair: "
                    f"{node_id}; evidence={','.join(evaluation['current_negative_evidence_ids'])}"
                )
            retention = contract["requirements"]["delayed_retention"]
            retained_match = re.fullmatch(r"passed_(\d+)d", str(meta.get("retention_status")))
            stored_days = int(retained_match.group(1)) if retained_match else 0
            if (
                not retained_match
                or stored_days < int(retention["min_delay_days"])
                or stored_days != int(evaluation["retention_verified_days"])
            ):
                errors.append(
                    f"mastered 状态 retention_status 与实际验证天数不一致: {node_id} "
                    f"stored={meta.get('retention_status')} verified={evaluation['retention_verified_days']}d"
                )
        elif meta.get("retention_status") != "not_required":
            errors.append(f"合同不要求延迟保持时 retention_status 应为 not_required: {node_id}")

    derived_mastery_groups: dict[tuple[str, str], dict[str, str]] = {}
    for (learner_id, goal_id, concept_id), state_id in state_keys.items():
        derived = derived_knowledge_by_state.get(state_id)
        if derived is not None:
            derived_mastery_groups.setdefault((learner_id, goal_id), {})[
                concept_id
            ] = str(derived["mastery"])
    for (learner_id, goal_id), mastery_by_concept in derived_mastery_groups.items():
        derived_boundaries = derive_boundary_positions(
            concept_relation_map, mastery_by_concept
        )
        for concept_id, expected_boundary in derived_boundaries.items():
            state_id = state_keys[(learner_id, goal_id, concept_id)]
            if node_meta[state_id].get("boundary_position") != expected_boundary:
                errors.append(
                    "state boundary_position 未随 canonical evidence 重算: "
                    f"{state_id} stored={node_meta[state_id].get('boundary_position')} "
                    f"derived={expected_boundary}"
                )

    for evidence_id, evidence_meta in node_meta.items():
        if evidence_meta.get("type") != "evidence":
            continue
        owner_count = canonical_evidence_owner_counts.get(evidence_id, 0)
        if evidence_meta.get("observation_validity") == "valid" and owner_count != 1:
            errors.append(
                "valid evidence 必须被唯一同 scope state.supported_by 消费: "
                f"{evidence_id} owners={owner_count}"
            )
        elif owner_count > 1:
            errors.append(
                f"evidence 不得被多个 state.supported_by 消费: {evidence_id} owners={owner_count}"
            )
    # Persisted teaching resolution is a cache of the current evidence-driven
    # decision, not an authority.  Recompute it from validated evidence,
    # issuance and real resources so recover/Cone cannot trust edited fields.
    if not allow_unresolved_teaching and not errors:
        active_resolution_meta = next(
            (
                meta
                for meta in node_meta.values()
                if meta.get("type") == "intervention"
                and meta.get("status") == "active"
                and meta.get("learner_id")
                == node_meta.get(str(manifest.get("active_learner_id")), {}).get("learner_id")
                and meta.get("goal_id") == manifest.get("active_goal_id")
            ),
            {},
        )
        if active_resolution_meta:
            active_scope_state = next(
                (
                    meta
                    for meta in node_meta.values()
                    if meta.get("type") == "state"
                    and meta.get("learner_id")
                    == active_resolution_meta.get("learner_id")
                    and meta.get("goal_id") == active_resolution_meta.get("goal_id")
                    and meta.get("concept_id")
                    == active_resolution_meta.get("current_checkpoint")
                ),
                None,
            )
            try:
                active_resolution_instant = parse_iso_instant(
                    active_resolution_meta.get("resolved_at")
                )
            except (TypeError, ValueError):
                active_resolution_instant = None
            if isinstance(active_scope_state, dict) and active_resolution_instant is not None:
                process_scope = {
                    "learner_id": active_scope_state.get("learner_id"),
                    "goal_id": active_scope_state.get("goal_id"),
                    "concept_id": active_scope_state.get("concept_id"),
                    "contract_id": active_scope_state.get("contract_id"),
                    "contract_version": active_scope_state.get("contract_version"),
                }
                for evidence_id, evidence_meta in node_meta.items():
                    if (
                        evidence_meta.get("type") != "evidence"
                        or evidence_meta.get("phase") != "teaching_process"
                        or canonical_evidence_owner_counts.get(evidence_id) != 1
                        or any(
                            evidence_meta.get(field) != expected
                            for field, expected in process_scope.items()
                        )
                    ):
                        continue
                    try:
                        observed = parse_iso_instant(evidence_meta.get("observed_at"))
                    except (TypeError, ValueError):
                        continue
                    if observed <= active_resolution_instant:
                        continue
                    post_decision_binding = (
                        evidence_meta.get("decision_fingerprint_at_observation")
                        == active_resolution_meta.get("resolved_decision_fingerprint")
                        and evidence_meta.get("route_binding_id")
                        == active_resolution_meta.get("resolved_route_binding_id")
                        and evidence_meta.get("route_id_at_observation")
                        == active_resolution_meta.get("route_id")
                        and evidence_meta.get("route_version_at_observation")
                        == active_resolution_meta.get("route_version")
                        and evidence_meta.get("verification_task_id")
                        == active_resolution_meta.get("current_verification_task_id")
                        and evidence_meta.get("bound_verification_task_id")
                        == active_resolution_meta.get("current_verification_task_id")
                    )
                    if not post_decision_binding:
                        errors.append(
                            "晚于 active resolution 的 canonical teaching_process 必须绑定该 decision epoch: "
                            f"{evidence_id}"
                        )
        try:
            expected_epoch_resolution = resolve_active_teaching(
                vault,
                write=False,
                _skip_validation=True,
                _as_of=active_resolution_meta.get("resolved_at"),
            )
            expected_process_resolution = resolve_active_teaching(
                vault,
                write=False,
                _skip_validation=True,
                _as_of=active_resolution_meta.get("process_refreshed_at"),
            )
        except VaultError as exc:
            errors.append(f"active teaching resolution 无法重算: {exc}")
        else:
            intervention_id = str(expected_epoch_resolution["intervention_id"])
            stored_resolution = node_meta.get(intervention_id, {})
            epoch_fields = (
                "teaching_resolution_schema",
                "resolved_activity",
                "resolved_carrier",
                "resolved_resource_id",
                "resolved_profile_refs",
                "resolved_profile_level",
                "resolved_profile_usage",
                "resolved_route_binding_id",
                "resolved_context_key",
                "resolved_at",
                "resolved_decision_fingerprint",
                "current_activity_id",
                "current_probe_id",
                "current_verification_task_id",
                "carrier",
                "adaptation_confidence",
            )
            for field in epoch_fields:
                if stored_resolution.get(field) != expected_epoch_resolution.get(field):
                    errors.append(
                        f"active teaching decision epoch 不是签发时证据推导值: "
                        f"{intervention_id}/{field} stored={stored_resolution.get(field)!r} "
                        f"derived={expected_epoch_resolution.get(field)!r}"
                    )
            for field in PROCESS_REFRESH_FIELDS:
                if stored_resolution.get(field) != expected_process_resolution.get(field):
                    errors.append(
                        f"active teaching process cache 不是刷新时证据推导值: "
                        f"{intervention_id}/{field} stored={stored_resolution.get(field)!r} "
                        f"derived={expected_process_resolution.get(field)!r}"
                    )
            try:
                process_refreshed_instant = parse_iso_instant(
                    stored_resolution.get("process_refreshed_at")
                )
            except (TypeError, ValueError):
                errors.append(
                    f"active teaching resolution process_refreshed_at 非法: {intervention_id}"
                )
            else:
                latest_process_instant = max(
                    (
                        parse_iso_instant(meta.get("observed_at"))
                        for meta in node_meta.values()
                        if meta.get("type") == "evidence"
                        and meta.get("phase") == "teaching_process"
                        and meta.get("learner_id")
                        == active_resolution_meta.get("learner_id")
                        and meta.get("goal_id")
                        == active_resolution_meta.get("goal_id")
                        and meta.get("concept_id")
                        == active_resolution_meta.get("current_checkpoint")
                    ),
                    default=None,
                )
                if (
                    latest_process_instant is not None
                    and process_refreshed_instant < latest_process_instant
                ):
                    errors.append(
                        "active teaching process_refreshed_at 早于最新过程 evidence: "
                        f"{intervention_id}"
                    )

    # index.json is a cache; stale content is a warning, not a fact error.
    disk_index_path = vault / INDEX_REL
    if disk_index_path.is_file():
        try:
            disk_index = json.loads(disk_index_path.read_text(encoding="utf-8"))
            if disk_index.get("schema") != SCHEMA or disk_index.get("nodes") != index.get("nodes"):
                warnings.append("index.json 已过期；运行 rebuild-index")
        except (OSError, json.JSONDecodeError):
            warnings.append("index.json 无法解析；运行 rebuild-index")
    else:
        warnings.append("缺少可重建的 index.json")

    summary = {
        "vault": str(vault.resolve()),
        "node_count": index.get("node_count", 0),
        "error_count": len(set(errors)),
        "warning_count": len(set(warnings)),
    }
    return sorted(set(errors)), sorted(set(warnings)), summary


@vault_transaction_writer
def rebuild_index(vault: Path) -> tuple[dict[str, Any], list[str]]:
    index, errors = build_index(vault)
    write_json(vault / INDEX_REL, index)
    return index, errors


def evaluate_mastery_contract(
    contract: dict[str, Any],
    evidence_records: list[tuple[str, dict[str, Any]]],
    *,
    state_context: dict[str, Any] | None = None,
    as_of: Any | None = None,
    allow_synthetic_demo: bool = False,
) -> dict[str, Any]:
    """Recompute immediate mastery and delayed retention as separate gates.

    A retention gap never erases an already-met immediate contract. Conversely,
    a newer eligible adverse result overrides an older pass in the same gate.
    The combined ``status`` is kept for state snapshots and backward callers;
    the explicit gate fields are authoritative.
    """

    requirements = contract.get("requirements", {})
    try:
        evaluation_instant = parse_iso_instant(as_of if as_of is not None else utc_now())
    except (TypeError, ValueError):
        evaluation_instant = None
    unique_evidence: dict[str, dict[str, Any]] = {}
    for evidence_id, meta in evidence_records:
        try:
            observed_instant = parse_iso_instant(meta.get("observed_at"))
        except (TypeError, ValueError):
            continue
        if evaluation_instant is not None and observed_instant <= evaluation_instant:
            unique_evidence.setdefault(evidence_id, meta)
    evidence_records = list(unique_evidence.items())
    evidence_by_id = dict(evidence_records)
    eligible = [
        (evidence_id, meta)
        for evidence_id, meta in evidence_records
        if evidence_mastery_eligibility(
            meta, allow_synthetic_demo=allow_synthetic_demo
        )[0]
    ]
    eligible_immediate = [
        (evidence_id, meta)
        for evidence_id, meta in eligible
        if meta.get("phase") == "verification"
    ]
    derived_retention_delays = {
        evidence_id: derived_retention_delay_days(meta, evidence_by_id)
        for evidence_id, meta in eligible
        if meta.get("phase") == "retention"
    }
    eligible_retention = [
        (evidence_id, meta)
        for evidence_id, meta in eligible
        if meta.get("phase") == "retention"
        and derived_retention_delays.get(evidence_id) is not None
    ]

    def is_positive(meta: dict[str, Any]) -> bool:
        return (
            meta.get("result") == "pass"
            and meta.get("response_correct") is True
            and is_unit_interval(meta.get("immediate_performance"))
        )

    def is_adverse(meta: dict[str, Any]) -> bool:
        return meta.get("result") in {"fail", "partial", "conflicted"} or meta.get(
            "response_correct"
        ) is False

    minimum_instant = datetime.min.replace(tzinfo=timezone.utc)

    def evidence_instant(meta: dict[str, Any]) -> datetime:
        try:
            return parse_iso_instant(meta.get("observed_at"))
        except (TypeError, ValueError):
            return minimum_instant

    def latest_per_verification_task(
        records: list[tuple[str, dict[str, Any]]]
    ) -> list[tuple[str, dict[str, Any]]]:
        by_task: dict[str, tuple[str, dict[str, Any]]] = {}
        for evidence_id, meta in records:
            task_id = str(meta.get("verification_task_id") or evidence_id)
            current = by_task.get(task_id)
            if current is None or (
                evidence_instant(meta), evidence_id
            ) > (
                evidence_instant(current[1]), current[0]
            ):
                by_task[task_id] = (evidence_id, meta)
        return sorted(by_task.values(), key=lambda item: (evidence_instant(item[1]), item[0]))

    # One issued verification task is one independent learning opportunity.
    # Repeated records for the same task may update its latest outcome but may
    # not inflate the contract's minimum evidence count.
    eligible_immediate = latest_per_verification_task(eligible_immediate)
    eligible_retention = latest_per_verification_task(eligible_retention)

    def latest_adverse_wins(
        positives: list[tuple[str, dict[str, Any]]],
        negatives: list[tuple[str, dict[str, Any]]],
    ) -> tuple[bool, list[str]]:
        latest_positive = max(
            (evidence_instant(meta) for _evidence_id, meta in positives),
            default=minimum_instant,
        )
        latest_negative = max(
            (evidence_instant(meta) for _evidence_id, meta in negatives),
            default=minimum_instant,
        )
        wins = bool(negatives and (not positives or latest_negative >= latest_positive))
        current_ids = [
            evidence_id
            for evidence_id, meta in negatives
            if wins and evidence_instant(meta) == latest_negative
        ]
        return wins, current_ids

    immediate_positive = [
        (evidence_id, meta)
        for evidence_id, meta in eligible_immediate
        if is_positive(meta)
    ]
    immediate_negative = [
        (evidence_id, meta)
        for evidence_id, meta in eligible_immediate
        if is_adverse(meta)
    ]
    immediate_adverse_current, current_immediate_negative_ids = latest_adverse_wins(
        immediate_positive, immediate_negative
    )

    immediate_missing: list[str] = []
    minimum = requirements.get("minimum_qualified_evidence")
    if (
        "minimum_qualified_evidence" not in requirements
        or not isinstance(minimum, int)
        or isinstance(minimum, bool)
        or minimum < 1
    ):
        immediate_missing.append("invalid minimum_qualified_evidence")
    elif len(immediate_positive) < minimum:
        immediate_missing.append(f"qualified evidence {len(immediate_positive)}/{minimum}")

    demonstrated: set[str] = set()
    for _evidence_id, meta in immediate_positive:
        values = meta.get("demonstrates", [])
        if not isinstance(values, list):
            continue
        for item in values:
            capability = str(item)
            if capability == "delayed_retention":
                continue
            if capability == "explanation" and meta.get("explanation_quality") != "pass":
                continue
            if capability == "near_transfer" and not is_unit_interval(meta.get("near_transfer")):
                continue
            demonstrated.add(capability)
    required_capabilities = requirements.get("required_capabilities")
    if isinstance(required_capabilities, list) and required_capabilities:
        for capability in required_capabilities:
            capability = str(capability)
            if capability == "delayed_retention":
                continue
            if capability not in demonstrated:
                immediate_missing.append(f"capability:{capability}")
    else:
        immediate_missing.append("invalid capabilities")

    minimum_transfer = requirements.get("min_near_transfer")
    if "min_near_transfer" not in requirements:
        immediate_missing.append("invalid min_near_transfer")
    elif minimum_transfer is not None:
        if not isinstance(minimum_transfer, (int, float)) or isinstance(minimum_transfer, bool):
            immediate_missing.append("invalid min_near_transfer")
        else:
            transfer_scores = [
                float(meta["near_transfer"])
                for _evidence_id, meta in immediate_positive
                if is_unit_interval(meta.get("near_transfer"))
            ]
            if not transfer_scores or max(transfer_scores) < float(minimum_transfer):
                immediate_missing.append(f"near_transfer>={minimum_transfer}")

    if not evidence_records:
        immediate_contract_status = "not_tested"
    elif immediate_adverse_current:
        immediate_contract_status = "not_met"
    elif immediate_missing:
        immediate_contract_status = "in_progress"
    else:
        immediate_contract_status = "met"

    state_context = state_context or {}
    # A persisted schedule receipt starts a distinct delayed-verification
    # cycle.  Historical retention outcomes remain immutable evidence, but a
    # newer qualified verification baseline must be able to open a new cycle
    # after repair instead of being permanently shadowed by the old failure.
    current_cycle_baseline = state_context.get("baseline_evidence_id")
    if isinstance(current_cycle_baseline, str) and current_cycle_baseline:
        eligible_retention = [
            (evidence_id, meta)
            for evidence_id, meta in eligible_retention
            if meta.get("baseline_evidence_id") == current_cycle_baseline
        ]
    evaluated_at = evaluation_instant

    retention = requirements.get("delayed_retention")
    retention_config_valid = isinstance(retention, dict) and isinstance(
        retention.get("required"), bool
    )
    retention_required = bool(retention_config_valid and retention.get("required") is True)
    retention_missing: list[str] = []
    retention_positive: list[tuple[str, dict[str, Any]]] = []
    retention_negative: list[tuple[str, dict[str, Any]]] = []
    retention_delays: list[int] = []
    current_retention_negative_ids: list[str] = []

    if not retention_config_valid:
        retention_status = "invalid_contract"
        retention_missing.append("invalid delayed_retention")
    elif not retention_required:
        retention_status = "not_required"
    else:
        minimum_score = retention.get("min_score")
        minimum_days = retention.get("min_delay_days")
        if not isinstance(minimum_score, (int, float)) or isinstance(minimum_score, bool):
            retention_status = "invalid_contract"
            retention_missing.append("invalid delayed_retention.min_score")
        elif not isinstance(minimum_days, int) or isinstance(minimum_days, bool) or minimum_days < 1:
            retention_status = "invalid_contract"
            retention_missing.append("invalid delayed_retention.min_delay_days")
        else:
            for evidence_id, meta in eligible_retention:
                delay = derived_retention_delays[evidence_id]
                score = meta.get("delayed_retention")
                meets_threshold = (
                    is_unit_interval(score)
                    and isinstance(delay, int)
                    and float(score) >= float(minimum_score)
                    and delay >= minimum_days
                    and isinstance(meta.get("demonstrates"), list)
                    and "delayed_retention" in meta.get("demonstrates", [])
                )
                if is_positive(meta) and meets_threshold:
                    retention_positive.append((evidence_id, meta))
                    retention_delays.append(delay)
                elif is_adverse(meta) or (
                    isinstance(delay, int)
                    and delay >= minimum_days
                    and is_unit_interval(score)
                    and float(score) < float(minimum_score)
                ):
                    retention_negative.append((evidence_id, meta))
            retention_adverse_current, current_retention_negative_ids = latest_adverse_wins(
                retention_positive, retention_negative
            )
            if retention_adverse_current:
                current_negative_meta = [
                    evidence_by_id[evidence_id]
                    for evidence_id in current_retention_negative_ids
                    if evidence_id in evidence_by_id
                ]
                retention_status = (
                    "conflicted"
                    if any(meta.get("result") == "conflicted" for meta in current_negative_meta)
                    else "failed"
                )
                retention_missing.append("latest_retention_adverse")
            elif retention_positive:
                retention_status = f"passed_{max(retention_delays)}d"
            elif immediate_contract_status != "met":
                retention_status = "not_started"
                retention_missing.append("immediate_contract_not_met")
            else:
                scheduled_for = state_context.get("scheduled_for")
                if scheduled_for is None and eligible_retention:
                    latest_retention = max(
                        eligible_retention,
                        key=lambda item: evidence_instant(item[1]),
                    )[1]
                    scheduled_for = latest_retention.get("scheduled_for")
                if scheduled_for in (None, ""):
                    retention_status = "not_started"
                else:
                    try:
                        scheduled_instant = parse_iso_instant(scheduled_for)
                    except (TypeError, ValueError):
                        scheduled_instant = None
                    if evaluated_at is None or scheduled_instant is None:
                        retention_status = "invalid_contract"
                        retention_missing.append("invalid retention scheduled_for/as_of")
                    elif evaluated_at < scheduled_instant:
                        retention_status = "pending"
                    else:
                        retention_status = "due"
                retention_missing.append(
                    f"delayed_retention>={minimum_score}@{minimum_days}d"
                )

    if immediate_contract_status == "not_tested":
        status = "not_tested"
    elif immediate_contract_status == "not_met":
        status = "not_met"
    elif immediate_contract_status != "met":
        status = "in_progress"
    elif retention_status == "not_required" or re.fullmatch(r"passed_\d+d", retention_status):
        status = "met"
    elif retention_status in {"failed", "conflicted"}:
        status = "not_met"
    else:
        status = "in_progress"

    invalid_contract = any(
        item.startswith("invalid ") for item in immediate_missing + retention_missing
    )
    if invalid_contract:
        next_action = "none"
    elif immediate_contract_status == "not_tested":
        next_action = "collect_immediate_verification"
    elif immediate_contract_status == "not_met":
        next_action = "immediate_repair"
    elif immediate_contract_status == "in_progress":
        substantive_gaps = [
            item
            for item in immediate_missing
            if not item.startswith("qualified evidence ")
        ]
        next_action = (
            "immediate_repair"
            if substantive_gaps
            else "collect_immediate_verification"
        )
    elif retention_status == "not_started":
        next_action = "schedule_retention"
    elif retention_status == "pending":
        next_action = "wait_until_scheduled_for"
    elif retention_status == "due":
        next_action = "issue_delayed_verification"
    elif retention_status in {"failed", "conflicted"}:
        next_action = "retention_repair"
    else:
        next_action = "none"

    immediate_positive_ids = [evidence_id for evidence_id, _meta in immediate_positive]
    retention_positive_ids = [evidence_id for evidence_id, _meta in retention_positive]
    immediate_negative_ids = [evidence_id for evidence_id, _meta in immediate_negative]
    retention_negative_ids = [evidence_id for evidence_id, _meta in retention_negative]
    negative_ids = list(dict.fromkeys(immediate_negative_ids + retention_negative_ids))
    return {
        "status": status,
        "immediate_contract_status": immediate_contract_status,
        "retention_status": retention_status,
        "next_action": next_action,
        "missing": immediate_missing + retention_missing,
        "immediate_missing": immediate_missing,
        "retention_missing": retention_missing,
        "qualified_evidence_ids": immediate_positive_ids + retention_positive_ids,
        "immediate_qualified_evidence_ids": immediate_positive_ids,
        "retention_evidence_ids": retention_positive_ids,
        "negative_evidence_ids": negative_ids,
        "immediate_negative_evidence_ids": immediate_negative_ids,
        "retention_negative_evidence_ids": retention_negative_ids,
        "current_negative_evidence_ids": list(
            dict.fromkeys(current_immediate_negative_ids + current_retention_negative_ids)
        ),
        # Compatibility alias for callers that previously only tracked failures.
        "qualified_failure_evidence_ids": negative_ids,
        "retention_verified_days": max(retention_delays, default=0),
        "retention_required": retention_required,
        "retention_scheduled_for": state_context.get("scheduled_for"),
        "evaluated_at": evaluated_at.isoformat() if evaluated_at is not None else None,
    }


def target_subgraph_for_goal(
    index: dict[str, Any], goal_id: str, requirements: dict[str, set[str]]
) -> set[str]:
    goal_node = index.get("nodes", {}).get(goal_id, {})
    targets = {
        relation["target"]
        for relation in goal_node.get("relations", [])
        if relation.get("type") == "targets"
    }
    result = set(targets)
    frontier = list(targets)
    while frontier:
        concept_id = frontier.pop()
        for prerequisite in requirements.get(concept_id, set()):
            if prerequisite not in result:
                result.add(prerequisite)
                frontier.append(prerequisite)
    return result


def is_eligible_teaching_candidate(
    concept_id: str,
    target_subgraph: set[str],
    states_by_concept: dict[str, dict[str, Any]],
) -> bool:
    state = states_by_concept.get(concept_id)
    return bool(
        concept_id in target_subgraph
        and state
        and state.get("mastery") != "mastered"
        and state.get("boundary_position") == "outer_fringe"
    )


def _candidate_binding_available(candidate: dict[str, Any]) -> bool:
    action = candidate.get("routing_action")
    if action == "diagnose_now":
        return isinstance(candidate.get("probe_id"), str) and bool(candidate["probe_id"].strip())
    if action == "teach_now":
        return all(
            isinstance(candidate.get(field), str) and bool(candidate[field].strip())
            for field in ("activity_id", "verification_task_id")
        )
    return False


def _complete_cost_vector(candidate: dict[str, Any]) -> dict[str, float] | None:
    vector = candidate.get("cost_vector")
    if not isinstance(vector, dict) or not vector:
        return None
    normalized: dict[str, float] = {}
    for key, value in vector.items():
        if (
            not isinstance(key, str)
            or not key
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value < 0
        ):
            return None
        normalized[key] = float(value)
    return normalized


def _cost_dominates(left: dict[str, float], right: dict[str, float]) -> bool:
    return left.keys() == right.keys() and all(left[key] <= right[key] for key in left) and any(
        left[key] < right[key] for key in left
    )


def _recomputed_focus_value(candidate: dict[str, Any]) -> float | None:
    """Return a verified Focus value; never trust a naked cached focus_z."""

    if candidate.get("ranking_status") != "complete" or candidate.get("validity") != "valid":
        return None
    components = {
        "goal": candidate.get("goal_relevance"),
        "interest": candidate.get("interest_evidence"),
        "readiness": candidate.get("readiness"),
    }
    if not all(is_unit_interval(value) for value in components.values()):
        return None
    weights = candidate.get("focus_weights")
    if (
        not isinstance(weights, dict)
        or set(weights) != {"goal", "interest", "readiness"}
        or not all(is_unit_interval(weights.get(field)) for field in components)
        or not math.isclose(
            sum(float(weights[field]) for field in components), 1.0, abs_tol=0.0002
        )
    ):
        return None
    source_refs = candidate.get("input_source_refs")
    if (
        not isinstance(source_refs, list)
        or not source_refs
        or any(not isinstance(item, str) or not item.strip() for item in source_refs)
        or len(source_refs) != len(set(source_refs))
    ):
        return None
    try:
        parse_iso_instant(candidate.get("calculated_at"))
    except (TypeError, ValueError):
        return None
    cached = candidate.get("focus_z")
    if not is_unit_interval(cached):
        return None
    recomputed = sum(float(weights[field]) * float(components[field]) for field in components)
    if not math.isclose(float(cached), recomputed, abs_tol=0.0002):
        return None
    return recomputed


def select_candidate_step_v3(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure v3 selector: eligibility -> route -> binding -> Pareto -> user priority -> Focus."""

    evaluated = [dict(candidate) for candidate in candidates]
    for candidate in evaluated:
        hard_eligible = all(
            candidate.get(field) is True
            for field in (
                "in_target_subgraph",
                "mastery_compatible",
                "prerequisites_satisfied",
                "hard_constraints_satisfied",
            )
        )
        candidate["eligibility_status"] = "eligible" if hard_eligible else "ineligible"
        candidate["decision_pool_status"] = "excluded"
        candidate["binding_status"] = "not_evaluated"
        candidate["pareto_status"] = "not_needed"
        candidate["selection_status"] = "not_selected"
        candidate["focus_input_status"] = "not_evaluated"

    eligible = [item for item in evaluated if item["eligibility_status"] == "eligible"]
    if not eligible:
        return {
            "selected_id": None,
            "selection_basis": "not_selected",
            "scope_status": "not_evaluated",
            "candidates": evaluated,
        }

    # A route decision may compare different concept steps. Each step keeps its
    # own concept contract, while learner/goal/route/time scope must match.
    # Missing scope is not treated as a match merely because every candidate
    # happens to omit the same field.
    decision_scope_fields = (
        "learner_id",
        "goal_id",
        "route_id",
        "route_version",
        "time_scope",
    )
    decision_scope_complete = all(
        all(item.get(field) not in (None, "") for field in decision_scope_fields)
        for item in eligible
    )
    candidate_contracts_complete = all(
        item.get("concept_id") not in (None, "")
        and item.get("contract_id") not in (None, "")
        and isinstance(item.get("contract_version"), int)
        and not isinstance(item.get("contract_version"), bool)
        and int(item["contract_version"]) >= 1
        for item in eligible
    )
    scope_values = {
        tuple(item.get(field) for field in decision_scope_fields) for item in eligible
    }
    if not decision_scope_complete or not candidate_contracts_complete or len(scope_values) != 1:
        for item in eligible:
            item["decision_pool_status"] = "scope_mismatch"
        return {
            "selected_id": None,
            "selection_basis": "not_selected",
            "scope_status": "missing_or_mixed",
            "candidates": evaluated,
        }

    route_levels = [
        item.get("route_level")
        for item in eligible
        if isinstance(item.get("route_level"), int) and not isinstance(item.get("route_level"), bool)
    ]
    if len(route_levels) != len(eligible):
        return {
            "selected_id": None,
            "selection_basis": "not_selected",
            "scope_status": "matched",
            "candidates": evaluated,
        }
    active_level = min(route_levels)
    route_pool = [item for item in eligible if item.get("route_level") == active_level]
    for item in eligible:
        item["decision_pool_status"] = "active" if item in route_pool else "standby"

    bound: list[dict[str, Any]] = []
    for item in route_pool:
        item["binding_status"] = "bound" if _candidate_binding_available(item) else "unavailable"
        if item["binding_status"] == "bound":
            bound.append(item)
    if not bound:
        return {
            "selected_id": None,
            "selection_basis": "not_selected",
            "scope_status": "matched",
            "candidates": evaluated,
        }

    comparison_scope_fields = (
        "routing_action",
        "route_level",
        "mastery_gate",
        "time_scope",
    )
    if any(
        any(item.get(field) in (None, "") for field in comparison_scope_fields)
        for item in bound
    ):
        return {
            "selected_id": None,
            "selection_basis": "cost_unresolved",
            "scope_status": "missing_comparison_scope",
            "needs_measurement": True,
            "candidates": evaluated,
        }
    route_default_order = sorted(
        bound,
        key=lambda item: (item.get("route_order", 0), str(item.get("candidate_step_id"))),
    )
    active_comparison_key = tuple(
        route_default_order[0].get(field) for field in comparison_scope_fields
    )
    comparison_keys = {
        tuple(item.get(field) for field in comparison_scope_fields) for item in bound
    }
    group_default_applied = len(comparison_keys) > 1
    if group_default_applied:
        for item in bound:
            item_key = tuple(item.get(field) for field in comparison_scope_fields)
            if item_key != active_comparison_key:
                item["decision_pool_status"] = "standby_action_gate"
        bound = [
            item
            for item in bound
            if tuple(item.get(field) for field in comparison_scope_fields)
            == active_comparison_key
        ]

    if len(bound) == 1:
        frontier = bound
        bound[0]["pareto_status"] = "not_needed"
    else:
        vectors = [_complete_cost_vector(item) for item in bound]
        comparable = all(vector is not None for vector in vectors) and len(
            {tuple(sorted(vector or {})) for vector in vectors}
        ) == 1
        if not comparable:
            for item in bound:
                item["pareto_status"] = "unresolved"
            frontier = bound
        else:
            frontier = []
            for index, item in enumerate(bound):
                dominated = any(
                    other_index != index
                    and _cost_dominates(vectors[other_index] or {}, vectors[index] or {})
                    for other_index in range(len(bound))
                )
                item["pareto_status"] = "dominated" if dominated else "frontier"
                if not dominated:
                    frontier.append(item)

    priority_status = "not_provided"
    priority_pool = list(frontier)
    declared_priorities = [item.get("user_cost_priority") for item in frontier]
    pareto_resolved = len(bound) == 1 or all(
        item.get("pareto_status") == "frontier" for item in frontier
    )
    if len(frontier) == 1:
        priority_status = "not_needed" if any(
            priority is not None for priority in declared_priorities
        ) else "not_provided"
    elif pareto_resolved and len(frontier) > 1 and all(
        isinstance(priority, list)
        and bool(priority)
        and all(isinstance(dimension, str) and dimension for dimension in priority)
        and len(priority) == len(set(priority))
        for priority in declared_priorities
    ) and all(priority == declared_priorities[0] for priority in declared_priorities):
        priority = declared_priorities[0]
        priority_vectors = [_complete_cost_vector(item) for item in frontier]
        if all(
            vector is not None and all(dimension in vector for dimension in priority)
            for vector in priority_vectors
        ):
            priority_status = "applied"
            for dimension in priority:
                minimum = min(float((_complete_cost_vector(item) or {})[dimension]) for item in priority_pool)
                priority_pool = [
                    item
                    for item in priority_pool
                    if math.isclose(float((_complete_cost_vector(item) or {})[dimension]), minimum)
                ]
                if len(priority_pool) == 1:
                    break
        else:
            priority_status = "invalid_dimension"
    elif not pareto_resolved and any(priority is not None for priority in declared_priorities):
        priority_status = "blocked_by_unresolved_pareto"
    elif any(priority is not None for priority in declared_priorities):
        priority_status = "inconsistent"

    ordered = sorted(
        priority_pool,
        key=lambda item: (item.get("route_order", 0), str(item.get("candidate_step_id"))),
    )
    priority_unresolved = priority_status in {
        "inconsistent",
        "invalid_dimension",
        "blocked_by_unresolved_pareto",
    }
    if priority_unresolved:
        chosen = ordered[0]
        basis = "cost_unresolved"
    elif len(ordered) == 1:
        chosen = ordered[0]
        if priority_status == "applied" and len(frontier) > 1:
            basis = "user_cost_priority"
        else:
            basis = (
                "cost_pareto"
                if len(bound) > 1
                else ("route_default" if group_default_applied else "active_route")
            )
    else:
        focus_equality_fields = (
            "learner_id",
            "goal_id",
            "routing_action",
            "route_level",
            "mastery_gate",
            "route_id",
            "route_version",
            "time_scope",
        )
        focus_required_fields = focus_equality_fields + (
            "concept_id",
            "contract_id",
            "contract_version",
        )
        focus_scope_complete = all(
            all(item.get(field) not in (None, "") for field in focus_required_fields)
            for item in ordered
        )
        same_focus_scope = focus_scope_complete and len(
            {
                tuple(item.get(field) for field in focus_equality_fields)
                for item in ordered
            }
        ) == 1
        recomputed_focus = [_recomputed_focus_value(item) for item in ordered]
        for item, value in zip(ordered, recomputed_focus):
            item["focus_input_status"] = "verified" if value is not None else "incomplete_or_invalid"
        focus_ready = same_focus_scope and all(
            item.get("pareto_status") == "frontier" and value is not None
            for item, value in zip(ordered, recomputed_focus)
        )
        if focus_ready:
            best_score = max(float(value) for value in recomputed_focus if value is not None)
            leaders = [
                item
                for item, value in zip(ordered, recomputed_focus)
                if value is not None and math.isclose(float(value), best_score)
            ]
            if len(leaders) == 1:
                chosen = leaders[0]
                basis = "focus"
            else:
                chosen = leaders[0]
                basis = "stable_tie_break"
        else:
            chosen = ordered[0]
            basis = "route_default"
    chosen["selection_status"] = "selected"
    return {
        "selected_id": chosen.get("candidate_step_id"),
        "selected_concept_id": chosen.get("concept_id"),
        "selection_basis": basis,
        "scope_status": "matched",
        "user_cost_priority": declared_priorities[0] if priority_status == "applied" else None,
        "user_cost_priority_status": priority_status,
        "needs_measurement": priority_unresolved,
        "candidates": evaluated,
    }


def manifest_candidate(path: Path) -> Path | None:
    resolved = path.resolve()
    if resolved.is_file():
        resolved = resolved.parent
    if (resolved / MANIFEST_REL).is_file():
        return resolved
    marker = resolved / ROUTE_FILE
    if marker.is_file():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            manifest = resolved / data.get("manifest", "")
            if manifest.is_file():
                return resolved
        except (OSError, json.JSONDecodeError, TypeError):
            return None
    return None


def upward_candidates(start: Path) -> list[Path]:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    results: list[Path] = []
    while True:
        candidate = manifest_candidate(current)
        if candidate:
            results.append(candidate)
        if current.parent == current:
            break
        current = current.parent
    return results


def bounded_candidates(start: Path, max_depth: int) -> list[Path]:
    root = start.resolve()
    if root.is_file():
        root = root.parent
    results: list[Path] = []
    if not root.is_dir():
        return results
    for current, dirs, _files in os.walk(root):
        current_path = Path(current)
        try:
            depth = len(current_path.relative_to(root).parts)
        except ValueError:
            continue
        dirs[:] = [item for item in dirs if item not in SKIP_DIRS and not item.startswith(".")]
        if depth >= max_depth:
            dirs[:] = []
        candidate = manifest_candidate(current_path)
        if candidate:
            results.append(candidate)
            dirs[:] = []
    return results


def recover_route(start: Path, max_depth: int, repair: bool) -> int:
    candidates = upward_candidates(start) + bounded_candidates(start, max_depth)
    unique = sorted({item.resolve() for item in candidates}, key=lambda item: str(item).lower())
    valid: list[dict[str, Any]] = []
    invalid: list[str] = []
    for vault in unique:
        try:
            manifest = json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))
            if manifest.get("schema") != SCHEMA:
                invalid.append(f"{vault} (schema 不匹配)")
                continue
            candidate_errors, candidate_warnings, _ = validate_vault(
                vault, allow_route_marker_issue=True
            )
            if candidate_errors:
                invalid.append(f"{vault} (校验失败: {'; '.join(candidate_errors)})")
                continue
            valid.append(
                {
                    "vault": str(vault),
                    "manifest": manifest,
                    "warnings": candidate_warnings,
                }
            )
        except (OSError, json.JSONDecodeError) as exc:
            invalid.append(f"{vault} ({exc})")

    if not valid:
        print(
            json_dump(
                {
                    "status": "not_found",
                    "searched_from": str(start.resolve()),
                    "max_depth": max_depth,
                    "invalid_candidates": invalid,
                    "next_action": "询问用户：从未创建，还是需要扩大范围继续找/明确重建？脚本未创建任何 Vault。",
                }
            ),
            end="",
        )
        return 4
    if len(valid) > 1:
        print(
            json_dump(
                {
                    "status": "multiple_matches",
                    "candidates": valid,
                    "next_action": "请用户选择精确 Vault；不要自动选最新项或合并。",
                }
            ),
            end="",
        )
        return 3

    selected = Path(valid[0]["vault"])
    marker = selected / ROUTE_FILE
    repaired = False
    if repair:
        with vault_transaction_lock(selected):
            write_route_marker(selected)
        repaired = True
    print(
        json_dump(
            {
                "status": "unique_match",
                "vault": str(selected),
                "vault_id": valid[0]["manifest"].get("vault_id"),
                "marker_present": marker.is_file(),
                "repaired": repaired,
                "warnings": valid[0].get("warnings", []),
                "next_action": "Vault 入口已定位；学习路线另用 recover-learning-route 检查，不能把入口恢复当作原路线恢复。",
            }
        ),
        end="",
    )
    return 0


def derive_process_adaptation(
    evidence_records: list[tuple[str, dict[str, Any]]]
) -> dict[str, Any]:
    """Turn canonical teaching-process evidence into feedback and cost state.

    This channel never grants mastery or efficacy preference. It only changes
    the immediate repair/escalation action and exposes measured practice cost
    for the next route comparison.
    """

    records = [
        (evidence_id, meta)
        for evidence_id, meta in evidence_records
        if meta.get("phase") == "teaching_process"
        and meta.get("observation_validity") == "valid"
        and meta.get("observation_confidence") in {"medium", "high"}
    ]
    records.sort(
        key=lambda item: (
            parse_iso_instant(item[1].get("observed_at")),
            item[0],
        )
    )
    elapsed = [
        float(meta["elapsed_seconds"])
        for _evidence_id, meta in records
        if isinstance(meta.get("elapsed_seconds"), (int, float))
        and not isinstance(meta.get("elapsed_seconds"), bool)
    ]
    attempts = [
        int(meta["attempts"])
        for _evidence_id, meta in records
        if isinstance(meta.get("attempts"), int)
        and not isinstance(meta.get("attempts"), bool)
    ]
    hints = [
        int(meta["hint_count"])
        for _evidence_id, meta in records
        if isinstance(meta.get("hint_count"), int)
        and not isinstance(meta.get("hint_count"), bool)
    ]
    efforts = [
        float(meta["self_reported_effort"])
        for _evidence_id, meta in records
        if isinstance(meta.get("self_reported_effort"), (int, float))
        and not isinstance(meta.get("self_reported_effort"), bool)
    ]
    cost_summary = {
        "practice_feedback_seconds": round(sum(elapsed), 3),
        "practice_feedback_minutes": round(sum(elapsed) / 60.0, 3),
        "total_attempts": sum(attempts),
        "total_hint_count": sum(hints),
        "mean_self_reported_effort": (
            round(sum(efforts) / len(efforts), 3) if efforts else None
        ),
    }
    assistance_order = {"A0": 0, "A1": 1, "A2": 2, "A3": 3, "A4": 4}
    observed_assistance = [
        str(meta.get("assistance_level"))
        for _evidence_id, meta in records
        if meta.get("assistance_level") in assistance_order
    ]
    max_observed_assistance_level = (
        max(observed_assistance, key=lambda item: assistance_order[item])
        if observed_assistance
        else None
    )
    latest_immediate_performance = (
        records[-1][1].get("immediate_performance") if records else None
    )
    high_support_load = bool(
        records
        and (
            cost_summary["total_attempts"] > len(records)
            or cost_summary["total_hint_count"] > 0
            or (
                isinstance(cost_summary["mean_self_reported_effort"], (int, float))
                and cost_summary["mean_self_reported_effort"] >= 5
            )
            or (
                isinstance(latest_immediate_performance, (int, float))
                and not isinstance(latest_immediate_performance, bool)
                and latest_immediate_performance < 0.5
            )
        )
    )
    base = {
        "schema": "uc-process-adaptation/0.1",
        "source_evidence_ids": [evidence_id for evidence_id, _meta in records],
        "consumer_ids": [
            "feedback_selection",
            "activity_selection",
            "representation_selection",
        ],
        "cost_summary": cost_summary,
        "latest_teaching_item_id": (
            records[-1][1].get("teaching_item_id") if records else None
        ),
        "max_observed_assistance_level": max_observed_assistance_level,
        "support_load_status": (
            "high" if high_support_load else "normal" if records else "not_measured"
        ),
    }
    if not records:
        return {
            **base,
            "status": "no_process_evidence",
            "latest_evidence_id": None,
            "latest_activity": None,
            "latest_error_signature": None,
            "same_error_count": 0,
            "text_variants_tried": 0,
            "feedback_rule": "collect_first_process_response",
            "next_action": "collect_process_evidence",
        }

    latest_id, latest = records[-1]

    def successful(meta: dict[str, Any]) -> bool:
        demonstrates = meta.get("demonstrates")
        return bool(
            meta.get("result") == "pass"
            and meta.get("response_correct") is True
            and meta.get("explanation_quality") == "pass"
            and isinstance(demonstrates, list)
            and "explanation" in demonstrates
        )

    def unsuccessful(meta: dict[str, Any]) -> bool:
        # Fail closed: partial, not_tested and incomplete explanation are all
        # repair states.  Merely avoiding an explicit `fail` is not readiness.
        return not successful(meta)

    latest_failed = unsuccessful(latest)
    latest_signature = (
        str(latest.get("error_signature")).strip()
        if latest_failed
        and isinstance(latest.get("error_signature"), str)
        and str(latest.get("error_signature")).strip()
        else None
    )
    streak: list[tuple[str, dict[str, Any]]] = []
    if latest_failed:
        for item in reversed(records):
            meta = item[1]
            if not unsuccessful(meta):
                break
            signature = meta.get("error_signature")
            if latest_signature is None:
                if item[0] != latest_id:
                    break
            elif signature != latest_signature:
                break
            streak.append(item)
    same_error_count = len(streak)
    variants = {
        str(meta.get("activity"))
        for _evidence_id, meta in streak
        if meta.get("carrier")
        in {"text_document", "text_dialogue", "text_hybrid"}
        if isinstance(meta.get("activity"), str) and str(meta.get("activity")).strip()
    }
    if not latest_failed:
        status = "ready_for_verification"
        feedback_rule = "confirm_then_open_unseen_verification"
        next_action = "open_unseen_verification"
    elif same_error_count >= 2 and len(variants) >= 2:
        status = "escalation_candidate"
        feedback_rule = "evaluate_text_failure_escalation_gate"
        next_action = "evaluate_escalation_gate"
    else:
        status = "repair_required"
        if high_support_load:
            feedback_rule = "reduce_information_then_correct_current_error"
            next_action = "shorter_text_repair"
        else:
            feedback_rule = "correct_only_current_error_then_retry"
            next_action = "text_repair"
    return {
        **base,
        "status": status,
        "latest_evidence_id": latest_id,
        "latest_activity": latest.get("activity"),
        "latest_error_signature": latest_signature,
        "same_error_count": same_error_count,
        "text_variants_tried": len(variants),
        "feedback_rule": feedback_rule,
        "next_action": next_action,
    }


@vault_transaction_writer
def resolve_active_teaching(
    vault: Path,
    *,
    write: bool = True,
    _preserve_decision_epoch: bool = False,
    _skip_validation: bool = False,
    _include_internal: bool = False,
    _as_of: str | None = None,
) -> dict[str, Any]:
    """Resolve the text policy into one issued, capable active resource.

    This is the production bridge between the response-profile calculation and
    the route actually consumed by recovery/Cone inspection.  A decision that
    has no uniquely compatible issued resource is rejected rather than written
    onto an unrelated teaching asset.
    """

    if write and _as_of is not None:
        raise VaultError("生产教学决策禁止调用者回拨 as_of；历史时间只用于只读重算")
    decision_as_of = _as_of or utc_now_precise()
    try:
        decision_instant = parse_iso_instant(decision_as_of)
    except (TypeError, ValueError) as exc:
        raise VaultError("教学决策 as_of 必须是带时区 ISO 时间") from exc
    if not _skip_validation:
        validation_errors, _warnings, _summary = validate_vault(
            vault, allow_unresolved_teaching=True
        )
        if validation_errors:
            raise VaultError("Vault 校验失败，不能解析教学决策:\n- " + "\n- ".join(validation_errors))
    index, index_errors = build_index(vault)
    if index_errors:
        raise VaultError("图谱存在错误，不能解析教学决策:\n- " + "\n- ".join(index_errors))
    manifest = json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))
    allow_synthetic_demo = trusted_synthetic_demo_authorized(vault, manifest)
    registry, _events, binding_errors = load_route_binding_registry(vault, manifest)
    if binding_errors:
        raise VaultError("route issuance 校验失败:\n- " + "\n- ".join(binding_errors))
    all_meta: dict[str, dict[str, Any]] = {}
    all_body: dict[str, str] = {}
    for node_id, node in index["nodes"].items():
        meta, body, _parse_errors = parse_note(vault / node["path"])
        all_meta[node_id] = meta
        all_body[node_id] = body

    active_routes = [
        (node_id, all_meta[node_id])
        for node_id, node in index["nodes"].items()
        if node["type"] == "intervention" and all_meta[node_id].get("status") == "active"
    ]
    active_learner_node_id = manifest.get("active_learner_id")
    learner_id = all_meta.get(str(active_learner_node_id), {}).get("learner_id")
    goal_id = manifest.get("active_goal_id")
    active_routes = [
        item
        for item in active_routes
        if item[1].get("learner_id") == learner_id and item[1].get("goal_id") == goal_id
    ]
    if len(active_routes) != 1:
        raise VaultError("必须有且只有一条当前 learner+goal 的 active intervention")
    intervention_id, intervention = active_routes[0]
    checkpoint = str(intervention.get("current_checkpoint"))
    state_entry = next(
        (
            (node_id, meta)
            for node_id, meta in all_meta.items()
            if meta.get("type") == "state"
            and meta.get("learner_id") == learner_id
            and meta.get("goal_id") == goal_id
            and meta.get("concept_id") == checkpoint
        ),
        None,
    )
    if state_entry is None:
        raise VaultError("active checkpoint 缺少同范围 state")
    _state_id, state = state_entry
    contract = next(
        (
            item
            for item in all_meta[str(goal_id)].get("mastery_contracts", [])
            if item.get("id") == state.get("contract_id")
            and item.get("version") == state.get("contract_version")
            and item.get("concept_id") == checkpoint
        ),
        None,
    )
    if not isinstance(contract, dict):
        raise VaultError("active checkpoint 的 mastery contract 无法解析")
    binding_key = (
        str(learner_id),
        str(goal_id),
        checkpoint,
        str(contract["id"]),
        int(contract["version"]),
        str(intervention.get("route_id")),
        int(intervention.get("route_version")),
    )
    current_issuance = registry.get(binding_key)
    if current_issuance is None:
        raise VaultError("active checkpoint 无有效 route issuance")
    current_context = dict(current_issuance["comparison_context"])
    issued_verification_task = current_issuance["issuance_snapshot"]["resources"][0][
        "verification_task"
    ]
    current_retention_required = bool(
        contract.get("requirements", {}).get("delayed_retention", {}).get("required") is True
    )

    contracts: dict[tuple[str, str, int], dict[str, Any]] = {}
    for node_id, meta in all_meta.items():
        if meta.get("type") != "goal":
            continue
        for item in meta.get("mastery_contracts", []):
            if isinstance(item, dict) and isinstance(item.get("version"), int):
                contracts[(node_id, str(item.get("id")), item["version"])] = item
    states: dict[tuple[str, str, str, str, int], dict[str, Any]] = {}
    state_windows: dict[tuple[str, str, str, str, int], list[str]] = {}
    for node_id, meta in all_meta.items():
        if meta.get("type") == "state" and isinstance(meta.get("contract_version"), int):
            scope = (
                str(meta.get("learner_id")),
                str(meta.get("goal_id")),
                str(meta.get("concept_id")),
                str(meta.get("contract_id")),
                meta["contract_version"],
            )
            states[scope] = meta
            state_windows[scope] = [
                str(relation["target"])
                for relation in index["nodes"][node_id].get("relations", [])
                if relation.get("type") == "supported_by"
            ]
    evidence_records = {
        node_id: meta for node_id, meta in all_meta.items() if meta.get("type") == "evidence"
    }
    current_scope = binding_key[:5]
    canonical_current_evidence = [
        (evidence_id, evidence_records[evidence_id])
        for evidence_id in state_windows.get(current_scope, [])
        if evidence_id in evidence_records
        and parse_iso_instant(evidence_records[evidence_id].get("observed_at"))
        <= decision_instant
    ]
    process_adaptation = derive_process_adaptation(canonical_current_evidence)
    policy = load_text_learning_policy()
    as_of = decision_as_of
    observations: list[dict[str, Any]] = []
    canonical_evidence_ids = sorted(
        {
            evidence_id
            for evidence_ids in state_windows.values()
            for evidence_id in evidence_ids
            if evidence_id in evidence_records
        }
    )
    for evidence_id in canonical_evidence_ids:
        evidence = evidence_records[evidence_id]
        if parse_iso_instant(evidence.get("observed_at")) > decision_instant:
            continue
        if evidence.get("phase") not in {"verification", "retention"}:
            # Diagnostic and teaching-process records have separate consumers;
            # they must never be adapted into method-efficacy observations.
            continue
        if evidence.get("learner_id") != learner_id:
            continue
        evidence_key = (
            str(evidence.get("learner_id")),
            str(evidence.get("goal_id")),
            str(evidence.get("concept_id")),
            str(evidence.get("contract_id")),
            evidence.get("contract_version") if isinstance(evidence.get("contract_version"), int) else -1,
            str(evidence.get("route_id_at_observation")),
            evidence.get("route_version_at_observation")
            if isinstance(evidence.get("route_version_at_observation"), int)
            else -1,
        )
        issuance = registry.get(evidence_key)
        if issuance is None or issuance.get("comparison_context") != current_context:
            continue
        own_contract = contracts.get(
            (
                str(evidence.get("goal_id")),
                str(evidence.get("contract_id")),
                int(evidence.get("contract_version")),
            )
        )
        if not isinstance(own_contract, dict):
            continue
        own_retention_required = bool(
            own_contract.get("requirements", {}).get("delayed_retention", {}).get("required")
            is True
        )
        if own_retention_required != current_retention_required:
            continue
        scope = (
            str(evidence.get("learner_id")),
            str(evidence.get("goal_id")),
            str(evidence.get("concept_id")),
            str(evidence.get("contract_id")),
            int(evidence.get("contract_version")),
        )
        scoped_evidence = [
            (other_id, evidence_records[other_id])
            for other_id in state_windows.get(scope, [])
            if other_id in evidence_records
            and parse_iso_instant(evidence_records[other_id].get("observed_at"))
            <= decision_instant
        ]
        observations.append(
            _adapt_profile_observation_from_validated_context(
                policy,
                evidence_id,
                evidence,
                own_contract,
                scoped_evidence,
                current_context,
                states.get(scope, {}),
                as_of=as_of,
                allow_trusted_synthetic_demo=allow_synthetic_demo,
            )
        )

    decision_inputs = intervention.get("teaching_decision_inputs", {})
    if not isinstance(decision_inputs, dict):
        raise VaultError("intervention teaching_decision_inputs 必须是对象")
    allowed_inputs = {
        "max_assistance_level",
        "introduced_terms",
        "static_visual_reason",
        "delivery_intent",
        "text_sufficiency",
        "hard_constraints",
        "forced_carrier",
        "prerequisite_gap",
        "matching_affordance",
        "matching_affordance_reason",
    }
    unknown_inputs = sorted(set(decision_inputs).difference(allowed_inputs))
    if unknown_inputs:
        raise VaultError("teaching_decision_inputs 含未允许字段: " + ",".join(unknown_inputs))
    response_profile_refs = sorted(
        observation["source"]["evidence_id"] for observation in observations
    )
    available_text_activities = sorted(
        {
            activity
            for resource_snapshot in current_issuance["issuance_snapshot"]["resources"]
            if resource_snapshot.get("carrier")
            in {"text_document", "text_dialogue", "text_hybrid"}
            for activity in resource_snapshot.get("supported_activities", [])
        }
    )
    available_text_activity_costs: dict[str, float] = {}
    for resource_snapshot in current_issuance["issuance_snapshot"]["resources"]:
        if resource_snapshot.get("carrier") not in {
            "text_document",
            "text_dialogue",
            "text_hybrid",
        }:
            continue
        duration = resource_snapshot.get("duration_minutes")
        if (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or duration < 0
        ):
            raise VaultError("已签发文字 resource 的 duration_minutes 非法")
        for supported_activity in resource_snapshot.get("supported_activities", []):
            previous = available_text_activity_costs.get(str(supported_activity))
            normalized_duration = float(duration)
            if previous is None or normalized_duration < previous:
                available_text_activity_costs[str(supported_activity)] = normalized_duration
    base_cost_vector = intervention.get("cost_vector")
    if not isinstance(base_cost_vector, dict) or set(base_cost_vector) != {
        "diagnosis",
        "prerequisites",
        "core_learning",
        "practice_feedback",
        "verification",
        "maintenance_relearning",
    }:
        raise VaultError("intervention cost_vector 必须是对象")
    if _complete_cost_vector({"cost_vector": base_cost_vector}) is None:
        raise VaultError("intervention cost_vector 必须是完整非负数值向量")
    decision_context = {
        "learner_id": learner_id,
        "goal_id": goal_id,
        "concept_id": checkpoint,
        "contract_id": contract["id"],
        "contract_version": contract["version"],
        "route_id": intervention["route_id"],
        "route_version": intervention["route_version"],
        "bound_verification_task_id": current_issuance["verification_task_id"],
        "verification_content_guard": policy.build_verification_content_guard(
            current_issuance["verification_task_id"],
            issued_verification_task["prompt"],
            issued_verification_task["protected_answers"],
        ),
        "evidence_refs": response_profile_refs,
        "domain": current_context["domain"],
        "knowledge_kind": current_context["knowledge_kind"],
        "target_performance": current_context["target_performance"],
        "prior_knowledge_band": current_context["prior_band"],
        "task_difficulty": current_context["task_difficulty"],
        "comparison_gate": {
            "retention_required": current_retention_required,
            "task_difficulty": current_context["task_difficulty"],
        },
        "context_key": current_issuance["context_key"],
        "response_profile_refs": response_profile_refs,
        "response_profile_observations": observations,
        **decision_inputs,
        "same_error_count": process_adaptation["same_error_count"],
        "text_variants_tried": process_adaptation["text_variants_tried"],
        "last_process_activity": process_adaptation["latest_activity"],
        "available_text_activities": available_text_activities,
        "available_text_activity_costs": available_text_activity_costs,
        "estimated_practice_feedback_minutes": float(
            base_cost_vector["practice_feedback"]
        ),
        "process_adaptation": process_adaptation,
    }
    try:
        decision = policy.decide_text_activity(decision_context)
    except Exception as exc:
        if exc.__class__.__name__ == "TextPolicyError":
            raise VaultError(f"文字教学决策失败: {exc}") from exc
        raise
    if decision.get("selection_status") in {"blocked", "escalation_required"}:
        raise VaultError(
            f"当前 Demo 没有可直接落盘的文字教学决策: {decision.get('selection_status')}"
        )
    issued_resource_ids = {
        item["id"] for item in current_issuance["issuance_snapshot"]["resources"]
    }
    used_resource_ids = {
        relation["target"]
        for relation in index["nodes"][intervention_id]["relations"]
        if relation.get("type") == "uses"
    }
    compatible: list[tuple[str, dict[str, Any]]] = []
    for resource_id in sorted(issued_resource_ids.intersection(used_resource_ids)):
        resource = all_meta.get(resource_id, {})
        taught = {
            relation["target"]
            for relation in index.get("nodes", {}).get(resource_id, {}).get("relations", [])
            if relation.get("type") == "teaches"
        }
        task = resource.get("verification_task")
        if (
            decision.get("activity") in resource.get("supported_activities", [])
            and decision.get("carrier") == resource.get("carrier")
            and checkpoint in taught
            and isinstance(task, dict)
            and task.get("id") == current_issuance.get("verification_task_id")
        ):
            compatible.append((resource_id, resource))
    if len(compatible) != 1:
        raise VaultError(
            "教学决策必须唯一解析到已签发且真实支持 activity/carrier/task 的 resource; "
            f"activity={decision.get('activity')} carrier={decision.get('carrier')} matches={len(compatible)}"
        )
    resource_id, resource = compatible[0]
    profile_selection = decision.get("profile_selection", {})
    selected_option = profile_selection.get("selected_option")
    consumed_profile_refs = (
        list(selected_option.get("observation_refs", []))
        if isinstance(selected_option, dict)
        and (
            decision.get("profile_usage_status") in {"activity_only", "activity_and_carrier"}
            or decision.get("repair_selection_basis") == "profile_alternative"
        )
        else []
    )
    resolved_cost_vector = dict(base_cost_vector)
    if process_adaptation["source_evidence_ids"]:
        resolved_cost_vector["practice_feedback"] = process_adaptation["cost_summary"][
            "practice_feedback_minutes"
        ]
        resolved_cost_basis = "measured_process_evidence"
    else:
        resolved_cost_basis = "route_estimate_no_process_measurement"
    resolved_at = decision_as_of
    resolution = {
        "teaching_resolution_schema": TEACHING_RESOLUTION_SCHEMA,
        "resolved_activity": decision["activity"],
        "resolved_carrier": decision["carrier"],
        "resolved_resource_id": resource_id,
        "resolved_profile_refs": consumed_profile_refs,
        "resolved_profile_level": profile_selection.get("evidence_level", "unknown"),
        "resolved_profile_usage": decision.get("profile_usage_status"),
        "resolved_process_refs": list(process_adaptation["source_evidence_ids"]),
        "resolved_process_status": process_adaptation["status"],
        "resolved_process_feedback_rule": process_adaptation["feedback_rule"],
        "resolved_process_next_action": process_adaptation["next_action"],
        "resolved_process_cost": dict(process_adaptation["cost_summary"]),
        "resolved_process_cost_selection": dict(decision["process_cost_selection"]),
        "resolved_cost_vector": resolved_cost_vector,
        "resolved_cost_basis": resolved_cost_basis,
        "resolved_same_error_count": process_adaptation["same_error_count"],
        "resolved_text_variants_tried": process_adaptation["text_variants_tried"],
        "resolved_latest_teaching_item_id": process_adaptation[
            "latest_teaching_item_id"
        ],
        "resolved_max_observed_assistance_level": process_adaptation[
            "max_observed_assistance_level"
        ],
        "resolved_process_support_load": process_adaptation[
            "support_load_status"
        ],
        "resolved_route_binding_id": current_issuance["binding_id"],
        "resolved_context_key": current_issuance["context_key"],
        "resolved_at": resolved_at,
        "process_refreshed_at": resolved_at,
        "resolved_decision_fingerprint": sha256_fingerprint(
            {"decision": decision, "resolved_at": resolved_at}
        ),
    }
    result = {
        "status": "resolved",
        "intervention_id": intervention_id,
        **resolution,
        "current_activity_id": resource_id,
        "current_probe_id": resource["diagnostic_probe"]["id"],
        "current_verification_task_id": resource["verification_task"]["id"],
        "carrier": resource["carrier"],
        "adaptation_confidence": resolution["resolved_profile_level"],
        "profile_selection_status": decision.get("profile_selection_status"),
    }
    if write:
        updated = dict(intervention)
        if _preserve_decision_epoch:
            if (
                not isinstance(intervention.get("resolved_at"), str)
                or not isinstance(
                    intervention.get("resolved_decision_fingerprint"), str
                )
            ):
                raise VaultError("过程刷新要求已有可验证的教学决策 epoch")
            for field in PROCESS_REFRESH_FIELDS:
                updated[field] = resolution[field]
            updated["process_refreshed_at"] = decision_as_of
            # The already delivered teaching item remains bound to the prior
            # decision epoch.  Process feedback/cost is refreshed, while a new
            # activity epoch still requires the explicit resolve/issue pair.
            result.update(
                {
                    "status": "process_refreshed",
                    "resolved_at": intervention["resolved_at"],
                    "process_refreshed_at": decision_as_of,
                    "resolved_decision_fingerprint": intervention[
                        "resolved_decision_fingerprint"
                    ],
                    "current_activity_id": intervention["current_activity_id"],
                    "current_probe_id": intervention["current_probe_id"],
                    "current_verification_task_id": intervention[
                        "current_verification_task_id"
                    ],
                    "carrier": intervention["carrier"],
                    "adaptation_confidence": intervention[
                        "adaptation_confidence"
                    ],
                }
            )
        else:
            updated.update(resolution)
            updated["current_activity_id"] = resource_id
            updated["current_probe_id"] = resource["diagnostic_probe"]["id"]
            updated["current_verification_task_id"] = resource[
                "verification_task"
            ]["id"]
            updated["carrier"] = resource["carrier"]
            updated["adaptation_confidence"] = resolution[
                "resolved_profile_level"
            ]
        updated["updated_at"] = resolved_at
        replace_note_meta(
            vault / index["nodes"][intervention_id]["path"],
            updated,
            all_body[intervention_id],
        )
        rebuilt_index, rebuilt_errors = rebuild_index(vault)
        if rebuilt_errors:
            raise VaultError("教学决策落盘后索引重建失败: " + "; ".join(rebuilt_errors))
        result["node_count"] = rebuilt_index["node_count"]
    if _include_internal:
        result["_decision"] = decision
    return result


@vault_transaction_writer
def issue_teaching_delivery(vault: Path, *, content_path: Path) -> dict[str, Any]:
    """Project, persist and return one real user-visible teaching item.

    The append-only delivery note is the bridge between a resolved method and a
    later learner response.  Process evidence cannot invent a teaching item ID;
    it must cite this exact projection and fingerprint.
    """

    errors, _warnings, _summary = validate_vault(vault)
    if errors:
        raise VaultError(
            "Vault 校验失败，不能签发教学内容:\n- " + "\n- ".join(errors)
        )
    try:
        content = json.loads(content_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VaultError(f"教学内容 JSON 无法读取: {exc}") from exc
    if not isinstance(content, dict):
        raise VaultError("教学内容 JSON 顶层必须是对象")
    index, index_errors = build_index(vault)
    if index_errors:
        raise VaultError("图谱存在错误，不能签发教学内容: " + "; ".join(index_errors))
    manifest = json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))
    active_interventions: list[tuple[str, dict[str, Any]]] = []
    for node_id, node in index.get("nodes", {}).items():
        if node.get("type") != "intervention":
            continue
        meta, _body, parse_errors = parse_note(vault / node["path"])
        if parse_errors:
            raise VaultError("intervention 无法解析: " + "; ".join(parse_errors))
        if meta.get("status") == "active" and meta.get("goal_id") == manifest.get(
            "active_goal_id"
        ):
            active_interventions.append((node_id, meta))
    if len(active_interventions) != 1:
        raise VaultError("必须有且只有一个当前 active intervention 才能签发教学")
    intervention_id, intervention = active_interventions[0]
    resolution = resolve_active_teaching(
        vault,
        write=False,
        _skip_validation=True,
        _include_internal=True,
        _as_of=intervention.get("resolved_at"),
    )
    decision = resolution.pop("_decision")
    policy = load_text_learning_policy()
    try:
        delivery_plan = policy.project_delivery_plan(decision, content)
    except Exception as exc:
        if exc.__class__.__name__ == "TextPolicyError":
            raise VaultError(f"教学内容未通过用户投影协议: {exc}") from exc
        raise
    issued_instant = datetime.now(timezone.utc)
    resolved_instant = parse_iso_instant(intervention.get("resolved_at"))
    if issued_instant <= resolved_instant:
        raise VaultError(
            "真实 wall clock 尚未晚于教学决策 resolved_at；拒绝制造未来签发时间，请立即重试"
        )
    issued_at = issued_instant.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    delivery_fingerprint = sha256_fingerprint(delivery_plan)
    teaching_item_id = "td-" + sha256_fingerprint(
        {
            "decision_fingerprint": resolution["resolved_decision_fingerprint"],
            "delivery_plan_fingerprint": delivery_fingerprint,
            "issued_at": issued_at,
        }
    )[:24]
    if teaching_item_id in index.get("nodes", {}):
        raise VaultError("同一教学签发记录已存在；不得覆盖追加记录")
    scope = decision.get("scope", {})
    learner_node_id = str(manifest.get("active_learner_id"))
    delivery_meta = {
        "schema": SCHEMA,
        "delivery_contract": TEACHING_DELIVERY_SCHEMA,
        "id": teaching_item_id,
        "type": "teaching_delivery",
        "title": f"教学签发：{scope.get('concept_id')}",
        "learner_id": scope.get("learner_id"),
        "goal_id": scope.get("goal_id"),
        "concept_id": scope.get("concept_id"),
        "contract_id": scope.get("contract_id"),
        "contract_version": scope.get("contract_version"),
        "route_id": decision.get("route_id"),
        "route_version": decision.get("route_version"),
        "route_binding_id": resolution["resolved_route_binding_id"],
        "context_key": resolution["resolved_context_key"],
        "decision_fingerprint": resolution["resolved_decision_fingerprint"],
        "resource_id": resolution["resolved_resource_id"],
        "activity": resolution["resolved_activity"],
        "carrier": resolution["resolved_carrier"],
        "delivery_plan": delivery_plan,
        "delivery_plan_fingerprint": delivery_fingerprint,
        "issued_at": issued_at,
        "source_kind": "agent_projection",
        "source_ref_ids": [str(content_path.resolve())],
        "created_at": issued_at,
        "updated_at": issued_at,
        "privacy": "sensitive",
        "tags": ["uc/teaching-delivery", "uc/append-only"],
    }
    body = (
        "# 已发行教学项\n\n"
        "> 追加记录：保存实际用户白名单投影及其指纹；过程作答必须引用本记录。\n\n"
        + relation_lines(
            [
                {"type": "for_learner", "target": learner_node_id},
                {"type": "for_goal", "target": str(scope.get("goal_id"))},
                {"type": "about", "target": str(scope.get("concept_id"))},
                {"type": "uses", "target": resolution["resolved_resource_id"]},
            ]
        )
    )
    delivery_path = vault / "30-learning" / "deliveries" / f"{teaching_item_id}.md"
    write_note(vault, delivery_path.relative_to(vault), delivery_meta, body)
    rebuilt, rebuilt_errors = rebuild_index(vault)
    if rebuilt_errors:
        delivery_path.unlink(missing_ok=True)
        rebuild_index(vault)
        raise VaultError(
            "教学签发写入后图谱校验失败，已回滚新记录: "
            + "; ".join(rebuilt_errors)
        )
    post_errors, _post_warnings, _post_summary = validate_vault(vault)
    if post_errors:
        delivery_path.unlink(missing_ok=True)
        rebuild_index(vault)
        raise VaultError(
            "教学签发未通过完整校验，已回滚新记录: "
            + "; ".join(post_errors)
        )
    return {
        "status": "issued",
        "teaching_item_id": teaching_item_id,
        "teaching_delivery_fingerprint": delivery_fingerprint,
        "issued_at": issued_at,
        "delivery_plan": delivery_plan,
        "process_binding": {
            "teaching_item_id": teaching_item_id,
            "teaching_delivery_fingerprint_at_observation": delivery_fingerprint,
            "verification_task_id": decision["bound_verification_task_id"],
            "bound_verification_task_id": decision[
                "bound_verification_task_id"
            ],
            "decision_fingerprint_at_observation": resolution[
                "resolved_decision_fingerprint"
            ],
            "route_id_at_observation": decision["route_id"],
            "route_version_at_observation": decision["route_version"],
            "route_binding_id": resolution["resolved_route_binding_id"],
            "context_key": resolution["resolved_context_key"],
            "activity": resolution["resolved_activity"],
            "carrier": resolution["resolved_carrier"],
        },
        "node_count": rebuilt["node_count"],
    }


def _append_relation(body: str, relation_type: str, target: str) -> str:
    relation = f"- {relation_type}: [[{target}]]"
    if relation in body.splitlines():
        raise VaultError(f"关系已存在，拒绝重复追加: {relation_type} -> {target}")
    return body.rstrip() + "\n" + relation + "\n"


def _restore_file_images(images: dict[Path, bytes | None]) -> list[str]:
    errors: list[str] = []
    for path, previous in images.items():
        try:
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write_bytes(path, previous)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    return errors


def _read_exact_json_record(
    record_path: Path,
    *,
    fields: set[str],
    label: str,
    optional_fields: set[str] | None = None,
) -> dict[str, Any]:
    try:
        value = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VaultError(f"{label} JSON 无法读取: {exc}") from exc
    optional = optional_fields or set()
    allowed = fields | optional
    if (
        not isinstance(value, dict)
        or not fields.issubset(value)
        or not set(value).issubset(allowed)
    ):
        missing = sorted(fields.difference(value if isinstance(value, dict) else {}))
        unknown = sorted(
            set(value).difference(allowed) if isinstance(value, dict) else set()
        )
        raise VaultError(
            f"{label} 顶层字段合同不一致"
            + (f"; missing={','.join(missing)}" if missing else "")
            + (f"; unknown={','.join(unknown)}" if unknown else "")
        )
    return value


def _replace_relation_targets(body: str, relation_type: str, targets: list[str]) -> str:
    prefix = f"- {relation_type}: [["
    lines = [line for line in body.rstrip().splitlines() if not line.startswith(prefix)]
    lines.extend(f"- {relation_type}: [[{target}]]" for target in targets)
    return "\n".join(lines).rstrip() + "\n"


def retention_teaching_item_id(
    route_binding_id: str, retention_task_id: str, scheduled_for: str
) -> str:
    """Derive the canonical learner-visible delayed-task issuance identity."""

    return "retention-item-" + sha256_fingerprint(
        {
            "route_binding_id": route_binding_id,
            "retention_task_id": retention_task_id,
            "scheduled_for": scheduled_for,
        }
    )[:24]


RETENTION_SCOPE_FIELDS = (
    "learner_id",
    "goal_id",
    "concept_id",
    "contract_id",
    "contract_version",
)
RETENTION_SCHEDULE_METADATA_FIELDS = frozenset(
    {
        "schema",
        "schedule_contract",
        "id",
        "type",
        "title",
        *RETENTION_SCOPE_FIELDS,
        "baseline_evidence_id",
        "retention_task_id",
        "route_binding_id",
        "route_id",
        "route_version",
        "context_key",
        "verification_task_fingerprint",
        "not_before",
        "scheduled_for",
        "supersedes_schedule_id",
        "scheduled_at",
        "immutable",
        "created_at",
        "updated_at",
        "privacy",
        "tags",
        "receipt_fingerprint",
    }
)
VERIFICATION_OPEN_METADATA_FIELDS = frozenset(
    {
        "schema",
        "open_contract",
        "id",
        "type",
        "title",
        *RETENTION_SCOPE_FIELDS,
        "retention_schedule_id",
        "baseline_evidence_id",
        "retention_task_id",
        "route_binding_id",
        "route_id",
        "route_version",
        "context_key",
        "verification_task_fingerprint",
        "schedule_fingerprint",
        "resource_id",
        "activity",
        "carrier",
        "scheduled_for",
        "opened_at",
        "immutable",
        "created_at",
        "updated_at",
        "privacy",
        "tags",
        "receipt_fingerprint",
    }
)


def _receipt_fingerprint_payload(
    receipt: dict[str, Any], allowed_fields: frozenset[str]
) -> dict[str, Any]:
    return {
        field: receipt.get(field)
        for field in sorted(allowed_fields.difference({"receipt_fingerprint"}))
    }


def _canonical_retention_schedule_relations(
    schedule: dict[str, Any], learner_node_id: str
) -> list[dict[str, str]]:
    relations = [
        {"type": "for_learner", "target": learner_node_id},
        {"type": "for_goal", "target": str(schedule.get("goal_id"))},
        {"type": "about", "target": str(schedule.get("concept_id"))},
        {"type": "derived_from", "target": str(schedule.get("baseline_evidence_id"))},
    ]
    if schedule.get("supersedes_schedule_id") is not None:
        relations.append(
            {
                "type": "supersedes",
                "target": str(schedule.get("supersedes_schedule_id")),
            }
        )
    return relations


def _canonical_retention_schedule_body(
    schedule: dict[str, Any], learner_node_id: str
) -> str:
    return (
        "# 延迟验证排期回执\n\n"
        "> 追加记录：保存排期时实际消费的 baseline 与 retention route binding。\n\n"
        + relation_lines(
            _canonical_retention_schedule_relations(schedule, learner_node_id)
        )
    )


def _canonical_verification_open_relations(
    opened: dict[str, Any], learner_node_id: str
) -> list[dict[str, str]]:
    return [
        {"type": "for_learner", "target": learner_node_id},
        {"type": "for_goal", "target": str(opened.get("goal_id"))},
        {"type": "about", "target": str(opened.get("concept_id"))},
        {
            "type": "scheduled_by",
            "target": str(opened.get("retention_schedule_id")),
        },
        {"type": "uses", "target": str(opened.get("resource_id"))},
    ]


def _canonical_verification_open_body(
    opened: dict[str, Any], learner_node_id: str
) -> str:
    return (
        "# 延迟验证开题回执\n\n"
        "> 追加记录：只保存开题身份和绑定，不保存题面或 protected answers。\n\n"
        + relation_lines(_canonical_verification_open_relations(opened, learner_node_id))
    )


def _stored_note_body(canonical_body: str) -> str:
    return canonical_body.rstrip() + "\n"


def _trusted_seed_route_prefix_length(manifest: dict[str, Any]) -> int:
    """Return the externally anchored legacy prefix length, or zero.

    The caller still has to validate the seed authority.  This helper only
    identifies which historical events are eligible for the narrow
    no-route_purpose compatibility rule.
    """

    if (
        manifest.get("reconstruction_status") != "synthetic_demo"
        or manifest.get("seed_source") != "assets/demo-seed.json"
        or manifest.get("route_trust_level")
        not in {"trusted_seed_source", "trusted_seed_prefix_local_extension"}
    ):
        return 0
    try:
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        bindings = seed.get("route_bindings")
        return len(bindings) if isinstance(bindings, list) else 0
    except (OSError, json.JSONDecodeError):
        return 0


def _is_legacy_trusted_seed_route_event(
    event: dict[str, Any], manifest: dict[str, Any]
) -> bool:
    sequence = event.get("sequence")
    prefix_length = _trusted_seed_route_prefix_length(manifest)
    return bool(
        isinstance(sequence, int)
        and not isinstance(sequence, bool)
        and 1 <= sequence <= prefix_length
        and event.get("route_purpose") is None
    )


def _schedule_fingerprint_payload(schedule: dict[str, Any]) -> dict[str, Any]:
    return _receipt_fingerprint_payload(
        schedule, RETENTION_SCHEDULE_METADATA_FIELDS
    )


def retention_schedule_id(
    *, route_binding_id: str, baseline_evidence_id: str, scheduled_for: str
) -> str:
    return "retention-schedule-" + sha256_fingerprint(
        {
            "route_binding_id": route_binding_id,
            "baseline_evidence_id": baseline_evidence_id,
            "scheduled_for": scheduled_for,
        }
    )[:24]


def verification_open_id(schedule_id: str) -> str:
    return "verification-open-" + sha256_fingerprint(
        {"retention_schedule_id": schedule_id}
    )[:24]


def _open_fingerprint_payload(open_receipt: dict[str, Any]) -> dict[str, Any]:
    return _receipt_fingerprint_payload(
        open_receipt, VERIFICATION_OPEN_METADATA_FIELDS
    )


def state_context_with_current_schedule(
    state: dict[str, Any], all_meta: dict[str, dict[str, Any]], *, strict: bool = False
) -> dict[str, Any]:
    """Resolve the current schedule receipt into an ephemeral evaluation view."""

    context = dict(state)
    schedule_id = state.get("current_retention_schedule_id")
    if schedule_id in (None, ""):
        return context
    schedule = all_meta.get(str(schedule_id), {})
    if schedule.get("type") != "retention_schedule":
        if strict:
            raise VaultError(
                f"state.current_retention_schedule_id 无法解析: {schedule_id}"
            )
        return context
    context.update(
        {
            "baseline_evidence_id": schedule.get("baseline_evidence_id"),
            "retention_task_id": schedule.get("retention_task_id"),
            "retention_route_binding_id": schedule.get("route_binding_id"),
            "scheduled_for": schedule.get("scheduled_for"),
        }
    )
    return context


def _qualified_verification_baseline(
    baseline: dict[str, Any],
    state: dict[str, Any],
    *,
    allow_synthetic_demo: bool,
) -> bool:
    eligible, _failures = evidence_mastery_eligibility(
        baseline, allow_synthetic_demo=allow_synthetic_demo
    )
    return bool(
        baseline.get("type") == "evidence"
        and baseline.get("phase") == "verification"
        and baseline.get("result") == "pass"
        and eligible
        and all(baseline.get(field) == state.get(field) for field in RETENTION_SCOPE_FIELDS)
    )


def _latest_adverse_retention_instant(
    records: Iterable[tuple[str, dict[str, Any]]]
) -> datetime | None:
    instants: list[datetime] = []
    for _evidence_id, evidence in records:
        if evidence.get("phase") != "retention" or evidence.get("result") not in {
            "fail",
            "partial",
            "conflicted",
        }:
            continue
        try:
            instants.append(parse_iso_instant(evidence.get("observed_at")))
        except (TypeError, ValueError):
            continue
    return max(instants, default=None)


def _route_target_performance(contract: dict[str, Any]) -> str:
    capabilities = set(
        contract.get("requirements", {}).get("required_capabilities", [])
    )
    for target, names in (
        ("diagnose", {"diagnosis"}),
        ("transfer", {"transfer", "near_transfer", "delayed_retention"}),
        ("predict", {"prediction", "trace_prediction"}),
        ("discriminate", {"discrimination"}),
        (
            "execute",
            {"application", "independent_application", "error_correction"},
        ),
        ("explain", {"explanation", "boundary_explanation"}),
    ):
        if capabilities.intersection(names):
            return target
    return "recall"


def _route_comparison_context(
    *,
    index: dict[str, Any],
    all_meta: dict[str, dict[str, Any]],
    concept_id: str,
    state: dict[str, Any],
    contract: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, str]:
    concept = all_meta.get(concept_id, {})
    domain_id = next(
        (
            str(relation.get("target"))
            for relation in index.get("nodes", {}).get(concept_id, {}).get(
                "relations", []
            )
            if relation.get("type") == "part_of"
            and index.get("nodes", {}).get(str(relation.get("target")), {}).get(
                "type"
            )
            == "domain"
        ),
        str(manifest.get("active_domain_id") or "domain-general"),
    )
    domain_meta = all_meta.get(domain_id, {})
    domain = None
    for tag in domain_meta.get("tags", []):
        if isinstance(tag, str) and "/domain/" in tag:
            domain = tag.rsplit("/domain/", 1)[-1]
            break
        if isinstance(tag, str) and tag.startswith("domain/"):
            domain = tag.split("/", 1)[-1]
            break
    if not domain:
        raw_domain = domain_id.removeprefix("domain-")
        domain = raw_domain.split("-", 1)[0] or "general"
    difficulty = str(concept.get("difficulty", "intermediate"))
    task_difficulty = {
        "introductory": "low",
        "beginner": "low",
        "intermediate": "medium",
        "advanced": "high",
    }.get(difficulty, "medium")
    return canonical_comparison_context(
        {
            "domain": domain,
            "knowledge_kind": concept.get("knowledge_kind"),
            "target_performance": _route_target_performance(contract),
            "prior_band": state.get("mastery"),
            "task_difficulty": task_difficulty,
        },
        label="derived route comparison_context",
    )


@vault_transaction_writer
def issue_route(vault: Path, *, record_path: Path) -> dict[str, Any]:
    """Append one canonical route issuance from a validated raw selection record."""

    errors, _warnings, _summary = validate_vault(vault)
    if errors:
        raise VaultError("Vault 校验失败，不能签发路线:\n- " + "\n- ".join(errors))
    record = _read_exact_json_record(
        record_path,
        fields={
            "purpose",
            "concept_id",
            "resource_id",
            "baseline_evidence_id",
            "source_ref_ids",
            "expected_chain_head",
            "user_cost_priority",
        },
        label="issue-route record",
    )
    purpose = record.get("purpose")
    if purpose not in {"learning", "retention"}:
        raise VaultError("issue-route purpose 只能是 learning 或 retention")
    concept_id = record.get("concept_id")
    resource_id = record.get("resource_id")
    if not isinstance(concept_id, str) or not concept_id.strip():
        raise VaultError("issue-route concept_id 必须是非空字符串")
    if not isinstance(resource_id, str) or not resource_id.strip():
        raise VaultError("issue-route resource_id 必须是非空字符串")
    source_ref_ids = record.get("source_ref_ids")
    expected_chain_head = record.get("expected_chain_head")
    if (
        not isinstance(source_ref_ids, list)
        or not source_ref_ids
        or any(not isinstance(item, str) or not item.strip() for item in source_ref_ids)
        or len(source_ref_ids) != len(set(source_ref_ids))
    ):
        raise VaultError("issue-route source_ref_ids 必须是非空唯一字符串数组")
    if (
        not isinstance(expected_chain_head, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_chain_head)
    ):
        raise VaultError("issue-route expected_chain_head 必须是 64 位 SHA-256")
    user_cost_priority = record.get("user_cost_priority")
    if user_cost_priority is not None and (
        not isinstance(user_cost_priority, list)
        or not user_cost_priority
        or any(item not in COST_DIMENSIONS for item in user_cost_priority)
        or len(user_cost_priority) != len(set(user_cost_priority))
    ):
        raise VaultError(
            "issue-route user_cost_priority 必须是 null 或非空、唯一的 canonical cost dimension 数组"
        )
    if isinstance(user_cost_priority, list):
        user_cost_priority = list(user_cost_priority)
    if purpose == "retention" and user_cost_priority is not None:
        raise VaultError("retention issue-route 不消费 user_cost_priority；必须为 null")

    index, index_errors = build_index(vault)
    if index_errors:
        raise VaultError("图谱存在错误，不能签发路线: " + "; ".join(index_errors))
    manifest = json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))
    registry, route_events, route_errors = load_route_binding_registry(vault, manifest)
    if route_errors:
        raise VaultError("route issuance 校验失败: " + "; ".join(route_errors))
    ledger_path = vault / ROUTE_BINDINGS_REL
    if not ledger_path.is_file():
        raise VaultError("缺少 route-bindings.json；当前入口只追加既有权威链")
    route_document = json.loads(ledger_path.read_text(encoding="utf-8"))
    if route_document.get("head_hash") != expected_chain_head:
        raise VaultError(
            "issue-route CAS 冲突: expected_chain_head "
            f"expected={expected_chain_head} actual={route_document.get('head_hash')}"
        )
    all_meta: dict[str, dict[str, Any]] = {}
    all_body: dict[str, str] = {}
    for node_id, node in index.get("nodes", {}).items():
        meta, body, parse_errors = parse_note(vault / node["path"])
        if parse_errors:
            raise VaultError(f"笔记无法解析: {node_id}: {'; '.join(parse_errors)}")
        all_meta[node_id] = meta
        all_body[node_id] = body
    learner_node_id = str(manifest.get("active_learner_id"))
    learner_id = all_meta.get(learner_node_id, {}).get("learner_id")
    goal_id = str(manifest.get("active_goal_id"))
    if not learner_id or all_meta.get(goal_id, {}).get("type") != "goal":
        raise VaultError("manifest 缺少唯一 active learner/goal")
    active_routes = [
        (node_id, meta)
        for node_id, meta in all_meta.items()
        if meta.get("type") == "intervention"
        and meta.get("status") == "active"
        and meta.get("learner_id") == learner_id
        and meta.get("goal_id") == goal_id
    ]
    if len(active_routes) != 1:
        raise VaultError("issue-route 要求当前 learner+goal 有且只有一条 active intervention")
    intervention_id, intervention = active_routes[0]
    for source_ref in source_ref_ids:
        source_meta = all_meta.get(source_ref, {})
        if source_meta.get("type") not in {"session", "evidence"}:
            raise VaultError(f"issue-route source_ref 不存在或不是 session/evidence: {source_ref}")
        if (
            source_meta.get("learner_id") != learner_id
            or source_meta.get("goal_id") != goal_id
        ):
            raise VaultError(f"issue-route source_ref learner/goal scope 不一致: {source_ref}")

    states_by_concept: dict[str, tuple[str, dict[str, Any]]] = {
        str(meta.get("concept_id")): (node_id, meta)
        for node_id, meta in all_meta.items()
        if meta.get("type") == "state"
        and meta.get("learner_id") == learner_id
        and meta.get("goal_id") == goal_id
    }
    state_entry = states_by_concept.get(concept_id)
    if state_entry is None:
        raise VaultError("issue-route concept 没有同 scope state")
    state_id, state = state_entry
    contract = next(
        (
            item
            for item in all_meta[goal_id].get("mastery_contracts", [])
            if isinstance(item, dict)
            and item.get("concept_id") == concept_id
            and item.get("id") == state.get("contract_id")
            and item.get("version") == state.get("contract_version")
        ),
        None,
    )
    if not isinstance(contract, dict):
        raise VaultError("issue-route 无法解析 concept 的 mastery contract")
    resource_node = index.get("nodes", {}).get(resource_id)
    if not isinstance(resource_node, dict) or resource_node.get("type") != "resource":
        raise VaultError("issue-route resource_id 不存在或不是 canonical resource")
    resource_meta = dict(all_meta[resource_id])
    resource_relations = resource_node.get("relations", [])
    resource_meta["teaches"] = [
        relation["target"]
        for relation in resource_relations
        if relation.get("type") == "teaches"
    ]
    resource_meta["requires"] = [
        relation["target"]
        for relation in resource_relations
        if relation.get("type") == "requires"
    ]
    normalized_resource = normalized_resource_snapshot(
        resource_meta, label=f"resource {resource_id}"
    )
    if concept_id not in normalized_resource["teaches"]:
        raise VaultError("issue-route resource 未 teaches 目标 concept")
    if any(
        states_by_concept.get(required, ({}, {}))[1].get("mastery") != "mastered"
        for required in normalized_resource["requires"]
    ):
        raise VaultError("issue-route resource 仍有未满足的 canonical prerequisite")

    requirements = {
        node_id: {
            relation["target"]
            for relation in node.get("relations", [])
            if relation.get("type") == "requires"
        }
        for node_id, node in index.get("nodes", {}).items()
        if node.get("type") == "concept"
    }
    target_subgraph = target_subgraph_for_goal(index, goal_id, requirements)
    next_route_version = 1 + max(
        (
            int(event["route_version"])
            for event in route_events
            if event.get("learner_id") == learner_id
            and event.get("goal_id") == goal_id
            and event.get("route_id") == intervention.get("route_id")
            and isinstance(event.get("route_version"), int)
        ),
        default=int(intervention.get("route_version", 0)),
    )
    issued_at = utc_now_precise()
    issued_instant = parse_iso_instant(issued_at)
    if route_events and issued_instant <= max(
        parse_iso_instant(event.get("issued_at")) for event in route_events
    ):
        raise VaultError("真实 wall clock 尚未晚于上一 route issuance；请稍后重试")

    selection_basis = "retention_contract"
    selection_priority_status = "not_applicable"
    focus_decision_id_used: str | None = None
    focus_time_scope_used: str | None = None
    current_focus_decision_id: str | None = None
    selection_candidate_costs: list[dict[str, Any]] = []
    baseline_evidence_id = record.get("baseline_evidence_id")
    if purpose == "learning":
        if baseline_evidence_id is not None:
            raise VaultError("learning issue-route 的 baseline_evidence_id 必须为 null")
        path = list(intervention.get("path", []))
        if concept_id not in path:
            raise VaultError("learning issue-route concept 不在 active route path")
        expected_focus_time_scope = f"route-chain-head:{expected_chain_head}"
        eligible_focus = [
            meta
            for meta in all_meta.values()
            if meta.get("type") == "focus_snapshot"
            and meta.get("learner_id") == learner_id
            and meta.get("goal_id") == goal_id
            and meta.get("calculation_purpose") == "residual_candidate_order"
            and isinstance(meta.get("consumer_ids"), list)
            and "focus_priority" in meta.get("consumer_ids", [])
            and meta.get("used_in_decision") is True
            and meta.get("ranking_status") == "complete"
            and meta.get("validity") == "valid"
            and meta.get("route_id") == intervention.get("route_id")
            and meta.get("route_version") == intervention.get("route_version")
            and meta.get("time_scope") == expected_focus_time_scope
            and parse_iso_instant(meta.get("calculated_at")) <= issued_instant
        ]
        latest_focus: dict[str, dict[str, Any]] = {}
        if eligible_focus:
            batch_latest: dict[str, datetime] = {}
            for focus in eligible_focus:
                decision_id = str(focus.get("decision_id"))
                calculated = parse_iso_instant(focus.get("calculated_at"))
                batch_latest[decision_id] = max(
                    calculated,
                    batch_latest.get(
                        decision_id, datetime.min.replace(tzinfo=timezone.utc)
                    ),
                )
            latest_batch_time = max(batch_latest.values())
            current_batches = sorted(
                decision_id
                for decision_id, calculated in batch_latest.items()
                if calculated == latest_batch_time
            )
            if len(current_batches) != 1:
                raise VaultError(
                    "Focus 当前 decision batch 不唯一；需重算或补测后再签发"
                )
            current_focus_decision_id = current_batches[0]
            current_focus_batch = [
                meta
                for meta in eligible_focus
                if meta.get("decision_id") == current_focus_decision_id
            ]
            current_focus_selection_bases = {
                meta.get("selection_basis") for meta in current_focus_batch
            }
            if (
                len(current_focus_selection_bases) != 1
                or not current_focus_selection_bases.issubset(
                    {"focus", "stable_tie_break", "route_default"}
                )
            ):
                raise VaultError(
                    "Focus 当前 decision batch 的 selection_basis 必须一致，"
                    "且只能是 focus/stable_tie_break/route_default"
                )
            for meta in current_focus_batch:
                focus_concept = str(meta.get("concept_id"))
                prior = latest_focus.get(focus_concept)
                if prior is None or parse_iso_instant(
                    meta.get("calculated_at")
                ) > parse_iso_instant(prior.get("calculated_at")):
                    latest_focus[focus_concept] = meta

        depth_cache: dict[str, int] = {}

        def route_level(candidate_concept: str, trail: set[str] | None = None) -> int:
            if candidate_concept in depth_cache:
                return depth_cache[candidate_concept]
            current_trail = set(trail or set())
            if candidate_concept in current_trail:
                return len(path)
            current_trail.add(candidate_concept)
            parents = requirements.get(candidate_concept, set())
            depth_cache[candidate_concept] = (
                0
                if not parents
                else 1 + max(route_level(parent, current_trail) for parent in parents)
            )
            return depth_cache[candidate_concept]

        resource_candidates: dict[str, list[dict[str, Any]]] = {}
        for candidate_resource_id, candidate_node in index.get("nodes", {}).items():
            if candidate_node.get("type") != "resource":
                continue
            candidate_meta = dict(all_meta[candidate_resource_id])
            candidate_relations = candidate_node.get("relations", [])
            candidate_meta["teaches"] = [
                relation["target"]
                for relation in candidate_relations
                if relation.get("type") == "teaches"
            ]
            candidate_meta["requires"] = [
                relation["target"]
                for relation in candidate_relations
                if relation.get("type") == "requires"
            ]
            try:
                candidate_snapshot = normalized_resource_snapshot(
                    candidate_meta, label=f"resource {candidate_resource_id}"
                )
            except VaultError:
                continue
            for taught_concept in candidate_snapshot["teaches"]:
                resource_candidates.setdefault(taught_concept, []).append(
                    candidate_snapshot
                )
        candidates: list[dict[str, Any]] = []
        candidate_resource_choice: dict[str, str] = {}
        time_scope = f"route-chain-head:{route_document.get('head_hash')}"
        base_cost = _complete_cost_vector(
            {"cost_vector": intervention.get("cost_vector")}
        )
        if base_cost is None:
            raise VaultError("active intervention 缺少可追溯的完整 cost_vector")
        for route_order, candidate_concept in enumerate(path):
            candidate_state_entry = states_by_concept.get(candidate_concept)
            if candidate_state_entry is None:
                continue
            candidate_state = candidate_state_entry[1]
            candidate_contract = next(
                (
                    item
                    for item in all_meta[goal_id].get("mastery_contracts", [])
                    if isinstance(item, dict)
                    and item.get("concept_id") == candidate_concept
                    and item.get("id") == candidate_state.get("contract_id")
                    and item.get("version") == candidate_state.get("contract_version")
                ),
                None,
            )
            if not isinstance(candidate_contract, dict):
                continue
            compatible_resources = [
                item
                for item in resource_candidates.get(candidate_concept, [])
                if all(
                    states_by_concept.get(required, ({}, {}))[1].get("mastery")
                    == "mastered"
                    for required in item["requires"]
                )
                and (
                    intervention.get("medium_policy") != "text_preferred"
                    or item["carrier"]
                    in {"text_document", "text_dialogue", "text_hybrid"}
                )
                and not any(
                    event.get("learner_id") == learner_id
                    and event.get("goal_id") == goal_id
                    and event.get("concept_id") == candidate_concept
                    and event.get("contract_id") == candidate_contract["id"]
                    and event.get("contract_version")
                    == candidate_contract["version"]
                    and (
                        event.get("verification_task_id")
                        == item["verification_task"]["id"]
                        or event.get("verification_task_fingerprint")
                        == sha256_fingerprint(item["verification_task"])
                    )
                    for event in route_events
                )
            ]
            compatible_resources.sort(
                key=lambda item: (item["duration_minutes"], item["id"])
            )
            routing_action = (
                "diagnose_now"
                if candidate_state.get("mastery") == "unknown"
                else "teach_now"
            )
            focus = latest_focus.get(candidate_concept, {})
            resource_options: list[dict[str, Any] | None] = (
                list(compatible_resources) if compatible_resources else [None]
            )
            for resource_order, selected_resource in enumerate(resource_options):
                selected_resource_id = (
                    str(selected_resource["id"])
                    if isinstance(selected_resource, dict)
                    else "__unbound__"
                )
                candidate_step_id = f"{candidate_concept}::{selected_resource_id}"
                if isinstance(selected_resource, dict):
                    candidate_resource_choice[candidate_step_id] = selected_resource_id
                explicit_cost = (
                    selected_resource.get("cost_vector")
                    if isinstance(selected_resource, dict)
                    else None
                )
                if isinstance(explicit_cost, dict):
                    cost_vector = dict(explicit_cost)
                    cost_vector_source = "resource.cost_vector"
                    fallback_cost_estimate = None
                else:
                    fallback_cost_estimate = dict(base_cost)
                    if isinstance(selected_resource, dict):
                        fallback_cost_estimate[
                            "diagnosis"
                            if routing_action == "diagnose_now"
                            else "core_learning"
                        ] = float(selected_resource["duration_minutes"])
                        cost_vector_source = (
                            "intervention.cost_vector+resource.duration_minutes:fallback_estimate"
                        )
                    else:
                        cost_vector_source = "intervention.cost_vector:unbound_estimate"
                    # A fallback estimate remains useful for route-default
                    # ordering/audit, but it is not a resource-owned six-axis
                    # trade-off and must not satisfy Pareto/user priority.
                    cost_vector = None
                candidates.append(
                    {
                        "candidate_step_id": candidate_step_id,
                        "concept_id": candidate_concept,
                        "resource_id": (
                            selected_resource_id
                            if isinstance(selected_resource, dict)
                            else None
                        ),
                        "resource_fingerprint": (
                            sha256_fingerprint(selected_resource)
                            if isinstance(selected_resource, dict)
                            else None
                        ),
                        "cost_vector_source": cost_vector_source,
                        "contract_id": candidate_contract["id"],
                        "contract_version": candidate_contract["version"],
                        "learner_id": learner_id,
                        "goal_id": goal_id,
                        "route_id": intervention.get("route_id"),
                        "route_version": next_route_version,
                        "time_scope": time_scope,
                        "in_target_subgraph": candidate_concept in target_subgraph,
                        "mastery_compatible": candidate_state.get("mastery")
                        != "mastered",
                        "prerequisites_satisfied": all(
                            states_by_concept.get(required, ({}, {}))[1].get("mastery")
                            == "mastered"
                            for required in requirements.get(candidate_concept, set())
                        ),
                        "hard_constraints_satisfied": isinstance(
                            selected_resource, dict
                        )
                        and candidate_state.get("boundary_position")
                        == "outer_fringe",
                        "route_level": route_level(candidate_concept),
                        "route_order": route_order * 1000 + resource_order,
                        "routing_action": routing_action,
                        "mastery_gate": candidate_state.get("mastery"),
                        "activity_id": selected_resource_id
                        if isinstance(selected_resource, dict)
                        and routing_action == "teach_now"
                        else None,
                        "probe_id": selected_resource["diagnostic_probe"]["id"]
                        if isinstance(selected_resource, dict)
                        and routing_action == "diagnose_now"
                        else None,
                        "verification_task_id": selected_resource[
                            "verification_task"
                        ]["id"]
                        if isinstance(selected_resource, dict)
                        else None,
                        "cost_vector": cost_vector,
                        "fallback_cost_estimate": fallback_cost_estimate,
                        "user_cost_priority": user_cost_priority,
                        "ranking_status": focus.get("ranking_status"),
                        "validity": focus.get("validity"),
                        "goal_relevance": focus.get("goal_relevance"),
                        "interest_evidence": focus.get("interest_evidence"),
                        "readiness": focus.get("readiness"),
                        "focus_weights": focus.get("focus_weights"),
                        "focus_z": focus.get("focus_z"),
                        "input_source_refs": focus.get("input_source_refs"),
                        "calculated_at": focus.get("calculated_at"),
                    }
                )
        selection = select_candidate_step_v3(candidates)
        selection_priority_status = str(
            selection.get("user_cost_priority_status")
        )
        if selection_priority_status in {
            "inconsistent",
            "invalid_dimension",
            "blocked_by_unresolved_pareto",
        }:
            raise VaultError(
                "user_cost_priority 无法在当前 Pareto 前沿安全应用；"
                f"status={selection_priority_status}，需澄清偏好或补测成本"
            )
        selected_concept = selection.get("selected_concept_id")
        if selected_concept is None:
            raise VaultError(
                "canonical route candidates 没有可签发项: "
                + str(selection.get("selection_basis"))
            )
        if selected_concept != concept_id:
            raise VaultError(
                f"record concept 不是 canonical selector 结果: selected={selected_concept}"
            )
        selected_candidate_id = str(selection.get("selected_id"))
        expected_resource_id = candidate_resource_choice.get(selected_candidate_id)
        if expected_resource_id != resource_id:
            raise VaultError(
                "record resource 不是当前 canonical cost selector 结果: "
                f"selected={expected_resource_id}"
            )
        selection_candidate_costs = sorted(
            [
                {
                    "concept_id": str(candidate.get("concept_id")),
                    "resource_id": str(candidate.get("resource_id")),
                    "resource_fingerprint": str(
                        candidate.get("resource_fingerprint")
                    ),
                    "cost_vector": (
                        dict(candidate["cost_vector"])
                        if isinstance(candidate.get("cost_vector"), dict)
                        else None
                    ),
                    "fallback_cost_estimate": (
                        dict(candidate["fallback_cost_estimate"])
                        if isinstance(
                            candidate.get("fallback_cost_estimate"), dict
                        )
                        else None
                    ),
                    "cost_vector_source": str(
                        candidate.get("cost_vector_source")
                    ),
                    "selected": candidate.get("candidate_step_id")
                    == selected_candidate_id,
                }
                for candidate in selection.get("candidates", [])
                if isinstance(candidate.get("resource_id"), str)
                and candidate.get("resource_id")
            ],
            key=lambda item: (item["concept_id"], item["resource_id"]),
        )
        selection_basis = str(selection.get("selection_basis"))
        if selection_basis in {"focus", "stable_tie_break"}:
            if current_focus_decision_id is None:
                raise VaultError("selector 声明消费 Focus，但没有唯一当前 decision batch")
            focus_decision_id_used = current_focus_decision_id
            focus_time_scope_used = expected_focus_time_scope
    else:
        if not isinstance(baseline_evidence_id, str) or not baseline_evidence_id.strip():
            raise VaultError("retention issue-route 必须提供 baseline_evidence_id")
        if baseline_evidence_id not in source_ref_ids:
            raise VaultError("retention issue-route source_ref_ids 必须包含 baseline evidence")
        baseline = all_meta.get(baseline_evidence_id, {})
        allow_synthetic_demo = trusted_synthetic_demo_authorized(vault, manifest)
        baseline_eligible, _baseline_failures = evidence_mastery_eligibility(
            baseline, allow_synthetic_demo=allow_synthetic_demo
        )
        supported_ids = {
            relation.get("target")
            for relation in index["nodes"][state_id].get("relations", [])
            if relation.get("type") == "supported_by"
        }
        if (
            baseline.get("type") != "evidence"
            or baseline.get("phase") != "verification"
            or not baseline_eligible
            or baseline.get("result") != "pass"
            or baseline_evidence_id not in supported_ids
            or any(baseline.get(field) != state.get(field) for field in (
                "learner_id", "goal_id", "concept_id", "contract_id", "contract_version"
            ))
        ):
            raise VaultError("retention issue-route baseline 必须是同 state 的合格 pass verification")
        delayed = contract.get("requirements", {}).get("delayed_retention", {})
        state_records = [
            (str(relation.get("target")), all_meta[str(relation.get("target"))])
            for relation in index["nodes"][state_id].get("relations", [])
            if relation.get("type") == "supported_by"
            and all_meta.get(str(relation.get("target")), {}).get("type")
            == "evidence"
        ]
        live_evaluation = evaluate_mastery_contract(
            contract,
            state_records,
            state_context=state_context_with_current_schedule(
                state, all_meta, strict=True
            ),
            as_of=issued_at,
            allow_synthetic_demo=allow_synthetic_demo,
        )
        latest_adverse = _latest_adverse_retention_instant(state_records)
        normal_retention_gate = bool(
            live_evaluation.get("immediate_contract_status") == "met"
            and live_evaluation.get("retention_status") == "not_started"
            and live_evaluation.get("next_action") == "schedule_retention"
        )
        repair_retention_gate = bool(
            live_evaluation.get("immediate_contract_status") == "met"
            and live_evaluation.get("retention_status") in {"failed", "conflicted"}
            and live_evaluation.get("next_action") == "retention_repair"
            and latest_adverse is not None
            and parse_iso_instant(baseline.get("observed_at")) > latest_adverse
        )
        if (
            not isinstance(delayed, dict)
            or delayed.get("required") is not True
            or not (normal_retention_gate or repair_retention_gate)
        ):
            raise VaultError(
                "state 尚未达到首次 retention gate，且没有晚于失败的新合格 verification baseline"
            )
        task_id = normalized_resource["verification_task"]["id"]
        task_fingerprint = sha256_fingerprint(
            normalized_resource["verification_task"]
        )
        if task_id == baseline.get("verification_item_id") or any(
            (
                event.get("verification_task_id") == task_id
                or event.get("verification_task_fingerprint") == task_fingerprint
            )
            and event.get("learner_id") == learner_id
            and event.get("goal_id") == goal_id
            and event.get("concept_id") == concept_id
            and event.get("contract_id") == contract["id"]
            and event.get("contract_version") == contract["version"]
            for event in route_events
        ):
            raise VaultError(
                "retention task 必须在同 scope 具有全新的 ID 与 task fingerprint"
            )

    selected_task_id = normalized_resource["verification_task"]["id"]
    selected_task_fingerprint = sha256_fingerprint(
        normalized_resource["verification_task"]
    )
    if purpose == "learning" and any(
        event.get("learner_id") == learner_id
        and event.get("goal_id") == goal_id
        and event.get("concept_id") == concept_id
        and event.get("contract_id") == contract["id"]
        and event.get("contract_version") == contract["version"]
        and (
            event.get("verification_task_id") == selected_task_id
            or event.get("verification_task_fingerprint")
            == selected_task_fingerprint
        )
        for event in route_events
    ):
        raise VaultError(
            "learning task 在同 scope 的 ID 或 task fingerprint 已签发；必须选择真正的新任务"
        )

    comparison_context = _route_comparison_context(
        index=index,
        all_meta=all_meta,
        concept_id=concept_id,
        state=state,
        contract=contract,
        manifest=manifest,
    )
    sequence = len(route_events) + 1
    route_id = str(intervention.get("route_id"))
    binding_seed = {
        "vault_id": manifest.get("vault_id"),
        "sequence": sequence,
        "learner_id": learner_id,
        "goal_id": goal_id,
        "concept_id": concept_id,
        "contract_id": contract["id"],
        "contract_version": contract["version"],
        "route_id": route_id,
        "route_version": next_route_version,
        "resource_id": resource_id,
        "issued_at": issued_at,
    }
    binding_id = f"rb-local-{sha256_fingerprint(binding_seed)[:24]}"
    snapshot_intervention_id = (
        intervention_id
        if purpose == "learning"
        else f"int-retention-{sha256_fingerprint(binding_seed)[:20]}"
    )
    snapshot = {
        "resources": [normalized_resource],
        "intervention": normalized_intervention_snapshot(
            {
                "id": snapshot_intervention_id,
                "route_id": route_id,
                "route_version": next_route_version,
                "goal_id": goal_id,
                "current_checkpoint": concept_id,
                "resource_ids": [resource_id],
            },
            label="derived route issuance intervention",
        ),
    }
    event = {
        "binding_id": binding_id,
        "learner_id": learner_id,
        "goal_id": goal_id,
        "concept_id": concept_id,
        "contract_id": contract["id"],
        "contract_version": contract["version"],
        "route_id": route_id,
        "route_version": next_route_version,
        "verification_task_id": normalized_resource["verification_task"]["id"],
        "issued_at": issued_at,
        "immutable": True,
        "source_ref_ids": list(source_ref_ids),
        "event_kind": "route_issued",
        "route_purpose": purpose,
        "baseline_evidence_id": baseline_evidence_id,
        "selection_decision": {
            "selection_basis": selection_basis,
            "user_cost_priority": user_cost_priority,
            "user_cost_priority_status": selection_priority_status,
            "focus_decision_id": focus_decision_id_used,
            "focus_time_scope": focus_time_scope_used,
            "candidate_costs": selection_candidate_costs,
        },
        "sequence": sequence,
        "previous_hash": route_document["head_hash"],
        "comparison_context": comparison_context,
        "context_key": comparison_context_key(comparison_context),
        "resource_fingerprint": sha256_fingerprint(snapshot["resources"]),
        "intervention_fingerprint": sha256_fingerprint(snapshot["intervention"]),
        "verification_task_fingerprint": sha256_fingerprint(
            normalized_resource["verification_task"]
        ),
        "issuance_snapshot": snapshot,
    }
    event["event_hash"] = sha256_fingerprint(event)
    updated_document = dict(route_document)
    updated_document["events"] = list(route_events) + [event]
    updated_document["head_sequence"] = sequence
    updated_document["head_hash"] = event["event_hash"]
    updated_manifest = dict(manifest)
    updated_manifest["route_binding_chain_length"] = sequence
    updated_manifest["route_binding_chain_head"] = event["event_hash"]
    if manifest.get("route_trust_level") in {
        "trusted_seed_source",
        "trusted_seed_prefix_local_extension",
    }:
        extension_sequence = int(
            route_document.get("local_extension_from_sequence") or sequence
        )
        updated_document["local_extension_from_sequence"] = extension_sequence
        updated_manifest["route_local_extension_from_sequence"] = extension_sequence
        updated_manifest["route_trust_level"] = (
            "trusted_seed_prefix_local_extension"
        )

    current_route_document = json.loads(ledger_path.read_text(encoding="utf-8"))
    current_manifest = json.loads(
        (vault / MANIFEST_REL).read_text(encoding="utf-8")
    )
    if (
        current_route_document.get("head_hash") != expected_chain_head
        or current_manifest.get("route_binding_chain_head")
        != expected_chain_head
    ):
        raise VaultError("issue-route CAS 冲突：route chain 在提交前已变化")

    touched_paths = {ledger_path, vault / MANIFEST_REL}
    if purpose == "learning":
        touched_paths.update(
            {
                vault / index["nodes"][intervention_id]["path"],
                vault / INDEX_REL,
            }
        )
    previous_images = {
        path: path.read_bytes() if path.exists() else None for path in touched_paths
    }
    try:
        write_json(ledger_path, updated_document)
        write_json(vault / MANIFEST_REL, updated_manifest)
        resolution_status = "not_applicable"
        if purpose == "learning":
            updated_intervention = dict(intervention)
            resolution_fields = {
                "teaching_resolution_schema",
                "resolved_activity",
                "resolved_carrier",
                "resolved_resource_id",
                "resolved_profile_refs",
                "resolved_profile_level",
                "resolved_profile_usage",
                *PROCESS_REFRESH_FIELDS,
                "resolved_route_binding_id",
                "resolved_context_key",
                "resolved_at",
                "process_refreshed_at",
                "resolved_decision_fingerprint",
            }
            for field in resolution_fields:
                updated_intervention.pop(field, None)
            updated_intervention.update(
                {
                    "route_version": next_route_version,
                    "current_checkpoint": concept_id,
                    "current_activity_id": resource_id,
                    "current_probe_id": normalized_resource["diagnostic_probe"]["id"],
                    "current_verification_task_id": normalized_resource[
                        "verification_task"
                    ]["id"],
                    "carrier": normalized_resource["carrier"],
                    "updated_at": issued_at,
                }
            )
            replace_note_meta(
                vault / index["nodes"][intervention_id]["path"],
                updated_intervention,
                _replace_relation_targets(
                    all_body[intervention_id], "uses", [resource_id]
                ),
            )
            _rebuilt, rebuild_errors = rebuild_index(vault)
            if rebuild_errors:
                raise VaultError("issue-route 后索引重建失败: " + "; ".join(rebuild_errors))
            mid_errors, _mid_warnings, _mid_summary = validate_vault(
                vault, allow_unresolved_teaching=True
            )
            if mid_errors:
                raise VaultError(
                    "issue-route 未解析教学前校验失败:\n- "
                    + "\n- ".join(mid_errors)
                )
            resolve_active_teaching(vault, write=True)
            resolution_status = "resolved"
        final_errors, _final_warnings, final_summary = validate_vault(vault)
        if final_errors:
            raise VaultError(
                "issue-route 写后校验失败:\n- " + "\n- ".join(final_errors)
            )
    except Exception as exc:
        rollback_errors = _restore_file_images(previous_images)
        if rollback_errors:
            raise VaultError(
                "issue-route 失败且 byte-exact 回滚不完整: "
                + "; ".join(rollback_errors)
                + f"; original={exc}"
            ) from exc
        raise
    routing_action = (
        "retention_task_reserved"
        if purpose == "retention"
        else ("diagnose_now" if state.get("mastery") == "unknown" else "teach_now")
    )
    next_action = {
        "retention_task_reserved": "schedule_retention",
        "diagnose_now": "present_issued_diagnostic_probe",
        "teach_now": "issue_teaching",
    }[routing_action]
    return {
        "status": "issued",
        "commit_status": "atomic_validated",
        "purpose": purpose,
        "routing_action": routing_action,
        "selection_basis": selection_basis,
        "binding_id": binding_id,
        "route_id": route_id,
        "route_version": next_route_version,
        "concept_id": concept_id,
        "resource_id": resource_id,
        "verification_task_id": event["verification_task_id"],
        "context_key": event["context_key"],
        "event_hash": event["event_hash"],
        "issued_at": issued_at,
        "active_resolution_status": resolution_status,
        "next_action": next_action,
        "user_cost_priority": user_cost_priority,
        "user_cost_priority_status": selection_priority_status,
        "user_cost_priority_provided": user_cost_priority is not None,
        "focus_decision_id": focus_decision_id_used,
        "focus_time_scope": focus_time_scope_used,
        "route_trust_segment": "local_chain_only",
        "node_count": final_summary["node_count"],
    }


def _schedule_retention_legacy(vault: Path, *, record_path: Path) -> dict[str, Any]:
    """Atomically bind a qualified baseline to an issued unseen retention task."""

    errors, _warnings, _summary = validate_vault(vault)
    if errors:
        raise VaultError(
            "Vault 校验失败，不能安排 retention:\n- " + "\n- ".join(errors)
        )
    record = _read_exact_json_record(
        record_path,
        fields={
            "state_id",
            "baseline_evidence_id",
            "route_binding_id",
            "scheduled_for",
        },
        label="schedule-retention record",
    )
    state_id = record.get("state_id")
    baseline_id = record.get("baseline_evidence_id")
    binding_id = record.get("route_binding_id")
    if any(
        not isinstance(value, str) or not value.strip()
        for value in (state_id, baseline_id, binding_id)
    ):
        raise VaultError(
            "schedule-retention state/baseline/route_binding 必须是非空字符串"
        )
    commit_at = utc_now_precise()
    commit_instant = parse_iso_instant(commit_at)
    try:
        scheduled_instant = parse_iso_instant(record.get("scheduled_for"))
    except (TypeError, ValueError) as exc:
        raise VaultError("schedule-retention scheduled_for 必须是带时区 ISO 时间") from exc
    if scheduled_instant <= commit_instant:
        raise VaultError("schedule-retention scheduled_for 必须晚于真实 wall clock")
    scheduled_for = scheduled_instant.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )

    index, index_errors = build_index(vault)
    if index_errors:
        raise VaultError("图谱存在错误，不能安排 retention: " + "; ".join(index_errors))
    state_node = index.get("nodes", {}).get(str(state_id))
    if not isinstance(state_node, dict) or state_node.get("type") != "state":
        raise VaultError("schedule-retention state_id 不存在或不是 state")
    all_meta: dict[str, dict[str, Any]] = {}
    for node_id, node in index.get("nodes", {}).items():
        meta, _body, parse_errors = parse_note(vault / node["path"])
        if parse_errors:
            raise VaultError(f"笔记无法解析: {node_id}: {'; '.join(parse_errors)}")
        all_meta[node_id] = meta
    state, state_body, state_parse_errors = parse_note(vault / state_node["path"])
    if state_parse_errors:
        raise VaultError("schedule-retention state 无法解析")
    scope_fields = (
        "learner_id",
        "goal_id",
        "concept_id",
        "contract_id",
        "contract_version",
    )
    goal = all_meta.get(str(state.get("goal_id")), {})
    contract = next(
        (
            item
            for item in goal.get("mastery_contracts", [])
            if isinstance(item, dict)
            and item.get("id") == state.get("contract_id")
            and item.get("version") == state.get("contract_version")
            and item.get("concept_id") == state.get("concept_id")
        ),
        None,
    )
    if not isinstance(contract, dict):
        raise VaultError("schedule-retention state 无唯一 mastery contract")
    retention_requirement = contract.get("requirements", {}).get(
        "delayed_retention", {}
    )
    if (
        not isinstance(retention_requirement, dict)
        or retention_requirement.get("required") is not True
    ):
        raise VaultError("当前 mastery contract 不要求 delayed retention")
    supported_ids = [
        str(relation.get("target"))
        for relation in state_node.get("relations", [])
        if relation.get("type") == "supported_by"
    ]
    state_records = [
        (evidence_id, all_meta[evidence_id])
        for evidence_id in supported_ids
        if all_meta.get(evidence_id, {}).get("type") == "evidence"
    ]
    live_evaluation = evaluate_mastery_contract(
        contract,
        state_records,
        state_context=state,
        as_of=commit_at,
        allow_synthetic_demo=trusted_synthetic_demo_authorized(
            vault,
            json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8")),
        ),
    )
    if (
        live_evaluation.get("immediate_contract_status") != "met"
        or live_evaluation.get("retention_status") != "not_started"
        or live_evaluation.get("next_action") != "schedule_retention"
    ):
        raise VaultError("state 当前不在 schedule_retention gate")
    if baseline_id not in set(live_evaluation.get("immediate_qualified_evidence_ids", [])):
        raise VaultError("baseline 必须是当前即时合同实际消费的合格 verification")
    baseline = all_meta.get(str(baseline_id), {})
    if (
        baseline.get("phase") != "verification"
        or baseline.get("result") != "pass"
        or any(baseline.get(field) != state.get(field) for field in scope_fields)
    ):
        raise VaultError("baseline 不是同 scope 的 pass verification")
    try:
        baseline_instant = parse_iso_instant(baseline.get("observed_at"))
    except (TypeError, ValueError) as exc:
        raise VaultError("baseline observed_at 非法") from exc
    min_delay_days = retention_requirement.get("min_delay_days")
    if (
        not isinstance(min_delay_days, int)
        or isinstance(min_delay_days, bool)
        or min_delay_days < 1
    ):
        raise VaultError("delayed_retention.min_delay_days 必须是正整数")
    if scheduled_instant < baseline_instant + timedelta(days=min_delay_days):
        raise VaultError("scheduled_for 早于 baseline + min_delay_days")

    manifest = json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))
    _registry, events, route_errors = load_route_binding_registry(vault, manifest)
    if route_errors:
        raise VaultError("route issuance 校验失败: " + "; ".join(route_errors))
    matching_events = [event for event in events if event.get("binding_id") == binding_id]
    if len(matching_events) != 1:
        raise VaultError("route_binding_id 必须唯一解析到已签发事件")
    issuance = matching_events[0]
    if issuance.get("route_purpose") != "retention":
        raise VaultError("schedule-retention 只能绑定 purpose=retention 的发行事件")
    if any(issuance.get(field) != state.get(field) for field in scope_fields):
        raise VaultError("retention route issuance 与 state 完整 scope 不一致")
    task_id = issuance.get("verification_task_id")
    if (
        not isinstance(task_id, str)
        or not task_id.strip()
        or task_id == baseline.get("verification_item_id")
    ):
        raise VaultError("retention task 必须是不同于 baseline 的新任务")
    try:
        issuance_instant = parse_iso_instant(issuance.get("issued_at"))
    except (TypeError, ValueError) as exc:
        raise VaultError("retention route issued_at 非法") from exc
    if issuance_instant > commit_instant:
        raise VaultError("retention route issuance 不得位于未来")
    if scheduled_instant < issuance_instant:
        raise VaultError("scheduled_for 不得早于 retention route issuance")
    used_task_evidence = [
        evidence_id
        for evidence_id, evidence in all_meta.items()
        if evidence.get("type") == "evidence"
        and all(evidence.get(field) == state.get(field) for field in scope_fields)
        and evidence.get("verification_item_id") == task_id
    ]
    if used_task_evidence:
        raise VaultError("retention task 已被 evidence 消费，不能重新排期")
    existing_schedule = (
        state.get("baseline_evidence_id"),
        state.get("retention_task_id"),
        state.get("scheduled_for"),
        state.get("retention_route_binding_id"),
    )
    if any(value is not None for value in existing_schedule):
        raise VaultError("state 已有 retention schedule；禁止隐式改期或换题")

    updated_state = dict(state)
    updated_state.update(
        {
            "baseline_evidence_id": baseline_id,
            "retention_task_id": task_id,
            "retention_route_binding_id": binding_id,
            "scheduled_for": scheduled_for,
        }
    )
    evaluation = evaluate_mastery_contract(
        contract,
        state_records,
        state_context=updated_state,
        as_of=commit_at,
        allow_synthetic_demo=trusted_synthetic_demo_authorized(vault, manifest),
    )
    if (
        evaluation.get("retention_status") != "pending"
        or evaluation.get("next_action") != "wait_until_scheduled_for"
    ):
        raise VaultError("schedule-retention 未能派生 pending/wait 状态")
    knowledge = derive_state_knowledge_status(
        evaluation, state_records, as_of=commit_at
    )
    updated_state.update(
        {
            "mastery": knowledge["mastery"],
            "mastery_confidence": knowledge["mastery_confidence"],
            "immediate_contract_status": evaluation[
                "immediate_contract_status"
            ],
            "contract_status": evaluation["status"],
            "retention_status": evaluation["retention_status"],
            "next_action": evaluation["next_action"],
            "misconception_flags": knowledge["misconception_flags"],
            "diagnostic_snapshot": knowledge["diagnostic_snapshot"],
            "evaluated_at": commit_at,
            "updated_at": commit_at,
        }
    )
    updated_state["tags"] = [
        item
        for item in updated_state.get("tags", [])
        if not (isinstance(item, str) and item.startswith("uc/state/"))
    ] + [f"uc/state/{knowledge['mastery']}"]
    state_path = vault / state_node["path"]
    touched_paths = {state_path, vault / INDEX_REL}
    previous_images = {
        path: path.read_bytes() if path.exists() else None for path in touched_paths
    }
    try:
        replace_note_meta(state_path, updated_state, state_body)
        _rebuilt, rebuild_errors = rebuild_index(vault)
        if rebuild_errors:
            raise VaultError(
                "schedule-retention 后索引重建失败: " + "; ".join(rebuild_errors)
            )
        final_errors, _final_warnings, final_summary = validate_vault(vault)
        if final_errors:
            raise VaultError(
                "schedule-retention 写后校验失败:\n- "
                + "\n- ".join(final_errors)
            )
    except Exception as exc:
        rollback_errors = _restore_file_images(previous_images)
        if rollback_errors:
            raise VaultError(
                "schedule-retention 失败且 byte-exact 回滚不完整: "
                + "; ".join(rollback_errors)
                + f"; original={exc}"
            ) from exc
        raise
    return {
        "status": "scheduled",
        "commit_status": "atomic_validated",
        "state_id": state_id,
        "baseline_evidence_id": baseline_id,
        "retention_task_id": task_id,
        "retention_route_binding_id": binding_id,
        "scheduled_for": scheduled_for,
        "retention_status": evaluation["retention_status"],
        "next_action": evaluation["next_action"],
        "committed_at": commit_at,
        "node_count": final_summary["node_count"],
    }


@vault_transaction_writer
def schedule_retention(vault: Path, *, record_path: Path) -> dict[str, Any]:
    """Atomically append a schedule receipt and move the state pointer."""

    errors, _warnings, _summary = validate_vault(vault)
    if errors:
        raise VaultError(
            "Vault 校验失败，不能安排 retention:\n- " + "\n- ".join(errors)
        )
    record = _read_exact_json_record(
        record_path,
        fields={
            "state_id",
            "baseline_evidence_id",
            "route_binding_id",
            "not_before",
            "expected_state_evaluated_at",
        },
        label="schedule-retention record",
    )
    state_id = record.get("state_id")
    baseline_id = record.get("baseline_evidence_id")
    binding_id = record.get("route_binding_id")
    expected_state_evaluated_at = record.get("expected_state_evaluated_at")
    if any(
        not isinstance(value, str) or not value.strip()
        for value in (
            state_id,
            baseline_id,
            binding_id,
            expected_state_evaluated_at,
        )
    ):
        raise VaultError(
            "schedule-retention state/baseline/route_binding/expected_state_evaluated_at "
            "必须是非空字符串"
        )
    not_before = record.get("not_before")
    if not_before is None:
        not_before_instant = None
        normalized_not_before = None
    else:
        try:
            not_before_instant = parse_iso_instant(not_before)
        except (TypeError, ValueError) as exc:
            raise VaultError("schedule-retention not_before 必须是 null 或带时区 ISO 时间") from exc
        normalized_not_before = not_before_instant.isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
    commit_at = utc_now_precise()
    commit_instant = parse_iso_instant(commit_at)

    index, index_errors = build_index(vault)
    if index_errors:
        raise VaultError("图谱存在错误，不能安排 retention: " + "; ".join(index_errors))
    state_node = index.get("nodes", {}).get(str(state_id))
    if not isinstance(state_node, dict) or state_node.get("type") != "state":
        raise VaultError("schedule-retention state_id 不存在或不是 state")
    all_meta: dict[str, dict[str, Any]] = {}
    all_body: dict[str, str] = {}
    for node_id, node in index.get("nodes", {}).items():
        meta, body, parse_errors = parse_note(vault / node["path"])
        if parse_errors:
            raise VaultError(f"笔记无法解析: {node_id}: {'; '.join(parse_errors)}")
        all_meta[node_id] = meta
        all_body[node_id] = body
    state = all_meta[str(state_id)]
    if state.get("evaluated_at") != expected_state_evaluated_at:
        raise VaultError(
            "schedule-retention CAS 冲突: expected_state_evaluated_at "
            f"expected={expected_state_evaluated_at} actual={state.get('evaluated_at')}"
        )
    goal = all_meta.get(str(state.get("goal_id")), {})
    contract = next(
        (
            item
            for item in goal.get("mastery_contracts", [])
            if isinstance(item, dict)
            and item.get("id") == state.get("contract_id")
            and item.get("version") == state.get("contract_version")
            and item.get("concept_id") == state.get("concept_id")
        ),
        None,
    )
    if not isinstance(contract, dict):
        raise VaultError("schedule-retention state 无唯一 mastery contract")
    delayed = contract.get("requirements", {}).get("delayed_retention", {})
    minimum_days = delayed.get("min_delay_days") if isinstance(delayed, dict) else None
    if (
        not isinstance(delayed, dict)
        or delayed.get("required") is not True
        or not isinstance(minimum_days, int)
        or isinstance(minimum_days, bool)
        or minimum_days < 1
    ):
        raise VaultError("当前 mastery contract 没有合法 delayed retention 要求")
    supported_ids = [
        str(relation.get("target"))
        for relation in state_node.get("relations", [])
        if relation.get("type") == "supported_by"
    ]
    state_records = [
        (evidence_id, all_meta[evidence_id])
        for evidence_id in supported_ids
        if all_meta.get(evidence_id, {}).get("type") == "evidence"
    ]
    manifest = json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))
    allow_synthetic_demo = trusted_synthetic_demo_authorized(vault, manifest)
    live_evaluation = evaluate_mastery_contract(
        contract,
        state_records,
        state_context=state_context_with_current_schedule(
            state, all_meta, strict=True
        ),
        as_of=commit_at,
        allow_synthetic_demo=allow_synthetic_demo,
    )
    baseline = all_meta.get(str(baseline_id), {})
    if (
        baseline_id not in supported_ids
        or baseline_id
        not in set(live_evaluation.get("immediate_qualified_evidence_ids", []))
        or not _qualified_verification_baseline(
            baseline, state, allow_synthetic_demo=allow_synthetic_demo
        )
    ):
        raise VaultError("baseline 必须是当前 state 实际消费的合格 pass verification")
    latest_adverse = _latest_adverse_retention_instant(state_records)
    normal_gate = bool(
        live_evaluation.get("immediate_contract_status") == "met"
        and live_evaluation.get("retention_status") == "not_started"
        and live_evaluation.get("next_action") == "schedule_retention"
    )
    repair_gate = bool(
        live_evaluation.get("immediate_contract_status") == "met"
        and live_evaluation.get("retention_status") in {"failed", "conflicted"}
        and live_evaluation.get("next_action") == "retention_repair"
        and latest_adverse is not None
        and parse_iso_instant(baseline.get("observed_at")) > latest_adverse
    )
    if not normal_gate and not repair_gate:
        raise VaultError(
            "state 当前既不在首次 schedule_retention gate，也没有晚于失败的新合格 verification baseline"
        )

    _registry, events, route_errors = load_route_binding_registry(vault, manifest)
    if route_errors:
        raise VaultError("route issuance 校验失败: " + "; ".join(route_errors))
    matches = [event for event in events if event.get("binding_id") == binding_id]
    if len(matches) != 1:
        raise VaultError("route_binding_id 必须唯一解析到已签发事件")
    issuance = matches[0]
    if (
        issuance.get("route_purpose") != "retention"
        or issuance.get("baseline_evidence_id") != baseline_id
        or any(issuance.get(field) != state.get(field) for field in RETENTION_SCOPE_FIELDS)
    ):
        raise VaultError(
            "schedule-retention 只能绑定同 scope、同 baseline、purpose=retention 的发行事件"
        )
    task_id = issuance.get("verification_task_id")
    task_fingerprint = issuance.get("verification_task_fingerprint")
    if (
        not isinstance(task_id, str)
        or not task_id.strip()
        or task_id == baseline.get("verification_item_id")
        or not isinstance(task_fingerprint, str)
        or not re.fullmatch(r"[0-9a-f]{64}", task_fingerprint)
    ):
        raise VaultError("retention task 必须是不同于 baseline 的已签发新任务")
    task_consumers = [
        node_id
        for node_id, meta in all_meta.items()
        if all(meta.get(field) == state.get(field) for field in RETENTION_SCOPE_FIELDS)
        and (
            meta.get("type") == "verification_open"
            and meta.get("retention_task_id") == task_id
            or meta.get("type") == "evidence"
            and meta.get("phase") in {"verification", "retention"}
            and meta.get("verification_item_id") == task_id
        )
    ]
    if task_consumers:
        raise VaultError(
            "retention task 已被 verification/retention/open 消费: "
            + ",".join(sorted(task_consumers))
        )
    try:
        if parse_iso_instant(issuance.get("issued_at")) > commit_instant:
            raise VaultError("retention route issuance 不得位于未来")
        baseline_instant = parse_iso_instant(baseline.get("observed_at"))
    except (TypeError, ValueError) as exc:
        if isinstance(exc, VaultError):
            raise
        raise VaultError("retention route/baseline 时间非法") from exc
    scheduled_instant = baseline_instant + timedelta(days=minimum_days)
    if not_before_instant is not None:
        scheduled_instant = max(scheduled_instant, not_before_instant)
    scheduled_for = scheduled_instant.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    previous_schedule_id = state.get("current_retention_schedule_id")
    if repair_gate:
        previous = all_meta.get(str(previous_schedule_id), {})
        if previous.get("type") != "retention_schedule":
            raise VaultError("retention repair 缺少可 supersede 的 current schedule receipt")
        if (
            previous.get("route_binding_id") == binding_id
            or previous.get("retention_task_id") == task_id
            or previous.get("verification_task_fingerprint") == task_fingerprint
        ):
            raise VaultError("retention repair 必须使用新 binding/task/fingerprint")
    elif previous_schedule_id is not None:
        raise VaultError("首次 retention schedule 前 state 不得已有 current schedule")

    schedule_id = retention_schedule_id(
        route_binding_id=str(binding_id),
        baseline_evidence_id=str(baseline_id),
        scheduled_for=scheduled_for,
    )
    schedule_path = (
        vault / "30-learning" / "retention-schedules" / f"{schedule_id}.md"
    )
    if schedule_id in all_meta or schedule_path.exists():
        raise VaultError("同一 retention schedule receipt 已存在；拒绝覆盖")
    schedule_meta: dict[str, Any] = {
        "schema": SCHEMA,
        "schedule_contract": RETENTION_SCHEDULE_SCHEMA,
        "id": schedule_id,
        "type": "retention_schedule",
        "title": f"延迟验证排期：{state.get('concept_id')}",
        **{field: state.get(field) for field in RETENTION_SCOPE_FIELDS},
        "baseline_evidence_id": baseline_id,
        "retention_task_id": task_id,
        "route_binding_id": binding_id,
        "route_id": issuance.get("route_id"),
        "route_version": issuance.get("route_version"),
        "context_key": issuance.get("context_key"),
        "verification_task_fingerprint": task_fingerprint,
        "not_before": normalized_not_before,
        "scheduled_for": scheduled_for,
        "supersedes_schedule_id": previous_schedule_id,
        "scheduled_at": commit_at,
        "immutable": True,
        "created_at": commit_at,
        "updated_at": commit_at,
        "privacy": "sensitive",
        "tags": ["uc/retention-schedule", "uc/append-only"],
    }
    schedule_meta["receipt_fingerprint"] = sha256_fingerprint(
        _schedule_fingerprint_payload(schedule_meta)
    )
    learner_node_id = next(
        (
            node_id
            for node_id, meta in all_meta.items()
            if meta.get("type") == "learner"
            and meta.get("learner_id") == state.get("learner_id")
        ),
        None,
    )
    if not learner_node_id:
        raise VaultError("schedule-retention 无法解析 learner node")
    schedule_body = _canonical_retention_schedule_body(
        schedule_meta, learner_node_id
    )

    updated_state = dict(state)
    for field in (
        "baseline_evidence_id",
        "retention_task_id",
        "retention_route_binding_id",
        "scheduled_for",
    ):
        updated_state.pop(field, None)
    updated_state["current_retention_schedule_id"] = schedule_id
    evaluation_meta = dict(all_meta)
    evaluation_meta[schedule_id] = schedule_meta
    evaluation = evaluate_mastery_contract(
        contract,
        state_records,
        state_context=state_context_with_current_schedule(
            updated_state, evaluation_meta, strict=True
        ),
        as_of=commit_at,
        allow_synthetic_demo=allow_synthetic_demo,
    )
    if (
        evaluation.get("retention_status") not in {"pending", "due"}
        or evaluation.get("next_action")
        not in {"wait_until_scheduled_for", "issue_delayed_verification"}
    ):
        raise VaultError("schedule-retention 未能派生 pending/due 状态")
    knowledge = derive_state_knowledge_status(
        evaluation, state_records, as_of=commit_at
    )
    updated_state.update(
        {
            "mastery": knowledge["mastery"],
            "mastery_confidence": knowledge["mastery_confidence"],
            "immediate_contract_status": evaluation["immediate_contract_status"],
            "contract_status": evaluation["status"],
            "retention_status": evaluation["retention_status"],
            "next_action": evaluation["next_action"],
            "misconception_flags": knowledge["misconception_flags"],
            "diagnostic_snapshot": knowledge["diagnostic_snapshot"],
            "evaluated_at": commit_at,
            "updated_at": commit_at,
        }
    )
    updated_state["tags"] = [
        item
        for item in updated_state.get("tags", [])
        if not (isinstance(item, str) and item.startswith("uc/state/"))
    ] + [f"uc/state/{knowledge['mastery']}"]
    state_path = vault / state_node["path"]
    touched_paths = {state_path, schedule_path, vault / INDEX_REL}
    previous_images = {
        path: path.read_bytes() if path.exists() else None for path in touched_paths
    }
    # Recheck the caller's compare-and-swap guard immediately before mutation.
    current_state, _body, current_errors = parse_note(state_path)
    if current_errors or current_state.get("evaluated_at") != expected_state_evaluated_at:
        raise VaultError("schedule-retention CAS 冲突：state 在提交前已变化")
    try:
        write_note(vault, schedule_path.relative_to(vault), schedule_meta, schedule_body)
        replace_note_meta(state_path, updated_state, all_body[str(state_id)])
        _rebuilt, rebuild_errors = rebuild_index(vault)
        if rebuild_errors:
            raise VaultError(
                "schedule-retention 后索引重建失败: " + "; ".join(rebuild_errors)
            )
        final_errors, _final_warnings, final_summary = validate_vault(vault)
        if final_errors:
            raise VaultError(
                "schedule-retention 写后校验失败:\n- "
                + "\n- ".join(final_errors)
            )
    except Exception as exc:
        rollback_errors = _restore_file_images(previous_images)
        if rollback_errors:
            raise VaultError(
                "schedule-retention 失败且 byte-exact 回滚不完整: "
                + "; ".join(rollback_errors)
                + f"; original={exc}"
            ) from exc
        raise
    return {
        "status": "scheduled",
        "commit_status": "atomic_validated",
        "state_id": state_id,
        "retention_schedule_id": schedule_id,
        "schedule_fingerprint": schedule_meta["receipt_fingerprint"],
        "baseline_evidence_id": baseline_id,
        "retention_task_id": task_id,
        "retention_route_binding_id": binding_id,
        "not_before": normalized_not_before,
        "scheduled_for": scheduled_for,
        "retention_status": evaluation["retention_status"],
        "next_action": evaluation["next_action"],
        "committed_at": commit_at,
        "node_count": final_summary["node_count"],
    }


def _open_delayed_verification_legacy(vault: Path, *, state_id: str) -> dict[str, Any]:
    """Read-only projection of one due, issued, unseen A0 retention task."""

    errors, _warnings, _summary = validate_vault(vault)
    if errors:
        raise VaultError(
            "Vault 校验失败，不能公开 delayed verification:\n- "
            + "\n- ".join(errors)
        )
    index, index_errors = build_index(vault)
    if index_errors:
        raise VaultError(
            "图谱存在错误，不能公开 delayed verification: "
            + "; ".join(index_errors)
        )
    state_node = index.get("nodes", {}).get(state_id)
    if not isinstance(state_node, dict) or state_node.get("type") != "state":
        raise VaultError("open-delayed-verification state-id 不存在或不是 state")
    all_meta: dict[str, dict[str, Any]] = {}
    for node_id, node in index.get("nodes", {}).items():
        meta, _body, parse_errors = parse_note(vault / node["path"])
        if parse_errors:
            raise VaultError(f"笔记无法解析: {node_id}: {'; '.join(parse_errors)}")
        all_meta[node_id] = meta
    state = all_meta[state_id]
    goal = all_meta.get(str(state.get("goal_id")), {})
    contract = next(
        (
            item
            for item in goal.get("mastery_contracts", [])
            if isinstance(item, dict)
            and item.get("id") == state.get("contract_id")
            and item.get("version") == state.get("contract_version")
            and item.get("concept_id") == state.get("concept_id")
        ),
        None,
    )
    if not isinstance(contract, dict):
        raise VaultError("state 无唯一 mastery contract")
    supported_ids = [
        str(relation.get("target"))
        for relation in state_node.get("relations", [])
        if relation.get("type") == "supported_by"
    ]
    state_records = [
        (evidence_id, all_meta[evidence_id])
        for evidence_id in supported_ids
        if all_meta.get(evidence_id, {}).get("type") == "evidence"
    ]
    manifest = json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))
    opened_at = utc_now_precise()
    evaluation = evaluate_mastery_contract(
        contract,
        state_records,
        state_context=state_context_with_current_schedule(
            state, all_meta, strict=True
        ),
        as_of=opened_at,
        allow_synthetic_demo=trusted_synthetic_demo_authorized(vault, manifest),
    )
    if (
        evaluation.get("retention_status") != "due"
        or evaluation.get("next_action") != "issue_delayed_verification"
    ):
        raise VaultError(
            "retention 尚未 due；当前状态="
            f"{evaluation.get('retention_status')}/{evaluation.get('next_action')}"
        )
    baseline_id = state.get("baseline_evidence_id")
    if baseline_id not in set(evaluation.get("immediate_qualified_evidence_ids", [])):
        raise VaultError("retention baseline 已不再是当前即时合同的合格依据")
    baseline = all_meta.get(str(baseline_id), {})
    task_id = state.get("retention_task_id")
    binding_id = state.get("retention_route_binding_id")
    if (
        baseline.get("phase") != "verification"
        or baseline.get("result") != "pass"
        or not isinstance(task_id, str)
        or task_id == baseline.get("verification_item_id")
        or not isinstance(binding_id, str)
    ):
        raise VaultError("retention state 的 baseline/task/binding 不完整或已漂移")
    _registry, events, route_errors = load_route_binding_registry(vault, manifest)
    if route_errors:
        raise VaultError("route issuance 校验失败: " + "; ".join(route_errors))
    matching = [event for event in events if event.get("binding_id") == binding_id]
    if len(matching) != 1:
        raise VaultError("retention_route_binding_id 无唯一发行事件")
    issuance = matching[0]
    scope_fields = (
        "learner_id",
        "goal_id",
        "concept_id",
        "contract_id",
        "contract_version",
    )
    if (
        issuance.get("route_purpose") != "retention"
        or issuance.get("baseline_evidence_id")
        != schedule.get("baseline_evidence_id")
        or issuance.get("verification_task_id") != task_id
        or any(issuance.get(field) != state.get(field) for field in scope_fields)
    ):
        raise VaultError("retention issuance 的 purpose/task/scope 与 state 不一致")
    try:
        if parse_iso_instant(state.get("scheduled_for")) > parse_iso_instant(opened_at):
            raise VaultError("scheduled_for 尚未到期")
    except (TypeError, ValueError) as exc:
        if isinstance(exc, VaultError):
            raise
        raise VaultError("state scheduled_for 非法") from exc
    if any(
        evidence.get("type") == "evidence"
        and evidence.get("phase") == "retention"
        and evidence.get("verification_item_id") == task_id
        and all(evidence.get(field) == state.get(field) for field in scope_fields)
        for evidence in all_meta.values()
    ):
        raise VaultError("retention task 已有作答 evidence，不能再次作为未见题公开")
    resources = issuance.get("issuance_snapshot", {}).get("resources", [])
    matching_resources = [
        resource
        for resource in resources
        if isinstance(resource, dict)
        and isinstance(resource.get("verification_task"), dict)
        and resource["verification_task"].get("id") == task_id
    ]
    if not matching_resources:
        raise VaultError("retention issuance snapshot 缺少绑定题面")
    resource = sorted(matching_resources, key=lambda item: str(item.get("id")))[0]
    task = resource["verification_task"]
    policy = load_text_learning_policy()
    guard = policy.build_verification_content_guard(
        str(task["id"]), str(task["prompt"]), task["protected_answers"]
    )
    policy._assert_revealed_prompt_matches_guard(str(task["prompt"]), guard)
    answer_values = (
        [task["protected_answers"]]
        if isinstance(task["protected_answers"], str)
        else list(task["protected_answers"])
    )
    revealed_text = " ".join(
        (str(task["prompt"]), str(task["success_criteria"]))
    ).casefold()
    for protected_answer in answer_values:
        normalized_answer = " ".join(str(protected_answer).casefold().split())
        if normalized_answer and normalized_answer in " ".join(revealed_text.split()):
            raise VaultError("delayed verification 题面或成功标准泄漏 protected answer")
    user_task = {
        "verification_task": str(task["prompt"]),
        "response_format": "请在 A0（无提示、无答案）条件下独立作答，并写出必要解释。",
        "success_criteria": str(task["success_criteria"]),
    }
    for field, value in user_task.items():
        policy._validate_user_value(value, field)
    activity = sorted(resource.get("supported_activities", []))[0]
    teaching_item_id = retention_teaching_item_id(
        binding_id, task_id, str(state["scheduled_for"])
    )
    return {
        "status": "opened",
        "phase": "retention",
        "audience": "agent_internal_with_user_task_projection",
        "user_task": user_task,
        "retention_binding": {
            "state_id": state_id,
            "teaching_item_id": teaching_item_id,
            "baseline_evidence_id": baseline_id,
            "retention_task_id": task_id,
            "verification_item_id": task_id,
            "verification_task_id": task_id,
            "bound_verification_task_id": task_id,
            "route_id_at_observation": issuance["route_id"],
            "route_version_at_observation": issuance["route_version"],
            "route_binding_id": binding_id,
            "context_key": issuance["context_key"],
            "activity": activity,
            "carrier": resource["carrier"],
            "scheduled_for": state["scheduled_for"],
            "assistance_level": "A0",
            "independence": "independent",
        },
        "opened_at": opened_at,
    }


@vault_transaction_writer
def open_delayed_verification(vault: Path, *, state_id: str) -> dict[str, Any]:
    """Persist/reuse a due open receipt before returning the unseen A0 task."""

    errors, _warnings, _summary = validate_vault(vault)
    if errors:
        raise VaultError(
            "Vault 校验失败，不能公开 delayed verification:\n- "
            + "\n- ".join(errors)
        )
    index, index_errors = build_index(vault)
    if index_errors:
        raise VaultError(
            "图谱存在错误，不能公开 delayed verification: "
            + "; ".join(index_errors)
        )
    state_node = index.get("nodes", {}).get(state_id)
    if not isinstance(state_node, dict) or state_node.get("type") != "state":
        raise VaultError("open-delayed-verification state-id 不存在或不是 state")
    all_meta: dict[str, dict[str, Any]] = {}
    for node_id, node in index.get("nodes", {}).items():
        meta, _body, parse_errors = parse_note(vault / node["path"])
        if parse_errors:
            raise VaultError(f"笔记无法解析: {node_id}: {'; '.join(parse_errors)}")
        all_meta[node_id] = meta
    state = all_meta[state_id]
    schedule_id = state.get("current_retention_schedule_id")
    schedule = all_meta.get(str(schedule_id), {})
    if schedule.get("type") != "retention_schedule":
        raise VaultError("state 没有可解析的 current retention schedule receipt")
    if any(schedule.get(field) != state.get(field) for field in RETENTION_SCOPE_FIELDS):
        raise VaultError("current retention schedule 与 state scope 不一致")
    goal = all_meta.get(str(state.get("goal_id")), {})
    contract = next(
        (
            item
            for item in goal.get("mastery_contracts", [])
            if isinstance(item, dict)
            and item.get("id") == state.get("contract_id")
            and item.get("version") == state.get("contract_version")
            and item.get("concept_id") == state.get("concept_id")
        ),
        None,
    )
    if not isinstance(contract, dict):
        raise VaultError("state 无唯一 mastery contract")
    supported_ids = [
        str(relation.get("target"))
        for relation in state_node.get("relations", [])
        if relation.get("type") == "supported_by"
    ]
    state_records = [
        (evidence_id, all_meta[evidence_id])
        for evidence_id in supported_ids
        if all_meta.get(evidence_id, {}).get("type") == "evidence"
    ]
    opened_at = utc_now_precise()
    opened_instant = parse_iso_instant(opened_at)
    manifest = json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))
    evaluation = evaluate_mastery_contract(
        contract,
        state_records,
        state_context=state_context_with_current_schedule(
            state, all_meta, strict=True
        ),
        as_of=opened_at,
        allow_synthetic_demo=trusted_synthetic_demo_authorized(vault, manifest),
    )
    if (
        evaluation.get("retention_status") != "due"
        or evaluation.get("next_action") != "issue_delayed_verification"
    ):
        raise VaultError(
            "retention 尚未 due；当前状态="
            f"{evaluation.get('retention_status')}/{evaluation.get('next_action')}"
        )
    baseline_id = str(schedule.get("baseline_evidence_id"))
    baseline = all_meta.get(baseline_id, {})
    if (
        baseline_id
        not in set(evaluation.get("immediate_qualified_evidence_ids", []))
        or not _qualified_verification_baseline(
            baseline,
            state,
            allow_synthetic_demo=trusted_synthetic_demo_authorized(vault, manifest),
        )
    ):
        raise VaultError("retention schedule baseline 已不再是合格即时验证")
    try:
        if parse_iso_instant(schedule.get("scheduled_for")) > opened_instant:
            raise VaultError("scheduled_for 尚未到期")
        if parse_iso_instant(schedule.get("scheduled_at")) > opened_instant:
            raise VaultError("真实 wall clock 早于 schedule.scheduled_at；拒绝开题")
    except (TypeError, ValueError) as exc:
        if isinstance(exc, VaultError):
            raise
        raise VaultError("schedule scheduled_for 非法") from exc

    _registry, events, route_errors = load_route_binding_registry(vault, manifest)
    if route_errors:
        raise VaultError("route issuance 校验失败: " + "; ".join(route_errors))
    matches = [
        event
        for event in events
        if event.get("binding_id") == schedule.get("route_binding_id")
    ]
    if len(matches) != 1:
        raise VaultError("schedule route_binding_id 无唯一发行事件")
    issuance = matches[0]
    task_id = str(schedule.get("retention_task_id"))
    if (
        issuance.get("route_purpose") != "retention"
        or issuance.get("verification_task_id") != task_id
        or issuance.get("verification_task_fingerprint")
        != schedule.get("verification_task_fingerprint")
        or any(issuance.get(field) != state.get(field) for field in RETENTION_SCOPE_FIELDS)
    ):
        raise VaultError("retention issuance purpose/task/fingerprint/scope 漂移")
    expected_open_id = verification_open_id(str(schedule_id))
    evidence_consumers = [
        node_id
        for node_id, meta in all_meta.items()
        if meta.get("type") == "evidence"
        and meta.get("phase") in {"verification", "retention"}
        and meta.get("verification_item_id") == task_id
        and all(meta.get(field) == state.get(field) for field in RETENTION_SCOPE_FIELDS)
    ]
    if evidence_consumers:
        raise VaultError(
            "retention task 已被 verification/retention evidence 消费: "
            + ",".join(sorted(evidence_consumers))
        )
    same_task_opens = [
        (node_id, meta)
        for node_id, meta in all_meta.items()
        if meta.get("type") == "verification_open"
        and meta.get("retention_task_id") == task_id
        and all(meta.get(field) == state.get(field) for field in RETENTION_SCOPE_FIELDS)
    ]
    existing_open = all_meta.get(expected_open_id)
    if same_task_opens and (
        len(same_task_opens) != 1 or same_task_opens[0][0] != expected_open_id
    ):
        raise VaultError("同 scope retention task 已被其他 verification_open 消费")

    resources = issuance.get("issuance_snapshot", {}).get("resources", [])
    matching_resources = [
        resource
        for resource in resources
        if isinstance(resource, dict)
        and isinstance(resource.get("verification_task"), dict)
        and resource["verification_task"].get("id") == task_id
    ]
    if len(matching_resources) != 1:
        raise VaultError("retention issuance snapshot 缺少唯一绑定题面")
    resource = matching_resources[0]
    task = resource["verification_task"]
    policy = load_text_learning_policy()
    guard = policy.build_verification_content_guard(
        str(task["id"]), str(task["prompt"]), task["protected_answers"]
    )
    policy._assert_revealed_prompt_matches_guard(str(task["prompt"]), guard)
    answer_values = (
        [task["protected_answers"]]
        if isinstance(task["protected_answers"], str)
        else list(task["protected_answers"])
    )
    revealed_text = " ".join(
        (str(task["prompt"]), str(task["success_criteria"]))
    ).casefold()
    for protected_answer in answer_values:
        normalized_answer = " ".join(str(protected_answer).casefold().split())
        if normalized_answer and normalized_answer in " ".join(revealed_text.split()):
            raise VaultError("delayed verification 题面或成功标准泄漏 protected answer")
    user_task = {
        "verification_task": str(task["prompt"]),
        "response_format": "请在 A0（无提示、无答案）条件下独立作答，并写出必要解释。",
        "success_criteria": str(task["success_criteria"]),
    }
    for field, value in user_task.items():
        policy._validate_user_value(value, field)
    activity = sorted(resource.get("supported_activities", []))[0]

    commit_status = "idempotent_reuse"
    receipt = existing_open if isinstance(existing_open, dict) else None
    if receipt is None:
        receipt = {
            "schema": SCHEMA,
            "open_contract": VERIFICATION_OPEN_SCHEMA,
            "id": expected_open_id,
            "type": "verification_open",
            "title": f"延迟验证开题：{state.get('concept_id')}",
            **{field: state.get(field) for field in RETENTION_SCOPE_FIELDS},
            "retention_schedule_id": schedule_id,
            "baseline_evidence_id": schedule.get("baseline_evidence_id"),
            "retention_task_id": task_id,
            "route_binding_id": schedule.get("route_binding_id"),
            "route_id": schedule.get("route_id"),
            "route_version": schedule.get("route_version"),
            "context_key": schedule.get("context_key"),
            "verification_task_fingerprint": schedule.get(
                "verification_task_fingerprint"
            ),
            "schedule_fingerprint": schedule.get("receipt_fingerprint"),
            "resource_id": resource.get("id"),
            "activity": activity,
            "carrier": resource.get("carrier"),
            "scheduled_for": schedule.get("scheduled_for"),
            "opened_at": opened_at,
            "immutable": True,
            "created_at": opened_at,
            "updated_at": opened_at,
            "privacy": "sensitive",
            "tags": ["uc/verification-open", "uc/append-only"],
        }
        receipt["receipt_fingerprint"] = sha256_fingerprint(
            _open_fingerprint_payload(receipt)
        )
        learner_node_id = next(
            (
                node_id
                for node_id, meta in all_meta.items()
                if meta.get("type") == "learner"
                and meta.get("learner_id") == state.get("learner_id")
            ),
            None,
        )
        if not learner_node_id:
            raise VaultError("open-delayed 无法解析 learner node")
        receipt_body = _canonical_verification_open_body(
            receipt, learner_node_id
        )
        receipt_path = (
            vault
            / "30-learning"
            / "verification-opens"
            / f"{expected_open_id}.md"
        )
        touched_paths = {receipt_path, vault / INDEX_REL}
        previous_images = {
            path: path.read_bytes() if path.exists() else None
            for path in touched_paths
        }
        try:
            write_note(vault, receipt_path.relative_to(vault), receipt, receipt_body)
            _rebuilt, rebuild_errors = rebuild_index(vault)
            if rebuild_errors:
                raise VaultError(
                    "open-delayed 后索引重建失败: " + "; ".join(rebuild_errors)
                )
            final_errors, _final_warnings, final_summary = validate_vault(vault)
            if final_errors:
                raise VaultError(
                    "open-delayed 写后校验失败:\n- " + "\n- ".join(final_errors)
                )
        except Exception as exc:
            rollback_errors = _restore_file_images(previous_images)
            if rollback_errors:
                raise VaultError(
                    "open-delayed 失败且 byte-exact 回滚不完整: "
                    + "; ".join(rollback_errors)
                    + f"; original={exc}"
                ) from exc
            raise
        commit_status = "atomic_validated"
        node_count = final_summary["node_count"]
    else:
        expected_fields = {
            **{field: schedule.get(field) for field in RETENTION_SCOPE_FIELDS},
            "retention_schedule_id": schedule_id,
            "baseline_evidence_id": schedule.get("baseline_evidence_id"),
            "retention_task_id": task_id,
            "route_binding_id": schedule.get("route_binding_id"),
            "route_id": schedule.get("route_id"),
            "route_version": schedule.get("route_version"),
            "context_key": schedule.get("context_key"),
            "verification_task_fingerprint": schedule.get(
                "verification_task_fingerprint"
            ),
            "schedule_fingerprint": schedule.get("receipt_fingerprint"),
            "resource_id": resource.get("id"),
            "activity": activity,
            "carrier": resource.get("carrier"),
            "scheduled_for": schedule.get("scheduled_for"),
        }
        if any(receipt.get(field) != value for field, value in expected_fields.items()):
            raise VaultError("existing verification_open receipt 与当前 schedule/issuance 漂移")
        node_count = index.get("node_count", 0)

    return {
        "status": "opened" if commit_status == "atomic_validated" else "already_opened",
        "commit_status": commit_status,
        "phase": "retention",
        "audience": "agent_internal_with_user_task_projection",
        "user_task": user_task,
        "retention_binding": {
            "state_id": state_id,
            "teaching_item_id": expected_open_id,
            "retention_schedule_id": schedule_id,
            "verification_open_id": expected_open_id,
            "baseline_evidence_id": schedule.get("baseline_evidence_id"),
            "retention_task_id": task_id,
            "verification_item_id": task_id,
            "verification_task_id": task_id,
            "bound_verification_task_id": task_id,
            "route_id_at_observation": schedule.get("route_id"),
            "route_version_at_observation": schedule.get("route_version"),
            "route_binding_id": schedule.get("route_binding_id"),
            "context_key": schedule.get("context_key"),
            "activity": activity,
            "carrier": resource.get("carrier"),
            "scheduled_for": schedule.get("scheduled_for"),
            "assistance_level": "A0",
            "independence": "independent",
        },
        "opened_at": receipt.get("opened_at"),
        "node_count": node_count,
    }


@vault_transaction_writer
def append_evidence(vault: Path, *, record_path: Path) -> dict[str, Any]:
    """Atomically append one canonical observation and recompute its consumers.

    The JSON input is deliberately raw-only.  Provenance, route authority,
    confidence, mastery eligibility, consumers, bindings, state, boundary and
    Focus invalidation are all derived inside this transaction.
    """

    validation_errors, _warnings, _summary = validate_vault(vault)
    if validation_errors:
        raise VaultError(
            "Vault 校验失败，不能追加 evidence:\n- "
            + "\n- ".join(validation_errors)
        )
    try:
        payload = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VaultError(f"evidence JSON 无法读取: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "source_session_id",
        "evidence",
    }:
        raise VaultError(
            "evidence JSON 顶层必须且只能包含 source_session_id 与 evidence"
        )
    source_session_id = payload.get("source_session_id")
    raw = payload.get("evidence")
    if not isinstance(source_session_id, str) or not source_session_id.strip():
        raise VaultError("source_session_id 必须是非空字符串")
    if not isinstance(raw, dict):
        raise VaultError("evidence 必须是对象")
    missing_fields = sorted(APPEND_EVIDENCE_RAW_FIELDS.difference(raw))
    unknown_fields = sorted(set(raw).difference(APPEND_EVIDENCE_RAW_FIELDS))
    if missing_fields or unknown_fields:
        raise VaultError(
            "evidence 原始字段合同不一致"
            + (f"; missing={','.join(missing_fields)}" if missing_fields else "")
            + (f"; unknown={','.join(unknown_fields)}" if unknown_fields else "")
        )

    evidence_id = raw.get("id")
    if not isinstance(evidence_id, str) or not re.fullmatch(
        r"ev-[a-z0-9][a-z0-9-]{1,95}", evidence_id
    ):
        raise VaultError("evidence.id 必须是 ev- 开头的 4..99 位小写 ASCII 安全 ID")
    summary_text = raw.get("summary")
    if (
        not isinstance(summary_text, str)
        or not summary_text.strip()
        or "\n" in summary_text
        or "\r" in summary_text
        or "[[" in summary_text
    ):
        raise VaultError("evidence.summary 必须是无 Wikilink 的非空单行文本")
    phase = raw.get("phase")
    if phase not in EVIDENCE_PHASE_VALUES:
        raise VaultError(f"evidence.phase 非法: {phase}")
    if raw.get("observation_validity") != "valid":
        raise VaultError("append-evidence 当前只提交 validity=valid 的 canonical observation")

    phase_sentinels: dict[str, dict[str, Any]] = {
        "diagnostic": {
            "teaching_delivery_fingerprint_at_observation": None,
            "verification_item_id": None,
            "verification_task_id": None,
            "bound_verification_task_id": None,
            "decision_fingerprint_at_observation": None,
            "verification_unseen": False,
            "answer_revealed_before_first_attempt": False,
            "near_transfer": "not_tested",
            "delayed_retention": "not_tested",
            "baseline_evidence_id": None,
            "retention_task_id": None,
            "scheduled_for": None,
        },
        "teaching_process": {
            "verification_item_id": None,
            "verification_unseen": False,
            "answer_revealed_before_first_attempt": False,
            "independence": "not_observed",
            "near_transfer": "not_tested",
            "delayed_retention": "not_tested",
            "baseline_evidence_id": None,
            "retention_task_id": None,
            "scheduled_for": None,
        },
        "verification": {
            "teaching_delivery_fingerprint_at_observation": None,
            "decision_fingerprint_at_observation": None,
            "delayed_retention": "not_tested",
            "baseline_evidence_id": None,
            "retention_task_id": None,
            "scheduled_for": None,
        },
        "retention": {
            "teaching_delivery_fingerprint_at_observation": None,
            "decision_fingerprint_at_observation": None,
            "near_transfer": "not_tested",
            "explanation_quality": "not_tested",
        },
    }
    sentinel_mismatches = [
        f"{field}={raw.get(field)!r} expected={expected!r}"
        for field, expected in phase_sentinels[str(phase)].items()
        if raw.get(field) != expected
    ]
    if sentinel_mismatches:
        raise VaultError(
            f"{phase} 原始记录含跨阶段值: " + "; ".join(sentinel_mismatches)
        )

    commit_at = utc_now_precise()
    try:
        observed_instant = parse_iso_instant(raw.get("observed_at"))
        commit_instant = parse_iso_instant(commit_at)
    except (TypeError, ValueError) as exc:
        raise VaultError("observed_at 必须是带时区 ISO 时间") from exc
    if observed_instant > commit_instant:
        raise VaultError("observed_at 不得晚于 append-evidence 的真实 wall clock")
    observed_at = observed_instant.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )

    index, index_errors = build_index(vault)
    if index_errors:
        raise VaultError("图谱存在错误，不能追加 evidence: " + "; ".join(index_errors))
    if evidence_id in index.get("nodes", {}):
        raise VaultError("evidence.id 已存在；append-only 记录不得覆盖或重放")
    all_meta: dict[str, dict[str, Any]] = {}
    all_body: dict[str, str] = {}
    for node_id, node in index.get("nodes", {}).items():
        meta, body, parse_errors = parse_note(vault / node["path"])
        if parse_errors:
            raise VaultError(f"笔记无法解析: {node_id}: {'; '.join(parse_errors)}")
        all_meta[node_id] = meta
        all_body[node_id] = body

    session = all_meta.get(source_session_id, {})
    if session.get("type") != "session":
        raise VaultError("source_session_id 不存在或不是 canonical session")
    scope = {
        "learner_id": raw.get("learner_id"),
        "goal_id": raw.get("goal_id"),
        "concept_id": raw.get("concept_id"),
        "contract_id": raw.get("contract_id"),
        "contract_version": raw.get("contract_version"),
    }
    if (
        session.get("learner_id") != scope["learner_id"]
        or session.get("goal_id") != scope["goal_id"]
    ):
        raise VaultError("canonical session 与 evidence learner/goal scope 不一致")
    source_kind = session.get("source_kind")
    source_ref = session.get("source_ref")
    if (
        not isinstance(source_kind, str)
        or not source_kind.strip()
        or not isinstance(source_ref, str)
        or not source_ref.strip()
    ):
        raise VaultError("canonical session 缺少可派生的 source_kind/source_ref")

    state_matches = [
        (node_id, meta)
        for node_id, meta in all_meta.items()
        if meta.get("type") == "state"
        and all(meta.get(field) == value for field, value in scope.items())
    ]
    if len(state_matches) != 1:
        raise VaultError("evidence 必须唯一解析到同 scope state")
    state_id, state = state_matches[0]
    goal = all_meta.get(str(scope["goal_id"]), {})
    contracts = [
        item
        for item in goal.get("mastery_contracts", [])
        if isinstance(item, dict)
        and item.get("id") == scope["contract_id"]
        and item.get("version") == scope["contract_version"]
        and item.get("concept_id") == scope["concept_id"]
    ]
    if len(contracts) != 1:
        raise VaultError("evidence 无唯一同 scope mastery contract")
    contract = contracts[0]

    manifest = json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))
    route_registry, _route_events, route_errors = load_route_binding_registry(
        vault, manifest
    )
    if route_errors:
        raise VaultError("route issuance 校验失败: " + "; ".join(route_errors))
    route_key = (
        str(scope["learner_id"]),
        str(scope["goal_id"]),
        str(scope["concept_id"]),
        str(scope["contract_id"]),
        scope["contract_version"]
        if isinstance(scope["contract_version"], int)
        and not isinstance(scope["contract_version"], bool)
        else -1,
        str(raw.get("route_id_at_observation")),
        raw.get("route_version_at_observation")
        if isinstance(raw.get("route_version_at_observation"), int)
        and not isinstance(raw.get("route_version_at_observation"), bool)
        else -1,
    )
    issuance = route_registry.get(route_key)
    if issuance is None:
        raise VaultError("evidence 无法绑定 immutable route issuance")
    expected_route_purpose = "retention" if phase == "retention" else "learning"
    if issuance.get("route_purpose") != expected_route_purpose:
        raise VaultError(
            f"append-evidence {phase} 必须绑定 purpose={expected_route_purpose} 的本地发行事件"
        )
    try:
        if observed_instant < parse_iso_instant(issuance.get("issued_at")):
            raise VaultError("evidence observed_at 早于 route issuance")
    except (TypeError, ValueError) as exc:
        if isinstance(exc, VaultError):
            raise
        raise VaultError("route issuance issued_at 非法") from exc
    issued_task_id = issuance.get("verification_task_id")
    if phase in {"teaching_process", "verification", "retention"} and (
        raw.get("verification_task_id") != issued_task_id
        or raw.get("bound_verification_task_id") != issued_task_id
    ):
        raise VaultError(
            f"{phase} 必须精确绑定 route issuance verification_task_id/bound"
        )
    if phase in {"verification", "retention"} and raw.get(
        "verification_item_id"
    ) != issued_task_id:
        raise VaultError("verification/retention item 必须等于已签发验证任务")
    if phase == "retention":
        open_id = raw.get("teaching_item_id")
        opened = all_meta.get(str(open_id), {})
        if opened.get("type") != "verification_open":
            raise VaultError(
                "retention teaching_item_id 必须引用已原子落盘的 verification_open receipt"
            )
        schedule = all_meta.get(str(opened.get("retention_schedule_id")), {})
        if schedule.get("type") != "retention_schedule":
            raise VaultError("verification_open 未绑定有效 retention_schedule receipt")
        copied_fields = (
            *RETENTION_SCOPE_FIELDS,
            "baseline_evidence_id",
            "retention_task_id",
            "scheduled_for",
        )
        if (
            any(opened.get(field) != raw.get(field) for field in copied_fields)
            or opened.get("route_binding_id") != issuance.get("binding_id")
            or opened.get("route_id") != raw.get("route_id_at_observation")
            or opened.get("route_version")
            != raw.get("route_version_at_observation")
            or opened.get("context_key") != issuance.get("context_key")
            or opened.get("activity") != raw.get("activity")
            or opened.get("carrier") != raw.get("carrier")
            or raw.get("retention_task_id") != issued_task_id
            or schedule.get("receipt_fingerprint")
            != opened.get("schedule_fingerprint")
        ):
            raise VaultError(
                "retention evidence 必须精确复制 open→schedule→issuance binding"
            )
        try:
            if parse_iso_instant(opened.get("opened_at")) >= observed_instant:
                raise VaultError(
                    "retention observed_at 必须真实晚于 verification_open.opened_at"
                )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, VaultError):
                raise
            raise VaultError("verification_open opened_at 非法") from exc

    active_intervention_id: str | None = None
    if phase == "teaching_process":
        active_matches = [
            (node_id, meta)
            for node_id, meta in all_meta.items()
            if meta.get("type") == "intervention"
            and meta.get("status") == "active"
            and meta.get("learner_id") == scope["learner_id"]
            and meta.get("goal_id") == scope["goal_id"]
            and meta.get("current_checkpoint") == scope["concept_id"]
            and meta.get("route_id") == raw.get("route_id_at_observation")
            and meta.get("route_version") == raw.get(
                "route_version_at_observation"
            )
        ]
        if len(active_matches) != 1:
            raise VaultError("teaching_process 必须绑定唯一当前 active route checkpoint")
        active_intervention_id, active_intervention = active_matches[0]
        decision_fingerprint = raw.get("decision_fingerprint_at_observation")
        if (
            not isinstance(decision_fingerprint, str)
            or not re.fullmatch(r"[0-9a-f]{64}", decision_fingerprint)
            or decision_fingerprint
            != active_intervention.get("resolved_decision_fingerprint")
        ):
            raise VaultError("teaching_process 未绑定当前 resolved decision fingerprint")
        delivery_id = raw.get("teaching_item_id")
        delivery = all_meta.get(str(delivery_id), {})
        delivery_fingerprint = raw.get(
            "teaching_delivery_fingerprint_at_observation"
        )
        if (
            delivery.get("type") != "teaching_delivery"
            or delivery.get("delivery_plan_fingerprint") != delivery_fingerprint
            or delivery.get("decision_fingerprint") != decision_fingerprint
            or delivery.get("route_binding_id") != issuance.get("binding_id")
            or delivery.get("context_key") != issuance.get("context_key")
            or delivery.get("activity") != raw.get("activity")
            or delivery.get("carrier") != raw.get("carrier")
            or any(delivery.get(field) != value for field, value in scope.items())
        ):
            raise VaultError(
                "teaching_process 未精确绑定 teaching_delivery id/content/decision/scope"
            )
        try:
            if observed_instant <= parse_iso_instant(delivery.get("issued_at")):
                raise VaultError(
                    "teaching_process observed_at 必须真实晚于 teaching_delivery issued_at"
                )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, VaultError):
                raise
            raise VaultError("teaching_delivery issued_at 非法") from exc

    meta: dict[str, Any] = {
        "schema": SCHEMA,
        "id": evidence_id,
        "type": "evidence",
        "title": f"证据：{scope['concept_id']} / {raw['evidence_kind']}",
        **scope,
        "phase": phase,
        "carrier": raw.get("carrier"),
        "teaching_item_id": raw.get("teaching_item_id"),
        "teaching_delivery_fingerprint_at_observation": raw.get(
            "teaching_delivery_fingerprint_at_observation"
        ),
        "verification_item_id": raw.get("verification_item_id"),
        "verification_unseen": raw.get("verification_unseen"),
        "answer_revealed_before_first_attempt": raw.get(
            "answer_revealed_before_first_attempt"
        ),
        "verification_task_id": raw.get("verification_task_id"),
        "bound_verification_task_id": raw.get("bound_verification_task_id"),
        "route_id_at_observation": raw.get("route_id_at_observation"),
        "route_version_at_observation": raw.get("route_version_at_observation"),
        "decision_fingerprint_at_observation": raw.get(
            "decision_fingerprint_at_observation"
        ),
        "context_key": issuance["context_key"],
        "route_binding_id": issuance["binding_id"],
        "source_kind": source_kind,
        "source_ref_ids": [source_ref],
        "observation_validity": raw.get("observation_validity"),
        "evidence_kind": raw.get("evidence_kind"),
        "demonstrates": raw.get("demonstrates"),
        "result": raw.get("result"),
        "independence": raw.get("independence"),
        "assistance_level": raw.get("assistance_level"),
        "activity": raw.get("activity"),
        "error_signature": raw.get("error_signature"),
        "elapsed_seconds": raw.get("elapsed_seconds"),
        "attempts": raw.get("attempts"),
        "hint_count": raw.get("hint_count"),
        "immediate_performance": raw.get("immediate_performance"),
        "near_transfer": raw.get("near_transfer"),
        "delayed_retention": raw.get("delayed_retention"),
        "response_correct": raw.get("response_correct"),
        "explanation_quality": raw.get("explanation_quality"),
        "self_reported_effort": raw.get("self_reported_effort"),
        "baseline_evidence_id": raw.get("baseline_evidence_id"),
        "retention_task_id": raw.get("retention_task_id"),
        "scheduled_for": raw.get("scheduled_for"),
        "observed_at": observed_at,
        "retention_delay_days": 0,
        "mastery_eligible": False,
        "consumer_ids": [],
        "field_bindings": {},
        "created_at": commit_at,
        "updated_at": commit_at,
        "privacy": "sensitive",
        "tags": ["uc/evidence", "uc/append-only"],
    }
    existing_evidence_meta = {
        node_id: item
        for node_id, item in all_meta.items()
        if item.get("type") == "evidence"
    }
    if phase == "retention":
        derived_delay = derived_retention_delay_days(meta, existing_evidence_meta)
        if derived_delay is None:
            raise VaultError(
                "retention_delay_days 无法由同 scope baseline evidence 与 observed_at 推导"
            )
        meta["retention_delay_days"] = derived_delay

    def derived_consumers(record: dict[str, Any]) -> list[str]:
        return sorted(
            {
                consumer
                for field in EVIDENCE_FIELD_CONSUMERS
                if evidence_field_is_actionable(record, field)
                for consumer in evidence_field_consumers_for_phase(record, field)
            }
        )

    meta["consumer_ids"] = derived_consumers(meta)
    allow_synthetic_demo = trusted_synthetic_demo_authorized(vault, manifest)
    derived_eligible, _eligibility_failures = evidence_mastery_eligibility(
        meta, allow_synthetic_demo=allow_synthetic_demo
    )
    meta["mastery_eligible"] = derived_eligible
    (
        meta["observation_confidence"],
        meta["observation_confidence_basis"],
    ) = derive_observation_confidence(
        meta,
        derived_mastery_eligible=derived_eligible,
        allow_synthetic_demo=allow_synthetic_demo,
    )
    meta["consumer_ids"] = derived_consumers(meta)
    meta["field_bindings"] = build_evidence_field_bindings(meta)

    state_relations = index["nodes"][state_id].get("relations", [])
    supported_ids = [
        str(relation["target"])
        for relation in state_relations
        if relation.get("type") == "supported_by"
    ]
    state_records = [
        (item_id, all_meta[item_id])
        for item_id in supported_ids
        if all_meta.get(item_id, {}).get("type") == "evidence"
    ] + [(evidence_id, meta)]
    evaluation = evaluate_mastery_contract(
        contract,
        state_records,
        state_context=state_context_with_current_schedule(
            state, all_meta, strict=True
        ),
        as_of=commit_at,
        allow_synthetic_demo=allow_synthetic_demo,
    )
    knowledge = derive_state_knowledge_status(
        evaluation, state_records, as_of=commit_at
    )
    evidence_times = [
        (item_id, item, parse_iso_instant(item.get("observed_at")))
        for item_id, item in state_records
    ]
    latest_supported_at = max(item[2] for item in evidence_times)
    independent_times = [
        item[2]
        for item in evidence_times
        if item[1].get("independence") == "independent"
        and item[1].get("assistance_level") == "A0"
    ]

    updated_target_state = dict(state)
    updated_target_state.update(
        {
            "mastery": knowledge["mastery"],
            "mastery_confidence": knowledge["mastery_confidence"],
            "immediate_contract_status": evaluation[
                "immediate_contract_status"
            ],
            "contract_status": evaluation["status"],
            "retention_status": evaluation["retention_status"],
            "next_action": evaluation["next_action"],
            "as_of": latest_supported_at.isoformat().replace("+00:00", "Z"),
            "evaluated_at": commit_at,
            "last_independent_evidence_at": (
                max(independent_times).isoformat().replace("+00:00", "Z")
                if independent_times
                else None
            ),
            "boundary_derived_at": latest_supported_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "last_assessed_at": latest_supported_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "misconception_flags": knowledge["misconception_flags"],
            "diagnostic_snapshot": knowledge["diagnostic_snapshot"],
            "updated_at": commit_at,
        }
    )
    updated_target_state["tags"] = [
        item
        for item in updated_target_state.get("tags", [])
        if not (isinstance(item, str) and item.startswith("uc/state/"))
    ] + [f"uc/state/{knowledge['mastery']}"]

    scoped_states = {
        node_id: dict(item)
        for node_id, item in all_meta.items()
        if item.get("type") == "state"
        and item.get("learner_id") == scope["learner_id"]
        and item.get("goal_id") == scope["goal_id"]
    }
    scoped_states[state_id] = updated_target_state
    concept_relations = {
        node_id: list(index["nodes"][node_id].get("relations", []))
        for node_id, item in all_meta.items()
        if item.get("type") == "concept"
    }
    derived_boundaries = derive_boundary_positions(
        concept_relations,
        {
            str(item["concept_id"]): str(item["mastery"])
            for item in scoped_states.values()
        },
    )
    updated_states: dict[str, dict[str, Any]] = {}
    boundary_changed_ids: list[str] = []
    for node_id, state_meta in scoped_states.items():
        expected_boundary = derived_boundaries.get(str(state_meta.get("concept_id")))
        if node_id == state_id or state_meta.get("boundary_position") != expected_boundary:
            candidate = dict(state_meta)
            candidate["boundary_position"] = expected_boundary
            candidate["updated_at"] = commit_at
            updated_states[node_id] = candidate
        if all_meta[node_id].get("boundary_position") != expected_boundary:
            boundary_changed_ids.append(node_id)

    focus_updates: dict[str, dict[str, Any]] = {}
    for node_id, item in all_meta.items():
        if (
            item.get("type") == "focus_snapshot"
            and item.get("learner_id") == scope["learner_id"]
            and item.get("goal_id") == scope["goal_id"]
        ):
            stale = dict(item)
            stale.update(
                {
                    "ranking_status": "stale",
                    "focus_z": None,
                    "validity": "stale",
                    "used_in_decision": False,
                    "selection_basis": "not_used",
                    "updated_at": commit_at,
                }
            )
            focus_updates[node_id] = stale

    evidence_path = vault / "20-learner" / "evidence" / f"{evidence_id}.md"
    touched_paths: set[Path] = {
        evidence_path,
        vault / INDEX_REL,
        *(vault / index["nodes"][node_id]["path"] for node_id in updated_states),
        *(vault / index["nodes"][node_id]["path"] for node_id in focus_updates),
    }
    if active_intervention_id is not None:
        touched_paths.add(vault / index["nodes"][active_intervention_id]["path"])
    previous_images = {
        path: path.read_bytes() if path.exists() else None for path in touched_paths
    }

    active_resolution_status = "not_applicable"
    try:
        evidence_body = (
            f"# {meta['title']}\n\n{summary_text.strip()}\n\n"
            + relation_lines(
                [
                    {"type": "about", "target": str(scope["concept_id"])},
                    {"type": "derived_from", "target": source_session_id},
                ]
            )
        )
        write_note(
            vault,
            evidence_path.relative_to(vault),
            meta,
            evidence_body,
        )
        for node_id, state_meta in updated_states.items():
            state_body = all_body[node_id]
            if node_id == state_id:
                state_body = _append_relation(
                    state_body, "supported_by", evidence_id
                )
            replace_note_meta(
                vault / index["nodes"][node_id]["path"], state_meta, state_body
            )
        for node_id, focus_meta in focus_updates.items():
            replace_note_meta(
                vault / index["nodes"][node_id]["path"],
                focus_meta,
                all_body[node_id],
            )
        _rebuilt, rebuild_errors = rebuild_index(vault)
        if rebuild_errors:
            raise VaultError(
                "append-evidence 后索引重建失败: " + "; ".join(rebuild_errors)
            )
        mid_errors, _mid_warnings, _mid_summary = validate_vault(
            vault, allow_unresolved_teaching=True
        )
        if mid_errors:
            raise VaultError(
                "append-evidence 派生状态未通过校验:\n- "
                + "\n- ".join(mid_errors)
            )
        if phase == "teaching_process":
            resolve_active_teaching(
                vault, write=True, _preserve_decision_epoch=True
            )
            active_resolution_status = "process_refreshed_epoch_preserved"
        final_errors, _final_warnings, final_summary = validate_vault(vault)
        if final_errors:
            raise VaultError(
                "append-evidence 完整事务未通过校验:\n- "
                + "\n- ".join(final_errors)
            )
    except Exception as exc:
        rollback_errors = _restore_file_images(previous_images)
        if rollback_errors:
            raise VaultError(
                "append-evidence 失败且精确回滚不完整: "
                + "; ".join(rollback_errors)
                + f"; original={exc}"
            ) from exc
        raise

    full_contract_completed = bool(
        phase in {"verification", "retention"} and evaluation["status"] == "met"
    )
    goal_target_ids = {
        str(relation["target"])
        for relation in index["nodes"][str(scope["goal_id"])].get(
            "relations", []
        )
        if relation.get("type") == "targets"
    }
    scoped_state_by_concept = {
        str(item.get("concept_id")): item for item in scoped_states.values()
    }
    all_targets_complete = bool(goal_target_ids) and all(
        scoped_state_by_concept.get(target_id, {}).get("mastery") == "mastered"
        and scoped_state_by_concept.get(target_id, {}).get("contract_status") == "met"
        for target_id in goal_target_ids
    )
    goal_complete = bool(full_contract_completed and all_targets_complete)
    route_reissue_required = bool(full_contract_completed and not goal_complete)
    return {
        "status": "committed",
        "commit_status": "atomic_validated",
        "evidence_id": evidence_id,
        "phase": phase,
        "state_id": state_id,
        "state_mastery": knowledge["mastery"],
        "contract_status": evaluation["status"],
        "immediate_contract_status": evaluation["immediate_contract_status"],
        "retention_status": evaluation["retention_status"],
        "next_action": evaluation["next_action"],
        "boundary_recomputed_count": len(scoped_states),
        "boundary_changed_state_ids": sorted(boundary_changed_ids),
        "focus_stale_ids": sorted(focus_updates),
        "active_resolution_status": active_resolution_status,
        "route_transition_status": (
            "goal_complete"
            if goal_complete
            else "route_reissue_required"
            if route_reissue_required
            else "unchanged"
        ),
        "route_reissue_required": route_reissue_required,
        "goal_complete": goal_complete,
        "route_mutated": False,
        "committed_at": commit_at,
        "node_count": final_summary["node_count"],
    }


@vault_transaction_writer
def project_verification_task_from_vault(
    vault: Path, *, process_evidence_id: str
) -> dict[str, str]:
    """Open the bound unseen task only from committed, post-decision process evidence."""

    errors, _warnings, _summary = validate_vault(vault)
    if errors:
        raise VaultError(
            "Vault 校验失败，不能公开验证题:\n- " + "\n- ".join(errors)
        )
    index, index_errors = build_index(vault)
    if index_errors:
        raise VaultError("图谱存在错误，不能公开验证题: " + "; ".join(index_errors))
    manifest = json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))
    active_learner_node = index.get("nodes", {}).get(
        str(manifest.get("active_learner_id")), {}
    )
    active_learner_meta = (
        parse_note(vault / active_learner_node["path"])[0]
        if isinstance(active_learner_node, dict) and active_learner_node.get("path")
        else {}
    )
    active_learner_id = active_learner_meta.get("learner_id")
    active_goal_id = manifest.get("active_goal_id")
    active_interventions = [
        node_id
        for node_id, node in index.get("nodes", {}).items()
        if node.get("type") == "intervention"
        and (
            lambda meta: meta.get("status") == "active"
            and meta.get("learner_id") == active_learner_id
            and meta.get("goal_id") == active_goal_id
        )(parse_note(vault / node["path"])[0])
    ]
    if len(active_interventions) != 1:
        raise VaultError("必须有且只有一个 active intervention 才能公开验证题")
    active_intervention_id = active_interventions[0]
    intervention_meta, _intervention_body, intervention_parse_errors = parse_note(
        vault / index["nodes"][active_intervention_id]["path"]
    )
    if intervention_parse_errors:
        raise VaultError(
            "当前 intervention 无法解析: " + "; ".join(intervention_parse_errors)
        )
    resolution = resolve_active_teaching(
        vault,
        write=False,
        _skip_validation=True,
        _include_internal=True,
        _as_of=intervention_meta.get("resolved_at"),
    )
    decision = resolution.pop("_decision")
    evidence_node = index.get("nodes", {}).get(process_evidence_id)
    if not isinstance(evidence_node, dict) or evidence_node.get("type") != "evidence":
        raise VaultError("process_evidence_id 不存在或不是 evidence")
    process_meta, _body, parse_errors = parse_note(vault / evidence_node["path"])
    if parse_errors:
        raise VaultError("过程 evidence 无法解析: " + "; ".join(parse_errors))
    if (
        process_meta.get("phase") != "teaching_process"
        or process_meta.get("mastery_eligible") is not False
        or process_meta.get("result") == "not_tested"
        or not isinstance(process_meta.get("response_correct"), bool)
    ):
        raise VaultError("必须提交真实教学过程 evidence，不能用空记录或 mastery evidence 开题")
    delivery_node = index.get("nodes", {}).get(
        str(process_meta.get("teaching_item_id"))
    )
    if (
        not isinstance(delivery_node, dict)
        or delivery_node.get("type") != "teaching_delivery"
    ):
        raise VaultError("过程 evidence 未引用真实已发行教学项")
    delivery_meta, _delivery_body, delivery_parse_errors = parse_note(
        vault / delivery_node["path"]
    )
    if delivery_parse_errors:
        raise VaultError("教学签发记录无法解析: " + "; ".join(delivery_parse_errors))
    if (
        delivery_meta.get("delivery_plan_fingerprint")
        != process_meta.get("teaching_delivery_fingerprint_at_observation")
        or delivery_meta.get("decision_fingerprint")
        != process_meta.get("decision_fingerprint_at_observation")
        or delivery_meta.get("activity") != process_meta.get("activity")
        or delivery_meta.get("carrier") != process_meta.get("carrier")
    ):
        raise VaultError("过程 evidence 未精确绑定实际教学投影及其内容指纹")
    try:
        if parse_iso_instant(delivery_meta.get("issued_at")) >= parse_iso_instant(
            process_meta.get("observed_at")
        ):
            raise VaultError("学习者作答必须晚于教学项签发")
    except (TypeError, ValueError):
        raise VaultError("教学签发或过程 evidence 时间非法") from None
    expected_scope = decision.get("scope")
    process_scope = {
        "learner_id": process_meta.get("learner_id"),
        "goal_id": process_meta.get("goal_id"),
        "concept_id": process_meta.get("concept_id"),
        "contract_id": process_meta.get("contract_id"),
        "contract_version": process_meta.get("contract_version"),
    }
    if process_scope != expected_scope:
        raise VaultError("过程 evidence 与当前教学决策完整 scope 不一致")
    if (
        process_meta.get("route_binding_id")
        != resolution.get("resolved_route_binding_id")
        or process_meta.get("route_id_at_observation") != decision.get("route_id")
        or process_meta.get("route_version_at_observation")
        != decision.get("route_version")
        or process_meta.get("bound_verification_task_id")
        != decision.get("bound_verification_task_id")
        or process_meta.get("verification_task_id")
        != decision.get("bound_verification_task_id")
        or delivery_meta.get("resource_id")
        != resolution.get("resolved_resource_id")
        or delivery_meta.get("activity") != resolution.get("resolved_activity")
        or delivery_meta.get("carrier") != resolution.get("resolved_carrier")
    ):
        raise VaultError(
            "过程 evidence 的 decision epoch 已非当前签发上下文；route/task/resource/activity/carrier 不一致"
        )
    process_refs = intervention_meta.get("resolved_process_refs")
    if (
        intervention_meta.get("resolved_process_status")
        != "ready_for_verification"
        or not isinstance(process_refs, list)
        or not process_refs
        or process_refs[-1] != process_evidence_id
    ):
        raise VaultError(
            "当前过程刷新尚未达到开题条件：该 evidence 未落地为 ready_for_verification"
        )
    canonical_process: list[tuple[str, dict[str, Any]]] = []
    open_instant = datetime.now(timezone.utc)
    for state_id, state_node in index.get("nodes", {}).items():
        if state_node.get("type") != "state":
            continue
        state_meta, _state_body, _state_errors = parse_note(vault / state_node["path"])
        state_scope = {
            "learner_id": state_meta.get("learner_id"),
            "goal_id": state_meta.get("goal_id"),
            "concept_id": state_meta.get("concept_id"),
            "contract_id": state_meta.get("contract_id"),
            "contract_version": state_meta.get("contract_version"),
        }
        if state_scope != expected_scope:
            continue
        for relation in state_node.get("relations", []):
            evidence_id = str(relation.get("target"))
            if relation.get("type") != "supported_by" or evidence_id not in index["nodes"]:
                continue
            evidence_meta, _evidence_body, _evidence_errors = parse_note(
                vault / index["nodes"][evidence_id]["path"]
            )
            if (
                evidence_meta.get("phase") == "teaching_process"
                and evidence_meta.get("decision_fingerprint_at_observation")
                == delivery_meta.get("decision_fingerprint")
                and evidence_meta.get("teaching_item_id")
                == process_meta.get("teaching_item_id")
                and parse_iso_instant(evidence_meta.get("observed_at"))
                <= open_instant
            ):
                canonical_process.append((evidence_id, evidence_meta))
    readiness = derive_process_adaptation(canonical_process)
    if (
        readiness.get("status") != "ready_for_verification"
        or readiness.get("latest_evidence_id") != process_evidence_id
    ):
        raise VaultError(
            "最新已提交教学过程尚未达到开题条件；按 process next_action 先修复或重试"
        )
    policy = load_text_learning_policy()
    process_record = {
        "observation_kind": "teaching_process",
        "scope": process_scope,
        "evidence_scope": dict(process_scope),
        "route_id_at_observation": process_meta.get("route_id_at_observation"),
        "route_version_at_observation": process_meta.get(
            "route_version_at_observation"
        ),
        "bound_route_id": decision.get("route_id"),
        "bound_route_version": decision.get("route_version"),
    }
    process_evaluation = policy.evaluate_text_unit(process_record, decision)
    resource_meta, _resource_body, resource_parse_errors = parse_note(
        vault / index["nodes"][resolution["resolved_resource_id"]]["path"]
    )
    if resource_parse_errors:
        raise VaultError("当前 resource 无法解析: " + "; ".join(resource_parse_errors))
    task = resource_meta.get("verification_task")
    if not isinstance(task, dict):
        raise VaultError("当前 resource 缺少 verification_task")
    return policy._project_verification_task_from_committed_process(
        decision,
        process_evaluation,
        {
            "task_id": task.get("id"),
            "verification_task": task.get("prompt"),
            "response_format": "按题目要求独立写出结果与必要解释。",
            "success_criteria": task.get("success_criteria"),
        },
    )


def recover_learning_route(vault: Path) -> int:
    """Return an existing route or an unconfirmed reconstruction candidate.

    This command is deliberately read-only. A reconstructed candidate must be
    shown to and confirmed by the user before a new intervention note is saved.
    """

    validation_errors, validation_warnings, _summary = validate_vault(
        vault,
        allow_active_route_ambiguity=True,
        allow_unresolved_teaching=True,
    )
    if validation_errors:
        raise VaultError("Vault/路线校验失败，不能恢复学习路线:\n- " + "\n- ".join(validation_errors))
    index, index_errors = build_index(vault)
    if index_errors:
        raise VaultError("图谱存在错误，不能恢复学习路线:\n- " + "\n- ".join(index_errors))
    if not (vault / MANIFEST_REL).is_file():
        raise VaultError("缺少 manifest，先恢复 Vault 入口")
    manifest = json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))
    allow_synthetic_demo = trusted_synthetic_demo_authorized(vault, manifest)
    all_meta: dict[str, dict[str, Any]] = {}
    for node_id, node in index["nodes"].items():
        all_meta[node_id], _, _ = parse_note(vault / node["path"])

    goal_candidates: set[str] = set()
    active_goal_id = manifest.get("active_goal_id")
    if active_goal_id in index["nodes"] and index["nodes"][active_goal_id]["type"] == "goal":
        goal_candidates.add(str(active_goal_id))
    sessions: list[tuple[str, dict[str, Any]]] = []
    for node_id, node in index["nodes"].items():
        if node["type"] != "session":
            continue
        meta = all_meta[node_id]
        sessions.append((node_id, meta))
        goal_id = meta.get("goal_id")
        if goal_id in index["nodes"] and index["nodes"][goal_id]["type"] == "goal":
            goal_candidates.add(str(goal_id))

    if not goal_candidates:
        print(
            json_dump(
                {
                    "status": "not_found",
                    "vault": str(vault.resolve()),
                    "next_action": "未找到可追溯 goal；询问用户是继续查找旧数据，还是明确重建。没有写入任何路线。",
                }
            ),
            end="",
        )
        return 4
    if len(goal_candidates) > 1 and not active_goal_id:
        print(
            json_dump(
                {
                    "status": "multiple_matches",
                    "goal_ids": sorted(goal_candidates),
                    "next_action": "请用户选择原目标；不要自动选最新项或合并。",
                }
            ),
            end="",
        )
        return 3

    goal_id = str(active_goal_id) if active_goal_id in goal_candidates else sorted(goal_candidates)[0]
    learner_node_id = manifest.get("active_learner_id")
    learner_id = all_meta.get(str(learner_node_id), {}).get("learner_id")
    if not learner_id:
        session_learners = {
            meta.get("learner_id") for _session_id, meta in sessions if meta.get("goal_id") == goal_id and meta.get("learner_id")
        }
        if len(session_learners) == 1:
            learner_id = session_learners.pop()
        else:
            raise VaultError("无法唯一确定学习者；请用户指定 Vault/学习者，不能自行合并")

    route_registry, _route_events, route_errors = load_route_binding_registry(vault, manifest)
    if route_errors:
        raise VaultError("route issuance 校验失败，不能恢复学习路线:\n- " + "\n- ".join(route_errors))
    due_retention_items: list[dict[str, Any]] = []
    goal_contracts = {
        (str(item.get("id")), item.get("version"), str(item.get("concept_id"))): item
        for item in all_meta.get(goal_id, {}).get("mastery_contracts", [])
        if isinstance(item, dict) and isinstance(item.get("version"), int)
    }
    recovery_as_of = utc_now()
    for state_id, state_meta in all_meta.items():
        if (
            state_meta.get("type") != "state"
            or state_meta.get("learner_id") != learner_id
            or state_meta.get("goal_id") != goal_id
        ):
            continue
        contract = goal_contracts.get(
            (
                str(state_meta.get("contract_id")),
                state_meta.get("contract_version"),
                str(state_meta.get("concept_id")),
            )
        )
        if not isinstance(contract, dict):
            raise VaultError(f"恢复时 state 无法解析 mastery contract: {state_id}")
        supported_evidence_ids = {
            relation.get("target")
            for relation in index.get("nodes", {}).get(state_id, {}).get("relations", [])
            if relation.get("type") == "supported_by"
        }
        scoped_evidence = [
            (str(evidence_id), all_meta[str(evidence_id)])
            for evidence_id in sorted(supported_evidence_ids)
            if str(evidence_id) in all_meta
            and all_meta[str(evidence_id)].get("type") == "evidence"
            and all_meta[str(evidence_id)].get("learner_id") == learner_id
            and all_meta[str(evidence_id)].get("goal_id") == goal_id
            and all_meta[str(evidence_id)].get("concept_id")
            == state_meta.get("concept_id")
            and all_meta[str(evidence_id)].get("contract_id")
            == state_meta.get("contract_id")
            and all_meta[str(evidence_id)].get("contract_version")
            == state_meta.get("contract_version")
        ]
        live_evaluation = evaluate_mastery_contract(
            contract,
            scoped_evidence,
            state_context=state_context_with_current_schedule(
                state_meta, all_meta, strict=True
            ),
            as_of=recovery_as_of,
            allow_synthetic_demo=allow_synthetic_demo,
        )
        if (
            live_evaluation.get("retention_status") != "due"
            or live_evaluation.get("next_action") != "issue_delayed_verification"
        ):
            continue
        schedule = all_meta.get(
            str(state_meta.get("current_retention_schedule_id")), {}
        )
        if schedule.get("type") != "retention_schedule":
            raise VaultError(f"due retention 无 current schedule receipt: {state_id}")
        matching_issuances = [
            event
            for key, event in route_registry.items()
            if key[:5]
            == (
                str(learner_id),
                str(goal_id),
                str(state_meta.get("concept_id")),
                str(state_meta.get("contract_id")),
                state_meta.get("contract_version"),
            )
            and event.get("verification_task_id")
            == schedule.get("retention_task_id")
        ]
        if len(matching_issuances) != 1:
            raise VaultError(f"due retention 无唯一 route issuance: {state_id}")
        issuance = matching_issuances[0]
        due_retention_items.append(
            {
                "state_id": state_id,
                "concept_id": state_meta.get("concept_id"),
                "contract_id": state_meta.get("contract_id"),
                "contract_version": state_meta.get("contract_version"),
                "retention_schedule_id": schedule.get("id"),
                "baseline_evidence_id": schedule.get("baseline_evidence_id"),
                "retention_task_id": schedule.get("retention_task_id"),
                "scheduled_for": schedule.get("scheduled_for"),
                "route_id": issuance.get("route_id"),
                "route_version": issuance.get("route_version"),
                "route_binding_id": issuance.get("binding_id"),
            }
        )
    structured_next_action: dict[str, Any] | None = None
    if due_retention_items:
        structured_next_action = {
            "action": "issue_delayed_verification",
            "items": due_retention_items,
        }

    existing_routes: list[dict[str, Any]] = []
    for node_id, node in index["nodes"].items():
        if node["type"] != "intervention":
            continue
        meta = all_meta[node_id]
        if meta.get("goal_id") == goal_id and meta.get("learner_id") == learner_id and meta.get("route_id"):
            existing_routes.append({"node_id": node_id, **meta})
    if existing_routes:
        active_routes = [item for item in existing_routes if item.get("status") == "active"]
        if len(active_routes) != 1:
            print(
                json_dump(
                    {
                        "status": "multiple_matches" if active_routes else "no_active_route",
                        "vault": str(vault.resolve()),
                        "routes": [
                            {
                                key: route.get(key)
                                for key in (
                                    "node_id",
                                    "status",
                                    "route_id",
                                    "route_version",
                                    "goal_id",
                                    "current_checkpoint",
                                    "parent_route_id",
                                    "return_checkpoint",
                                    "path",
                                )
                            }
                            for route in (active_routes or existing_routes)
                        ],
                        "warnings": validation_warnings,
                        "next_action": (
                            "存在多个 active route；请用户按 route_id、断点和支线返回点选择，不能自动按版本号挑选。"
                            if active_routes
                            else "只找到非 active 的历史路线；请用户确认恢复哪条或重新构造，命令未写入。"
                        ),
                    }
                ),
                end="",
            )
            return 3
        route = active_routes[0]
        print(
            json_dump(
                {
                    "status": "route_available",
                    "vault": str(vault.resolve()),
                    "route": {
                        key: route.get(key)
                        for key in (
                            "node_id",
                            "status",
                            "route_id",
                            "route_version",
                            "goal_id",
                            "current_checkpoint",
                            "completed_step_evidence_ids",
                            "parent_route_id",
                            "return_checkpoint",
                            "recovery_status",
                            "recovered_from",
                            "path",
                            "resolved_resource_id",
                            "resolved_activity",
                            "resolved_carrier",
                            "resolved_profile_refs",
                            "resolved_profile_level",
                            "resolved_profile_usage",
                            "resolved_process_refs",
                            "resolved_process_status",
                            "resolved_process_feedback_rule",
                            "resolved_process_next_action",
                            "resolved_process_cost",
                            "resolved_process_cost_selection",
                            "resolved_cost_vector",
                            "resolved_cost_basis",
                            "resolved_latest_teaching_item_id",
                            "resolved_max_observed_assistance_level",
                            "resolved_process_support_load",
                        )
                    },
                    "warnings": validation_warnings,
                    "next_action": structured_next_action
                    or {
                        "action": "resume_active_route",
                        "checkpoint": route.get("current_checkpoint"),
                        "resource_id": route.get("resolved_resource_id"),
                        "activity": route.get("resolved_activity"),
                    },
                }
            ),
            end="",
        )
        return 0

    goal_node = index["nodes"][goal_id]
    target_ids = [
        relation["target"] for relation in goal_node["relations"] if relation["type"] == "targets"
    ]
    requirements = {
        node_id: [
            relation["target"]
            for relation in node["relations"]
            if relation["type"] == "requires"
        ]
        for node_id, node in index["nodes"].items()
        if node["type"] == "concept"
    }
    path: list[str] = []
    seen: set[str] = set()

    def append_with_prerequisites(concept_id: str) -> None:
        if concept_id in seen:
            return
        seen.add(concept_id)
        for prerequisite in requirements.get(concept_id, []):
            append_with_prerequisites(prerequisite)
        path.append(concept_id)

    for target_id in target_ids:
        append_with_prerequisites(target_id)

    state_by_concept: dict[str, tuple[str, dict[str, Any]]] = {}
    for node_id, node in index["nodes"].items():
        meta = all_meta[node_id]
        if (
            node["type"] == "state"
            and meta.get("learner_id") == learner_id
            and meta.get("goal_id") == goal_id
        ):
            state_by_concept[str(meta.get("concept_id"))] = (node_id, meta)

    completed_evidence: list[str] = []
    current_checkpoint: str | None = None
    state_meta_by_concept = {concept_id: record[1] for concept_id, record in state_by_concept.items()}
    reconstructed_subgraph = set(path)
    for concept_id in path:
        state_record = state_by_concept.get(concept_id)
        if state_record and state_record[1].get("mastery") == "mastered":
            for relation in index["nodes"][state_record[0]]["relations"]:
                if relation["type"] == "supported_by" and relation["target"] not in completed_evidence:
                    completed_evidence.append(relation["target"])
        elif current_checkpoint is None and is_eligible_teaching_candidate(
            concept_id, reconstructed_subgraph, state_meta_by_concept
        ):
            current_checkpoint = concept_id

    recovered_session_ids = [
        session_id for session_id, meta in sessions if meta.get("goal_id") == goal_id
    ]
    candidate = {
        "route_id": f"route-reconstructed-{learner_id}-{goal_id}",
        "route_version": 1,
        "goal_id": goal_id,
        "current_checkpoint": current_checkpoint,
        "completed_step_evidence_ids": completed_evidence,
        "parent_route_id": None,
        "return_checkpoint": None,
        "recovery_status": "reconstructed_unconfirmed",
        "recovered_from": [goal_id, *recovered_session_ids, *completed_evidence],
        "path": path,
    }
    print(
        json_dump(
            {
                "status": "reconstructed_unconfirmed",
                "vault": str(vault.resolve()),
                "candidate": candidate,
                "next_action": structured_next_action
                or {
                    "action": "confirm_reconstructed_route",
                    "message": "向用户说明来源、路径和断点；确认后才新建 intervention。命令未写入路线。",
                },
            }
        ),
        end="",
    )
    return 0


def load_cone_data(vault: Path) -> dict[str, Any]:
    validation_errors, _warnings, _summary = validate_vault(vault)
    if validation_errors:
        raise VaultError("Vault 校验失败，先运行 validate:\n- " + "\n- ".join(validation_errors))
    index, _ = build_index(vault)
    manifest = json.loads((vault / MANIFEST_REL).read_text(encoding="utf-8"))
    active_learner_node_id = manifest.get("active_learner_id")
    active_goal_id = manifest.get("active_goal_id")
    if not active_learner_node_id or not active_goal_id:
        raise VaultError("manifest 缺少 active learner 或 active goal，无法选择 Focus 快照")

    all_meta: dict[str, dict[str, Any]] = {}
    for node_id, node in index["nodes"].items():
        all_meta[node_id], _, _ = parse_note(vault / node["path"])
    learner_id = all_meta.get(active_learner_node_id, {}).get("learner_id")
    goal_meta = all_meta.get(active_goal_id, {})

    states_by_concept: dict[str, dict[str, Any]] = {}
    focus_by_concept: dict[str, dict[str, Any]] = {}
    for node_id, node in index["nodes"].items():
        meta = all_meta[node_id]
        if (
            node["type"] == "state"
            and meta.get("learner_id") == learner_id
            and meta.get("goal_id") == active_goal_id
        ):
            states_by_concept[str(meta.get("concept_id"))] = meta
        if (
            node["type"] == "focus_snapshot"
            and meta.get("learner_id") == learner_id
            and meta.get("goal_id") == active_goal_id
        ):
            concept_id = str(meta.get("concept_id"))
            previous = focus_by_concept.get(concept_id)
            if previous is None or parse_iso_instant(meta.get("calculated_at")) > parse_iso_instant(
                previous.get("calculated_at")
            ):
                focus_by_concept[concept_id] = meta

    concept_ids = {
        node_id
        for node_id, node in index["nodes"].items()
        if node["type"] == "concept" and node_id in focus_by_concept
    }
    if not concept_ids:
        raise VaultError("当前 learner + goal 没有 focus_snapshot；不得回退到共享 concept 猜测")

    requirements = {
        concept_id: {
            relation["target"]
            for relation in index["nodes"][concept_id]["relations"]
            if relation["type"] == "requires"
        }
        for concept_id, node in index["nodes"].items()
        if node["type"] == "concept"
    }
    target_subgraph = target_subgraph_for_goal(index, active_goal_id, requirements)

    interventions: list[dict[str, Any]] = []
    for node_id, node in index["nodes"].items():
        if node["type"] != "intervention":
            continue
        meta = all_meta[node_id]
        if meta.get("goal_id") == active_goal_id and meta.get("learner_id") == learner_id:
            interventions.append(meta)
    active_interventions = [item for item in interventions if item.get("status") == "active"]
    if len(active_interventions) > 1:
        raise VaultError("同一 learner+goal 有多个 active route；请用户选择后再导出 Focus Cone")
    candidate_id: str | None = None
    candidate_source = "none"
    candidate_status = "no_active_route"
    active_checkpoint_id: str | None = None
    selected_routing_action: str | None = None
    selected_next_step_id: str | None = None
    selected_activity_id: str | None = None
    selected_activity: str | None = None
    selected_probe_id: str | None = None
    selected_verification_task_id: str | None = None
    selected_profile_refs: list[str] = []
    selected_profile_level: str | None = None
    selected_profile_usage: str | None = None
    selected_route_binding_id: str | None = None
    selected_context_key: str | None = None
    selected_selection_basis = "not_selected"
    binding_failure_code: str | None = None
    if active_interventions:
        active_route = active_interventions[0]
        checkpoint = str(active_route.get("current_checkpoint"))
        active_checkpoint_id = checkpoint
        if is_eligible_teaching_candidate(checkpoint, target_subgraph, states_by_concept):
            candidate_source = "active_route_checkpoint"
            checkpoint_state = states_by_concept.get(checkpoint, {})
            selected_routing_action = (
                "diagnose_now"
                if checkpoint_state.get("mastery", "unknown") == "unknown"
                else "teach_now"
            )
            activity_id = str(active_route.get("resolved_resource_id", ""))
            resource_meta = all_meta.get(activity_id, {})
            probe = resource_meta.get("diagnostic_probe")
            verification = resource_meta.get("verification_task")
            if selected_routing_action == "diagnose_now":
                probe_id = active_route.get("current_probe_id")
                if (
                    isinstance(probe, dict)
                    and isinstance(probe_id, str)
                    and probe.get("id") == probe_id
                ):
                    candidate_id = checkpoint
                    selected_selection_basis = "active_route"
                    selected_probe_id = probe_id
                    selected_next_step_id = probe_id
                    candidate_status = "selected"
                else:
                    binding_failure_code = "probe_unavailable"
                    candidate_status = "active_route_checkpoint_missing_probe"
            else:
                verification_task_id = active_route.get("current_verification_task_id")
                if (
                    resource_meta.get("type") == "resource"
                    and isinstance(verification, dict)
                    and isinstance(verification_task_id, str)
                    and verification.get("id") == verification_task_id
                ):
                    candidate_id = checkpoint
                    selected_selection_basis = "resolved_active_teaching"
                    selected_activity_id = activity_id
                    selected_activity = str(active_route.get("resolved_activity"))
                    selected_verification_task_id = verification_task_id
                    selected_next_step_id = activity_id
                    selected_profile_refs = list(active_route.get("resolved_profile_refs", []))
                    selected_profile_level = str(active_route.get("resolved_profile_level"))
                    selected_profile_usage = str(active_route.get("resolved_profile_usage"))
                    selected_route_binding_id = str(active_route.get("resolved_route_binding_id"))
                    selected_context_key = str(active_route.get("resolved_context_key"))
                    candidate_status = "selected"
                else:
                    binding_failure_code = "teaching_binding_unavailable"
                    candidate_status = "active_route_checkpoint_missing_teaching_binding"
        else:
            candidate_status = "active_route_checkpoint_ineligible"

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for node_id in sorted(concept_ids):
        node = index["nodes"][node_id]
        meta = all_meta[node_id]
        state = states_by_concept.get(node_id, {})
        focus_meta = focus_by_concept[node_id]
        in_target_subgraph = node_id in target_subgraph
        eligible = is_eligible_teaching_candidate(node_id, target_subgraph, states_by_concept)
        mastery = state.get("mastery", "unknown")
        boundary = state.get("boundary_position", "unknown")
        ranking_status = focus_meta.get("ranking_status", "incomplete")
        blocking_prerequisite_ids = sorted(
            prerequisite
            for prerequisite in requirements.get(node_id, set())
            if states_by_concept.get(prerequisite, {}).get("mastery") != "mastered"
        )
        if node_id == candidate_id:
            selection_status = "selected"
            routing_action = str(selected_routing_action)
            reason_codes = ["active_route_checkpoint", "goal_required", "prerequisites_satisfied"]
            if routing_action == "diagnose_now":
                reason_codes.append("probe_available")
        elif node_id == active_checkpoint_id and binding_failure_code:
            selection_status = "not_evaluated"
            routing_action = "defer_unmodeled"
            reason_codes = [
                "active_route_checkpoint",
                "goal_required",
                "prerequisites_satisfied",
                binding_failure_code,
            ]
        elif not in_target_subgraph:
            selection_status = "ineligible"
            routing_action = "defer_unmodeled"
            reason_codes = ["outside_goal_subgraph"]
        elif mastery == "mastered":
            selection_status = "ineligible"
            routing_action = "exclude_mastered"
            reason_codes = ["mastery_contract_met"]
        elif boundary == "blocked":
            selection_status = "ineligible"
            routing_action = "defer_blocked"
            reason_codes = ["prerequisite_gap"]
        elif eligible:
            selection_status = "eligible"
            routing_action = "defer_unmodeled"
            reason_codes = ["goal_required", "prerequisites_satisfied", "not_active_route_checkpoint"]
        else:
            selection_status = "not_evaluated"
            routing_action = "defer_unmodeled"
            reason_codes = ["focus_inputs_incomplete"] if ranking_status != "complete" else ["prerequisite_gap"]
        nodes.append(
            {
                "id": node_id,
                "title": meta.get("title", node_id),
                "x": float(meta.get("graph_x", 0.0)),
                "y": float(meta.get("graph_y", 0.0)),
                "goal": focus_meta.get("goal_relevance"),
                "goal_status": focus_meta.get("goal_relevance_status"),
                "interest": focus_meta.get("interest_evidence"),
                "interest_status": focus_meta.get("interest_evidence_status"),
                "readiness": focus_meta.get("readiness"),
                "readiness_status": focus_meta.get("readiness_status"),
                "focus_z": focus_meta.get("focus_z"),
                "ranking_status": ranking_status,
                "focus_weights": focus_meta.get("focus_weights"),
                "focus_model": focus_meta.get("focus_model"),
                "score_kind": focus_meta.get("score_kind"),
                "causal_status": focus_meta.get("causal_status"),
                "calculated_at": focus_meta.get("calculated_at"),
                "snapshot_id": focus_meta.get("id"),
                "state_id": focus_meta.get("state_id"),
                "contract_id": focus_meta.get("contract_id"),
                "contract_version": focus_meta.get("contract_version"),
                "input_confidence": focus_meta.get("input_confidence"),
                "mastery": mastery,
                "boundary": boundary,
                "confidence": state.get("mastery_confidence", "low"),
                "candidate": node_id == candidate_id,
                "in_target_subgraph": in_target_subgraph,
                "eligible_teaching_candidate": eligible,
                "selection_status": selection_status,
                "selection_basis": selected_selection_basis if node_id == candidate_id else "not_selected",
                "routing_action": routing_action,
                "reason_codes": reason_codes,
                "next_step_id": selected_next_step_id if node_id == candidate_id else None,
                "activity_id": selected_activity_id if node_id == candidate_id else None,
                "activity": selected_activity if node_id == candidate_id else None,
                "probe_id": selected_probe_id if node_id == candidate_id else None,
                "verification_task_id": (
                    selected_verification_task_id if node_id == candidate_id else None
                ),
                "profile_refs": selected_profile_refs if node_id == candidate_id else [],
                "profile_level": selected_profile_level if node_id == candidate_id else None,
                "profile_usage": selected_profile_usage if node_id == candidate_id else None,
                "route_binding_id": selected_route_binding_id if node_id == candidate_id else None,
                "context_key": selected_context_key if node_id == candidate_id else None,
                "blocking_prerequisite_ids": blocking_prerequisite_ids,
            }
        )
        for relation in node["relations"]:
            if relation["target"] in concept_ids:
                edges.append({"source": node_id, "target": relation["target"], "type": relation["type"]})
    return {
        "schema": SCHEMA,
        "view_kind": "agent_internal_focus_inspection",
        "audience": "agent_internal",
        "user_visibility": "hidden_by_default",
        "privacy": "private",
        "derived": True,
        "rebuildable": True,
        "authoritative": False,
        "score_kind": "heuristic_cone_coordinate",
        "causal_status": "not_established",
        "decision_role": "experimental_priority",
        "title": f"Agent 内部 Focus Cone：{goal_meta.get('title', active_goal_id)}",
        "learner_id": learner_id,
        "goal_id": active_goal_id,
        "candidate_id": candidate_id,
        "candidate_source": candidate_source,
        "candidate_status": candidate_status,
        "selection_basis": selected_selection_basis,
        "resolved_teaching": {
            "activity_id": selected_activity_id,
            "activity": selected_activity,
            "profile_refs": selected_profile_refs,
            "profile_level": selected_profile_level,
            "profile_usage": selected_profile_usage,
            "route_binding_id": selected_route_binding_id,
            "context_key": selected_context_key,
        },
        "nodes": nodes,
        "edges": edges,
    }


CONE_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent 内部 Focus Cone 决策检查</title>
<style>
  :root { color-scheme: light dark; --bg: light-dark(#f7f7f4,#171817); --surface: light-dark(#ffffff,#222422); --fg: light-dark(#20221f,#f2f3ef); --muted: light-dark(#686d66,#aeb3ab); --line: light-dark(#cfd3cb,#4c514b); --accent: light-dark(#236a5d,#6bc5ad); --mastered: light-dark(#377b4b,#70c482); --partial: light-dark(#a26a13,#e6ad4f); --unknown: light-dark(#737973,#a9afa8); --none: light-dark(#9d4242,#e38282); --focus: light-dark(#275eaa,#74a9ef); }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px; background: var(--bg); color: var(--fg); font-family: ui-sans-serif, system-ui, "Microsoft YaHei", sans-serif; overflow-wrap: anywhere; }
  main { max-width: 1080px; min-width: 0; margin: 0 auto; }
  h1 { font-size: clamp(1.35rem, 3vw, 2rem); font-weight: 600; margin: 0 0 6px; overflow-wrap: anywhere; }
  .subtitle { margin: 0 0 18px; color: var(--muted); }
  .controls { display: grid; grid-template-columns: repeat(3, minmax(160px, 1fr)); gap: 14px; margin-bottom: 14px; }
  label { display: grid; min-width: 0; gap: 5px; font-size: .9rem; }
  input[type="range"] { width: 100%; min-width: 0; accent-color: var(--accent); }
  .stage { position: relative; min-height: 570px; background: var(--surface); border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
  svg { width: 100%; height: 570px; display: block; cursor: grab; touch-action: none; }
  svg:active { cursor: grabbing; }
  .wire { fill: none; stroke: var(--line); stroke-width: 1; opacity: .65; vector-effect: non-scaling-stroke; }
  .edge { stroke: var(--line); stroke-width: 1.2; opacity: .62; vector-effect: non-scaling-stroke; }
  .node circle { stroke: var(--surface); stroke-width: 2; vector-effect: non-scaling-stroke; }
  .node.mastered circle { fill: var(--mastered); }
  .node.partial circle { fill: var(--partial); }
  .node.unknown circle { fill: var(--unknown); }
  .node.none circle { fill: var(--none); }
  .node.candidate circle { stroke: var(--focus); stroke-width: 4; }
  .node text { fill: var(--fg); font-size: 12px; paint-order: stroke; stroke: var(--surface); stroke-width: 3px; stroke-linejoin: round; pointer-events: none; }
  .axis-label { fill: var(--muted); font-size: 12px; }
  .detail { position: absolute; left: 14px; right: 14px; bottom: 14px; padding: 10px 12px; background: color-mix(in srgb, var(--surface) 92%, transparent); border: 1px solid var(--line); border-radius: 10px; }
  .detail strong { font-weight: 600; }
  .legend { display: flex; max-width: 100%; gap: 16px; flex-wrap: wrap; margin-top: 12px; color: var(--muted); font-size: .88rem; }
  .legend span { min-width: 0; white-space: normal; }
  .legend span::before { content: ""; display: inline-block; width: 10px; height: 10px; margin-right: 6px; border-radius: 50%; background: var(--unknown); }
  .legend .m::before { background: var(--mastered); } .legend .p::before { background: var(--partial); } .legend .n::before { background: var(--none); } .legend .u::before { background: var(--unknown); } .legend .c::before { background: var(--focus); box-shadow: inset 0 0 0 3px var(--surface); outline: 2px solid var(--focus); }
  .note, .unranked { margin-top: 12px; color: var(--muted); font-size: .88rem; }
  @media (max-width: 620px) { body { padding: 14px; } .controls { grid-template-columns: 1fr; } .stage { min-height: 470px; } svg { height: 470px; } }
</style>
</head>
<body>
<main>
  <h1 id="coneHeading">Agent 内部 Focus Cone</h1>
  <p class="subtitle">audience=agent_internal · private=true · authoritative=false · causal_status=not_established</p>
  <section class="controls" aria-label="仅用于检查视图的 Focus 权重">
    <label>w_goal_relevance <output id="goalOut">40%</output><input id="goal" type="range" min="0" max="100" value="40"></label>
    <label>w_interest_evidence <output id="interestOut">30%</output><input id="interest" type="range" min="0" max="100" value="30"></label>
    <label>w_readiness <output id="readinessOut">30%</output><input id="readiness" type="range" min="0" max="100" value="30"></label>
  </section>
  <section class="stage">
    <svg id="cone" viewBox="0 0 960 570" role="img" aria-labelledby="coneTitle coneDesc">
      <title id="coneTitle">Agent 内部启发式 Focus 坐标检查</title>
      <desc id="coneDesc">节点高度是可调检查权重产生的启发式坐标。它不是掌握概率、能力值、候选资格或教学效果的因果估计。</desc>
      <g id="wire"></g><g id="edges"></g><g id="nodes"></g>
      <text class="axis-label" x="24" y="28">higher display_focus_z</text>
      <text class="axis-label" x="24" y="548">lower display_focus_z</text>
    </svg>
    <div class="detail" id="detail" aria-live="polite">select concept_id → inspect cached score, state scope, selection_status, routing_action, reason_codes</div>
  </section>
  <div class="legend" aria-label="图例"><span class="m">mastery=mastered</span><span class="p">mastery=partial</span><span class="n">mastery=none</span><span class="u">mastery=unknown</span><span class="c">selection_status=selected</span></div>
  <div class="unranked" id="unranked"></div>
  <p class="note">display_only=true；调整权重不修改快照、状态、路线或候选。普通教学输出不得包含本视图字段。</p>
</main>
<script>
const data = __DATA__;
document.getElementById('coneHeading').textContent = data.title;
const svg = document.getElementById('cone');
const wireGroup = document.getElementById('wire');
const edgeGroup = document.getElementById('edges');
const nodeGroup = document.getElementById('nodes');
const detail = document.getElementById('detail');
const unranked = document.getElementById('unranked');
const controls = ['goal','interest','readiness'].map(id => document.getElementById(id));
let yaw = -0.45, pitch = 0.86, dragging = false, lastX = 0, lastY = 0;
const byId = new Map(data.nodes.map(node => [node.id, node]));
const ns = 'http://www.w3.org/2000/svg';

function weights() {
  const raw = controls.map(control => Number(control.value));
  const total = raw.reduce((sum, value) => sum + value, 0) || 1;
  controls.forEach((control, index) => document.getElementById(control.id + 'Out').value = Math.round(raw[index] / total * 100) + '%');
  return { goal: raw[0] / total, interest: raw[1] / total, readiness: raw[2] / total };
}

function focus(node, w) {
  if (node.ranking_status !== 'complete' || ![node.goal,node.interest,node.readiness].every(Number.isFinite)) return null;
  return node.goal*w.goal + node.interest*w.interest + node.readiness*w.readiness;
}

function world(node, w) {
  const z = focus(node, w);
  if (z === null) return null;
  const radius = 0.22 + 0.78 * (1-z);
  return { x: node.x*radius, y: node.y*radius, z: z*1.8-0.9, focus: z };
}

function project(point) {
  const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
  const x1 = point.x*cy - point.y*sy;
  const y1 = point.x*sy + point.y*cy;
  const depth = y1*cp - point.z*sp;
  const vertical = y1*sp + point.z*cp;
  const scale = 1.05 / (1.55 + depth*0.22);
  return { x: 480 + x1*330*scale, y: 298 - vertical*260*scale, depth, scale, focus: point.focus };
}

function svgEl(name, attrs = {}) {
  const element = document.createElementNS(ns, name);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
  return element;
}

function drawWire() {
  wireGroup.replaceChildren();
  for (const level of [0, .25, .5, .75, 1]) {
    const points = [];
    const radius = .96*(1-level) + .06;
    for (let i=0; i<=48; i++) {
      const angle = i/48*Math.PI*2;
      points.push(project({x:Math.cos(angle)*radius,y:Math.sin(angle)*radius,z:level*1.8-.9}));
    }
    wireGroup.append(svgEl('path',{class:'wire',d:points.map((p,i)=>(i?'L':'M')+p.x.toFixed(1)+' '+p.y.toFixed(1)).join(' ')}));
  }
  for (let i=0; i<8; i++) {
    const angle = i/8*Math.PI*2;
    const a = project({x:Math.cos(angle),y:Math.sin(angle),z:-.9});
    const b = project({x:0,y:0,z:.9});
    wireGroup.append(svgEl('line',{class:'wire',x1:a.x,y1:a.y,x2:b.x,y2:b.y}));
  }
}

function candidateFor() {
  return data.candidate_id;
}

function draw() {
  const w = weights();
  drawWire();
  const ranked = data.nodes.filter(node => focus(node,w) !== null);
  const omitted = data.nodes.filter(node => focus(node,w) === null);
  unranked.textContent = omitted.length ? 'unranked_concept_ids=['+omitted.map(node=>node.id).join(', ')+'] · reason=ranking_status_incomplete' : 'unranked_concept_ids=[]';
  const projected = ranked.map(node => { const worldPoint = world(node,w); return {node,world:worldPoint,screen:project(worldPoint)}; });
  const candidate = candidateFor();
  const screens = new Map(projected.map(item => [item.node.id,item.screen]));
  edgeGroup.replaceChildren();
  for (const edge of data.edges) {
    const source = screens.get(edge.source), target = screens.get(edge.target);
    if (!source || !target) continue;
    const line = svgEl('line',{class:'edge',x1:source.x,y1:source.y,x2:target.x,y2:target.y});
    line.append(svgEl('title'));
    line.firstChild.textContent = edge.type;
    edgeGroup.append(line);
  }
  nodeGroup.replaceChildren();
  projected.sort((a,b)=>b.screen.depth-a.screen.depth);
  for (const item of projected) {
    const node = item.node, screen = item.screen;
    const group = svgEl('g',{class:'node '+node.mastery+(node.id===candidate?' candidate':''),'data-id':node.id,role:'button',tabindex:'0','aria-label':node.title});
    const circle = svgEl('circle',{cx:screen.x,cy:screen.y,r:Math.max(8,12*screen.scale)});
    circle.setAttribute('role','button');
    circle.setAttribute('aria-label','concept_id '+node.id+'，display_focus_z '+item.world.focus.toFixed(3)+'，selection_status '+node.selection_status);
    group.append(circle);
    const label = svgEl('text',{x:screen.x+11,y:screen.y-10}); label.textContent=node.title; group.append(label);
    const selectNode = () => showDetail(node,item.world.focus,node.id===candidate);
    group.addEventListener('click',selectNode);
    group.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();selectNode();}});
    nodeGroup.append(group);
  }
}

function showDetail(node,z,isCandidate) {
  detail.textContent = 'concept_id='+node.id+' | display_focus_z='+z.toFixed(3)+' | cached_focus_z='+String(node.focus_z)+' | mastery='+node.mastery+' | boundary='+node.boundary+' | selection_status='+node.selection_status+' | routing_action='+node.routing_action+' | next_step_id='+String(node.next_step_id)+' | activity_id='+String(node.activity_id)+' | probe_id='+String(node.probe_id)+' | verification_task_id='+String(node.verification_task_id)+' | reason_codes=['+node.reason_codes.join(',')+'] | selected='+String(isCandidate);
}

controls.forEach(control => control.addEventListener('input', draw));
svg.addEventListener('pointerdown', event => { dragging=true; lastX=event.clientX; lastY=event.clientY; svg.setPointerCapture(event.pointerId); });
svg.addEventListener('pointermove', event => { if(!dragging)return; yaw+=(event.clientX-lastX)*.008; pitch=Math.max(.2,Math.min(1.25,pitch+(event.clientY-lastY)*.006)); lastX=event.clientX; lastY=event.clientY; draw(); });
svg.addEventListener('pointerup', event => { dragging=false; svg.releasePointerCapture(event.pointerId); });
svg.addEventListener('pointercancel', () => dragging=false);
draw();
</script>
</body>
</html>
'''


def export_cone(vault: Path, output: Path, *, force: bool = False) -> None:
    resolved_output = output.resolve()
    if resolved_output.exists() and not force:
        raise VaultError(f"输出已存在，拒绝覆盖；确认后使用 --force: {resolved_output}")
    data = load_cone_data(vault)
    serialized = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    content = CONE_TEMPLATE.replace("__DATA__", serialized)
    atomic_write_text(resolved_output, content)


def inspect_cone(vault: Path) -> int:
    """Print the private Agent decision payload without writing to the Vault."""

    print(json_dump(load_cone_data(vault)), end="")
    return 0


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0 or parsed > 8:
        raise argparse.ArgumentTypeError("max-depth 必须在 0..8")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="理解成本 Demo Vault 工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="在空目录初始化匿名 Vault")
    init_parser.add_argument("--vault", required=True, type=Path)
    init_parser.add_argument("--learner-id", required=True, help="ASCII 匿名 ID，例如 learner-demo-01")

    seed_parser = subparsers.add_parser("seed-demo", help="在空目录生成合成 Demo")
    seed_parser.add_argument("--vault", required=True, type=Path)

    validate_parser = subparsers.add_parser("validate", help="只读校验 Vault")
    validate_parser.add_argument("--vault", required=True, type=Path)

    index_parser = subparsers.add_parser("rebuild-index", help="从 Markdown 重建派生索引")
    index_parser.add_argument("--vault", required=True, type=Path)

    recover_parser = subparsers.add_parser("recover-route", help="只读查找已有 Vault 入口；可显式修复 marker，不恢复学习路线")
    recover_parser.add_argument("--start", required=True, type=Path)
    recover_parser.add_argument("--max-depth", default=4, type=positive_int)
    recover_parser.add_argument("--repair", action="store_true")

    learning_route_parser = subparsers.add_parser(
        "recover-learning-route",
        help="只读返回现有学习路线，或从 goal/session/evidence 构造未确认候选",
    )
    learning_route_parser.add_argument("--vault", required=True, type=Path)

    resolve_teaching_parser = subparsers.add_parser(
        "resolve-teaching",
        help="消费 Vault 画像证据并把教学决策原子落到 active intervention/resource",
    )
    resolve_teaching_parser.add_argument("--vault", required=True, type=Path)
    resolve_teaching_parser.add_argument("--dry-run", action="store_true")

    issue_teaching_parser = subparsers.add_parser(
        "issue-teaching",
        help="将安全白名单教学内容投影为用户可见计划，并追加可验证的教学签发记录",
    )
    issue_teaching_parser.add_argument("--vault", required=True, type=Path)
    issue_teaching_parser.add_argument("--content", required=True, type=Path)

    issue_route_parser = subparsers.add_parser(
        "issue-route",
        help="从严格原始选择记录重算候选，并原子追加 canonical route issuance",
    )
    issue_route_parser.add_argument("--vault", required=True, type=Path)
    issue_route_parser.add_argument("--record", required=True, type=Path)

    schedule_retention_parser = subparsers.add_parser(
        "schedule-retention",
        help="将合格即时验证绑定到已签发新任务，并原子追加 retention schedule receipt（可立即 due）",
    )
    schedule_retention_parser.add_argument("--vault", required=True, type=Path)
    schedule_retention_parser.add_argument("--record", required=True, type=Path)

    open_delayed_parser = subparsers.add_parser(
        "open-delayed-verification",
        help="仅在 retention due 时先追加/复用 verification open receipt，再安全公开未见 A0 题面",
    )
    open_delayed_parser.add_argument("--vault", required=True, type=Path)
    open_delayed_parser.add_argument("--state-id", required=True)

    append_evidence_parser = subparsers.add_parser(
        "append-evidence",
        help="严格提交原始观察，并原子重算 state/boundary/Focus/教学决策",
    )
    append_evidence_parser.add_argument("--vault", required=True, type=Path)
    append_evidence_parser.add_argument("--record", required=True, type=Path)

    open_verification_parser = subparsers.add_parser(
        "open-verification",
        help="只从已提交且绑定当前决策的教学过程 evidence 公开未见验证题",
    )
    open_verification_parser.add_argument("--vault", required=True, type=Path)
    open_verification_parser.add_argument("--process-evidence-id", required=True)

    inspect_cone_parser = subparsers.add_parser(
        "inspect-cone",
        help="只读输出 Agent 内部 Focus 决策 JSON；不用于普通教学回复",
    )
    inspect_cone_parser.add_argument("--vault", required=True, type=Path)

    cone_parser = subparsers.add_parser(
        "export-cone",
        help="显式审计/调试时导出 Agent 内部三维 Focus Cone",
    )
    cone_parser.add_argument("--vault", required=True, type=Path)
    cone_parser.add_argument("--output", required=True, type=Path)
    cone_parser.add_argument("--force", action="store_true", help="确认覆盖已有导出文件")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,31}", args.learner_id):
                raise VaultError("learner-id 只能使用 2–32 位小写 ASCII 字母、数字和连字符")
            initialize_vault(args.vault, args.learner_id)
            print(json_dump({"status": "created", "vault": str(args.vault.resolve())}), end="")
            return 0
        if args.command == "seed-demo":
            seed_demo(args.vault)
            print(json_dump({"status": "seeded", "vault": str(args.vault.resolve()), "source": str(SEED_PATH)}), end="")
            return 0
        if args.command == "validate":
            errors, warnings, summary = validate_vault(args.vault)
            print(json_dump({"status": "ok" if not errors else "invalid", **summary, "errors": errors, "warnings": warnings}), end="")
            return 0 if not errors else 2
        if args.command == "rebuild-index":
            index, errors = rebuild_index(args.vault)
            print(json_dump({"status": "rebuilt" if not errors else "rebuilt_with_errors", "node_count": index["node_count"], "errors": errors}), end="")
            return 0 if not errors else 2
        if args.command == "recover-route":
            return recover_route(args.start, args.max_depth, args.repair)
        if args.command == "recover-learning-route":
            return recover_learning_route(args.vault)
        if args.command == "resolve-teaching":
            print(
                json_dump(resolve_active_teaching(args.vault, write=not args.dry_run)),
                end="",
            )
            return 0
        if args.command == "issue-teaching":
            print(
                json_dump(
                    issue_teaching_delivery(args.vault, content_path=args.content)
                ),
                end="",
            )
            return 0
        if args.command == "issue-route":
            print(
                json_dump(issue_route(args.vault, record_path=args.record)),
                end="",
            )
            return 0
        if args.command == "schedule-retention":
            print(
                json_dump(
                    schedule_retention(args.vault, record_path=args.record)
                ),
                end="",
            )
            return 0
        if args.command == "open-delayed-verification":
            print(
                json_dump(
                    open_delayed_verification(
                        args.vault, state_id=args.state_id
                    )
                ),
                end="",
            )
            return 0
        if args.command == "append-evidence":
            print(
                json_dump(append_evidence(args.vault, record_path=args.record)),
                end="",
            )
            return 0
        if args.command == "open-verification":
            print(
                json_dump(
                    project_verification_task_from_vault(
                        args.vault,
                        process_evidence_id=args.process_evidence_id,
                    )
                ),
                end="",
            )
            return 0
        if args.command == "inspect-cone":
            return inspect_cone(args.vault)
        if args.command == "export-cone":
            export_cone(args.vault, args.output, force=args.force)
            print(json_dump({"status": "exported", "output": str(args.output.resolve())}), end="")
            return 0
        raise VaultError(f"未知命令: {args.command}")
    except VaultError as exc:
        print(json_dump({"status": "error", "message": str(exc)}), end="", file=sys.stderr)
        return 2
    except OSError as exc:
        print(json_dump({"status": "io_error", "message": str(exc)}), end="", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
