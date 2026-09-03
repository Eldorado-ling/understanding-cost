#!/usr/bin/env python3
"""Deterministic forward and red-team checks for the Demo Vault tool."""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import text_learning as text_policy
import vault_tool as tool


DEFAULT_PROTECTED_PROMPT = (
    "未见验证题：函数 outer 调用 inner 后，将以什么顺序返回？请说明调用栈变化。"
)
DEFAULT_PROTECTED_ANSWERS = ["inner 先返回，outer 后返回；调用栈按后进先出顺序弹出。"]


def verification_guard(task_id: str) -> dict:
    return text_policy.build_verification_content_guard(
        task_id,
        DEFAULT_PROTECTED_PROMPT,
        DEFAULT_PROTECTED_ANSWERS,
    )


def capture_json(function, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = function(*args, **kwargs)
    return code, json.loads(stream.getvalue())


def seed(root: Path) -> Path:
    vault = root / "vault"
    tool.seed_demo(vault)
    return vault


def snapshot_tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


VAULT_WRITER_SUBPROCESS = r"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, sys.argv[1])
import vault_tool as tool

spec = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
vault = Path(spec["vault"])
result_path = Path(spec["result_path"])
marker_path = Path(spec["marker_path"]) if spec.get("marker_path") else None
release_path = Path(spec["release_path"]) if spec.get("release_path") else None
started_path = Path(spec["started_path"]) if spec.get("started_path") else None


def write_signal(path, value):
    if path is not None:
        tool.atomic_write_text(path, value)


def wait_for_release():
    deadline = time.monotonic() + 20
    while release_path is not None and not release_path.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("subprocess hook release timeout")
        time.sleep(0.01)


hook = spec.get("hook")
if hook == "pause_before_issue_first_write":
    original_write_json = tool.write_json
    paused = {"value": False}

    def write_json_with_pause(path, value):
        if not paused["value"] and Path(path).name == "route-bindings.json":
            paused["value"] = True
            write_signal(marker_path, "paused-after-cas-before-write")
            wait_for_release()
        return original_write_json(path, value)

    tool.write_json = write_json_with_pause
elif hook == "fail_after_schedule_write":
    original_validate = tool.validate_vault
    paused = {"value": False}

    def validate_after_schedule_then_fail(*args, **kwargs):
        result = original_validate(*args, **kwargs)
        if (
            not paused["value"]
            and any((vault / "30-learning/retention-schedules").glob("*.md"))
        ):
            paused["value"] = True
            write_signal(marker_path, "paused-after-schedule-write")
            wait_for_release()
            raise RuntimeError("injected-after-schedule-write")
        return result

    tool.validate_vault = validate_after_schedule_then_fail

write_signal(started_path, "calling-writer")
try:
    operation = spec["operation"]
    if operation == "issue_route":
        value = tool.issue_route(vault, record_path=Path(spec["record_path"]))
    elif operation == "schedule_retention":
        value = tool.schedule_retention(
            vault, record_path=Path(spec["record_path"])
        )
    elif operation == "open_delayed_verification":
        value = tool.open_delayed_verification(
            vault, state_id=spec["state_id"]
        )
    else:
        raise RuntimeError(f"unsupported subprocess operation: {operation}")
except Exception as exc:
    result = {
        "status": "error",
        "error_type": type(exc).__name__,
        "error": str(exc),
    }
else:
    result = {"status": "ok", "value": value}
tool.atomic_write_text(result_path, json.dumps(result, ensure_ascii=False))
"""


def launch_vault_writer_subprocess(
    root: Path,
    *,
    label: str,
    operation: str,
    vault: Path,
    record_path: Path | None = None,
    state_id: str | None = None,
    hook: str | None = None,
    marker_path: Path | None = None,
    release_path: Path | None = None,
    lock_timeout_seconds: float | None = None,
) -> tuple[subprocess.Popen[str], Path, Path]:
    """Launch one real independent process against the shared Vault."""

    result_path = root / f"{label}-result.json"
    started_path = root / f"{label}-started.txt"
    spec_path = root / f"{label}-spec.json"
    spec = {
        "operation": operation,
        "vault": str(vault),
        "record_path": str(record_path) if record_path is not None else None,
        "state_id": state_id,
        "result_path": str(result_path),
        "started_path": str(started_path),
        "hook": hook,
        "marker_path": str(marker_path) if marker_path is not None else None,
        "release_path": str(release_path) if release_path is not None else None,
    }
    tool.atomic_write_text(
        spec_path, json.dumps(spec, ensure_ascii=False, indent=2)
    )
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    if lock_timeout_seconds is not None:
        environment[tool.VAULT_LOCK_TIMEOUT_ENV] = str(lock_timeout_seconds)
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            VAULT_WRITER_SUBPROCESS,
            str(Path(__file__).resolve().parent),
            str(spec_path),
        ],
        cwd=str(Path(__file__).resolve().parent.parent),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return process, result_path, started_path


def wait_for_path(path: Path, *, timeout_seconds: float = 20) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not path.exists():
        if time.monotonic() >= deadline:
            raise AssertionError(f"等待子进程信号超时: {path}")
        time.sleep(0.01)


def finish_vault_writer_subprocess(
    process: subprocess.Popen[str], result_path: Path
) -> dict:
    stdout, stderr = process.communicate(timeout=30)
    assert process.returncode == 0, {
        "returncode": process.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
    assert result_path.is_file(), {"stdout": stdout, "stderr": stderr}
    return json.loads(result_path.read_text(encoding="utf-8"))


@contextlib.contextmanager
def frozen_tool_clock(instant: datetime):
    """Freeze every vault_tool wall-clock read, including validator checks."""

    original_datetime = tool.datetime

    class FrozenDateTime(datetime):
        current = instant.astimezone(timezone.utc)

        @classmethod
        def now(cls, tz=None):
            value = cls.current
            cls.current = cls.current + timedelta(milliseconds=1)
            return value if tz is None else value.astimezone(tz)

    tool.datetime = FrozenDateTime
    try:
        yield FrozenDateTime
    finally:
        tool.datetime = original_datetime


def add_call_stack_resource(
    vault: Path,
    *,
    suffix: str,
    duration_minutes: float = 3,
    cost_vector: dict[str, float] | None = None,
) -> dict:
    """Add one canonical test resource with a genuinely new unseen task."""

    source_path = (
        vault / "30-learning/resources/res-python-call-stack-faded.md"
    )
    meta, body, parse_errors = tool.parse_note(source_path)
    assert parse_errors == []
    resource_id = f"res-python-call-stack-{suffix}"
    task_id = f"verify-python-call-stack-{suffix}"
    meta.update(
        {
            "id": resource_id,
            "title": f"调用栈测试资源 {suffix}",
            "duration_minutes": duration_minutes,
            "supported_activities": [
                "predict_explain",
                "contrast_cases",
                "worked_example_fading",
            ],
            "diagnostic_probe": {
                "id": f"probe-python-call-stack-{suffix}",
                "prompt": "诊断：写出一个两层调用的入栈与返回方向。",
                "success_criteria": "独立区分入栈与返回方向。",
            },
            "verification_task": {
                "id": task_id,
                "prompt": (
                    f"未见任务 {suffix}：函数 q(0)=2，q(n)=q(n-1)+3。"
                    "不要运行代码，写出 q(2) 的栈帧数和返回结果。"
                ),
                "success_criteria": "A0 独立写出最大栈帧数、逐层返回结果和理由。",
                "protected_answers": [
                    f"answer-{suffix}-three-frames",
                    f"answer-{suffix}-q2-eight",
                ],
            },
        }
    )
    if cost_vector is None:
        meta.pop("cost_vector", None)
    else:
        meta["cost_vector"] = dict(cost_vector)
    resource_path = vault / "30-learning/resources" / f"{resource_id}.md"
    tool.atomic_write_text(
        resource_path,
        tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n",
    )
    _index, rebuild_errors = tool.rebuild_index(vault)
    assert rebuild_errors == []
    errors, _warnings, _summary = tool.validate_vault(vault)
    assert errors == [], errors
    return meta


def add_priority_frontier_resources(vault: Path, *, suffix: str) -> tuple[dict, dict]:
    """Create two real non-dominated resource choices for one route step."""

    resource_a = add_call_stack_resource(
        vault,
        suffix=f"{suffix}-diagnosis",
        duration_minutes=0.5,
        cost_vector={
            "diagnosis": 1,
            "prerequisites": 0,
            "core_learning": 2,
            "practice_feedback": 1,
            "verification": 1,
            "maintenance_relearning": 1,
        },
    )
    resource_b = add_call_stack_resource(
        vault,
        suffix=f"{suffix}-core",
        duration_minutes=0.6,
        cost_vector={
            "diagnosis": 2,
            "prerequisites": 0,
            "core_learning": 1,
            "practice_feedback": 1,
            "verification": 1,
            "maintenance_relearning": 1,
        },
    )
    return resource_a, resource_b


def write_residual_focus_snapshot(
    vault: Path,
    *,
    suffix: str,
    decision_id: str,
    selection_basis: str = "focus",
    route_id: str | None = None,
    route_version: int | None = None,
    time_scope: str | None = None,
    calculated_at: str | None = None,
    validate: bool = True,
) -> tuple[Path, dict]:
    """Clone the private Demo Focus view into one auditable decision snapshot."""

    index, index_errors = tool.build_index(vault)
    assert index_errors == []
    source_id, source_node = next(
        (node_id, node)
        for node_id, node in sorted(index["nodes"].items())
        if node["type"] == "focus_snapshot"
        and (
            tool.parse_note(vault / node["path"])[0].get("concept_id")
            == "kc-python-call-stack"
        )
        and (
            tool.parse_note(vault / node["path"])[0].get(
                "calculation_purpose"
            )
            == "inspect_view"
        )
    )
    source_meta, source_body, source_errors = tool.parse_note(
        vault / source_node["path"]
    )
    assert source_errors == [], source_id
    intervention, _intervention_body, intervention_errors = tool.parse_note(
        vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
    )
    assert intervention_errors == []
    ledger = json.loads(
        (vault / tool.ROUTE_BINDINGS_REL).read_text(encoding="utf-8")
    )
    stamp = calculated_at or tool.utc_now_precise()
    focus_id = "focus-test-" + hashlib.sha256(
        f"{suffix}|{decision_id}|{stamp}".encode("utf-8")
    ).hexdigest()[:24]
    focus = json.loads(json.dumps(source_meta))
    focus_weights = focus["focus_weights"]
    recomputed_focus_z = round(
        float(focus_weights["goal"]) * float(focus["goal_relevance"])
        + float(focus_weights["interest"])
        * float(focus["interest_evidence"])
        + float(focus_weights["readiness"]) * float(focus["readiness"]),
        4,
    )
    focus.update(
        {
            "focus_snapshot_contract": tool.FOCUS_SNAPSHOT_SCHEMA,
            "id": focus_id,
            "title": f"Focus 决策快照：{suffix}",
            "route_id": route_id or intervention["route_id"],
            "route_version": (
                route_version
                if route_version is not None
                else intervention["route_version"]
            ),
            "time_scope": time_scope
            or f"route-chain-head:{ledger['head_hash']}",
            "decision_id": decision_id,
            "calculation_purpose": "residual_candidate_order",
            "consumer_ids": ["focus_priority"],
            "used_in_decision": True,
            "selection_basis": selection_basis,
            "ranking_status": "complete",
            "focus_z": recomputed_focus_z,
            "validity": "valid",
            "calculated_at": stamp,
            "created_at": stamp,
            "updated_at": stamp,
        }
    )
    focus_path = (
        vault / "30-learning/visuals/snapshots" / f"{focus_id}.md"
    )
    tool.atomic_write_text(
        focus_path,
        tool.render_frontmatter(focus) + "\n" + source_body.rstrip() + "\n",
    )
    _rebuilt, rebuild_errors = tool.rebuild_index(vault)
    assert rebuild_errors == []
    if validate:
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors
    return focus_path, focus


def write_learning_route_record(
    root: Path,
    resource_id: str,
    *,
    user_cost_priority: list[str] | None = None,
) -> Path:
    record_path = root / "issue-learning-route.json"
    vault = root / "vault"
    ledger = json.loads(
        (vault / tool.ROUTE_BINDINGS_REL).read_text(encoding="utf-8")
    )
    tool.atomic_write_text(
        record_path,
        json.dumps(
            {
                "purpose": "learning",
                "concept_id": "kc-python-call-stack",
                "resource_id": resource_id,
                "baseline_evidence_id": None,
                "source_ref_ids": ["ses-demo-a17-20260826t063000z"],
                "expected_chain_head": ledger["head_hash"],
                "user_cost_priority": user_cost_priority,
            },
            ensure_ascii=False,
        ),
    )
    return record_path


def write_retention_route_record(
    root: Path,
    *,
    resource_id: str,
    baseline_evidence_id: str,
) -> Path:
    vault = root / "vault"
    ledger = json.loads(
        (vault / tool.ROUTE_BINDINGS_REL).read_text(encoding="utf-8")
    )
    record_path = root / f"issue-retention-{resource_id}.json"
    tool.atomic_write_text(
        record_path,
        json.dumps(
            {
                "purpose": "retention",
                "concept_id": "kc-python-call-stack",
                "resource_id": resource_id,
                "baseline_evidence_id": baseline_evidence_id,
                "source_ref_ids": [baseline_evidence_id],
                "expected_chain_head": ledger["head_hash"],
                "user_cost_priority": None,
            },
            ensure_ascii=False,
        ),
    )
    return record_path


def write_schedule_record(
    root: Path,
    *,
    state: dict,
    baseline_evidence_id: str,
    route_binding_id: str,
    not_before: str | None,
    expected_state_evaluated_at: str | None = None,
) -> Path:
    record_path = root / f"schedule-{route_binding_id}.json"
    tool.atomic_write_text(
        record_path,
        json.dumps(
            {
                "state_id": state["id"],
                "baseline_evidence_id": baseline_evidence_id,
                "route_binding_id": route_binding_id,
                "not_before": not_before,
                "expected_state_evaluated_at": (
                    expected_state_evaluated_at
                    if expected_state_evaluated_at is not None
                    else state["evaluated_at"]
                ),
            },
            ensure_ascii=False,
        ),
    )
    return record_path


def ensure_local_learning_route(vault: Path, *, suffix: str) -> dict | None:
    """Move a legacy seed checkpoint onto a local purpose=learning issuance."""

    intervention, _body, parse_errors = tool.parse_note(
        vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
    )
    assert parse_errors == []
    manifest = json.loads((vault / tool.MANIFEST_REL).read_text(encoding="utf-8"))
    _registry, events, route_errors = tool.load_route_binding_registry(
        vault, manifest
    )
    assert route_errors == []
    current = [
        event
        for event in events
        if event.get("route_id") == intervention["route_id"]
        and event.get("route_version") == intervention["route_version"]
        and event.get("concept_id") == intervention["current_checkpoint"]
    ]
    if len(current) == 1 and current[0].get("route_purpose") == "learning":
        return None
    safe_suffix = "auto-" + hashlib.sha256(suffix.encode("utf-8")).hexdigest()[:12]
    resource = add_call_stack_resource(
        vault, suffix=safe_suffix, duration_minutes=1
    )
    record_path = write_learning_route_record(vault.parent, resource["id"])
    issued = tool.issue_route(vault, record_path=record_path)
    assert issued["purpose"] == "learning", issued
    return issued


def refresh_evidence_derivations(meta: dict) -> None:
    """Rebuild every caller-independent evidence field after a fixture edit."""

    allow_synthetic_demo = meta.get("source_kind") == "synthetic_demo"
    field_consumers = tool.PHASE_FIELD_CONSUMERS.get(str(meta.get("phase")))
    assert field_consumers is not None, meta.get("phase")
    meta["consumer_ids"] = sorted(
        {
            consumer
            for field, allowed_consumers in field_consumers.items()
            if tool.evidence_field_is_actionable(meta, field)
            for consumer in allowed_consumers
        }
    )
    derived_eligible, failures = tool.evidence_mastery_eligibility(
        meta, allow_synthetic_demo=allow_synthetic_demo
    )
    assert derived_eligible is meta["mastery_eligible"], failures
    (
        meta["observation_confidence"],
        meta["observation_confidence_basis"],
    ) = tool.derive_observation_confidence(
        meta,
        derived_mastery_eligible=derived_eligible,
        allow_synthetic_demo=allow_synthetic_demo,
    )
    meta["consumer_ids"] = sorted(
        {
            consumer
            for field, allowed_consumers in field_consumers.items()
            if tool.evidence_field_is_actionable(meta, field)
            for consumer in allowed_consumers
        }
    )
    meta["field_bindings"] = tool.build_evidence_field_bindings(meta)


def write_raw_evidence_record(
    vault: Path,
    meta: dict,
    *,
    evidence_id: str,
    summary: str,
    source_session_id: str = "ses-demo-a17-20260826t063000z",
) -> Path:
    """Write the exact caller-owned input accepted by append_evidence."""

    raw = {field: meta.get(field) for field in tool.APPEND_EVIDENCE_RAW_FIELDS}
    raw.update({"id": evidence_id, "summary": summary})
    record_path = vault.parent / f".{evidence_id}-raw.json"
    tool.atomic_write_text(
        record_path,
        json.dumps(
            {"source_session_id": source_session_id, "evidence": raw},
            ensure_ascii=False,
        ),
    )
    return record_path


def call_stack_diagnostic_fixture(
    vault: Path, *, evidence_id: str, teaching_item_id: str | None = None
) -> tuple[dict, dict, dict]:
    """Build a raw diagnostic bound to the trusted call-stack issuance."""

    ensure_local_learning_route(vault, suffix=f"{evidence_id}-diagnostic")
    intervention, _intervention_body, intervention_errors = tool.parse_note(
        vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
    )
    assert intervention_errors == []
    manifest = json.loads((vault / tool.MANIFEST_REL).read_text(encoding="utf-8"))
    registry, _events, registry_errors = tool.load_route_binding_registry(
        vault, manifest
    )
    assert registry_errors == []
    issuance = next(
        item
        for key, item in registry.items()
        if key[2] == "kc-python-call-stack"
        and item["route_id"] == intervention["route_id"]
        and item["route_version"] == intervention["route_version"]
        and item.get("route_purpose") == "learning"
    )
    issued_resource = issuance["issuance_snapshot"]["resources"][0]
    probe = issued_resource["diagnostic_probe"]
    source_path = vault / "20-learner/evidence/ev-demo-a17-004.md"
    diagnostic, _body, parse_errors = tool.parse_note(source_path)
    assert parse_errors == []
    diagnostic.update(
        {
            "id": evidence_id,
            "learner_id": issuance["learner_id"],
            "goal_id": issuance["goal_id"],
            "concept_id": issuance["concept_id"],
            "contract_id": issuance["contract_id"],
            "contract_version": issuance["contract_version"],
            "phase": "diagnostic",
            "evidence_kind": "diagnostic_probe",
            "teaching_item_id": teaching_item_id or probe["id"],
            "teaching_delivery_fingerprint_at_observation": None,
            "verification_item_id": None,
            "verification_task_id": None,
            "bound_verification_task_id": None,
            "decision_fingerprint_at_observation": None,
            "route_id_at_observation": issuance["route_id"],
            "route_version_at_observation": issuance["route_version"],
            "verification_unseen": False,
            "answer_revealed_before_first_attempt": False,
            "activity": issued_resource["supported_activities"][0],
            "carrier": issued_resource["carrier"],
            "observation_validity": "valid",
            "demonstrates": ["prediction"],
            "result": "fail",
            "independence": "independent",
            "assistance_level": "A0",
            "error_signature": "return_order_confusion",
            "elapsed_seconds": 210,
            "attempts": 1,
            "hint_count": 0,
            "immediate_performance": 0.2,
            "near_transfer": "not_tested",
            "delayed_retention": "not_tested",
            "response_correct": False,
            "explanation_quality": "fail",
            "self_reported_effort": 6,
            "baseline_evidence_id": None,
            "retention_task_id": None,
            "scheduled_for": None,
            "observed_at": (
                datetime.now(timezone.utc) - timedelta(milliseconds=1)
            ).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        }
    )
    return diagnostic, issuance, probe


def append_demo_call_stack_process(
    vault: Path,
    *,
    evidence_id: str,
    result: str,
    observed_offset_seconds: int = 1,
    raw_overrides: dict | None = None,
    delivery_overrides: dict | None = None,
    issuance_out: dict | None = None,
) -> dict:
    """Issue real teaching and append one raw process observation transactionally."""

    ensure_teachable_call_stack(vault, suffix=evidence_id)
    intervention_path = (
        vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
    )
    intervention, _intervention_body, intervention_errors = tool.parse_note(
        intervention_path
    )
    assert intervention_errors == []
    content_path = vault / f".{evidence_id}-delivery-content.json"
    tool.atomic_write_text(
        content_path,
        json.dumps(valid_delivery_content(vault=vault), ensure_ascii=False),
    )
    issued = tool.issue_teaching_delivery(vault, content_path=content_path)
    if issuance_out is not None:
        issuance_out.update(json.loads(json.dumps(issued)))
    delivery_path = (
        vault
        / "30-learning/deliveries"
        / f"{issued['teaching_item_id']}.md"
    )
    delivery, _delivery_body, delivery_errors = tool.parse_note(delivery_path)
    assert delivery_errors == []
    if delivery_overrides:
        delivery.update(delivery_overrides)
        tool.atomic_write_text(
            delivery_path,
            tool.render_frontmatter(delivery)
            + "\n"
            + _delivery_body.rstrip()
            + "\n",
        )
        _rebuilt, rebuild_errors = tool.rebuild_index(vault)
        assert rebuild_errors == []
    source_path = vault / "20-learner/evidence/ev-demo-a17-003.md"
    meta, _body, parse_errors = tool.parse_note(source_path)
    assert parse_errors == []
    passed = result == "pass"
    meta.update(
        {
            "id": evidence_id,
            "title": f"证据：调用栈教学过程追加 {result}",
            **issued["process_binding"],
            "result": result,
            "response_correct": passed,
            "explanation_quality": "pass" if passed else result,
            "error_signature": None if passed else "return_order_confusion",
            "elapsed_seconds": 75 if passed else 120,
            "attempts": 1,
            "hint_count": 0 if passed else 1,
            "independence": "not_observed",
            "assistance_level": "A1",
        }
    )
    observed_instant = max(
        tool.parse_iso_instant(intervention["resolved_at"])
        + timedelta(seconds=observed_offset_seconds),
        tool.parse_iso_instant(issued["issued_at"]) + timedelta(milliseconds=1),
    )
    if hasattr(tool.datetime, "current"):
        tool.datetime.current = max(  # type: ignore[attr-defined]
            tool.datetime.current,  # type: ignore[attr-defined]
            observed_instant + timedelta(milliseconds=1),
        )
    else:
        wait_seconds = (
            observed_instant - tool.datetime.now(timezone.utc)
        ).total_seconds()
        if wait_seconds > 0:
            time.sleep(wait_seconds + 0.01)
    meta["observed_at"] = observed_instant.isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    if raw_overrides:
        meta.update(raw_overrides)
    record_path = write_raw_evidence_record(
        vault,
        meta,
        evidence_id=evidence_id,
        summary=f"调用栈教学过程追加 {result}。",
    )
    committed = tool.append_evidence(vault, record_path=record_path)
    assert committed["status"] == "committed", committed
    committed_path = vault / f"20-learner/evidence/{evidence_id}.md"
    committed_meta, _committed_body, committed_errors = tool.parse_note(
        committed_path
    )
    assert committed_errors == []
    return committed_meta


def append_demo_call_stack_verification(
    vault: Path,
    *,
    process: dict,
    evidence_id: str,
) -> dict:
    """Append one independent pass against the process-bound issued task."""

    projected = tool.project_verification_task_from_vault(
        vault, process_evidence_id=process["id"]
    )
    assert set(projected) == {
        "verification_task",
        "response_format",
        "success_criteria",
    }
    source, _body, parse_errors = tool.parse_note(
        vault / "20-learner/evidence/ev-demo-a17-001.md"
    )
    assert parse_errors == []
    source.update(
        {
            "id": evidence_id,
            "learner_id": process["learner_id"],
            "goal_id": process["goal_id"],
            "concept_id": process["concept_id"],
            "contract_id": process["contract_id"],
            "contract_version": process["contract_version"],
            "phase": "verification",
            "evidence_kind": "independent_performance",
            "carrier": process["carrier"],
            "teaching_item_id": process["teaching_item_id"],
            "teaching_delivery_fingerprint_at_observation": None,
            "verification_item_id": process["verification_task_id"],
            "verification_task_id": process["verification_task_id"],
            "bound_verification_task_id": process[
                "bound_verification_task_id"
            ],
            "route_id_at_observation": process["route_id_at_observation"],
            "route_version_at_observation": process[
                "route_version_at_observation"
            ],
            "decision_fingerprint_at_observation": None,
            "verification_unseen": True,
            "answer_revealed_before_first_attempt": False,
            "observation_validity": "valid",
            "demonstrates": [
                "explanation",
                "trace_prediction",
                "error_correction",
            ],
            "result": "pass",
            "independence": "independent",
            "assistance_level": "A0",
            "activity": process["activity"],
            "error_signature": None,
            "elapsed_seconds": 90,
            "attempts": 1,
            "hint_count": 0,
            "immediate_performance": 0.95,
            "near_transfer": 0.9,
            "delayed_retention": "not_tested",
            "response_correct": True,
            "explanation_quality": "pass",
            "self_reported_effort": 3,
            "baseline_evidence_id": None,
            "retention_task_id": None,
            "scheduled_for": None,
        }
    )
    observed_instant = max(
        tool.datetime.now(timezone.utc) - timedelta(milliseconds=1),
        tool.parse_iso_instant(process["observed_at"])
        + timedelta(milliseconds=1),
    )
    if hasattr(tool.datetime, "current"):
        tool.datetime.current = max(  # type: ignore[attr-defined]
            tool.datetime.current,  # type: ignore[attr-defined]
            observed_instant + timedelta(milliseconds=1),
        )
    else:
        wait_seconds = (
            observed_instant - tool.datetime.now(timezone.utc)
        ).total_seconds()
        if wait_seconds > 0:
            time.sleep(wait_seconds + 0.01)
    source["observed_at"] = observed_instant.isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    record_path = write_raw_evidence_record(
        vault,
        source,
        evidence_id=evidence_id,
        summary="调用栈未见任务 A0 独立通过。",
    )
    committed = tool.append_evidence(vault, record_path=record_path)
    assert committed["status"] == "committed", committed
    meta, _committed_body, committed_errors = tool.parse_note(
        vault / "20-learner/evidence" / f"{evidence_id}.md"
    )
    assert committed_errors == []
    return meta


def prepare_immediate_met_call_stack(root: Path, *, suffix: str) -> dict:
    """Produce two real issued, opened, independent immediate verifications."""

    vault = seed(root)
    process_one = append_demo_call_stack_process(
        vault,
        evidence_id=f"ev-{suffix}-process-1",
        result="pass",
    )
    verification_one = append_demo_call_stack_verification(
        vault,
        process=process_one,
        evidence_id=f"ev-{suffix}-verification-1",
    )
    second_resource = add_call_stack_resource(
        vault,
        suffix=f"{suffix}-learning-2",
        duration_minutes=0.5,
    )
    second_route = tool.issue_route(
        vault,
        record_path=write_learning_route_record(root, second_resource["id"]),
    )
    assert second_route["purpose"] == "learning"
    process_two = append_demo_call_stack_process(
        vault,
        evidence_id=f"ev-{suffix}-process-2",
        result="pass",
    )
    verification_two = append_demo_call_stack_verification(
        vault,
        process=process_two,
        evidence_id=f"ev-{suffix}-verification-2",
    )
    state_path = (
        vault / "20-learner/states/ks-demo-a17-kc-python-call-stack.md"
    )
    state, _body, state_errors = tool.parse_note(state_path)
    assert state_errors == []
    assert state["immediate_contract_status"] == "met", state
    assert state["retention_status"] == "not_started", state
    assert state["next_action"] == "schedule_retention", state
    assert state.get("current_retention_schedule_id") is None
    return {
        "vault": vault,
        "state": state,
        "state_path": state_path,
        "baseline": verification_two,
        "first_verification": verification_one,
        "latest_learning_route": second_route,
    }


def issue_retention_route_for_prepared(
    root: Path, prepared: dict, *, suffix: str
) -> dict:
    vault = prepared["vault"]
    baseline = prepared["baseline"]
    retention_resource = add_call_stack_resource(
        vault,
        suffix=f"{suffix}-retention",
        duration_minutes=2,
    )
    retention_route = tool.issue_route(
        vault,
        record_path=write_retention_route_record(
            root,
            resource_id=retention_resource["id"],
            baseline_evidence_id=baseline["id"],
        ),
    )
    assert retention_route["purpose"] == "retention"
    return {
        "retention_resource": retention_resource,
        "retention_route": retention_route,
    }


def prepare_retention_schedule(
    root: Path,
    *,
    suffix: str,
    not_before: str | None,
) -> dict:
    prepared = prepare_immediate_met_call_stack(root, suffix=suffix)
    vault = prepared["vault"]
    baseline = prepared["baseline"]
    issued = issue_retention_route_for_prepared(root, prepared, suffix=suffix)
    retention_resource = issued["retention_resource"]
    retention_route = issued["retention_route"]
    schedule_record = write_schedule_record(
        root,
        state=prepared["state"],
        baseline_evidence_id=baseline["id"],
        route_binding_id=retention_route["binding_id"],
        not_before=not_before,
    )
    schedule = tool.schedule_retention(vault, record_path=schedule_record)
    state, _body, state_errors = tool.parse_note(prepared["state_path"])
    assert state_errors == []
    assert state["current_retention_schedule_id"] == schedule[
        "retention_schedule_id"
    ]
    for removed in (
        "baseline_evidence_id",
        "retention_task_id",
        "retention_route_binding_id",
        "scheduled_for",
    ):
        assert removed not in state
    prepared.update(
        {
            "state": state,
            "retention_resource": retention_resource,
            "retention_route": retention_route,
            "schedule": schedule,
            "schedule_record": schedule_record,
        }
    )
    return prepared


def append_demo_retention_evidence(
    vault: Path,
    *,
    opened: dict,
    evidence_id: str,
    result: str = "pass",
    teaching_item_id: str | None = None,
) -> dict:
    """Append one delayed response that exactly copies an open receipt binding."""

    binding = opened["retention_binding"]
    state, _state_body, state_errors = tool.parse_note(
        vault / "20-learner/states/ks-demo-a17-kc-python-call-stack.md"
    )
    assert state_errors == []
    source, _body, parse_errors = tool.parse_note(
        vault / "20-learner/evidence/ev-demo-a17-001-retention.md"
    )
    assert parse_errors == []
    passed = result == "pass"
    source.update(
        {
            "id": evidence_id,
            **{
                field: state[field]
                for field in (
                    "learner_id",
                    "goal_id",
                    "concept_id",
                    "contract_id",
                    "contract_version",
                )
            },
            "phase": "retention",
            "evidence_kind": "delayed_transfer",
            "carrier": binding["carrier"],
            "teaching_item_id": (
                teaching_item_id
                if teaching_item_id is not None
                else binding["teaching_item_id"]
            ),
            "teaching_delivery_fingerprint_at_observation": None,
            "verification_item_id": binding["verification_item_id"],
            "verification_unseen": True,
            "answer_revealed_before_first_attempt": False,
            "verification_task_id": binding["verification_task_id"],
            "bound_verification_task_id": binding[
                "bound_verification_task_id"
            ],
            "route_id_at_observation": binding["route_id_at_observation"],
            "route_version_at_observation": binding[
                "route_version_at_observation"
            ],
            "decision_fingerprint_at_observation": None,
            "observation_validity": "valid",
            "demonstrates": ["delayed_retention"],
            "result": result,
            "independence": "independent",
            "assistance_level": "A0",
            "activity": binding["activity"],
            "error_signature": None if passed else "retention_return_order_error",
            "elapsed_seconds": 100,
            "attempts": 1,
            "hint_count": 0,
            "immediate_performance": 0.9 if passed else 0.3,
            "near_transfer": "not_tested",
            "delayed_retention": 0.9 if passed else 0.2,
            "response_correct": passed,
            "explanation_quality": "not_tested",
            "self_reported_effort": 3 if passed else 6,
            "baseline_evidence_id": binding["baseline_evidence_id"],
            "retention_task_id": binding["retention_task_id"],
            "scheduled_for": binding["scheduled_for"],
            "observed_at": tool.utc_now_precise(),
        }
    )
    record_path = write_raw_evidence_record(
        vault,
        source,
        evidence_id=evidence_id,
        summary=f"延迟验证 {result}。",
    )
    committed = tool.append_evidence(vault, record_path=record_path)
    assert committed["status"] == "committed", committed
    meta, _committed_body, committed_errors = tool.parse_note(
        vault / "20-learner/evidence" / f"{evidence_id}.md"
    )
    assert committed_errors == []
    return meta


def failed_process_record(
    evidence_id: str,
    *,
    observed_at: str,
    activity: str,
    carrier: str = "text_hybrid",
    assistance_level: str = "A1",
    attempts: int = 1,
    hint_count: int = 0,
    self_reported_effort: float = 4.0,
    immediate_performance: float = 0.7,
    observation_confidence: str = "medium",
    source_kind: str = "behavior_observation",
) -> tuple[str, dict]:
    return evidence_id, {
        "phase": "teaching_process",
        "observation_validity": "valid",
        "observation_confidence": observation_confidence,
        "source_kind": source_kind,
        "observed_at": observed_at,
        "activity": activity,
        "teaching_item_id": f"teach-{evidence_id}",
        "carrier": carrier,
        "assistance_level": assistance_level,
        "elapsed_seconds": 60,
        "attempts": attempts,
        "hint_count": hint_count,
        "self_reported_effort": self_reported_effort,
        "immediate_performance": immediate_performance,
        "result": "fail",
        "response_correct": False,
        "explanation_quality": "fail",
        "demonstrates": ["explanation"],
        "error_signature": "same-process-error",
    }


def rehash_route_binding_document(vault: Path, document: dict) -> None:
    previous_hash = document["chain_anchor"]
    for event in document["events"]:
        snapshot = event.get("issuance_snapshot")
        if isinstance(snapshot, dict):
            resources = snapshot.get("resources")
            intervention = snapshot.get("intervention")
            if isinstance(resources, list):
                event["resource_fingerprint"] = tool.sha256_fingerprint(resources)
                tasks = [
                    resource.get("verification_task")
                    for resource in resources
                    if isinstance(resource, dict)
                    and isinstance(resource.get("verification_task"), dict)
                ]
                if tasks:
                    event["verification_task_fingerprint"] = tool.sha256_fingerprint(
                        tasks[0]
                    )
            if isinstance(intervention, dict):
                event["intervention_fingerprint"] = tool.sha256_fingerprint(
                    intervention
                )
        event["previous_hash"] = previous_hash
        payload = dict(event)
        payload.pop("event_hash", None)
        event["event_hash"] = tool.sha256_fingerprint(payload)
        previous_hash = event["event_hash"]
    document["head_sequence"] = len(document["events"])
    document["head_hash"] = previous_hash
    manifest_path = vault / tool.MANIFEST_REL
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["route_binding_chain_length"] = len(document["events"])
    manifest["route_binding_chain_head"] = previous_hash
    tool.write_json(manifest_path, manifest)


def test_happy_path() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-happy-") as temporary:
        vault = seed(Path(temporary))
        errors, warnings, summary = tool.validate_vault(vault)
        assert errors == [], errors
        assert warnings == [], warnings
        assert summary["node_count"] == 37, summary

        index, index_errors = tool.build_index(vault)
        assert index_errors == [], index_errors
        assert all(
            relation["target"] in index["nodes"]
            for node in index["nodes"].values()
            for relation in node["relations"]
        )
        assert index["nodes"]["sys-router"]["wikilinks"] == [
            "usr-demo-a17",
            "goal-demo-a17-recursion",
            "ses-demo-a17-20260826t063000z",
            "dom-python",
        ]

        cone = tool.load_cone_data(vault)
        assert cone["candidate_id"] == "kc-python-call-stack", cone
        assert cone["candidate_source"] == "active_route_checkpoint", cone
        assert cone["audience"] == "agent_internal" and cone["authoritative"] is False
        assert sum(1 for node in cone["nodes"] if node["candidate"]) == 1
        selected = next(node for node in cone["nodes"] if node["candidate"])
        assert selected["selection_status"] == "selected"
        assert selected["routing_action"] == "diagnose_now"
        assert selected["next_step_id"] == selected["probe_id"]
        assert selected["activity"] is None
        assert selected["activity_id"] is None
        assert selected["verification_task_id"] is None
        assert selected["probe_id"] == "probe-python-call-stack-faded-v1"
        intervention_meta, _, intervention_errors = tool.parse_note(
            vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
        )
        resource_meta, _, resource_errors = tool.parse_note(
            vault / index["nodes"][intervention_meta["resolved_resource_id"]]["path"]
        )
        assert intervention_errors == [] and resource_errors == []
        assert intervention_meta["resolved_activity"] == "worked_example_fading"
        assert intervention_meta["resolved_resource_id"] == resource_meta["id"]
        assert intervention_meta["current_activity_id"] == resource_meta["id"]
        assert intervention_meta["resolved_carrier"] == resource_meta["carrier"]
        assert "worked_example_fading" in resource_meta["supported_activities"]
        assert resource_meta["duration_minutes"] == 4
        assert resource_meta["diagnostic_probe"]["id"] == selected["probe_id"]
        concept_meta, _, _ = tool.parse_note(
            vault / "10-domain/python/kc-python-recursion.md"
        )
        assert "focus_z" not in concept_meta
        focus_nodes = [
            node for node in index["nodes"].values() if node["type"] == "focus_snapshot"
        ]
        assert len(focus_nodes) == 7

        output = vault / "30-learning/visuals/test-cone.html"
        tool.export_cone(vault, output)
        assert output.is_file()
        try:
            tool.export_cone(vault, output)
        except tool.VaultError as exc:
            assert "拒绝覆盖" in str(exc)
        else:
            raise AssertionError("export_cone silently overwrote an existing file")


def test_inspect_cone_is_deterministic_and_read_only() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-inspect-") as temporary:
        vault = seed(Path(temporary))

        def snapshot() -> dict[str, str]:
            return {
                path.relative_to(vault).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(vault.rglob("*"))
                if path.is_file()
            }

        before = snapshot()
        first_code, first = capture_json(tool.inspect_cone, vault)
        second_code, second = capture_json(tool.inspect_cone, vault)
        after = snapshot()
        assert first_code == second_code == 0
        assert first == second
        assert before == after
        assert first["view_kind"] == "agent_internal_focus_inspection"
        assert first["privacy"] == "private"
        assert first["derived"] is True and first["rebuildable"] is True
        assert first["authoritative"] is False


def test_cone_never_falls_back_to_highest_score_without_active_route() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-no-route-cone-") as temporary:
        vault = seed(Path(temporary))
        intervention = vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
        intervention.rename(vault / "route-record.disabled")
        try:
            tool.load_cone_data(vault)
        except tool.VaultError as exc:
            assert "active intervention" in str(exc)
        else:
            raise AssertionError(
                "缺少 active route 时 Cone 必须拒绝生成，不能回退到最高 Focus 分"
            )


def test_unknown_focus_input_is_null_and_unranked() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-focus-null-") as temporary:
        vault = seed(Path(temporary))
        snapshot = next(
            (vault / "30-learning/visuals/snapshots").glob(
                "focus-demo-a17-goal-demo-a17-recursion-kc-python-recursion-*.md"
            )
        )
        meta, body, parse_errors = tool.parse_note(snapshot)
        assert parse_errors == []
        meta["interest_evidence"] = None
        meta["interest_evidence_status"] = "unknown"
        meta["focus_z"] = None
        meta["ranking_status"] = "incomplete"
        tool.atomic_write_text(snapshot, tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n")
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors
        cone = tool.load_cone_data(vault)
        recursion = next(node for node in cone["nodes"] if node["id"] == "kc-python-recursion")
        assert recursion["interest"] is None
        assert recursion["focus_z"] is None
        assert recursion["ranking_status"] == "incomplete"

        meta["interest_evidence"] = 0
        tool.atomic_write_text(snapshot, tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n")
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("在 unknown 时必须为 null" in item for item in errors), errors


def test_route_recovery() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-route-") as temporary:
        vault = seed(Path(temporary))
        marker = vault / tool.ROUTE_FILE
        backup = vault / "marker.backup"
        marker.rename(backup)
        errors, warnings, _ = tool.validate_vault(vault)
        assert errors == []
        assert any("marker 丢失" in item for item in warnings)

        code, result = capture_json(tool.recover_route, vault, 2, False)
        assert code == 0 and result["status"] == "unique_match"
        assert not marker.exists()
        code, result = capture_json(tool.recover_route, vault, 2, True)
        assert code == 0 and result["repaired"] is True and marker.exists()

        intervention = (
            vault
            / "30-learning/interventions/int-demo-a17-recursion-path.md"
        )
        intervention.rename(vault / "route-record.disabled")
        code, result = capture_json(tool.recover_learning_route, vault)
        assert code == 0
        assert result["status"] == "reconstructed_unconfirmed"
        assert result["candidate"]["current_checkpoint"] == "kc-python-call-stack"
        assert not intervention.exists(), "read-only recovery recreated a route"


def test_due_retention_recovery_issues_delayed_verification() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-due-retention-") as temporary:
        root = Path(temporary)
        not_before = (
            datetime.now(timezone.utc) + timedelta(days=8)
        ).isoformat()
        prepared = prepare_retention_schedule(
            root,
            suffix="due-recovery",
            not_before=not_before,
        )
        schedule = prepared["schedule"]
        assert schedule["retention_status"] == "pending"
        due_at = tool.parse_iso_instant(schedule["scheduled_for"]) + timedelta(
            seconds=1
        )
        with frozen_tool_clock(due_at):
            code, result = capture_json(
                tool.recover_learning_route, prepared["vault"]
            )
        assert code == 0, result
        assert result["status"] == "route_available", result
        assert result["next_action"]["action"] == "issue_delayed_verification"
        due_items = result["next_action"]["items"]
        assert len(due_items) == 1, due_items
        assert due_items[0]["concept_id"] == "kc-python-call-stack"
        assert due_items[0]["retention_schedule_id"] == schedule[
            "retention_schedule_id"
        ]
        assert due_items[0]["baseline_evidence_id"] == prepared["baseline"]["id"]
        assert due_items[0]["retention_task_id"] == schedule["retention_task_id"]
        assert due_items[0]["route_binding_id"] == prepared["retention_route"][
            "binding_id"
        ]


def test_no_silent_creation() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-empty-") as temporary:
        root = Path(temporary)
        code, result = capture_json(tool.recover_route, root, 2, False)
        assert code == 4 and result["status"] == "not_found"
        assert list(root.iterdir()) == [], "not-found recovery created files"


def test_mastery_rejects_high_help() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-help-") as temporary:
        vault = seed(Path(temporary))
        evidence = vault / "20-learner/evidence/ev-demo-a17-001.md"
        text = evidence.read_text(encoding="utf-8")
        evidence.write_text(
            text.replace('assistance_level: "A0"', 'assistance_level: "A4"'),
            encoding="utf-8",
            newline="\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("mastered 状态未满足结构化合同" in item for item in errors), errors


def test_nonbehavior_canonical_sources_cannot_satisfy_mastery() -> None:
    cases = (
        ("self_report", "ev-demo-a17-001", "verification"),
        ("model_generated", "ev-demo-a17-001-retention", "retention"),
    )
    for source_kind, target_evidence_id, expected_phase in cases:
        with tempfile.TemporaryDirectory(
            prefix=f"uc-demo-nonbehavior-{source_kind}-"
        ) as temporary:
            vault = seed(Path(temporary))
            session_path = (
                vault
                / "20-learner/sessions/ses-demo-a17-20260826t063000z.md"
            )
            session, session_body, session_errors = tool.parse_note(session_path)
            assert session_errors == []
            session["source_kind"] = source_kind
            tool.replace_note_meta(session_path, session, session_body)

            evidence_by_id: dict[str, dict] = {}
            for evidence_path in sorted(
                (vault / "20-learner/evidence").glob("*.md")
            ):
                evidence, evidence_body, parse_errors = tool.parse_note(
                    evidence_path
                )
                assert parse_errors == []
                # Every record derived from this canonical session must agree
                # with the session before the validator can assess mastery.
                evidence["source_kind"] = source_kind
                evidence["mastery_eligible"] = False
                refresh_evidence_derivations(evidence)
                assert evidence["observation_confidence"] == "low"
                assert (
                    evidence["observation_confidence_basis"]
                    == "nonbehavior_source_cap"
                )
                tool.replace_note_meta(evidence_path, evidence, evidence_body)
                evidence_by_id[evidence["id"]] = evidence

            target = evidence_by_id[target_evidence_id]
            assert target["phase"] == expected_phase
            assert target["source_ref_ids"] == [session["source_ref"]]
            assert target["field_bindings"] == tool.build_evidence_field_bindings(
                target
            )
            eligible, eligibility_failures = tool.evidence_mastery_eligibility(
                target
            )
            assert eligible is False
            assert eligibility_failures == ["source_not_behavior"]

            goal, _goal_body, goal_errors = tool.parse_note(
                vault / "20-learner/goals/goal-demo-a17-recursion.md"
            )
            assert goal_errors == []
            contract = next(
                item
                for item in goal["mastery_contracts"]
                if item["id"] == "mc-python-function-baseline"
            )
            state, _state_body, state_errors = tool.parse_note(
                vault / "20-learner/states/ks-demo-a17-kc-python-function.md"
            )
            assert state_errors == []
            scoped_evidence = [
                (evidence_id, evidence)
                for evidence_id, evidence in evidence_by_id.items()
                if evidence.get("learner_id") == target["learner_id"]
                and evidence.get("goal_id") == target["goal_id"]
                and evidence.get("concept_id") == target["concept_id"]
                and evidence.get("contract_id") == target["contract_id"]
                and evidence.get("contract_version") == target["contract_version"]
            ]
            contract_evaluation = tool.evaluate_mastery_contract(
                contract,
                scoped_evidence,
                state_context=state,
                as_of=state["evaluated_at"],
            )
            assert contract_evaluation["status"] == "in_progress"
            assert contract_evaluation["qualified_evidence_ids"] == []
            assert contract_evaluation["qualified_failure_evidence_ids"] == []

            errors, _warnings, _summary = tool.validate_vault(vault)
            assert any(
                "mastered 状态未满足结构化合同: "
                "ks-demo-a17-kc-python-function" in item
                for item in errors
            ), errors
            assert not any(
                "source_kind 必须从 canonical session 派生" in item
                or "observation_confidence 不是来源与资格推导值" in item
                or "field_binding source_ref_ids 非法" in item
                for item in errors
            ), errors

            observation = (
                text_policy._build_response_observation_from_validated_vault_inputs(
                    target_evidence_id,
                    target,
                    contract,
                    scoped_evidence,
                    comparison_context_from_key(target["context_key"]),
                    state_context=state,
                    as_of=state["evaluated_at"],
                )
            )
            assert observation["mastery_gate_met"] is False
            assert observation["source"]["derived_mastery_eligible"] is False
            assert observation["source"]["mastery_eligibility_failures"] == [
                "source_not_behavior"
            ]
            assert observation["mastery_gate_derivation"]["contract_status"] == (
                "in_progress"
            )
            assert observation["mastery_gate_derivation"][
                "qualified_evidence_ids"
            ] == []


def test_mastery_contract_requires_delayed_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-contract-") as temporary:
        vault = seed(Path(temporary))
        retention = vault / "20-learner/evidence/ev-demo-a17-001-retention.md"
        assert retention.is_file()
        retention.rename(vault / "ev-demo-a17-001-retention.disabled")
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("mastered 状态缺少合同要求的延迟保持证据" in item for item in errors), errors


def test_evidence_contract_version_must_match_state() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-contract-version-") as temporary:
        vault = seed(Path(temporary))
        evidence = vault / "20-learner/evidence/ev-demo-a17-001.md"
        text = evidence.read_text(encoding="utf-8")
        evidence.write_text(
            text.replace("contract_version: 1", "contract_version: 2"),
            encoding="utf-8",
            newline="\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("evidence contract_id/version 未在 goal 定义" in item for item in errors), errors
        assert any("state 与 evidence 的 goal/contract/version 不一致" in item for item in errors), errors


def test_contract_cannot_omit_transfer_requirement() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-contract-field-") as temporary:
        vault = seed(Path(temporary))
        goal_note = vault / "20-learner/goals/goal-demo-a17-recursion.md"
        meta, body, parse_errors = tool.parse_note(goal_note)
        assert parse_errors == []
        contract = next(
            item
            for item in meta["mastery_contracts"]
            if item["id"] == "mc-python-function-baseline"
        )
        del contract["requirements"]["min_near_transfer"]
        goal_note.write_text(
            tool.render_frontmatter(meta) + "\n" + body,
            encoding="utf-8",
            newline="\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("缺少 min_near_transfer" in item for item in errors), errors


def test_duplicate_evidence_cannot_satisfy_minimum_count() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-duplicate-evidence-") as temporary:
        vault = seed(Path(temporary))
        goal_note = vault / "20-learner/goals/goal-demo-a17-recursion.md"
        goal_meta, goal_body, parse_errors = tool.parse_note(goal_note)
        assert parse_errors == []
        contract = next(
            item
            for item in goal_meta["mastery_contracts"]
            if item["id"] == "mc-python-iteration-baseline"
        )
        # The v3 seed contains one immediate baseline plus one delayed-retention
        # verification. Require a third unique item so duplicating one ID cannot
        # satisfy the count.
        contract["requirements"]["minimum_qualified_evidence"] = 3
        goal_note.write_text(
            tool.render_frontmatter(goal_meta) + "\n" + goal_body,
            encoding="utf-8",
            newline="\n",
        )
        state = vault / "20-learner/states/ks-demo-a17-kc-python-iteration.md"
        text = state.read_text(encoding="utf-8")
        state.write_text(
            text.replace(
                "- supported_by: [[ev-demo-a17-002]]",
                "- supported_by: [[ev-demo-a17-002]]\n- supported_by: [[ev-demo-a17-002]]",
            ),
            encoding="utf-8",
            newline="\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("supported_by 重复引用同一 evidence" in item for item in errors), errors
        assert any("derived=in_progress" in item for item in errors), errors


def test_newer_failure_invalidates_older_mastery() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-newer-fail-") as temporary:
        vault = seed(Path(temporary))
        source = vault / "20-learner/evidence/ev-demo-a17-002.md"
        meta, body, parse_errors = tool.parse_note(source)
        assert parse_errors == []
        meta = dict(meta)
        meta["id"] = "ev-demo-a17-002-later-fail"
        meta["title"] = "证据：kc-python-iteration / later_failure"
        meta["evidence_kind"] = "delayed_transfer"
        meta["result"] = "fail"
        meta["response_correct"] = False
        meta["immediate_performance"] = 0.4
        meta["delayed_retention"] = 0.4
        meta["retention_delay_days"] = 8
        meta["observed_at"] = "2026-08-27T06:10:00+00:00"
        meta["field_bindings"] = tool.build_evidence_field_bindings(meta)
        tool.write_note(
            vault,
            "20-learner/evidence/ev-demo-a17-002-later-fail.md",
            meta,
            body,
        )
        state = vault / "20-learner/states/ks-demo-a17-kc-python-iteration.md"
        state_meta, state_body, state_errors = tool.parse_note(state)
        assert state_errors == []
        state_body = (
            state_body.rstrip()
            + "\n- supported_by: [[ev-demo-a17-002-later-fail]]\n"
        )
        for field in (
            "evaluated_at",
            "as_of",
            "boundary_derived_at",
            "last_assessed_at",
            "last_independent_evidence_at",
        ):
            state_meta[field] = meta["observed_at"]
        tool.atomic_write_text(
            state,
            tool.render_frontmatter(state_meta) + "\n" + state_body,
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("derived=not_met" in item for item in errors), errors
        assert any("mastered 状态未满足结构化合同" in item for item in errors), errors


def test_retention_days_cannot_exceed_observed_delay() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-retention-days-") as temporary:
        vault = seed(Path(temporary))
        state = vault / "20-learner/states/ks-demo-a17-kc-python-iteration.md"
        text = state.read_text(encoding="utf-8")
        state.write_text(
            text.replace('retention_status: "passed_7d"', 'retention_status: "passed_365d"'),
            encoding="utf-8",
            newline="\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("retention_status 与实际验证天数不一致" in item for item in errors), errors


def test_failed_explanation_cannot_satisfy_explanation_capability() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-explanation-conflict-") as temporary:
        vault = seed(Path(temporary))
        evidence = vault / "20-learner/evidence/ev-demo-a17-001.md"
        text = evidence.read_text(encoding="utf-8")
        evidence.write_text(
            text.replace('explanation_quality: "pass"', 'explanation_quality: "fail"'),
            encoding="utf-8",
            newline="\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("explanation 声明与 explanation_quality 冲突" in item for item in errors), errors
        assert any("mastered 状态未满足结构化合同" in item for item in errors), errors


def test_evidence_scores_must_stay_in_unit_interval() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-score-range-") as temporary:
        vault = seed(Path(temporary))
        baseline = vault / "20-learner/evidence/ev-demo-a17-002-baseline.md"
        baseline_text = baseline.read_text(encoding="utf-8")
        baseline.write_text(
            baseline_text.replace("immediate_performance: 0.92", "immediate_performance: 9.0")
            .replace("near_transfer: 0.86", "near_transfer: 9.0"),
            encoding="utf-8",
            newline="\n",
        )
        retention = vault / "20-learner/evidence/ev-demo-a17-002.md"
        retention_text = retention.read_text(encoding="utf-8")
        retention.write_text(
            retention_text.replace("delayed_retention: 0.82", "delayed_retention: 9.0"),
            encoding="utf-8",
            newline="\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("immediate_performance 必须在 0..1" in item for item in errors), errors
        assert any("near_transfer 必须在 0..1" in item for item in errors), errors
        assert any("delayed_retention 必须在 0..1" in item for item in errors), errors


def test_route_checkpoint_must_be_teachable() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-checkpoint-") as temporary:
        vault = seed(Path(temporary))
        route = vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
        text = route.read_text(encoding="utf-8")
        route.write_text(
            text.replace(
                'current_checkpoint: "kc-python-call-stack"',
                'current_checkpoint: "kc-python-recursion"',
            ),
            encoding="utf-8",
            newline="\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("checkpoint 不是可学 outer_fringe" in item for item in errors), errors
        try:
            tool.load_cone_data(vault)
        except tool.VaultError as exc:
            assert "Vault 校验失败" in str(exc)
        else:
            raise AssertionError("blocked checkpoint was exported as a teaching candidate")


def test_route_cannot_reuse_state_from_another_goal_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-cross-goal-") as temporary:
        vault = seed(Path(temporary))
        state = vault / "20-learner/states/ks-demo-a17-kc-python-call-stack.md"
        text = state.read_text(encoding="utf-8")
        state.write_text(
            text.replace(
                'goal_id: "goal-demo-a17-recursion"',
                'goal_id: "goal-other-scope"',
            ),
            encoding="utf-8",
            newline="\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("checkpoint 不是可学 outer_fringe" in item for item in errors), errors


def test_route_cannot_reuse_completed_evidence_from_another_goal() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-cross-goal-evidence-") as temporary:
        vault = seed(Path(temporary))
        evidence = vault / "20-learner/evidence/ev-demo-a17-002.md"
        text = evidence.read_text(encoding="utf-8")
        evidence.write_text(
            text.replace(
                'goal_id: "goal-demo-a17-recursion"',
                'goal_id: "goal-other-scope"',
            ),
            encoding="utf-8",
            newline="\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("completed evidence 属于其他目标" in item for item in errors), errors


def test_focus_snapshot_must_remain_private_and_rebuildable() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-focus-scope-") as temporary:
        vault = seed(Path(temporary))
        matches = list(
            (vault / "30-learning/visuals/snapshots").glob(
                "focus-demo-a17-goal-demo-a17-recursion-kc-python-recursion-*.md"
            )
        )
        assert len(matches) == 1, matches
        snapshot = matches[0]
        text = snapshot.read_text(encoding="utf-8")
        snapshot.write_text(
            text.replace('privacy: "private"', 'privacy: "shared"'),
            encoding="utf-8",
            newline="\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("focus snapshot 必须 private + derived + rebuildable" in item for item in errors), errors


def test_route_recovery_requires_unique_active_route() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-routes-") as temporary:
        vault = seed(Path(temporary))
        source = vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
        meta, body, parse_errors = tool.parse_note(source)
        assert parse_errors == []
        meta["id"] = "int-demo-a17-recursion-branch"
        meta["title"] = "递归临时活动支线"
        meta["route_id"] = "route-demo-a17-recursion-branch"
        meta["parent_route_id"] = "route-demo-a17-recursion"
        meta["return_checkpoint"] = "kc-python-call-stack"
        tool.write_note(
            vault,
            "30-learning/interventions/int-demo-a17-recursion-branch.md",
            meta,
            body,
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("多个 active route" in item for item in errors), errors
        code, result = capture_json(tool.recover_learning_route, vault)
        assert code == 3 and result["status"] == "multiple_matches", result
        assert len(result["routes"]) == 2, result


def test_requires_cycle_is_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-cycle-") as temporary:
        vault = seed(Path(temporary))
        function_note = vault / "10-domain/python/kc-python-function.md"
        text = function_note.read_text(encoding="utf-8")
        function_note.write_text(
            text.replace(
                "- related_to: [[kc-python-call-stack]]",
                "- related_to: [[kc-python-call-stack]]\n- requires: [[kc-python-recursion]]",
            ),
            encoding="utf-8",
            newline="\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("requires 存在环" in item for item in errors), errors


def test_title_is_not_inserted_as_html() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-xss-") as temporary:
        vault = seed(Path(temporary))
        note = vault / "10-domain/python/kc-python-recursion.md"
        text = note.read_text(encoding="utf-8")
        note.write_text(
            text.replace(
                'title: "递归"',
                'title: "</script><img src=x onerror=alert(1)>"',
            ),
            encoding="utf-8",
            newline="\n",
        )
        output = vault / "30-learning/visuals/xss-test.html"
        tool.export_cone(vault, output)
        html = output.read_text(encoding="utf-8")
        assert "detail.innerHTML" not in html
        assert 'title: "</script>' not in html
        assert "<\\/script><img" in html


def canonical_context_key(
    *,
    domain: str,
    knowledge_kind: str,
    target_performance: str,
    prior_knowledge_band: str,
    task_difficulty: str,
) -> str:
    return "|".join(
        (
            f"domain={domain.casefold()}",
            f"knowledge_kind={knowledge_kind}",
            f"target_performance={target_performance}",
            f"prior_band={prior_knowledge_band}",
            f"task_difficulty={task_difficulty}",
        )
    )


def comparison_context_from_key(value: str) -> dict[str, str]:
    parts = dict(part.split("=", 1) for part in value.split("|"))
    assert set(parts) == {
        "domain",
        "knowledge_kind",
        "target_performance",
        "prior_band",
        "task_difficulty",
    }, parts
    return parts


def text_context(**overrides):
    context = {
        "learner_id": "demo-a17",
        "goal_id": "goal-demo-a17-recursion",
        "concept_id": "kc-python-call-stack",
        "contract_id": "mc-python-call-stack",
        "contract_version": 1,
        "route_id": "route-demo-a17-recursion",
        "route_version": 1,
        "bound_verification_task_id": "verify-python-call-stack-unseen-v1",
        "evidence_refs": [],
        "response_profile_refs": [],
        "response_profile_observations": [],
        "domain": "python",
        "knowledge_kind": "rule",
        "target_performance": "discriminate",
        "prior_knowledge_band": "partial",
        "task_difficulty": "medium",
        "comparison_gate": {
            "retention_required": False,
            "task_difficulty": "medium",
        },
        "delivery_intent": "learn",
        "text_sufficiency": "sufficient",
    }
    context.update(overrides)
    if "comparison_gate" not in overrides and "task_difficulty" in overrides:
        context["comparison_gate"] = {
            "retention_required": False,
            "task_difficulty": context["task_difficulty"],
        }
    if "context_key" not in overrides:
        context["context_key"] = canonical_context_key(
            domain=context["domain"],
            knowledge_kind=context["knowledge_kind"],
            target_performance=context["target_performance"],
            prior_knowledge_band=context["prior_knowledge_band"],
            task_difficulty=context["task_difficulty"],
        )
    if "verification_content_guard" not in overrides:
        context["verification_content_guard"] = verification_guard(
            context["bound_verification_task_id"]
        )
    return context


def decision_scope(decision: dict) -> dict:
    return {
        key: decision[key]
        for key in (
            "learner_id",
            "goal_id",
            "concept_id",
            "contract_id",
            "contract_version",
        )
    }


def valid_delivery_content(*, vault=None, **overrides):
    content = {
        "teaching_basis": {"anchor_ids": [], "focus_capabilities": ["explanation"]},
        "learning_objective": "区分递归与循环",
        "method_label": "先比较，再独立判断",
        "orientation": "先看两个最小案例。",
        "explanation": "只解释决定差异的规则。",
        "example": "案例 A / 案例 B",
        "learner_task": "判断第三个案例并说明理由。",
        "response_format": "结论＋一句理由",
        "feedback_rule": "只纠正当前错误。",
        "verification_rule": "教学过程证据被接受后，才给出绑定的未见案例。",
        "success_criteria": "独立判断正确且理由命中规则。",
        "next_step": None,
    }
    content.update(overrides)
    if vault is not None:
        brief = tool.prepare_teaching_brief(vault)
        content["teaching_basis"].update({
            field: brief[field]
            for field in ("route_binding_id", "decision_fingerprint", "brief_fingerprint")
        })
    return content


def ensure_teachable_call_stack(vault: Path, *, suffix: str) -> None:
    """Use canonical diagnostic evidence and a fresh route, never forge mastery."""
    state, _body, errors = tool.parse_note(
        vault / "20-learner/states/ks-demo-a17-kc-python-call-stack.md"
    )
    assert errors == [], errors
    if state["mastery"] != "unknown":
        ensure_local_learning_route(vault, suffix=suffix)
        return
    evidence_id = "ev-ready-diagnostic-" + hashlib.sha256(suffix.encode("utf-8")).hexdigest()[:12]
    diagnostic, _issuance, _probe = call_stack_diagnostic_fixture(vault, evidence_id=evidence_id)
    record = write_raw_evidence_record(
        vault, diagnostic, evidence_id=evidence_id,
        summary="教学测试先完成真实绑定诊断；返回方向存在已观察到的错误。",
    )
    committed = tool.append_evidence(vault, record_path=record)
    assert committed["state_mastery"] == "none", committed
    resource = add_call_stack_resource(
        vault, suffix="ready-" + hashlib.sha256(suffix.encode("utf-8")).hexdigest()[:12],
        duration_minutes=0.5,
    )
    issued = tool.issue_route(vault, record_path=write_learning_route_record(vault.parent, resource["id"]))
    assert issued["routing_action"] == "teach_now", issued


def test_text_hybrid_is_default_for_text_sufficient_learning() -> None:
    decision = text_policy.decide_text_activity(text_context())
    assert decision["activity"] == "contrast_cases"
    assert decision["carrier"] == "text_hybrid"
    assert decision["selection_status"] == "selected"
    assert "text_default_low_coordination" in decision["reason_codes"]
    assert decision["learner_id"] == "demo-a17"
    assert decision["goal_id"] == "goal-demo-a17-recursion"
    assert decision["concept_id"] == "kc-python-call-stack"
    assert decision["contract_id"] == "mc-python-call-stack"
    assert decision["contract_version"] == 1
    assert decision["evidence_refs"] == []
    assert decision["scope"] == decision_scope(decision)
    assert decision["context_key"] == canonical_context_key(
        domain="python",
        knowledge_kind="rule",
        target_performance="discriminate",
        prior_knowledge_band="partial",
        task_difficulty="medium",
    )
    assert decision["comparison_gate"] == {
        "retention_required": False,
        "task_difficulty": "medium",
    }


def test_every_demo_concept_uses_text_policy_vocabulary() -> None:
    seed_data = json.loads(tool.SEED_PATH.read_text(encoding="utf-8"))
    contracts = {
        item["concept_id"]: item
        for item in seed_data["goal"]["mastery_contracts"]
    }
    for concept in seed_data["concepts"]:
        contract = contracts[concept["id"]]
        decision = text_policy.decide_text_activity(
            text_context(
                concept_id=concept["id"],
                contract_id=contract["id"],
                contract_version=contract["version"],
                knowledge_kind=concept["knowledge_kind"],
                target_performance="explain",
            )
        )
        assert decision["knowledge_kind"] == concept["knowledge_kind"]
        assert decision["protocol_version"] == "text-demo-v0.5"


def test_validator_rejects_old_text_protocol() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-old-text-protocol-") as temporary:
        vault = seed(Path(temporary))
        resource = vault / "30-learning/resources/res-python-call-stack-trace.md"
        meta, body, parse_errors = tool.parse_note(resource)
        assert parse_errors == []
        meta["protocol_version"] = "text-demo-v0.1"
        tool.atomic_write_text(resource, tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n")
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("protocol_version 非法" in item for item in errors), errors


def test_focus_diagnosis_requires_explicit_probe_binding() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-focus-probe-") as temporary:
        vault = seed(Path(temporary))
        snapshot = next(
            (vault / "30-learning/visuals/snapshots").glob(
                "focus-demo-a17-goal-demo-a17-recursion-kc-python-call-stack-*.md"
            )
        )
        meta, body, parse_errors = tool.parse_note(snapshot)
        assert parse_errors == []
        meta["interest_evidence"] = None
        meta["interest_evidence_status"] = "unknown"
        meta["focus_z"] = None
        meta["ranking_status"] = "incomplete"
        tool.atomic_write_text(snapshot, tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n")
        cone = tool.load_cone_data(vault)
        selected = next(node for node in cone["nodes"] if node["candidate"])
        # Missing Focus input cannot replace the canonical mastery/readiness
        # diagnosis already bound by the active route.
        assert selected["routing_action"] == "diagnose_now"
        assert selected["selection_basis"] == "active_route"

        # Diagnosis is justified by unknown mastery/readiness and must bind a
        # concrete probe; it is not justified by missing interest data.
        state = vault / "20-learner/states/ks-demo-a17-kc-python-call-stack.md"
        state_meta, state_body, state_errors = tool.parse_note(state)
        assert state_errors == []
        state_meta["mastery"] = "unknown"
        state_meta["mastery_confidence"] = "low"
        tool.atomic_write_text(
            state,
            tool.render_frontmatter(state_meta) + "\n" + state_body.rstrip() + "\n",
        )
        cone = tool.load_cone_data(vault)
        selected = next(node for node in cone["nodes"] if node["candidate"])
        assert selected["routing_action"] == "diagnose_now"
        assert selected["probe_id"] == "probe-python-call-stack-faded-v1"
        assert selected["next_step_id"] == selected["probe_id"]
        assert selected["activity_id"] is None
        assert selected["verification_task_id"] is None
        assert "probe_available" in selected["reason_codes"]

        intervention = vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
        route_meta, route_body, route_errors = tool.parse_note(intervention)
        assert route_errors == []
        route_meta["current_probe_id"] = "missing-probe"
        tool.atomic_write_text(
            intervention,
            tool.render_frontmatter(route_meta) + "\n" + route_body.rstrip() + "\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("current_probe_id 与 resource 不一致" in item for item in errors), errors
        try:
            tool.load_cone_data(vault)
        except tool.VaultError as exc:
            assert "Vault 校验失败" in str(exc)
        else:
            raise AssertionError("缺少真实 probe 时不得生成 diagnose_now")


def test_diagnostic_probe_must_come_from_issuance_snapshot() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-diagnostic-issuance-") as temporary:
        vault = seed(Path(temporary))
        diagnostic, _issuance, _probe = call_stack_diagnostic_fixture(
            vault,
            evidence_id="ev-demo-diagnostic-unissued-probe",
            teaching_item_id="probe-never-issued",
        )
        record_path = write_raw_evidence_record(
            vault,
            diagnostic,
            evidence_id=diagnostic["id"],
            summary="伪造未签发诊断 probe。",
        )
        try:
            tool.append_evidence(vault, record_path=record_path)
        except tool.VaultError as exc:
            assert (
                "diagnostic teaching_item_id 必须唯一绑定已签发 resource 的 probe"
                in str(exc)
            ), exc
        else:
            raise AssertionError("append-evidence 不得接受未签发 diagnostic probe")
        assert not (
            vault
            / "20-learner/evidence/ev-demo-diagnostic-unissued-probe.md"
        ).exists()


def test_diagnostic_evidence_recomputes_state_and_rejects_stale_or_forged_snapshot() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-diagnostic-state-") as temporary:
        vault = seed(Path(temporary))
        diagnostic, _issuance, probe = call_stack_diagnostic_fixture(
            vault, evidence_id="ev-demo-call-stack-diagnostic"
        )
        record_path = write_raw_evidence_record(
            vault,
            diagnostic,
            evidence_id=diagnostic["id"],
            summary="调用栈已签发诊断显示返回顺序混淆。",
        )
        committed = tool.append_evidence(vault, record_path=record_path)
        assert committed["status"] == "committed", committed
        diagnostic_path = vault / (
            "20-learner/evidence/ev-demo-call-stack-diagnostic.md"
        )
        diagnostic, _diagnostic_body, diagnostic_errors = tool.parse_note(
            diagnostic_path
        )
        assert diagnostic_errors == []
        assert diagnostic["teaching_item_id"] == probe["id"]

        state_path = (
            vault / "20-learner/states/ks-demo-a17-kc-python-call-stack.md"
        )
        state, state_body, state_errors = tool.parse_note(state_path)
        assert state_errors == []
        index, index_errors = tool.build_index(vault)
        assert index_errors == []
        supported_ids = [
            relation["target"]
            for relation in index["nodes"][state["id"]]["relations"]
            if relation["type"] == "supported_by"
        ]
        evidence_records = []
        for evidence_id in supported_ids:
            node = index["nodes"][evidence_id]
            evidence, _evidence_body, evidence_errors = tool.parse_note(
                vault / node["path"]
            )
            assert evidence_errors == []
            evidence_records.append((evidence_id, evidence))
        goal, _goal_body, goal_errors = tool.parse_note(
            vault / "20-learner/goals/goal-demo-a17-recursion.md"
        )
        assert goal_errors == []
        contract = next(
            item
            for item in goal["mastery_contracts"]
            if item["id"] == state["contract_id"]
            and item["version"] == state["contract_version"]
        )
        evaluation = tool.evaluate_mastery_contract(
            contract,
            evidence_records,
            state_context=state,
            as_of=state["evaluated_at"],
            allow_synthetic_demo=True,
        )
        knowledge = tool.derive_state_knowledge_status(
            evaluation,
            evidence_records,
            as_of=state["evaluated_at"],
        )
        concept_relations = {
            node_id: node["relations"]
            for node_id, node in index["nodes"].items()
            if node["type"] == "concept"
        }
        mastery_by_concept: dict[str, str] = {}
        for candidate in sorted((vault / "20-learner/states").glob("*.md")):
            candidate_meta, _candidate_body, candidate_errors = tool.parse_note(
                candidate
            )
            assert candidate_errors == []
            mastery_by_concept[candidate_meta["concept_id"]] = candidate_meta[
                "mastery"
            ]
        mastery_by_concept[state["concept_id"]] = knowledge["mastery"]
        boundary = tool.derive_boundary_positions(
            concept_relations, mastery_by_concept
        )[state["concept_id"]]

        assert knowledge["mastery"] == "none"
        assert knowledge["mastery_confidence"] == "medium"
        assert knowledge["misconception_flags"] == ["return_order_confusion"]
        assert knowledge["diagnostic_snapshot"] == tool.derive_diagnostic_snapshot(
            evidence_records, as_of=state["evaluated_at"]
        )
        assert knowledge["diagnostic_snapshot"]["teaching_item_id"] == probe["id"]
        assert boundary == "outer_fringe"
        assert state["mastery"] == knowledge["mastery"]
        assert state["mastery_confidence"] == knowledge["mastery_confidence"]
        assert state["misconception_flags"] == knowledge["misconception_flags"]
        assert state["diagnostic_snapshot"] == knowledge["diagnostic_snapshot"]
        assert state["boundary_position"] == boundary
        assert state["as_of"] == diagnostic["observed_at"]
        assert state["boundary_derived_at"] == diagnostic["observed_at"]
        assert state["last_assessed_at"] == diagnostic["observed_at"]
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors

        canonical_state = json.loads(json.dumps(state))
        stale_state = json.loads(json.dumps(canonical_state))
        stale_state.update(
            {
                "mastery": "unknown",
                "mastery_confidence": "low",
                "misconception_flags": [],
                "diagnostic_snapshot": None,
            }
        )
        tool.atomic_write_text(
            state_path,
            tool.render_frontmatter(stale_state) + "\n" + state_body,
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        for field in (
            "mastery",
            "mastery_confidence",
            "misconception_flags",
            "diagnostic_snapshot",
        ):
            assert any(
                f"state {field} 不是 canonical evidence 推导值" in error
                for error in errors
            ), (field, errors)

        forged_state = json.loads(json.dumps(canonical_state))
        forged_state["boundary_position"] = "blocked"
        forged_state["diagnostic_snapshot"]["source_evidence_id"] = (
            "ev-forged-diagnostic"
        )
        tool.atomic_write_text(
            state_path,
            tool.render_frontmatter(forged_state) + "\n" + state_body,
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "state diagnostic_snapshot 不是 canonical evidence 推导值" in error
            for error in errors
        ), errors
        assert any(
            "state boundary_position 不是图谱与 mastery 推导值" in error
            for error in errors
        ), errors


def test_first_text_failure_repairs_text_before_video() -> None:
    decision = text_policy.decide_text_activity(
        text_context(
            same_error_count=1,
            text_variants_tried=1,
            max_assistance_level="A2",
            matching_affordance="video",
            matching_affordance_reason="continuous_motion_is_target",
        )
    )
    assert decision["carrier"] == "text_hybrid"
    assert decision["selection_status"] == "repair_selected"
    assert decision["escalation"]["status"] == "text_repair_required"


def test_prerequisite_gap_replans_without_medium_escalation() -> None:
    decision = text_policy.decide_text_activity(
        text_context(
            prerequisite_gap=True,
            same_error_count=3,
            text_variants_tried=3,
            max_assistance_level="A3",
            matching_affordance="interactive",
            matching_affordance_reason="real_time_feedback_required",
        )
    )
    assert decision["selection_status"] == "blocked"
    assert decision["carrier"] == "text_hybrid"
    assert decision["escalation"]["status"] == "not_eligible"
    assert decision["reason_codes"] == ["prerequisite_gap"]


def test_repeated_text_failure_requires_matching_affordance_to_escalate() -> None:
    no_affordance = text_policy.decide_text_activity(
        text_context(same_error_count=2, text_variants_tried=2, max_assistance_level="A2")
    )
    assert no_affordance["carrier"] == "text_hybrid"
    assert no_affordance["escalation"]["status"] == "text_repair_required"

    escalated = text_policy.decide_text_activity(
        text_context(
            same_error_count=2,
            text_variants_tried=2,
            max_assistance_level="A2",
            matching_affordance="interactive",
            matching_affordance_reason="real_time_feedback_required",
        )
    )
    assert escalated["carrier"] == "interactive"
    assert escalated["escalation"] == {
        "status": "selected",
        "target_medium": "interactive",
        "affordance_reason": "real_time_feedback_required",
    }


def test_delivery_plan_allowlist_hides_internal_fields() -> None:
    decision = text_policy.decide_text_activity(text_context())
    decision.update(
        {
            "learner_id": "secret-learner",
            "focus_z": 0.91,
            "reason_codes": ["internal-only"],
        }
    )
    content = valid_delivery_content(focus_z=0.91, assistance_level="A2")
    delivery = text_policy.project_delivery_plan(decision, content)
    assert set(delivery) == set(text_policy.USER_DELIVERY_FIELDS)
    assert delivery["medium"] == "文字文件＋对话"
    serialized = json.dumps(delivery, ensure_ascii=False)
    for forbidden in ("secret-learner", "focus_z", "reason_codes", "A2"):
        assert forbidden not in serialized


def test_process_evidence_drives_repair_delivery_and_measured_cost() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-process-partial-") as temporary:
        vault = seed(Path(temporary))
        intervention_path = (
            vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
        )
        intervention, intervention_body, intervention_errors = tool.parse_note(
            intervention_path
        )
        assert intervention_errors == []
        process_path = vault / "20-learner/evidence/ev-demo-a17-003.md"
        process, process_body, process_errors = tool.parse_note(process_path)
        assert process_errors == []

        assert intervention["teaching_resolution_schema"] == (
            "uc-active-teaching-resolution/0.2"
        )
        assert intervention["resolved_process_status"] == "repair_required"
        assert intervention["resolved_process_refs"] == [process["id"]]
        assert intervention["resolved_process_feedback_rule"] == (
            "reduce_information_then_correct_current_error"
        )
        assert intervention["resolved_process_next_action"] == "shorter_text_repair"
        assert intervention["resolved_latest_teaching_item_id"] == process[
            "teaching_item_id"
        ]
        assert intervention["resolved_max_observed_assistance_level"] == "A1"
        assert intervention["resolved_process_support_load"] == "high"
        assert intervention["resolved_activity"] == "worked_example_fading"
        assert intervention["resolved_activity"] != process["activity"]
        resource_meta, _resource_body, resource_errors = tool.parse_note(
            vault
            / "30-learning/resources"
            / f"{intervention['resolved_resource_id']}.md"
        )
        assert resource_errors == []
        assert resource_meta["duration_minutes"] == 4
        assert "worked_example_fading" in resource_meta["supported_activities"]
        assert intervention["resolved_process_cost"] == {
            "practice_feedback_seconds": 430.0,
            "practice_feedback_minutes": 7.167,
            "total_attempts": 2,
            "total_hint_count": 1,
            "mean_self_reported_effort": 5.0,
        }
        assert intervention["resolved_cost_vector"]["practice_feedback"] == 7.167

        resolved = tool.resolve_active_teaching(
            vault,
            write=False,
            _include_internal=True,
            _as_of=intervention["resolved_at"],
        )
        decision = resolved["_decision"]
        assert decision["process_adaptation"]["status"] == "repair_required"
        assert decision["repair_selection_basis"] == "measured_cost_alternative"
        projected = text_policy.project_delivery_plan(
            decision,
            valid_delivery_content(
                feedback_rule="调用者伪造：直接公布完整答案。",
                next_step={
                    "instruction": "调用者伪造：跳过修复。",
                    "when": "立即",
                },
            ),
        )
        assert projected["feedback_rule"] == text_policy.PROCESS_FEEDBACK_RULE_PUBLIC[
            "reduce_information_then_correct_current_error"
        ]
        assert projected["next_step"] == {
            "instruction": text_policy.PROCESS_NEXT_ACTION_PUBLIC[
                "shorter_text_repair"
            ],
            "when": None,
        }
        assert "伪造" not in json.dumps(projected, ensure_ascii=False)

        original_cost_vector = dict(intervention["resolved_cost_vector"])
        process["elapsed_seconds"] = 550
        process["hint_count"] = 3
        refresh_evidence_derivations(process)
        tool.atomic_write_text(
            process_path,
            tool.render_frontmatter(process) + "\n" + process_body.rstrip() + "\n",
        )
        updated = tool.resolve_active_teaching(vault, write=True)
        assert updated["resolved_process_cost"]["practice_feedback_seconds"] == 550.0
        assert updated["resolved_process_cost"]["practice_feedback_minutes"] == 9.167
        assert updated["resolved_process_cost"]["total_hint_count"] == 3
        assert updated["resolved_cost_vector"]["practice_feedback"] == 9.167
        assert updated["resolved_process_cost"] != intervention[
            "resolved_process_cost"
        ]
        assert updated["resolved_cost_vector"] != original_cost_vector
        for dimension, value in original_cost_vector.items():
            if dimension != "practice_feedback":
                assert updated["resolved_cost_vector"][dimension] == value
        persisted, _persisted_body, persisted_errors = tool.parse_note(
            intervention_path
        )
        assert persisted_errors == []
        assert persisted["resolved_process_cost"] == updated[
            "resolved_process_cost"
        ]
        assert persisted["resolved_cost_vector"] == updated["resolved_cost_vector"]

    with tempfile.TemporaryDirectory(prefix="uc-demo-process-fail-") as temporary:
        vault = seed(Path(temporary))
        process_path = vault / "20-learner/evidence/ev-demo-a17-003.md"
        process, process_body, process_errors = tool.parse_note(process_path)
        assert process_errors == []
        process.update(
            {
                "result": "fail",
                "response_correct": False,
                "explanation_quality": "fail",
            }
        )
        refresh_evidence_derivations(process)
        tool.atomic_write_text(
            process_path,
            tool.render_frontmatter(process) + "\n" + process_body.rstrip() + "\n",
        )
        failed = tool.resolve_active_teaching(vault, write=True)
        assert failed["resolved_process_status"] == "repair_required"
        assert failed["resolved_process_refs"] == [process["id"]]
        assert failed["resolved_process_feedback_rule"] == (
            "reduce_information_then_correct_current_error"
        )
        assert failed["resolved_process_next_action"] == "shorter_text_repair"
        assert failed["resolved_process_support_load"] == "high"
        assert failed["resolved_activity"] != process["activity"]


def test_measured_process_cost_changes_repair_activity_selection() -> None:
    def repair_context(*, measured_minutes: float, measured_seconds: float) -> dict:
        return text_context(
            same_error_count=1,
            text_variants_tried=1,
            process_adaptation={
                "schema": "uc-process-adaptation/0.1",
                "source_evidence_ids": ["ev-process-cost-1"],
                "consumer_ids": [
                    "feedback_selection",
                    "activity_selection",
                    "representation_selection",
                ],
                "cost_summary": {
                    "practice_feedback_seconds": measured_seconds,
                    "practice_feedback_minutes": measured_minutes,
                    "total_attempts": 1,
                    "total_hint_count": 1,
                    "mean_self_reported_effort": 4.0,
                },
                "max_observed_assistance_level": "A1",
                "support_load_status": "high",
                "status": "repair_required",
                "latest_evidence_id": "ev-process-cost-1",
                "latest_activity": "error_analysis",
                "latest_teaching_item_id": "teach-process-cost-1",
                "latest_error_signature": "return_order_confusion",
                "same_error_count": 1,
                "text_variants_tried": 1,
                "feedback_rule": "reduce_information_then_correct_current_error",
                "next_action": "shorter_text_repair",
            },
            available_text_activities=[
                "predict_explain",
                "contrast_cases",
                "worked_example_fading",
            ],
            available_text_activity_costs={
                "predict_explain": 6,
                "contrast_cases": 6,
                "worked_example_fading": 4,
            },
            estimated_practice_feedback_minutes=5,
        )

    over_budget = text_policy.decide_text_activity(
        repair_context(measured_minutes=7.167, measured_seconds=430)
    )
    assert over_budget["activity"] == "worked_example_fading", over_budget
    assert over_budget["repair_selection_basis"] == "measured_cost_alternative"
    assert over_budget["process_cost_selection"] == {
        "status": "over_estimate",
        "estimated_minutes": 5.0,
        "measured_minutes": 7.167,
        "selected_by_cost": True,
        "consumer": "activity_selection",
    }

    within_budget = text_policy.decide_text_activity(
        repair_context(measured_minutes=4.0, measured_seconds=240)
    )
    assert within_budget["activity"] == "contrast_cases", within_budget
    assert within_budget["repair_selection_basis"] == "available_text_alternative"
    assert within_budget["process_cost_selection"] == {
        "status": "within_estimate",
        "estimated_minutes": 5.0,
        "measured_minutes": 4.0,
        "selected_by_cost": False,
        "consumer": "activity_selection",
    }


def test_process_attempt_identity_rejects_replay_but_allows_later_retry() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-process-replay-") as temporary:
        vault = seed(Path(temporary))
        source_path = vault / "20-learner/evidence/ev-demo-a17-003.md"
        replay, replay_body, replay_errors = tool.parse_note(source_path)
        assert replay_errors == []
        replay.update(
            {
                "id": "ev-demo-a17-003-replayed",
                "title": "证据：同一时刻换 ID 重放过程记录",
            }
        )
        refresh_evidence_derivations(replay)
        replay_path = (
            vault / "20-learner/evidence/ev-demo-a17-003-replayed.md"
        )
        tool.atomic_write_text(
            replay_path,
            tool.render_frontmatter(replay) + "\n" + replay_body.rstrip() + "\n",
        )
        state_path = vault / "20-learner/states/ks-demo-a17-kc-python-call-stack.md"
        state_meta, state_body, state_errors = tool.parse_note(state_path)
        assert state_errors == []
        state_body = (
            state_body.rstrip()
            + f"\n- supported_by: [[{replay['id']}]]\n"
        )
        tool.atomic_write_text(
            state_path,
            tool.render_frontmatter(state_meta) + "\n" + state_body,
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            replay["id"] in error
            and ("重复" in error or "重放" in error)
            and (
                "teaching_process" in error
                or "process" in error
                or "observation event" in error
            )
            for error in errors
        ), errors

    with tempfile.TemporaryDirectory(prefix="uc-demo-process-retry-") as temporary:
        vault = seed(Path(temporary))
        retry = append_demo_call_stack_process(
            vault,
            evidence_id="ev-demo-a17-003-later-retry",
            result="pass",
            observed_offset_seconds=1,
        )
        assert retry["teaching_item_id"].startswith("td-")
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors


def test_process_event_identity_does_not_depend_on_teaching_item_id() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-process-event-id-") as temporary:
        vault = seed(Path(temporary))
        source_path = vault / "20-learner/evidence/ev-demo-a17-003.md"
        replay, replay_body, parse_errors = tool.parse_note(source_path)
        assert parse_errors == []
        replay.update(
            {
                "id": "ev-demo-a17-003-different-item-replay",
                "title": "证据：同一过程事件伪装成不同教学 item",
                "teaching_item_id": "teach-python-call-stack-forged-alternative",
            }
        )
        refresh_evidence_derivations(replay)
        replay_path = (
            vault
            / "20-learner/evidence/ev-demo-a17-003-different-item-replay.md"
        )
        tool.atomic_write_text(
            replay_path,
            tool.render_frontmatter(replay) + "\n" + replay_body.rstrip() + "\n",
        )
        state_path = vault / "20-learner/states/ks-demo-a17-kc-python-call-stack.md"
        state_meta, state_body, state_errors = tool.parse_note(state_path)
        assert state_errors == []
        state_body = (
            state_body.rstrip()
            + f"\n- supported_by: [[{replay['id']}]]\n"
        )
        tool.atomic_write_text(
            state_path,
            tool.render_frontmatter(state_meta) + "\n" + state_body,
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            replay["id"] in error
            and "重放同一 observation event" in error
            for error in errors
        ), errors


def test_teaching_process_rejects_unobserved_mastery_and_retention_values() -> None:
    mutations = {
        "verification_item_id": "verify-forged-process-item",
        "independence": "independent",
        "near_transfer": 0.8,
        "delayed_retention": 0.9,
        "retention_delay_days": 1,
    }
    for field, forged_value in mutations.items():
        with tempfile.TemporaryDirectory(
            prefix=f"uc-demo-process-sentinel-{field}-"
        ) as temporary:
            vault = seed(Path(temporary))
            path = vault / "20-learner/evidence/ev-demo-a17-003.md"
            meta, body, parse_errors = tool.parse_note(path)
            assert parse_errors == []
            meta[field] = forged_value
            refresh_evidence_derivations(meta)
            tool.atomic_write_text(
                path,
                tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n",
            )
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert any(
                "teaching_process 不得保存本阶段未测的具体表现值" in error
                and f"/{field} " in error
                for error in errors
            ), (field, errors)


def test_only_text_carriers_count_as_process_text_variants() -> None:
    text_first = failed_process_record(
        "ev-text-1",
        observed_at="2026-08-28T01:00:00+00:00",
        activity="predict_explain",
        carrier="text_hybrid",
    )
    video_second = failed_process_record(
        "ev-video-2",
        observed_at="2026-08-28T01:01:00+00:00",
        activity="contrast_cases",
        carrier="video",
    )
    interactive_third = failed_process_record(
        "ev-interactive-3",
        observed_at="2026-08-28T01:02:00+00:00",
        activity="worked_example_fading",
        carrier="interactive",
    )
    mixed = tool.derive_process_adaptation(
        [text_first, video_second, interactive_third]
    )
    assert mixed["same_error_count"] == 3
    assert mixed["text_variants_tried"] == 1

    text_fourth = failed_process_record(
        "ev-text-4",
        observed_at="2026-08-28T01:03:00+00:00",
        activity="contrast_cases",
        carrier="text_document",
    )
    two_text_variants = tool.derive_process_adaptation(
        [text_first, video_second, interactive_third, text_fourth]
    )
    assert two_text_variants["same_error_count"] == 4
    assert two_text_variants["text_variants_tried"] == 2

    nontext_only = tool.derive_process_adaptation(
        [video_second, interactive_third]
    )
    assert nontext_only["text_variants_tried"] == 0


def test_process_adaptation_requires_medium_or_high_observation_confidence() -> None:
    low_id, low = failed_process_record(
        "ev-process-confidence-low",
        observed_at="2026-08-28T01:10:00+00:00",
        activity="predict_explain",
        source_kind="self_report",
        observation_confidence="low",
    )
    derived_low, low_basis = tool.derive_observation_confidence(
        low, derived_mastery_eligible=False
    )
    assert (derived_low, low_basis) == ("low", "nonbehavior_source_cap")
    low["observation_confidence"] = derived_low
    excluded = tool.derive_process_adaptation([(low_id, low)])
    assert excluded["status"] == "no_process_evidence"
    assert excluded["source_evidence_ids"] == []
    assert excluded["latest_teaching_item_id"] is None

    medium_id, medium = failed_process_record(
        "ev-process-confidence-medium",
        observed_at="2026-08-28T01:11:00+00:00",
        activity="contrast_cases",
        source_kind="behavior_observation",
        observation_confidence="medium",
    )
    derived_medium, medium_basis = tool.derive_observation_confidence(
        medium, derived_mastery_eligible=False
    )
    assert (derived_medium, medium_basis) == (
        "medium",
        "observed_process_or_diagnostic_behavior",
    )
    medium["observation_confidence"] = derived_medium
    medium_only = tool.derive_process_adaptation(
        [(low_id, low), (medium_id, medium)]
    )
    assert medium_only["source_evidence_ids"] == [medium_id]
    assert medium_only["latest_evidence_id"] == medium_id
    assert medium_only["latest_teaching_item_id"] == medium["teaching_item_id"]

    high_id, high = failed_process_record(
        "ev-process-confidence-high",
        observed_at="2026-08-28T01:12:00+00:00",
        activity="worked_example_fading",
        observation_confidence="high",
    )
    medium_and_high = tool.derive_process_adaptation(
        [(low_id, low), (medium_id, medium), (high_id, high)]
    )
    assert medium_and_high["source_evidence_ids"] == [medium_id, high_id]
    assert medium_and_high["latest_evidence_id"] == high_id
    assert medium_and_high["latest_teaching_item_id"] == high[
        "teaching_item_id"
    ]


def test_observed_assistance_controls_repeated_error_escalation_gate() -> None:
    def decision_for(assistance_level: str) -> tuple[dict, dict]:
        records = [
            failed_process_record(
                f"ev-assistance-{assistance_level}-1",
                observed_at="2026-08-28T02:00:00+00:00",
                activity="predict_explain",
                assistance_level=assistance_level,
            ),
            failed_process_record(
                f"ev-assistance-{assistance_level}-2",
                observed_at="2026-08-28T02:01:00+00:00",
                activity="contrast_cases",
                assistance_level=assistance_level,
            ),
        ]
        adaptation = tool.derive_process_adaptation(records)
        decision = text_policy.decide_text_activity(
            text_context(
                # Keep the caller's declared ceiling identical. The observed
                # process value, not this ceiling, must decide the gate.
                max_assistance_level="A4",
                same_error_count=adaptation["same_error_count"],
                text_variants_tried=adaptation["text_variants_tried"],
                process_adaptation=adaptation,
                matching_affordance="interactive",
                matching_affordance_reason="real_time_feedback_required",
                estimated_practice_feedback_minutes=5,
            )
        )
        return adaptation, decision

    a1_adaptation, a1_decision = decision_for("A1")
    assert set(a1_adaptation["consumer_ids"]) == {
        "feedback_selection",
        "activity_selection",
        "representation_selection",
    }
    assert a1_adaptation["max_observed_assistance_level"] == "A1"
    assert a1_decision["carrier"] == "text_hybrid"
    assert a1_decision["selection_status"] == "repair_selected"
    assert a1_decision["escalation"]["status"] == "text_repair_required"

    a2_adaptation, a2_decision = decision_for("A2")
    assert "representation_selection" in a2_adaptation["consumer_ids"]
    assert a2_adaptation["max_observed_assistance_level"] == "A2"
    assert a2_decision["carrier"] == "interactive"
    assert a2_decision["selection_status"] == "escalation_required"
    assert a2_decision["escalation"] == {
        "status": "selected",
        "target_medium": "interactive",
        "affordance_reason": "real_time_feedback_required",
    }


def test_process_support_load_changes_feedback_and_next_action() -> None:
    normal = tool.derive_process_adaptation(
        [
            failed_process_record(
                "ev-support-normal",
                observed_at="2026-08-28T03:00:00+00:00",
                activity="predict_explain",
            )
        ]
    )
    assert normal["support_load_status"] == "normal"
    assert normal["feedback_rule"] == "correct_only_current_error_then_retry"
    assert normal["next_action"] == "text_repair"

    overload_cases = {
        "attempts": {"attempts": 2},
        "hint_count": {"hint_count": 1},
        "self_reported_effort": {"self_reported_effort": 5.0},
        "low_immediate_performance": {"immediate_performance": 0.49},
    }
    overloaded: dict[str, dict] = {}
    for index, (case, overrides) in enumerate(overload_cases.items(), start=1):
        record = failed_process_record(
            f"ev-support-{case}",
            observed_at=f"2026-08-28T03:0{index}:00+00:00",
            activity="predict_explain",
            **overrides,
        )
        adaptation = tool.derive_process_adaptation([record])
        overloaded[case] = adaptation
        assert adaptation["support_load_status"] == "high", (case, adaptation)
        assert adaptation["feedback_rule"] == (
            "reduce_information_then_correct_current_error"
        )
        assert adaptation["next_action"] == "shorter_text_repair"

    high = overloaded["hint_count"]
    decision = text_policy.decide_text_activity(
        text_context(
            same_error_count=high["same_error_count"],
            text_variants_tried=high["text_variants_tried"],
            process_adaptation=high,
            estimated_practice_feedback_minutes=5,
        )
    )
    delivery = text_policy.project_delivery_plan(
        decision,
        valid_delivery_content(
            feedback_rule="调用者不得覆盖高支持负荷反馈。",
            next_step="调用者不得跳过更短修复。",
        ),
    )
    assert delivery["feedback_rule"] == (
        text_policy.PROCESS_FEEDBACK_RULE_PUBLIC[
            "reduce_information_then_correct_current_error"
        ]
    )
    assert delivery["next_step"] == {
        "instruction": text_policy.PROCESS_NEXT_ACTION_PUBLIC[
            "shorter_text_repair"
        ],
        "when": None,
    }


def test_verification_task_is_revealed_only_after_accepted_process_evidence() -> None:
    decision = text_policy.decide_text_activity(text_context())
    delivery = text_policy.project_delivery_plan(decision, valid_delivery_content())
    assert "verification_rule" in delivery
    assert "verification_task" not in delivery
    assert "verify-python-call-stack-unseen-v1" not in json.dumps(
        delivery, ensure_ascii=False
    )

    try:
        text_policy._project_verification_task_from_committed_process(
            decision,
            {},
            {
                "task_id": decision["bound_verification_task_id"],
                "verification_task": DEFAULT_PROTECTED_PROMPT,
                "response_format": "给出返回顺序并说明理由。",
                "success_criteria": "A0 独立作答且顺序、理由均正确。",
            },
        )
    except text_policy.TextPolicyError as exc:
        assert "过程 evidence" in str(exc)
    else:
        raise AssertionError("教学过程 evidence 未通过前不得公开原验证题")

    scope = decision_scope(decision)
    process_record = {
        "observation_kind": "teaching_process",
        "scope": scope,
        "evidence_scope": dict(scope),
        "verification_task_id": decision["bound_verification_task_id"],
        "bound_verification_task_id": decision["bound_verification_task_id"],
        "route_id_at_observation": decision["route_id"],
        "route_version_at_observation": decision["route_version"],
        "bound_route_id": decision["route_id"],
        "bound_route_version": decision["route_version"],
        "response_correct": True,
        "verification_assistance_level": "A0",
    }
    process = text_policy.evaluate_text_unit(process_record, decision)
    assert process["qualification_status"] == "teaching_process_recorded", process
    projected = text_policy._project_verification_task_from_committed_process(
        decision,
        process,
        {
            "task_id": decision["bound_verification_task_id"],
            "verification_task": DEFAULT_PROTECTED_PROMPT,
            "response_format": "给出返回顺序并说明理由。",
            "success_criteria": "A0 独立作答且顺序、理由均正确。",
        },
    )
    assert set(projected) == {
        "verification_task",
        "response_format",
        "success_criteria",
    }
    assert decision["bound_verification_task_id"] not in json.dumps(
        projected, ensure_ascii=False
    )

    try:
        text_policy._project_verification_task_from_committed_process(
            decision,
            process,
            {
                "task_id": "verify-unbound-task",
                "verification_task": "错误绑定的验证题",
                "response_format": "作答",
                "success_criteria": "正确",
            },
        )
    except text_policy.TextPolicyError as exc:
        assert "绑定任务不一致" in str(exc)
    else:
        raise AssertionError("不得投影未绑定到 candidate_step 的验证任务")


def test_vault_is_the_only_production_verification_opening_boundary() -> None:
    assert not hasattr(text_policy, "project_verification_task"), (
        "公开 text API 不得接受调用者手写的 process_evaluation"
    )

    with tempfile.TemporaryDirectory(prefix="uc-demo-open-missing-") as temporary:
        vault = seed(Path(temporary))
        try:
            tool.project_verification_task_from_vault(
                vault, process_evidence_id="ev-process-not-committed"
            )
        except tool.VaultError as exc:
            assert "不存在或不是 evidence" in str(exc)
        else:
            raise AssertionError("未落盘的过程记录不得打开验证题")

    with tempfile.TemporaryDirectory(prefix="uc-demo-open-old-") as temporary:
        vault = seed(Path(temporary))
        try:
            tool.project_verification_task_from_vault(
                vault, process_evidence_id="ev-demo-a17-003"
            )
        except tool.VaultError as exc:
            assert "decision epoch" in str(exc) and "签发上下文" in str(exc), exc
        else:
            raise AssertionError("未绑定当前 decision epoch 的旧过程 evidence 不得开题")

    with tempfile.TemporaryDirectory(prefix="uc-demo-open-unbound-") as temporary:
        vault = seed(Path(temporary))
        meta = append_demo_call_stack_process(
            vault,
            evidence_id="ev-demo-a17-005-unbound",
            result="pass",
        )
        path = vault / "20-learner/evidence/ev-demo-a17-005-unbound.md"
        meta, body, parse_errors = tool.parse_note(path)
        assert parse_errors == []
        meta["route_binding_id"] = "rb-not-issued"
        refresh_evidence_derivations(meta)
        tool.atomic_write_text(
            path, tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n"
        )
        try:
            tool.project_verification_task_from_vault(
                vault, process_evidence_id=meta["id"]
            )
        except tool.VaultError as exc:
            assert "route_binding_id" in str(exc)
        else:
            raise AssertionError("未绑定当前 route issuance 的过程 evidence 必须拒绝")

    with tempfile.TemporaryDirectory(prefix="uc-demo-open-epoch-") as temporary:
        vault = seed(Path(temporary))
        meta = append_demo_call_stack_process(
            vault,
            evidence_id="ev-demo-a17-005-wrong-epoch",
            result="pass",
        )
        path = vault / "20-learner/evidence/ev-demo-a17-005-wrong-epoch.md"
        meta, body, parse_errors = tool.parse_note(path)
        assert parse_errors == []
        meta["decision_fingerprint_at_observation"] = "0" * 64
        refresh_evidence_derivations(meta)
        tool.atomic_write_text(
            path, tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n"
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            meta["id"] in error
            and "decision epoch" in error
            for error in errors
        ), errors
        try:
            tool.project_verification_task_from_vault(
                vault, process_evidence_id=meta["id"]
            )
        except tool.VaultError as exc:
            assert "decision epoch" in str(exc)
        else:
            raise AssertionError("调用者伪造 decision fingerprint 不得开题")

    for result in ("partial", "fail"):
        with tempfile.TemporaryDirectory(
            prefix=f"uc-demo-open-{result}-"
        ) as temporary:
            vault = seed(Path(temporary))
            meta = append_demo_call_stack_process(
                vault,
                evidence_id=f"ev-demo-a17-005-{result}",
                result=result,
            )
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert errors == [], errors
            try:
                tool.project_verification_task_from_vault(
                    vault, process_evidence_id=meta["id"]
                )
            except tool.VaultError as exc:
                assert "ready_for_verification" in str(exc), exc
            else:
                raise AssertionError(f"{result} 教学过程不得打开未见验证题")

    with tempfile.TemporaryDirectory(prefix="uc-demo-open-committed-") as temporary:
        vault = seed(Path(temporary))
        meta = append_demo_call_stack_process(
            vault,
            evidence_id="ev-demo-a17-005-process-pass",
            result="pass",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors
        projected = tool.project_verification_task_from_vault(
            vault, process_evidence_id=meta["id"]
        )
        delivery, _delivery_body, delivery_errors = tool.parse_note(
            vault
            / "30-learning/deliveries"
            / f"{meta['teaching_item_id']}.md"
        )
        assert delivery_errors == []
        resource, _resource_body, resource_errors = tool.parse_note(
            vault
            / "30-learning/resources"
            / f"{delivery['resource_id']}.md"
        )
        assert resource_errors == []
        assert projected["verification_task"] == resource["verification_task"][
            "prompt"
        ]
        assert set(projected) == {
            "verification_task",
            "response_format",
            "success_criteria",
        }


def test_teaching_delivery_issuance_binds_process_exactly() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-issued-delivery-") as temporary:
        vault = seed(Path(temporary))
        issued: dict = {}
        process = append_demo_call_stack_process(
            vault,
            evidence_id="ev-demo-issued-process-pass",
            result="pass",
            issuance_out=issued,
        )
        process_path = (
            vault / "20-learner/evidence/ev-demo-issued-process-pass.md"
        )
        process, process_body, process_errors = tool.parse_note(process_path)
        assert process_errors == []
        delivery_path = (
            vault
            / "30-learning/deliveries"
            / f"{process['teaching_item_id']}.md"
        )
        delivery, delivery_body, delivery_errors = tool.parse_note(delivery_path)
        assert delivery_errors == []
        intervention, _intervention_body, intervention_errors = tool.parse_note(
            vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
        )
        assert intervention_errors == []
        manifest = json.loads((vault / tool.MANIFEST_REL).read_text(encoding="utf-8"))
        registry, _events, registry_errors = tool.load_route_binding_registry(
            vault, manifest
        )
        assert registry_errors == []
        route_issuance = next(
            item
            for item in registry.values()
            if item["binding_id"] == delivery["route_binding_id"]
        )

        assert delivery["type"] == "teaching_delivery"
        assert delivery["source_kind"] == "agent_projection"
        assert delivery["delivery_plan_fingerprint"] == tool.sha256_fingerprint(
            delivery["delivery_plan"]
        )
        assert process["teaching_item_id"] == delivery["id"]
        assert process["teaching_delivery_fingerprint_at_observation"] == (
            delivery["delivery_plan_fingerprint"]
        )
        assert process["decision_fingerprint_at_observation"] == delivery[
            "decision_fingerprint"
        ]
        assert delivery["decision_fingerprint"] == intervention[
            "resolved_decision_fingerprint"
        ]
        assert set(issued["delivery_plan"]) == set(text_policy.USER_DELIVERY_FIELDS)
        assert "process_binding" not in issued["delivery_plan"]
        binding = issued["process_binding"]
        assert set(binding) == {
            "teaching_item_id",
            "teaching_delivery_fingerprint_at_observation",
            "verification_task_id",
            "bound_verification_task_id",
            "decision_fingerprint_at_observation",
            "route_id_at_observation",
            "route_version_at_observation",
            "route_binding_id",
            "context_key",
            "activity",
            "carrier",
        }
        assert binding == {
            "teaching_item_id": delivery["id"],
            "teaching_delivery_fingerprint_at_observation": delivery[
                "delivery_plan_fingerprint"
            ],
            "verification_task_id": route_issuance["verification_task_id"],
            "bound_verification_task_id": route_issuance[
                "verification_task_id"
            ],
            "decision_fingerprint_at_observation": delivery[
                "decision_fingerprint"
            ],
            "route_id_at_observation": route_issuance["route_id"],
            "route_version_at_observation": route_issuance["route_version"],
            "route_binding_id": route_issuance["binding_id"],
            "context_key": route_issuance["context_key"],
            "activity": delivery["activity"],
            "carrier": delivery["carrier"],
        }
        for field, value in binding.items():
            assert process[field] == value, field
        assert binding["verification_task_id"] == intervention[
            "current_verification_task_id"
        ]
        assert binding["activity"] == intervention["resolved_activity"]
        assert binding["carrier"] == intervention["resolved_carrier"]
        assert tool.parse_iso_instant(delivery["issued_at"]) < (
            tool.parse_iso_instant(process["observed_at"])
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors
        opened = tool.project_verification_task_from_vault(
            vault, process_evidence_id=process["id"]
        )
        assert set(opened) == {
            "verification_task",
            "response_format",
            "success_criteria",
        }

        original_process = json.loads(json.dumps(process))
        forged_process_cases = (
            (
                "teaching_item_id",
                "td-never-issued",
                "teaching_process 引用了未发行的教学项",
            ),
            (
                "teaching_delivery_fingerprint_at_observation",
                "0" * 64,
                "未精确绑定先发行的教学项/内容/decision epoch",
            ),
            (
                "decision_fingerprint_at_observation",
                "f" * 64,
                "decision epoch",
            ),
            (
                "observed_at",
                (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "evidence observed_at 不得位于未来",
            ),
        )
        for field, forged_value, expected_error in forged_process_cases:
            forged = json.loads(json.dumps(original_process))
            forged[field] = forged_value
            refresh_evidence_derivations(forged)
            tool.atomic_write_text(
                process_path,
                tool.render_frontmatter(forged) + "\n" + process_body.rstrip() + "\n",
            )
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert any(expected_error in error for error in errors), (
                field,
                errors,
            )
            try:
                tool.project_verification_task_from_vault(
                    vault, process_evidence_id=process["id"]
                )
            except tool.VaultError as exc:
                assert expected_error in str(exc), (field, exc)
            else:
                raise AssertionError(f"伪造过程绑定必须拒绝: {field}")
            tool.atomic_write_text(
                process_path,
                tool.render_frontmatter(original_process)
                + "\n"
                + process_body.rstrip()
                + "\n",
            )

        forged_delivery = json.loads(json.dumps(delivery))
        forged_delivery["issued_at"] = (
            datetime.now(timezone.utc) + timedelta(days=1)
        ).isoformat()
        tool.atomic_write_text(
            delivery_path,
            tool.render_frontmatter(forged_delivery)
            + "\n"
            + delivery_body.rstrip()
            + "\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "teaching_delivery issued_at 不得位于未来" in error
            for error in errors
        ), errors
        try:
            tool.project_verification_task_from_vault(
                vault, process_evidence_id=process["id"]
            )
        except tool.VaultError as exc:
            assert "teaching_delivery issued_at 不得位于未来" in str(exc)
        else:
            raise AssertionError("未来签发的教学项不得验证或开题")

    invalid_append_cases = (
        (
            "unissued-item",
            {"teaching_item_id": "td-never-issued"},
            None,
            "未精确绑定 teaching_delivery",
        ),
        (
            "wrong-plan-fingerprint",
            {"teaching_delivery_fingerprint_at_observation": "0" * 64},
            None,
            "未精确绑定 teaching_delivery",
        ),
        (
            "wrong-decision-epoch",
            {"decision_fingerprint_at_observation": "f" * 64},
            None,
            "未绑定当前 resolved decision fingerprint",
        ),
        (
            "future-evidence",
            {
                "observed_at": (
                    datetime.now(timezone.utc) + timedelta(days=1)
                ).isoformat()
            },
            None,
            "observed_at 不得晚于 append-evidence 的真实 wall clock",
        ),
        (
            "future-delivery",
            None,
            {
                "issued_at": (
                    datetime.now(timezone.utc) + timedelta(days=1)
                ).isoformat()
            },
            "teaching_delivery issued_at 不得位于未来",
        ),
    )
    for case, raw_overrides, delivery_overrides, expected_error in (
        invalid_append_cases
    ):
        with tempfile.TemporaryDirectory(
            prefix=f"uc-demo-append-process-{case}-"
        ) as temporary:
            vault = seed(Path(temporary))
            evidence_id = f"ev-demo-append-process-{case}"
            try:
                append_demo_call_stack_process(
                    vault,
                    evidence_id=evidence_id,
                    result="pass",
                    raw_overrides=raw_overrides,
                    delivery_overrides=delivery_overrides,
                )
            except tool.VaultError as exc:
                assert expected_error in str(exc), (case, exc)
            else:
                raise AssertionError(
                    f"append-evidence 不得接受无效教学绑定: {case}"
                )
            assert not (
                vault / "20-learner/evidence" / f"{evidence_id}.md"
            ).exists()


def test_failed_process_cannot_open_after_explicit_repair_decision_epoch() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-repair-epoch-") as temporary:
        vault = seed(Path(temporary))
        process = append_demo_call_stack_process(
            vault,
            evidence_id="ev-demo-process-fail-before-repair-epoch",
            result="fail",
        )
        intervention_path = (
            vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
        )
        refreshed, _body, refreshed_errors = tool.parse_note(intervention_path)
        assert refreshed_errors == []
        assert refreshed["resolved_process_status"] == "escalation_candidate"
        assert refreshed["resolved_process_next_action"] == (
            "evaluate_escalation_gate"
        )
        assert refreshed["resolved_decision_fingerprint"] == process[
            "decision_fingerprint_at_observation"
        ]

        repaired = tool.resolve_active_teaching(vault, write=True)
        assert repaired["resolved_activity"] != process["activity"]
        assert repaired["resolved_decision_fingerprint"] != process[
            "decision_fingerprint_at_observation"
        ]
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors
        try:
            tool.project_verification_task_from_vault(
                vault, process_evidence_id=process["id"]
            )
        except tool.VaultError as exc:
            assert "decision epoch" in str(exc), exc
        else:
            raise AssertionError("新修复 decision epoch 生效后不得用旧过程 evidence 开题")


def test_open_verification_requires_explanation_to_be_observed() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-open-explanation-") as temporary:
        vault = seed(Path(temporary))
        meta = append_demo_call_stack_process(
            vault,
            evidence_id="ev-demo-a17-005-explanation-not-tested",
            result="pass",
        )
        path = (
            vault
            / "20-learner/evidence/ev-demo-a17-005-explanation-not-tested.md"
        )
        meta, body, parse_errors = tool.parse_note(path)
        assert parse_errors == []
        meta["explanation_quality"] = "not_tested"
        refresh_evidence_derivations(meta)
        tool.atomic_write_text(
            path, tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n"
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            meta["id"] in error
            and "explanation" in error
            and "冲突" in error
            for error in errors
        ), errors
        try:
            tool.project_verification_task_from_vault(
                vault, process_evidence_id=meta["id"]
            )
        except tool.VaultError as exc:
            assert "explanation" in str(exc) and "冲突" in str(exc)
        else:
            raise AssertionError("解释未观察时，即使答案正确也不得打开验证题")


def test_historical_as_of_cannot_be_written_as_current_resolution() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-historical-write-") as temporary:
        vault = seed(Path(temporary))
        intervention, _body, parse_errors = tool.parse_note(
            vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
        )
        assert parse_errors == []
        historical_as_of = (
            tool.parse_iso_instant(intervention["resolved_at"])
            - timedelta(seconds=1)
        ).isoformat()
        try:
            tool.resolve_active_teaching(
                vault,
                write=True,
                _as_of=historical_as_of,
            )
        except tool.VaultError as exc:
            assert "历史" in str(exc) or "_as_of" in str(exc)
        else:
            raise AssertionError("历史 as-of 只允许只读重算，不得覆盖当前 resolution")


def test_resolved_at_cannot_be_rolled_back_without_epoch_recompute() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-resolution-epoch-") as temporary:
        vault = seed(Path(temporary))
        path = vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
        meta, body, parse_errors = tool.parse_note(path)
        assert parse_errors == []
        original_fingerprint = meta["resolved_decision_fingerprint"]
        meta["resolved_at"] = (
            tool.parse_iso_instant(meta["resolved_at"]) - timedelta(seconds=1)
        ).isoformat()
        tool.atomic_write_text(
            path, tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n"
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "resolved_decision_fingerprint" in error
            and original_fingerprint in error
            for error in errors
        ), errors


def test_verification_item_must_equal_the_issued_task() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-verification-item-") as temporary:
        vault = seed(Path(temporary))
        source_path = vault / "20-learner/evidence/ev-demo-a17-001.md"
        meta, body, parse_errors = tool.parse_note(source_path)
        assert parse_errors == []
        assert meta["verification_item_id"] == meta["verification_task_id"]
        meta.update(
            {
                "id": "ev-demo-a17-001-copied-item",
                "title": "证据：复制验证记录后替换 item",
                "verification_item_id": "verify-caller-substituted-item",
            }
        )
        refresh_evidence_derivations(meta)
        copied_path = (
            vault / "20-learner/evidence/ev-demo-a17-001-copied-item.md"
        )
        tool.atomic_write_text(
            copied_path,
            tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n",
        )
        state_path = vault / "20-learner/states/ks-demo-a17-kc-python-function.md"
        state_meta, state_body, state_errors = tool.parse_note(state_path)
        assert state_errors == []
        state_body = (
            state_body.rstrip()
            + f"\n- supported_by: [[{meta['id']}]]\n"
        )
        tool.atomic_write_text(
            state_path,
            tool.render_frontmatter(state_meta) + "\n" + state_body,
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "verification/retention item 必须等于已签发 task" in error
            and meta["id"] in error
            for error in errors
        ), errors


def test_verification_content_guard_blocks_prompt_examples_and_answers() -> None:
    decision = text_policy.decide_text_activity(text_context())
    safe = text_policy.project_delivery_plan(decision, valid_delivery_content())
    assert safe["example"] == "案例 A / 案例 B"

    leaking_contents = (
        valid_delivery_content(explanation=DEFAULT_PROTECTED_PROMPT),
        valid_delivery_content(
            example=f"先看这个教学例子：{DEFAULT_PROTECTED_PROMPT} 然后再比较。"
        ),
        valid_delivery_content(example="提示片段：inner 先返回，outer 后返回。"),
        valid_delivery_content(explanation=DEFAULT_PROTECTED_ANSWERS[0]),
    )
    for content in leaking_contents:
        try:
            text_policy.project_delivery_plan(decision, content)
        except text_policy.TextPolicyError as exc:
            assert "保留的未见验证" in str(exc)
        else:
            raise AssertionError("初始教学内容不得泄露题面、嵌入题面或答案内容")

    split_cases = (
        (
            text_policy.decide_text_activity(
                text_context(
                    verification_content_guard=text_policy.build_verification_content_guard(
                        "verify-python-call-stack-unseen-v1",
                        DEFAULT_PROTECTED_PROMPT,
                        ["跨字段甲乙丙丁保护"],
                    )
                )
            ),
            valid_delivery_content(explanation="跨字段甲乙", example="丙丁保护"),
            "explanation/example",
        ),
        (
            text_policy.decide_text_activity(
                text_context(
                    introduced_terms=["数组一", "丙丁保护"],
                    verification_content_guard=text_policy.build_verification_content_guard(
                        "verify-python-call-stack-unseen-v1",
                        DEFAULT_PROTECTED_PROMPT,
                        ["数组拆分甲乙丙丁保护"],
                    ),
                )
            ),
            valid_delivery_content(
                term_grounding=[
                    {
                        "term": "数组一",
                        "what_it_is": "第一项",
                        "owner_scope": "当前案例",
                        "role_here": "只用于回归测试",
                        "relation_direction": "数组拆分甲乙",
                    },
                    {
                        "term": "丙丁保护",
                        "what_it_is": "第二项",
                        "owner_scope": "当前案例",
                        "role_here": "只用于回归测试",
                        "relation_direction": "与第一项相邻",
                    },
                ]
            ),
            "array elements",
        ),
        (
            text_policy.decide_text_activity(
                text_context(
                    introduced_terms=["术语项"],
                    verification_content_guard=text_policy.build_verification_content_guard(
                        "verify-python-call-stack-unseen-v1",
                        DEFAULT_PROTECTED_PROMPT,
                        ["术语甲乙丙丁保护"],
                    ),
                )
            ),
            valid_delivery_content(
                term_grounding=[
                    {
                        "term": "术语项",
                        "what_it_is": "术语甲乙",
                        "owner_scope": "丙丁保护",
                        "role_here": "只用于回归测试",
                        "relation_direction": "与当前概念相连",
                    }
                ]
            ),
            "adjacent term_grounding values",
        ),
    )
    for split_decision, split_content, label in split_cases:
        try:
            text_policy.project_delivery_plan(split_decision, split_content)
        except text_policy.TextPolicyError as exc:
            assert "组合阅读流" in str(exc), (label, exc)
        else:
            raise AssertionError(f"跨 {label} 拆分的保护答案仍必须被阻断")

    mismatched_guard = verification_guard("verify-other-task")
    try:
        text_policy.decide_text_activity(
            text_context(verification_content_guard=mismatched_guard)
        )
    except text_policy.TextPolicyError as exc:
        assert "task_id" in str(exc)
    else:
        raise AssertionError("verification content guard 必须绑定当前 task_id")


def test_new_term_requires_complete_grounding() -> None:
    decision = text_policy.decide_text_activity(
        text_context(introduced_terms=["参数"])
    )
    try:
        text_policy.project_delivery_plan(decision, valid_delivery_content())
    except text_policy.TextPolicyError as exc:
        assert "term_grounding" in str(exc)
    else:
        raise AssertionError("未解释的新术语不得进入教学输出")

    incomplete = valid_delivery_content(
        term_grounding=[
            {
                "term": "参数",
                "what_it_is": "一项带名称和数值范围的控制项",
                "owner_scope": "属于 Live2D 模型",
                "role_here": "改变嘴巴可见图形的形状",
            }
        ]
    )
    try:
        text_policy.project_delivery_plan(decision, incomplete)
    except text_policy.TextPolicyError as exc:
        assert "relation_direction" in str(exc)
    else:
        raise AssertionError("缺少关系方向的术语解释不得通过")

    grounded = valid_delivery_content(
        term_grounding=[
            {
                "term": "参数",
                "what_it_is": "一项带名称和数值范围的控制项",
                "owner_scope": "属于 Live2D 模型",
                "role_here": "在本例中改变嘴巴可见图形的形状",
                "relation_direction": "参数值变化，嘴巴图形随之变化",
            }
        ]
    )
    delivery = text_policy.project_delivery_plan(decision, grounded)
    assert delivery["term_grounding"][0]["owner_scope"] == "属于 Live2D 模型"


def test_complex_relation_requires_concrete_static_visual() -> None:
    decision = text_policy.decide_text_activity(
        text_context(static_visual_reason="multi_object_mapping")
    )
    assert decision["carrier"] == "text_hybrid"
    assert decision["visual_support"] == {
        "status": "selected",
        "kind": "annotated_diagram",
        "reason": "multi_object_mapping",
    }
    try:
        text_policy.project_delivery_plan(decision, valid_delivery_content())
    except text_policy.TextPolicyError as exc:
        assert "没有提供具体 visual" in str(exc)
    else:
        raise AssertionError("复杂关系已选择图示时不得输出纯线性文字")

    placeholder = valid_delivery_content(
        visual={
            "kind": "annotated_diagram",
            "asset": "见下图",
            "observation_focus": "观察连接",
            "text_equivalent": "一个控制项连接三个图形。",
            "learner_reading_task": "说出连接关系",
            "labels_grounded": True,
            "relation_direction_marked": True,
        }
    )
    try:
        text_policy.project_delivery_plan(decision, placeholder)
    except text_policy.TextPolicyError as exc:
        assert "占位说明" in str(exc)
    else:
        raise AssertionError("未落地标签的图示不得通过")

    concrete = valid_delivery_content(
        visual={
            "kind": "annotated_diagram",
            "asset": "parameter-to-mouth-parts.svg",
            "observation_focus": "观察一个控制项如何连接上唇、下唇和牙齿三块图形。",
            "text_equivalent": "模型中的同一个控制项分别连接上唇、下唇和牙齿，控制方向从控制项指向三块图形。",
            "learner_reading_task": "沿箭头说出控制方向，并指出共同变化的三块图形。",
            "labels_grounded": True,
            "relation_direction_marked": True,
        }
    )
    delivery = text_policy.project_delivery_plan(decision, concrete)
    assert delivery["medium"] == "文字文件＋静态图示＋对话"
    assert delivery["visual"]["asset"] == "parameter-to-mouth-parts.svg"


def test_delivery_plan_rejects_missing_core_teaching_content() -> None:
    decision = text_policy.decide_text_activity(text_context())
    try:
        text_policy.project_delivery_plan(decision, {})
    except text_policy.TextPolicyError as exc:
        assert "learning_objective" in str(exc)
    else:
        raise AssertionError("空教学计划不得通过")


def test_delivery_plan_rejects_nested_internal_fields() -> None:
    decision = text_policy.decide_text_activity(text_context())
    content = {
        "learning_objective": "区分递归与循环",
        "explanation": {"safe_text": "比较终止条件", "debug_info": {"focus_z": 0.8}},
    }
    try:
        text_policy.project_delivery_plan(decision, content)
    except text_policy.TextPolicyError as exc:
        assert "内部字段" in str(exc)
    else:
        raise AssertionError("嵌套内部字段不得进入用户投影")


def test_delivery_plan_rejects_internal_routing_bindings() -> None:
    decision = text_policy.decide_text_activity(text_context())
    for internal_key in ("next_step_id", "activity_id", "probe_id", "verification_task_id"):
        content = {
            "learning_objective": "区分递归与循环",
            "explanation": {internal_key: "internal-only"},
        }
        try:
            text_policy.project_delivery_plan(decision, content)
        except text_policy.TextPolicyError as exc:
            assert "内部字段" in str(exc)
        else:
            raise AssertionError(f"{internal_key} 不得进入用户投影")


def test_nontext_affordance_requires_auditable_reason() -> None:
    try:
        text_policy.decide_text_activity(
            text_context(
                same_error_count=2,
                text_variants_tried=2,
                max_assistance_level="A2",
                matching_affordance="video",
            )
        )
    except text_policy.TextPolicyError as exc:
        assert "matching_affordance_reason" in str(exc)
    else:
        raise AssertionError("非文字可供性必须绑定可审计原因")


def test_text_unit_requires_unseen_independent_verification() -> None:
    decision = text_policy.decide_text_activity(text_context())
    scope = decision_scope(decision)
    valid = {
        "observation_kind": "verification",
        "learner_response_present": True,
        "teaching_item_id": "teach-1",
        "verification_item_id": "verify-2",
        "verification_unseen": True,
        "verification_task_id": decision["bound_verification_task_id"],
        "bound_verification_task_id": decision["bound_verification_task_id"],
        "route_id_at_observation": decision["route_id"],
        "route_version_at_observation": decision["route_version"],
        "bound_route_id": decision["route_id"],
        "bound_route_version": decision["route_version"],
        "answer_revealed_before_first_attempt": False,
        "verification_assistance_level": "A0",
        "response_correct": True,
        "required_capabilities": ["independent_application", "near_transfer"],
        "demonstrated_capabilities": ["independent_application", "near_transfer"],
        "explanation_required": True,
        "explanation_quality": "pass",
        "near_transfer_required": True,
        "near_transfer": 0.8,
        "near_transfer_threshold": 0.75,
        "scope": scope,
        "evidence_scope": dict(scope),
    }
    result = text_policy.evaluate_text_unit(valid, decision)
    assert result["unit_status"] == "passed", result
    assert result["mastery_update_allowed"] is False

    invalid = dict(valid)
    invalid["verification_item_id"] = "teach-1"
    invalid["verification_assistance_level"] = "A1"
    result = text_policy.evaluate_text_unit(invalid, decision)
    assert result["unit_status"] == "not_passed"
    assert "verification_item_reused" in result["failures"]
    assert "verification_not_independent" in result["failures"]


def _candidate_step(
    candidate_id: str,
    *,
    route_order: int,
    cost_vector: dict[str, float],
    focus_z: float | None,
    ranking_status: str = "complete",
    user_cost_priority: list[str] | None = None,
    goal_id: str = "goal-demo-a17-recursion",
    route_id: str = "route-demo-a17-recursion",
    route_version: int = 3,
) -> dict:
    candidate = {
        "candidate_step_id": candidate_id,
        "concept_id": f"concept-{candidate_id}",
        "learner_id": "demo-a17",
        "goal_id": goal_id,
        "contract_id": f"mc-{candidate_id}",
        "contract_version": 1,
        "route_id": route_id,
        "route_version": route_version,
        "time_scope": "session-2026-08-28",
        "in_target_subgraph": True,
        "mastery_compatible": True,
        "prerequisites_satisfied": True,
        "hard_constraints_satisfied": True,
        "route_level": 0,
        "route_order": route_order,
        "routing_action": "teach_now",
        "mastery_gate": "mc-demo-route@1",
        "activity_id": f"activity-{candidate_id}",
        "verification_task_id": f"verify-{candidate_id}",
        "cost_vector": cost_vector,
        "ranking_status": ranking_status,
        "focus_z": focus_z,
        "user_cost_priority": user_cost_priority,
    }
    if focus_z is not None and ranking_status == "complete":
        candidate.update(
            {
                "goal_relevance": focus_z,
                "interest_evidence": focus_z,
                "readiness": focus_z,
                "focus_weights": {"goal": 0.4, "interest": 0.35, "readiness": 0.25},
                "input_source_refs": [f"evidence-{candidate_id}"],
                "calculated_at": "2026-08-28T04:00:00+00:00",
                "validity": "valid",
            }
        )
    return candidate


def test_v3_selector_orders_pareto_priority_then_focus() -> None:
    candidates = [
        _candidate_step(
            "a", route_order=0, cost_vector={"time": 10, "hints": 2}, focus_z=0.50
        ),
        _candidate_step(
            "b", route_order=1, cost_vector={"time": 12, "hints": 1}, focus_z=0.80
        ),
        _candidate_step(
            "c", route_order=2, cost_vector={"time": 15, "hints": 3}, focus_z=0.99
        ),
    ]
    result = tool.select_candidate_step_v3(candidates)
    assert result["selected_id"] == "b", result
    assert result["selection_basis"] == "focus", result
    by_id = {item["candidate_step_id"]: item for item in result["candidates"]}
    assert by_id["c"]["pareto_status"] == "dominated"
    assert by_id["c"]["selection_status"] == "not_selected"

    # Focus cannot revive an ineligible candidate even when its score is highest.
    candidates[1]["prerequisites_satisfied"] = False
    result = tool.select_candidate_step_v3(candidates)
    assert result["selected_id"] == "a", result
    by_id = {item["candidate_step_id"]: item for item in result["candidates"]}
    assert by_id["b"]["eligibility_status"] == "ineligible"

    # An explicit ordered cost preference applies only inside the Pareto frontier.
    priority_candidates = [dict(item, user_cost_priority=["time"]) for item in candidates]
    priority_candidates[1]["prerequisites_satisfied"] = True
    result = tool.select_candidate_step_v3(priority_candidates)
    assert result["selected_id"] == "a", result
    assert result["selection_basis"] == "user_cost_priority", result


def test_v3_selector_refuses_scope_mix_and_unresolved_cost_shortcut() -> None:
    mixed = [
        _candidate_step("a", route_order=0, cost_vector={"time": 10}, focus_z=0.4),
        _candidate_step(
            "b",
            route_order=1,
            cost_vector={"time": 9},
            focus_z=0.9,
            goal_id="goal-other",
        ),
    ]
    result = tool.select_candidate_step_v3(mixed)
    assert result["selected_id"] is None, result
    assert result["scope_status"] == "missing_or_mixed"

    unresolved = [
        _candidate_step(
            "a",
            route_order=0,
            cost_vector={"time": 10},
            focus_z=0.4,
            user_cost_priority=["time"],
        ),
        _candidate_step(
            "b",
            route_order=1,
            cost_vector={"time": 9, "hints": 2},
            focus_z=0.9,
            user_cost_priority=["time"],
        ),
    ]
    result = tool.select_candidate_step_v3(unresolved)
    assert result["selected_id"] == "a", result
    assert result["selection_basis"] == "cost_unresolved", result
    assert result["user_cost_priority_status"] == "blocked_by_unresolved_pareto"
    assert result["needs_measurement"] is True

    single = _candidate_step(
        "only",
        route_order=0,
        cost_vector={"time": 10},
        focus_z=None,
        ranking_status="not_needed",
    )
    result = tool.select_candidate_step_v3([single])
    assert result["selected_id"] == "only", result
    assert result["selection_basis"] == "active_route"
    assert result["candidates"][0]["pareto_status"] == "not_needed"


def test_v3_selector_enforces_route_scope_and_traced_focus() -> None:
    same_route = [
        _candidate_step(
            "a", route_order=0, cost_vector={"time": 10, "hints": 1}, focus_z=0.35
        ),
        _candidate_step(
            "b", route_order=1, cost_vector={"time": 10, "hints": 1}, focus_z=0.85
        ),
    ]
    assert same_route[0]["contract_id"] != same_route[1]["contract_id"]
    result = tool.select_candidate_step_v3(same_route)
    assert result["selected_id"] == "b", result
    assert result["selection_basis"] == "focus", result

    cross_route = [dict(item) for item in same_route]
    cross_route[1]["route_id"] = "route-other"
    result = tool.select_candidate_step_v3(cross_route)
    assert result["selected_id"] is None, result
    assert result["scope_status"] == "missing_or_mixed", result

    cross_version = [dict(item) for item in same_route]
    cross_version[1]["route_version"] = 4
    result = tool.select_candidate_step_v3(cross_version)
    assert result["selected_id"] is None, result
    assert result["scope_status"] == "missing_or_mixed", result

    naked_focus = [dict(item) for item in same_route]
    for field in (
        "goal_relevance",
        "interest_evidence",
        "readiness",
        "focus_weights",
        "input_source_refs",
        "calculated_at",
        "validity",
    ):
        naked_focus[1].pop(field, None)
    naked_focus[1]["focus_z"] = 0.99
    result = tool.select_candidate_step_v3(naked_focus)
    assert result["selected_id"] == "a", result
    assert result["selection_basis"] == "route_default", result
    by_id = {item["candidate_step_id"]: item for item in result["candidates"]}
    assert by_id["b"]["focus_input_status"] == "incomplete_or_invalid"


def test_v3_selector_never_compares_different_action_gate_level_or_time_scope() -> None:
    base = _candidate_step(
        "a", route_order=0, cost_vector={"time": 100, "hints": 3}, focus_z=0.20
    )
    tempting = _candidate_step(
        "b", route_order=1, cost_vector={"time": 1, "hints": 0}, focus_z=0.99
    )

    different_action = [dict(base), dict(tempting)]
    different_action[1]["routing_action"] = "diagnose_now"
    different_action[1]["probe_id"] = "probe-b"
    result = tool.select_candidate_step_v3(different_action)
    assert result["selected_id"] == "a", result
    assert result["selection_basis"] == "route_default", result
    by_id = {item["candidate_step_id"]: item for item in result["candidates"]}
    assert by_id["b"]["decision_pool_status"] == "standby_action_gate"
    assert by_id["b"]["pareto_status"] == "not_needed"

    different_gate = [dict(base), dict(tempting)]
    different_gate[1]["mastery_gate"] = "mc-other-gate@1"
    result = tool.select_candidate_step_v3(different_gate)
    assert result["selected_id"] == "a", result
    by_id = {item["candidate_step_id"]: item for item in result["candidates"]}
    assert by_id["b"]["decision_pool_status"] == "standby_action_gate"
    assert by_id["b"]["pareto_status"] == "not_needed"

    different_level = [dict(base), dict(tempting)]
    different_level[1]["route_level"] = 1
    result = tool.select_candidate_step_v3(different_level)
    assert result["selected_id"] == "a", result
    by_id = {item["candidate_step_id"]: item for item in result["candidates"]}
    assert by_id["b"]["decision_pool_status"] == "standby"
    assert by_id["b"]["pareto_status"] == "not_needed"

    different_time = [dict(base), dict(tempting)]
    different_time[1]["time_scope"] = "session-other"
    result = tool.select_candidate_step_v3(different_time)
    assert result["selected_id"] is None, result
    assert result["scope_status"] == "missing_or_mixed"
    assert all(
        item["pareto_status"] == "not_needed" for item in result["candidates"]
    )


def test_v3_selector_invalid_or_inconsistent_priority_never_reaches_focus() -> None:
    base = [
        _candidate_step(
            "a",
            route_order=0,
            cost_vector={"time": 10, "hints": 2},
            focus_z=0.20,
        ),
        _candidate_step(
            "b",
            route_order=1,
            cost_vector={"time": 12, "hints": 1},
            focus_z=0.99,
        ),
    ]

    invalid = [dict(item, user_cost_priority=["unknown_dimension"]) for item in base]
    result = tool.select_candidate_step_v3(invalid)
    assert result["selected_id"] == "a", result
    assert result["selection_basis"] == "cost_unresolved", result
    assert result["user_cost_priority_status"] == "invalid_dimension"
    assert result["needs_measurement"] is True

    inconsistent = [
        dict(base[0], user_cost_priority=["time"]),
        dict(base[1], user_cost_priority=["hints"]),
    ]
    result = tool.select_candidate_step_v3(inconsistent)
    assert result["selected_id"] == "a", result
    assert result["selection_basis"] == "cost_unresolved", result
    assert result["user_cost_priority_status"] == "inconsistent"
    assert result["needs_measurement"] is True


def test_observation_update_requires_consumer_scope_source_time_and_validity() -> None:
    scope = {
        "learner_id": "demo-a17",
        "goal_id": "goal-demo-a17-recursion",
        "concept_id": "kc-python-call-stack",
        "contract_id": "mc-python-call-stack",
        "contract_version": 1,
    }
    other_scope = dict(scope, goal_id="goal-other")
    update = text_policy.prepare_observation_update(
        {
            "phase": "teaching_process",
            "scope": scope,
            "source_refs": ["turn-001"],
            "observed_at": "2026-08-28T04:00:00+08:00",
            "validity": "valid",
            "confidence": 0.8,
            "fields": {
                "elapsed_seconds": {
                    "value": 42,
                    "consumers": ["activity_selection"],
                },
                "attempts": {
                    "value": 1,
                    "consumers": ["feedback_selection"],
                    "scope": other_scope,
                },
                "near_transfer": {
                    "value": 0.8,
                    "consumers": ["activity_selection"],
                },
                "unused_future_value": {
                    "value": 7,
                    "consumers": ["activity_selection"],
                },
            },
        }
    )
    assert update["commit_status"] == "ready", update
    assert set(update["prepared_fields"]) == {"elapsed_seconds"}
    assert update["consumer_index"] == {"activity_selection": ["elapsed_seconds"]}
    dropped = {item["field"]: item["reason"] for item in update["dropped_fields"]}
    assert dropped["attempts"] == "scope_mismatch"
    assert dropped["near_transfer"] == "field_not_used_in_phase"
    assert dropped["unused_future_value"] == "field_not_allowlisted"

    provisional = text_policy.prepare_observation_update(
        {
            "phase": "verification",
            "scope": scope,
            "source_refs": ["turn-002"],
            "observed_at": "2026-08-28T04:05:00+08:00",
            "validity": "provisional",
            "fields": {
                "verification_unseen": {
                    "value": True,
                    "consumers": ["verification_gate"],
                }
            },
        }
    )
    assert provisional["commit_status"] == "nothing_to_commit"
    assert provisional["commit_allowed"] is False
    assert provisional["dropped_fields"][0]["reason"] == (
        "validity_insufficient_for_mastery_consumer"
    )


def test_prepare_observation_update_drops_fields_without_real_consumers() -> None:
    scope = {
        "learner_id": "demo-a17",
        "goal_id": "goal-demo-a17-recursion",
        "concept_id": "kc-python-call-stack",
        "contract_id": "mc-python-call-stack",
        "contract_version": 1,
    }

    def prepare(field: str, value) -> dict:
        return text_policy.prepare_observation_update(
            {
                "phase": "diagnostic",
                "scope": scope,
                "source_refs": ["turn-learner-confidence"],
                "observed_at": "2026-08-28T04:10:00+00:00",
                "validity": "valid",
                "fields": {
                    field: {
                        "value": value,
                        "consumers": ["experiment_evaluation"],
                    }
                },
            }
        )

    unsupported = {
        "representation": "paired_text_cases",
        "learner_confidence": "high",
        "interest_event": {"kind": "revisit", "about": "python"},
    }
    for field, value in unsupported.items():
        result = prepare(field, value)
        assert result["commit_status"] == "nothing_to_commit", (field, result)
        assert result["prepared_fields"] == {}
        assert result["consumer_index"] == {}
        assert result["dropped_fields"] == [
            {"field": field, "reason": "field_not_allowlisted"}
        ]


def test_phase_kind_and_mixed_phase_prepared_updates_are_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-phase-kind-") as temporary:
        vault = seed(Path(temporary))
        path = vault / "20-learner/evidence/ev-demo-a17-003.md"
        meta, body, parse_errors = tool.parse_note(path)
        assert parse_errors == []
        meta["evidence_kind"] = "independent_performance"
        refresh_evidence_derivations(meta)
        tool.atomic_write_text(
            path,
            tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "evidence_kind 与 phase 不一致" in error and meta["id"] in error
            for error in errors
        ), errors
        try:
            text_policy._validate_vault_evidence_envelope("fixture", meta)
        except text_policy.TextPolicyError as exc:
            assert "evidence_kind" in str(exc)
        else:
            raise AssertionError("Text adapter 不得接受 phase/kind 错配")

    scope = {
        "learner_id": "demo-a17",
        "goal_id": "goal-demo-a17-recursion",
        "concept_id": "kc-python-call-stack",
        "contract_id": "mc-python-call-stack",
        "contract_version": 1,
    }
    prepared = text_policy.prepare_observation_update(
        {
            "phase": "teaching_process",
            "scope": scope,
            "source_refs": ["turn-mixed-phase"],
            "observed_at": "2026-08-28T04:20:00+00:00",
            "validity": "valid",
            "fields": {
                "elapsed_seconds": {
                    "value": 30,
                    "consumers": ["activity_selection"],
                },
                "delayed_retention": {
                    "value": 0.8,
                    "consumers": ["retention_recompute"],
                },
            },
        }
    )
    assert set(prepared["prepared_fields"]) == {"elapsed_seconds"}
    assert prepared["dropped_fields"] == [
        {"field": "delayed_retention", "reason": "field_not_used_in_phase"}
    ]

    forged = json.loads(json.dumps(prepared))
    forged["prepared_fields"]["delayed_retention"] = {
        "value": 0.8,
        "consumers": ["retention_recompute"],
        "scope": scope,
        "source_refs": ["turn-mixed-phase"],
        "observed_at": "2026-08-28T04:20:00+00:00",
        "validity": "valid",
        "confidence": "not_estimated",
    }
    try:
        text_policy._prepared_values_for_scope(
            forged, scope, "teaching_process"
        )
    except text_policy.TextPolicyError as exc:
        assert "字段不属于该 phase" in str(exc)
    else:
        raise AssertionError("调用者不得把 retention 字段伪造进 process update")

    wrong_phase = json.loads(json.dumps(prepared))
    wrong_phase["phase"] = "retention"
    try:
        text_policy._prepared_values_for_scope(
            wrong_phase, scope, "teaching_process"
        )
    except text_policy.TextPolicyError as exc:
        assert "phase 与 evidence.phase 不一致" in str(exc)
    else:
        raise AssertionError("prepared update 不得跨 phase 复用")


def test_issue_learning_route_extends_trusted_seed_with_route_v2() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-issue-learning-") as temporary:
        root = Path(temporary)
        vault = seed(root)
        ledger_path = vault / tool.ROUTE_BINDINGS_REL
        manifest_path = vault / tool.MANIFEST_REL
        before_ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        before_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert before_manifest["route_trust_level"] == "trusted_seed_source"
        resource = add_call_stack_resource(vault, suffix="learning-v2")
        record_path = write_learning_route_record(root, resource["id"])

        issued = tool.issue_route(vault, record_path=record_path)
        assert issued["status"] == "issued"
        assert issued["commit_status"] == "atomic_validated"
        assert issued["purpose"] == "learning"
        assert issued["route_version"] == 2
        assert issued["concept_id"] == "kc-python-call-stack"
        assert issued["resource_id"] == resource["id"]
        assert issued["active_resolution_status"] == "resolved"
        assert issued["routing_action"] == "diagnose_now"
        assert issued["next_action"] == "present_issued_diagnostic_probe"
        assert issued["next_action"] != "resolve_teaching"
        assert issued["route_trust_segment"] == "local_chain_only"

        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_sequence = before_ledger["head_sequence"] + 1
        event = ledger["events"][-1]
        assert event["sequence"] == expected_sequence
        assert event["route_version"] == 2
        assert event["binding_id"] == issued["binding_id"]
        assert event["event_hash"] == issued["event_hash"]
        assert event["previous_hash"] == before_ledger["head_hash"]
        assert event["route_purpose"] == "learning"
        assert event["source_ref_ids"] == [
            "ses-demo-a17-20260826t063000z"
        ]
        assert ledger["head_sequence"] == expected_sequence
        assert ledger["head_hash"] == event["event_hash"]
        assert ledger["local_extension_from_sequence"] == expected_sequence
        assert manifest["route_binding_chain_length"] == expected_sequence
        assert manifest["route_binding_chain_head"] == event["event_hash"]
        assert manifest["route_local_extension_from_sequence"] == (
            expected_sequence
        )
        assert manifest["route_trust_level"] == (
            "trusted_seed_prefix_local_extension"
        )

        intervention, _body, parse_errors = tool.parse_note(
            vault / "30-learning/interventions/int-demo-a17-recursion-path.md"
        )
        assert parse_errors == []
        assert intervention["route_version"] == 2
        assert intervention["resolved_route_binding_id"] == issued["binding_id"]
        assert intervention["resolved_context_key"] == issued["context_key"]
        errors, _warnings, summary = tool.validate_vault(vault)
        assert errors == [], errors
        assert summary["node_count"] == 38


def test_issue_learning_route_next_action_matches_resolved_teach_branch() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-route-next-action-") as temporary:
        root = Path(temporary)
        vault = seed(root)
        diagnostic, _issuance, _probe = call_stack_diagnostic_fixture(
            vault, evidence_id="ev-route-next-action-diagnostic"
        )
        diagnostic.update(
            {
                "result": "pass",
                "response_correct": True,
                "explanation_quality": "pass",
                "immediate_performance": 0.9,
                "error_signature": None,
                "self_reported_effort": 2,
            }
        )
        refresh_evidence_derivations(diagnostic)
        committed = tool.append_evidence(
            vault,
            record_path=write_raw_evidence_record(
                vault,
                diagnostic,
                evidence_id=diagnostic["id"],
                summary="已签发诊断显示可进入正式文字教学。",
            ),
        )
        assert committed["state_mastery"] == "partial", committed
        resource = add_call_stack_resource(
            vault, suffix="route-next-action-teach", duration_minutes=0.5
        )
        issued = tool.issue_route(
            vault,
            record_path=write_learning_route_record(root, resource["id"]),
        )
        assert issued["active_resolution_status"] == "resolved"
        assert issued["routing_action"] == "teach_now"
        assert issued["next_action"] == "issue_teaching"
        assert issued["next_action"] != "resolve_teaching"
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors


def test_issue_route_requires_explicit_user_cost_priority_field() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-route-priority-schema-") as temporary:
        root = Path(temporary)
        vault = seed(root)
        resource = add_call_stack_resource(
            vault, suffix="priority-schema", duration_minutes=1
        )
        record_path = write_learning_route_record(root, resource["id"])
        record = json.loads(record_path.read_text(encoding="utf-8"))
        assert record["user_cost_priority"] is None
        record.pop("user_cost_priority")
        tool.atomic_write_text(
            record_path, json.dumps(record, ensure_ascii=False)
        )
        before = snapshot_tree_bytes(vault)
        try:
            tool.issue_route(vault, record_path=record_path)
        except tool.VaultError as exc:
            assert "字段合同不一致" in str(exc), exc
            assert "user_cost_priority" in str(exc), exc
        else:
            raise AssertionError("issue-route 缺少必填 priority 字段必须 fail closed")
        assert snapshot_tree_bytes(vault) == before


def test_issue_route_user_cost_priority_selects_real_resource_frontier() -> None:
    cases = (
        (None, "diagnosis", "route_default", "not_provided"),
        (["diagnosis"], "diagnosis", "user_cost_priority", "applied"),
        (["core_learning"], "core", "user_cost_priority", "applied"),
    )
    for priority, expected_suffix, expected_basis, expected_status in cases:
        with tempfile.TemporaryDirectory(
            prefix="uc-demo-route-production-priority-"
        ) as temporary:
            root = Path(temporary)
            vault = seed(root)
            resource_a, resource_b = add_priority_frontier_resources(
                vault, suffix="production-priority"
            )
            expected_resource = {
                "diagnosis": resource_a,
                "core": resource_b,
            }[expected_suffix]
            issued = tool.issue_route(
                vault,
                record_path=write_learning_route_record(
                    root,
                    expected_resource["id"],
                    user_cost_priority=priority,
                ),
            )
            assert issued["resource_id"] == expected_resource["id"], issued
            assert issued["selection_basis"] == expected_basis, issued
            assert issued["user_cost_priority"] == priority, issued
            assert issued["user_cost_priority_status"] == expected_status, issued
            assert issued["user_cost_priority_provided"] is (priority is not None)

            ledger = json.loads(
                (vault / tool.ROUTE_BINDINGS_REL).read_text(encoding="utf-8")
            )
            decision = ledger["events"][-1]["selection_decision"]
            assert decision["selection_basis"] == expected_basis
            assert decision["user_cost_priority"] == priority
            assert decision["user_cost_priority_status"] == expected_status
            candidate_costs = {
                item["resource_id"]: item
                for item in decision["candidate_costs"]
            }
            for resource in (resource_a, resource_b):
                stored = candidate_costs[resource["id"]]
                assert stored["cost_vector"] == resource["cost_vector"]
                assert stored["cost_vector_source"] == "resource.cost_vector"
                assert stored["selected"] is (
                    resource["id"] == expected_resource["id"]
                )
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert errors == [], errors


def test_issue_route_rejects_invalid_duplicate_and_retention_priority_zero_write() -> None:
    for label, priority in (
        ("invalid", ["not-a-cost-dimension"]),
        ("duplicate", ["diagnosis", "diagnosis"]),
    ):
        with tempfile.TemporaryDirectory(
            prefix=f"uc-demo-route-{label}-priority-"
        ) as temporary:
            root = Path(temporary)
            vault = seed(root)
            resource_a, _resource_b = add_priority_frontier_resources(
                vault, suffix=f"{label}-priority"
            )
            before = snapshot_tree_bytes(vault)
            try:
                tool.issue_route(
                    vault,
                    record_path=write_learning_route_record(
                        root,
                        resource_a["id"],
                        user_cost_priority=priority,
                    ),
                )
            except tool.VaultError as exc:
                assert "user_cost_priority" in str(exc), exc
            else:
                raise AssertionError(f"{label} priority 必须 fail closed")
            assert snapshot_tree_bytes(vault) == before

    with tempfile.TemporaryDirectory(
        prefix="uc-demo-retention-contradictory-priority-"
    ) as temporary:
        root = Path(temporary)
        prepared = prepare_immediate_met_call_stack(
            root, suffix="retention-contradictory-priority"
        )
        vault = prepared["vault"]
        resource = add_call_stack_resource(
            vault,
            suffix="retention-contradictory-priority-task",
            duration_minutes=2,
        )
        record_path = write_retention_route_record(
            root,
            resource_id=resource["id"],
            baseline_evidence_id=prepared["baseline"]["id"],
        )
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["user_cost_priority"] = ["diagnosis"]
        tool.atomic_write_text(
            record_path, json.dumps(record, ensure_ascii=False)
        )
        before = snapshot_tree_bytes(vault)
        try:
            tool.issue_route(vault, record_path=record_path)
        except tool.VaultError as exc:
            assert "retention issue-route 不消费 user_cost_priority" in str(exc), exc
        else:
            raise AssertionError("retention priority 与合同矛盾时必须 fail closed")
        assert snapshot_tree_bytes(vault) == before


def test_issue_route_priority_never_promotes_fallback_cost_estimates() -> None:
    with tempfile.TemporaryDirectory(
        prefix="uc-demo-route-priority-unresolved-cost-"
    ) as temporary:
        root = Path(temporary)
        vault = seed(root)
        resource_a = add_call_stack_resource(
            vault, suffix="unresolved-cost-a", duration_minutes=1
        )
        add_call_stack_resource(
            vault, suffix="unresolved-cost-b", duration_minutes=2
        )
        before = snapshot_tree_bytes(vault)
        try:
            tool.issue_route(
                vault,
                record_path=write_learning_route_record(
                    root,
                    resource_a["id"],
                    user_cost_priority=["diagnosis"],
                ),
            )
        except tool.VaultError as exc:
            assert "blocked_by_unresolved_pareto" in str(exc), exc
        else:
            raise AssertionError(
                "多候选只有 fallback estimate 时 priority 不得伪造 Pareto 结果"
            )
        assert snapshot_tree_bytes(vault) == before

    with tempfile.TemporaryDirectory(
        prefix="uc-demo-route-null-priority-fallback-"
    ) as temporary:
        root = Path(temporary)
        vault = seed(root)
        resource_a = add_call_stack_resource(
            vault, suffix="fallback-route-default-a", duration_minutes=1
        )
        resource_b = add_call_stack_resource(
            vault, suffix="fallback-route-default-b", duration_minutes=2
        )
        issued = tool.issue_route(
            vault,
            record_path=write_learning_route_record(root, resource_a["id"]),
        )
        assert issued["selection_basis"] == "route_default", issued
        assert issued["user_cost_priority_status"] == "not_provided", issued
        ledger = json.loads(
            (vault / tool.ROUTE_BINDINGS_REL).read_text(encoding="utf-8")
        )
        candidate_costs = {
            item["resource_id"]: item
            for item in ledger["events"][-1]["selection_decision"][
                "candidate_costs"
            ]
        }
        for resource in (resource_a, resource_b):
            stored = candidate_costs[resource["id"]]
            assert stored["cost_vector"] is None
            assert isinstance(stored["fallback_cost_estimate"], dict)
            assert stored["cost_vector_source"].endswith("fallback_estimate")
        assert candidate_costs[resource_a["id"]]["selected"] is True
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors


def test_issue_route_focus_snapshot_scope_time_and_batch_are_exact() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-focus-exact-") as temporary:
        root = Path(temporary)
        vault = seed(root)
        resource_a, _resource_b = add_priority_frontier_resources(
            vault, suffix="focus-exact"
        )
        focus_path, focus = write_residual_focus_snapshot(
            vault,
            suffix="focus-exact",
            decision_id="decision-focus-exact",
        )
        original_focus = focus_path.read_bytes()
        _meta, focus_body, focus_errors = tool.parse_note(focus_path)
        assert focus_errors == []
        record_path = write_learning_route_record(root, resource_a["id"])
        future = (
            datetime.now(timezone.utc) + timedelta(days=1)
        ).isoformat(timespec="microseconds").replace("+00:00", "Z")
        cases = (
            (
                "missing-route-id",
                lambda item: item.pop("route_id"),
                "focus snapshot 缺少 route_id",
            ),
            (
                "wrong-route-id",
                lambda item: item.__setitem__("route_id", "route-never-issued"),
                "focus snapshot route_id/version 无历史发行依据",
            ),
            (
                "wrong-time-scope",
                lambda item: item.__setitem__(
                    "time_scope", "route-chain-head:" + "0" * 64
                ),
                "focus snapshot time_scope 不在 route chain 历史中",
            ),
            (
                "future-calculated-at",
                lambda item: item.__setitem__("calculated_at", future),
                "focus snapshot calculated_at 不得位于未来",
            ),
        )
        for label, mutate, expected_error in cases:
            tampered = json.loads(json.dumps(focus))
            mutate(tampered)
            tool.atomic_write_text(
                focus_path,
                tool.render_frontmatter(tampered)
                + "\n"
                + focus_body.rstrip()
                + "\n",
            )
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert any(expected_error in item for item in errors), (
                label,
                errors,
            )
            before_rejected_issue = snapshot_tree_bytes(vault)
            try:
                tool.issue_route(vault, record_path=record_path)
            except tool.VaultError as exc:
                assert "Vault 校验失败" in str(exc), (label, exc)
            else:
                raise AssertionError(f"{label} Focus 不得被 issue-route 消费")
            assert snapshot_tree_bytes(vault) == before_rejected_issue
            tool.atomic_write_bytes(focus_path, original_focus)
            restored_errors, _warnings, _summary = tool.validate_vault(vault)
            assert restored_errors == [], restored_errors

        issued = tool.issue_route(vault, record_path=record_path)
        assert issued["selection_basis"] == "stable_tie_break", issued
        assert issued["focus_decision_id"] == focus["decision_id"]
        assert issued["focus_time_scope"] == focus["time_scope"]
        ledger = json.loads(
            (vault / tool.ROUTE_BINDINGS_REL).read_text(encoding="utf-8")
        )
        decision = ledger["events"][-1]["selection_decision"]
        assert decision["focus_decision_id"] == focus["decision_id"]
        assert decision["focus_time_scope"] == focus["time_scope"]
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors

    with tempfile.TemporaryDirectory(prefix="uc-demo-focus-mixed-batch-") as temporary:
        root = Path(temporary)
        vault = seed(root)
        resource_a, _resource_b = add_priority_frontier_resources(
            vault, suffix="focus-mixed-batch"
        )
        _first_path, first = write_residual_focus_snapshot(
            vault,
            suffix="focus-mixed-batch-a",
            decision_id="decision-focus-batch-a",
        )
        second_at = (
            tool.parse_iso_instant(first["calculated_at"])
            - timedelta(microseconds=1)
        ).isoformat(timespec="microseconds").replace("+00:00", "Z")
        write_residual_focus_snapshot(
            vault,
            suffix="focus-mixed-batch-b",
            decision_id="decision-focus-batch-b",
            calculated_at=second_at,
            validate=False,
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "同一 current residual Focus batch 不得混用多个 decision_id"
            in item
            for item in errors
        ), errors
        before = snapshot_tree_bytes(vault)
        try:
            tool.issue_route(
                vault,
                record_path=write_learning_route_record(root, resource_a["id"]),
            )
        except tool.VaultError as exc:
            assert "Vault 校验失败" in str(exc), exc
        else:
            raise AssertionError("mixed Focus decision batch 必须 fail closed")
        assert snapshot_tree_bytes(vault) == before


def test_issue_route_consumes_current_stable_tie_break_focus_batch() -> None:
    with tempfile.TemporaryDirectory(
        prefix="uc-demo-focus-stable-tie-batch-"
    ) as temporary:
        root = Path(temporary)
        vault = seed(root)
        resource_a, resource_b = add_priority_frontier_resources(
            vault, suffix="focus-stable-tie-batch"
        )
        _focus_path, focus = write_residual_focus_snapshot(
            vault,
            suffix="focus-stable-tie-batch",
            decision_id="decision-focus-stable-tie-batch",
            selection_basis="stable_tie_break",
        )

        issued = tool.issue_route(
            vault,
            record_path=write_learning_route_record(root, resource_a["id"]),
        )
        assert issued["resource_id"] == resource_a["id"], issued
        assert issued["selection_basis"] == "stable_tie_break", issued
        assert issued["focus_decision_id"] == focus["decision_id"]
        assert issued["focus_time_scope"] == focus["time_scope"]

        ledger = json.loads(
            (vault / tool.ROUTE_BINDINGS_REL).read_text(encoding="utf-8")
        )
        decision = ledger["events"][-1]["selection_decision"]
        assert decision["selection_basis"] == "stable_tie_break"
        assert decision["focus_decision_id"]
        assert decision["focus_time_scope"]
        assert decision["focus_decision_id"] == focus["decision_id"]
        assert decision["focus_time_scope"] == focus["time_scope"]
        candidate_ids = {
            item["resource_id"] for item in decision["candidate_costs"]
        }
        assert {resource_a["id"], resource_b["id"]}.issubset(candidate_ids)
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors


def test_issue_route_recomputes_predeclared_route_default_focus_batch() -> None:
    with tempfile.TemporaryDirectory(
        prefix="uc-demo-focus-route-default-recompute-"
    ) as temporary:
        root = Path(temporary)
        vault = seed(root)
        resource_a, _resource_b = add_priority_frontier_resources(
            vault, suffix="focus-route-default-recompute"
        )
        _focus_path, focus = write_residual_focus_snapshot(
            vault,
            suffix="focus-route-default-recompute",
            decision_id="decision-focus-route-default-recompute",
            selection_basis="route_default",
        )

        issued = tool.issue_route(
            vault,
            record_path=write_learning_route_record(root, resource_a["id"]),
        )
        assert issued["selection_basis"] == "stable_tie_break", issued
        assert issued["selection_basis"] != focus["selection_basis"]
        assert issued["focus_decision_id"] == focus["decision_id"]
        assert issued["focus_time_scope"] == focus["time_scope"]

        decision = json.loads(
            (vault / tool.ROUTE_BINDINGS_REL).read_text(encoding="utf-8")
        )["events"][-1]["selection_decision"]
        assert decision["selection_basis"] == "stable_tie_break"
        assert decision["focus_decision_id"]
        assert decision["focus_time_scope"]
        assert decision["focus_decision_id"] == focus["decision_id"]
        assert decision["focus_time_scope"] == focus["time_scope"]
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors


def test_issue_route_rejects_mixed_focus_selection_basis_zero_write() -> None:
    with tempfile.TemporaryDirectory(
        prefix="uc-demo-focus-mixed-selection-basis-"
    ) as temporary:
        root = Path(temporary)
        vault = seed(root)
        resource_a, _resource_b = add_priority_frontier_resources(
            vault, suffix="focus-mixed-selection-basis"
        )
        _first_path, first = write_residual_focus_snapshot(
            vault,
            suffix="focus-mixed-selection-basis-a",
            decision_id="decision-focus-mixed-selection-basis",
            selection_basis="stable_tie_break",
        )
        second_at = (
            tool.parse_iso_instant(first["calculated_at"])
            - timedelta(microseconds=1)
        ).isoformat(timespec="microseconds").replace("+00:00", "Z")
        second_path, _second = write_residual_focus_snapshot(
            vault,
            suffix="focus-mixed-selection-basis-b",
            decision_id=first["decision_id"],
            selection_basis="route_default",
            calculated_at=second_at,
            validate=False,
        )

        mixed_errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "同一 current residual Focus" in item
            and "selection_basis 必须唯一一致" in item
            and first["decision_id"] in item
            for item in mixed_errors
        ), mixed_errors

        before = snapshot_tree_bytes(vault)
        try:
            tool.issue_route(
                vault,
                record_path=write_learning_route_record(root, resource_a["id"]),
            )
        except tool.VaultError as exc:
            assert (
                "selection_basis 必须一致" in str(exc)
                or "Vault 校验失败" in str(exc)
            ), exc
        else:
            raise AssertionError(
                "同一 current decision batch 混合 selection_basis 必须 fail closed"
            )
        assert snapshot_tree_bytes(vault) == before

        second_meta, second_body, second_errors = tool.parse_note(second_path)
        assert second_errors == []
        second_meta["selection_basis"] = "stable_tie_break"
        tool.atomic_write_text(
            second_path,
            tool.render_frontmatter(second_meta)
            + "\n"
            + second_body.rstrip()
            + "\n",
        )
        repaired_errors, _warnings, _summary = tool.validate_vault(vault)
        assert repaired_errors == [], repaired_errors


def test_retention_chain_head_invalidates_old_focus_until_current_batch() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-focus-chain-head-") as temporary:
        root = Path(temporary)
        prepared = prepare_immediate_met_call_stack(
            root, suffix="focus-chain-head"
        )
        vault = prepared["vault"]
        old_focus_path, old_focus = write_residual_focus_snapshot(
            vault,
            suffix="focus-before-retention",
            decision_id="decision-focus-before-retention",
        )
        assert old_focus_path.is_file()
        resource_a, resource_b = add_priority_frontier_resources(
            vault, suffix="focus-chain-head"
        )
        issued_retention = issue_retention_route_for_prepared(
            root, prepared, suffix="focus-chain-head"
        )["retention_route"]
        assert issued_retention["purpose"] == "retention"
        assert old_focus["time_scope"] != (
            "route-chain-head:" + issued_retention["event_hash"]
        )

        issued_without_current_focus = tool.issue_route(
            vault,
            record_path=write_learning_route_record(root, resource_a["id"]),
        )
        assert issued_without_current_focus["selection_basis"] == "route_default"
        assert issued_without_current_focus["focus_decision_id"] is None
        assert issued_without_current_focus["focus_time_scope"] is None
        stale_decision = json.loads(
            (vault / tool.ROUTE_BINDINGS_REL).read_text(encoding="utf-8")
        )["events"][-1]["selection_decision"]
        assert stale_decision["focus_decision_id"] is None
        assert stale_decision["focus_time_scope"] is None

        resource_c = add_call_stack_resource(
            vault,
            suffix="focus-chain-head-current-peer",
            duration_minutes=0.7,
            cost_vector=resource_b["cost_vector"],
        )
        _new_focus_path, new_focus = write_residual_focus_snapshot(
            vault,
            suffix="focus-after-retention-and-learning",
            decision_id="decision-focus-current-head",
        )
        issued_with_current_focus = tool.issue_route(
            vault,
            record_path=write_learning_route_record(root, resource_b["id"]),
        )
        assert issued_with_current_focus["resource_id"] == resource_b["id"]
        assert issued_with_current_focus["selection_basis"] == "stable_tie_break", (
            issued_with_current_focus
        )
        assert issued_with_current_focus["focus_decision_id"] == new_focus[
            "decision_id"
        ]
        assert issued_with_current_focus["focus_time_scope"] == new_focus[
            "time_scope"
        ]
        current_decision = json.loads(
            (vault / tool.ROUTE_BINDINGS_REL).read_text(encoding="utf-8")
        )["events"][-1]["selection_decision"]
        assert current_decision["focus_decision_id"] == new_focus["decision_id"]
        assert current_decision["focus_time_scope"] == new_focus["time_scope"]
        candidate_ids = {
            item["resource_id"] for item in current_decision["candidate_costs"]
        }
        assert {resource_b["id"], resource_c["id"]}.issubset(candidate_ids)
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors

    with tempfile.TemporaryDirectory(
        prefix="uc-demo-route-single-fallback-priority-"
    ) as temporary:
        root = Path(temporary)
        vault = seed(root)
        resource = add_call_stack_resource(
            vault, suffix="single-fallback-priority", duration_minutes=1
        )
        issued = tool.issue_route(
            vault,
            record_path=write_learning_route_record(
                root,
                resource["id"],
                user_cost_priority=["diagnosis"],
            ),
        )
        assert issued["resource_id"] == resource["id"]
        assert issued["selection_basis"] == "active_route"
        assert issued["user_cost_priority"] == ["diagnosis"]
        assert issued["user_cost_priority_status"] == "not_needed"
        ledger = json.loads(
            (vault / tool.ROUTE_BINDINGS_REL).read_text(encoding="utf-8")
        )
        stored = ledger["events"][-1]["selection_decision"]["candidate_costs"]
        selected = next(item for item in stored if item["selected"])
        assert selected["resource_id"] == resource["id"]
        assert selected["cost_vector"] is None
        assert isinstance(selected["fallback_cost_estimate"], dict)
        assert selected["cost_vector_source"].endswith("fallback_estimate")
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors


def test_issue_learning_route_rolls_back_byte_exact_after_resolution_write() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-issue-learning-fault-") as temporary:
        root = Path(temporary)
        vault = seed(root)
        resource = add_call_stack_resource(vault, suffix="learning-fault")
        record_path = write_learning_route_record(root, resource["id"])
        before = snapshot_tree_bytes(vault)
        original_resolve = tool.resolve_active_teaching
        fault = {"raised_after_write": False}

        def resolve_then_fail(*args, **kwargs):
            result = original_resolve(*args, **kwargs)
            fault["raised_after_write"] = True
            raise RuntimeError("injected-after-resolve-write")

        tool.resolve_active_teaching = resolve_then_fail
        try:
            try:
                tool.issue_route(vault, record_path=record_path)
            except RuntimeError as exc:
                assert str(exc) == "injected-after-resolve-write"
            else:
                raise AssertionError("issue-route 写后故障必须触发事务回滚")
        finally:
            tool.resolve_active_teaching = original_resolve

        assert fault["raised_after_write"] is True
        assert snapshot_tree_bytes(vault) == before
        errors, _warnings, summary = tool.validate_vault(vault)
        assert errors == [], errors
        assert summary["node_count"] == 38


def test_cross_process_issue_route_cas_allows_exactly_one_commit() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-route-process-race-") as temporary:
        root = Path(temporary)
        vault = seed(root)
        resource = add_call_stack_resource(vault, suffix="process-race")
        record_path = write_learning_route_record(root, resource["id"])
        ledger_path = vault / tool.ROUTE_BINDINGS_REL
        before_ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        pause_marker = root / "issue-a-paused.txt"
        release_marker = root / "issue-a-release.txt"
        process_a, result_a_path, _started_a = launch_vault_writer_subprocess(
            root,
            label="issue-a",
            operation="issue_route",
            vault=vault,
            record_path=record_path,
            hook="pause_before_issue_first_write",
            marker_path=pause_marker,
            release_path=release_marker,
        )
        try:
            wait_for_path(pause_marker)
            process_b, result_b_path, started_b = launch_vault_writer_subprocess(
                root,
                label="issue-b",
                operation="issue_route",
                vault=vault,
                record_path=record_path,
            )
            wait_for_path(started_b)
            time.sleep(0.15)
            assert process_b.poll() is None
            assert not result_b_path.exists(), (
                "第二个独立进程必须等待同一 Vault 的事务锁"
            )
            tool.atomic_write_text(release_marker, "release")
            result_a = finish_vault_writer_subprocess(process_a, result_a_path)
            result_b = finish_vault_writer_subprocess(process_b, result_b_path)
        finally:
            if not release_marker.exists():
                tool.atomic_write_text(release_marker, "release")
            if process_a.poll() is None:
                process_a.kill()
                process_a.communicate()

        assert result_a["status"] == "ok", result_a
        assert result_b["status"] == "error", result_b
        assert "CAS 冲突" in result_b["error"], result_b
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert len(ledger["events"]) == len(before_ledger["events"]) + 1
        assert ledger["head_sequence"] == before_ledger["head_sequence"] + 1
        assert ledger["head_hash"] == result_a["value"]["event_hash"]
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors


def test_cross_process_lock_timeout_is_zero_write() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-route-lock-timeout-") as temporary:
        root = Path(temporary)
        vault = seed(root)
        resource = add_call_stack_resource(vault, suffix="lock-timeout")
        record_path = write_learning_route_record(root, resource["id"])
        before = snapshot_tree_bytes(vault)
        pause_marker = root / "holder-paused.txt"
        release_marker = root / "holder-release.txt"
        holder, holder_result_path, _holder_started = (
            launch_vault_writer_subprocess(
                root,
                label="lock-holder",
                operation="issue_route",
                vault=vault,
                record_path=record_path,
                hook="pause_before_issue_first_write",
                marker_path=pause_marker,
                release_path=release_marker,
            )
        )
        try:
            wait_for_path(pause_marker)
            contender, contender_result_path, contender_started = (
                launch_vault_writer_subprocess(
                    root,
                    label="lock-timeout-contender",
                    operation="issue_route",
                    vault=vault,
                    record_path=record_path,
                    lock_timeout_seconds=0,
                )
            )
            wait_for_path(contender_started)
            contender_result = finish_vault_writer_subprocess(
                contender, contender_result_path
            )
            assert contender_result["status"] == "error", contender_result
            assert "事务锁超时" in contender_result["error"], contender_result
            assert "未写入任何数据" in contender_result["error"], contender_result
            assert snapshot_tree_bytes(vault) == before
            tool.atomic_write_text(release_marker, "release")
            holder_result = finish_vault_writer_subprocess(
                holder, holder_result_path
            )
        finally:
            if not release_marker.exists():
                tool.atomic_write_text(release_marker, "release")
            if holder.poll() is None:
                holder.kill()
                holder.communicate()

        assert holder_result["status"] == "ok", holder_result
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors


def test_cross_process_failed_schedule_rollback_preserves_waiting_success() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-schedule-process-race-") as temporary:
        root = Path(temporary)
        prepared = prepare_immediate_met_call_stack(
            root, suffix="schedule-process-race"
        )
        prepared.update(
            issue_retention_route_for_prepared(
                root, prepared, suffix="schedule-process-race"
            )
        )
        vault = prepared["vault"]
        record_path = write_schedule_record(
            root,
            state=prepared["state"],
            baseline_evidence_id=prepared["baseline"]["id"],
            route_binding_id=prepared["retention_route"]["binding_id"],
            not_before=(
                datetime.now(timezone.utc) + timedelta(days=8)
            ).isoformat(),
        )
        pause_marker = root / "schedule-a-paused.txt"
        release_marker = root / "schedule-a-release.txt"
        process_a, result_a_path, _started_a = launch_vault_writer_subprocess(
            root,
            label="schedule-a",
            operation="schedule_retention",
            vault=vault,
            record_path=record_path,
            hook="fail_after_schedule_write",
            marker_path=pause_marker,
            release_path=release_marker,
        )
        try:
            wait_for_path(pause_marker)
            process_b, result_b_path, started_b = launch_vault_writer_subprocess(
                root,
                label="schedule-b",
                operation="schedule_retention",
                vault=vault,
                record_path=record_path,
            )
            wait_for_path(started_b)
            time.sleep(0.15)
            assert process_b.poll() is None
            assert not result_b_path.exists(), (
                "成功事务必须等待失败事务完成 byte-exact rollback"
            )
            tool.atomic_write_text(release_marker, "release")
            result_a = finish_vault_writer_subprocess(process_a, result_a_path)
            result_b = finish_vault_writer_subprocess(process_b, result_b_path)
        finally:
            if not release_marker.exists():
                tool.atomic_write_text(release_marker, "release")
            if process_a.poll() is None:
                process_a.kill()
                process_a.communicate()

        assert result_a == {
            "status": "error",
            "error_type": "RuntimeError",
            "error": "injected-after-schedule-write",
        }, result_a
        assert result_b["status"] == "ok", result_b
        schedule_id = result_b["value"]["retention_schedule_id"]
        schedule_path = (
            vault / "30-learning/retention-schedules" / f"{schedule_id}.md"
        )
        assert schedule_path.is_file()
        state, _body, state_errors = tool.parse_note(prepared["state_path"])
        assert state_errors == []
        assert state["current_retention_schedule_id"] == schedule_id
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors


def test_retention_schedule_open_and_append_receipt_happy_chain() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-retention-happy-") as temporary:
        root = Path(temporary)
        prepared = prepare_retention_schedule(
            root,
            suffix="retention-happy",
            not_before=(
                datetime.now(timezone.utc) + timedelta(days=8)
            ).isoformat(),
        )
        vault = prepared["vault"]
        schedule = prepared["schedule"]
        assert schedule["retention_status"] == "pending"
        assert schedule["next_action"] == "wait_until_scheduled_for"
        pending_snapshot = snapshot_tree_bytes(vault)
        try:
            tool.open_delayed_verification(
                vault, state_id=prepared["state"]["id"]
            )
        except tool.VaultError as exc:
            assert "retention 尚未 due" in str(exc), exc
        else:
            raise AssertionError("pending retention 不得提前开题")
        assert snapshot_tree_bytes(vault) == pending_snapshot

        due_at = tool.parse_iso_instant(schedule["scheduled_for"]) + timedelta(
            seconds=1
        )
        with frozen_tool_clock(due_at) as clock:
            before_open = snapshot_tree_bytes(vault)
            opened = tool.open_delayed_verification(
                vault, state_id=prepared["state"]["id"]
            )
            assert opened["status"] == "opened"
            assert opened["commit_status"] == "atomic_validated"
            assert opened["phase"] == "retention"
            assert set(opened["user_task"]) == {
                "verification_task",
                "response_format",
                "success_criteria",
            }
            assert "A0" in opened["user_task"]["response_format"]
            serialized_user_task = json.dumps(
                opened["user_task"], ensure_ascii=False
            )
            for answer in prepared["retention_resource"]["verification_task"][
                "protected_answers"
            ]:
                assert answer not in serialized_user_task
            binding = opened["retention_binding"]
            assert binding["teaching_item_id"] == binding[
                "verification_open_id"
            ]
            assert binding["retention_schedule_id"] == schedule[
                "retention_schedule_id"
            ]
            assert binding["baseline_evidence_id"] == prepared["baseline"]["id"]
            assert binding["route_binding_id"] == prepared["retention_route"][
                "binding_id"
            ]
            receipt_path = (
                vault
                / "30-learning/verification-opens"
                / f"{binding['verification_open_id']}.md"
            )
            receipt, _body, receipt_errors = tool.parse_note(receipt_path)
            assert receipt_errors == []
            assert receipt["type"] == "verification_open"
            assert receipt["retention_schedule_id"] == schedule[
                "retention_schedule_id"
            ]
            assert "protected_answers" not in json.dumps(
                receipt, ensure_ascii=False
            )
            assert snapshot_tree_bytes(vault) != before_open

            after_first_open = snapshot_tree_bytes(vault)
            reopened = tool.open_delayed_verification(
                vault, state_id=prepared["state"]["id"]
            )
            assert reopened["status"] == "already_opened"
            assert reopened["commit_status"] == "idempotent_reuse"
            assert reopened["opened_at"] == opened["opened_at"]
            assert reopened["retention_binding"] == binding
            assert snapshot_tree_bytes(vault) == after_first_open

            clock.current = due_at + timedelta(seconds=1)
            retention = append_demo_retention_evidence(
                vault,
                opened=opened,
                evidence_id="ev-retention-happy-pass",
            )
            assert retention["teaching_item_id"] == binding[
                "verification_open_id"
            ]
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert errors == [], errors
            state, _state_body, state_errors = tool.parse_note(
                prepared["state_path"]
            )
            assert state_errors == []
            assert state["retention_status"] == "passed_7d"
            assert state["contract_status"] == "met"
            assert state["mastery"] == "mastered"
            try:
                tool.open_delayed_verification(
                    vault, state_id=prepared["state"]["id"]
                )
            except tool.VaultError as exc:
                assert "evidence 消费" in str(exc) or "retention 尚未 due" in str(
                    exc
                ), exc
            else:
                raise AssertionError("已有 retention evidence 后不得再次开题")


def test_retention_receipts_are_exact_immutable_safe_records() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-retention-receipt-exact-") as temporary:
        root = Path(temporary)
        prepared = prepare_retention_schedule(
            root,
            suffix="retention-receipt-exact",
            not_before=(
                datetime.now(timezone.utc) + timedelta(days=8)
            ).isoformat(),
        )
        vault = prepared["vault"]
        due_at = tool.parse_iso_instant(
            prepared["schedule"]["scheduled_for"]
        ) + timedelta(seconds=1)
        with frozen_tool_clock(due_at):
            opened = tool.open_delayed_verification(
                vault, state_id=prepared["state"]["id"]
            )
            open_id = opened["retention_binding"]["verification_open_id"]
            open_path = (
                vault / "30-learning/verification-opens" / f"{open_id}.md"
            )
            schedule_id = prepared["schedule"]["retention_schedule_id"]
            schedule_path = (
                vault
                / "30-learning/retention-schedules"
                / f"{schedule_id}.md"
            )
            original_open = open_path.read_bytes()
            original_schedule = schedule_path.read_bytes()

            def validate_tampered_note(
                path: Path, meta: dict, body: str, original: bytes
            ) -> list[str]:
                tool.atomic_write_text(
                    path,
                    tool.render_frontmatter(meta)
                    + "\n"
                    + body.rstrip()
                    + "\n",
                )
                errors, _warnings, _summary = tool.validate_vault(vault)
                tool.atomic_write_bytes(path, original)
                restored_errors, _restored_warnings, _restored_summary = (
                    tool.validate_vault(vault)
                )
                assert restored_errors == [], restored_errors
                return errors

            open_meta, open_body, open_parse_errors = tool.parse_note(open_path)
            assert open_parse_errors == []
            for injected_field, injected_value in (
                ("prompt", prepared["retention_resource"]["verification_task"]["prompt"]),
                ("answer", prepared["retention_resource"]["verification_task"]["protected_answers"][0]),
                ("user_task", opened["user_task"]),
            ):
                forged = json.loads(json.dumps(open_meta))
                forged[injected_field] = injected_value
                errors = validate_tampered_note(
                    open_path, forged, open_body, original_open
                )
                assert any(
                    "verification_open metadata 字段必须精确匹配合同" in item
                    for item in errors
                ), (injected_field, errors)

            for leaked_text in (
                prepared["retention_resource"]["verification_task"]["prompt"],
                prepared["retention_resource"]["verification_task"][
                    "protected_answers"
                ][0],
            ):
                errors = validate_tampered_note(
                    open_path,
                    open_meta,
                    open_body + "\n" + leaked_text,
                    original_open,
                )
                assert any(
                    "verification_open 正文必须精确等于 canonical receipt body"
                    in item
                    for item in errors
                ), errors

            changed_open = json.loads(json.dumps(open_meta))
            changed_open["title"] += "（篡改）"
            errors = validate_tampered_note(
                open_path, changed_open, open_body, original_open
            )
            assert any(
                "verification_open receipt_fingerprint 非法" in item
                for item in errors
            ), errors
            errors = validate_tampered_note(
                open_path,
                open_meta,
                open_body.replace("延迟验证开题回执", "延迟验证开题回执!", 1),
                original_open,
            )
            assert any(
                "verification_open 正文必须精确等于 canonical receipt body"
                in item
                for item in errors
            ), errors

            schedule_meta, schedule_body, schedule_parse_errors = tool.parse_note(
                schedule_path
            )
            assert schedule_parse_errors == []
            early_open = json.loads(json.dumps(open_meta))
            early_at = (
                tool.parse_iso_instant(schedule_meta["scheduled_at"])
                - timedelta(microseconds=1)
            ).isoformat(timespec="microseconds").replace("+00:00", "Z")
            early_open["opened_at"] = early_at
            early_open["created_at"] = early_at
            early_open["updated_at"] = early_at
            early_open["receipt_fingerprint"] = tool.sha256_fingerprint(
                tool._open_fingerprint_payload(early_open)
            )
            errors = validate_tampered_note(
                open_path, early_open, open_body, original_open
            )
            assert any(
                "verification_open 早于 schedule.scheduled_at" in item
                for item in errors
            ), errors

            forged_schedule = json.loads(json.dumps(schedule_meta))
            forged_schedule["prompt"] = "排期回执不得夹带题面"
            errors = validate_tampered_note(
                schedule_path,
                forged_schedule,
                schedule_body,
                original_schedule,
            )
            assert any(
                "retention_schedule metadata 字段必须精确匹配合同" in item
                for item in errors
            ), errors
            changed_schedule = json.loads(json.dumps(schedule_meta))
            changed_schedule["title"] += "（篡改）"
            errors = validate_tampered_note(
                schedule_path,
                changed_schedule,
                schedule_body,
                original_schedule,
            )
            assert any(
                "retention_schedule receipt_fingerprint 非法" in item
                for item in errors
            ), errors
            errors = validate_tampered_note(
                schedule_path,
                schedule_meta,
                schedule_body + "\n夹带不属于回执的内容",
                original_schedule,
            )
            assert any(
                "retention_schedule 正文必须精确等于 canonical receipt body"
                in item
                for item in errors
            ), errors


def test_retention_binding_is_scoped_to_its_issued_baseline() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-retention-baseline-binding-") as temporary:
        root = Path(temporary)
        prepared = prepare_immediate_met_call_stack(
            root, suffix="retention-baseline-binding"
        )
        vault = prepared["vault"]
        baseline_a = prepared["first_verification"]
        baseline_b = prepared["baseline"]
        retention_resource = add_call_stack_resource(
            vault,
            suffix="retention-baseline-binding-task",
            duration_minutes=2,
        )
        retention_route = tool.issue_route(
            vault,
            record_path=write_retention_route_record(
                root,
                resource_id=retention_resource["id"],
                baseline_evidence_id=baseline_a["id"],
            ),
        )
        wrong_record = write_schedule_record(
            root,
            state=prepared["state"],
            baseline_evidence_id=baseline_b["id"],
            route_binding_id=retention_route["binding_id"],
            not_before=(
                datetime.now(timezone.utc) + timedelta(days=8)
            ).isoformat(),
        )
        before_wrong_baseline = snapshot_tree_bytes(vault)
        try:
            tool.schedule_retention(vault, record_path=wrong_record)
        except tool.VaultError as exc:
            assert "同 baseline" in str(exc), exc
        else:
            raise AssertionError("retention binding 不得改绑另一个合格 baseline")
        assert snapshot_tree_bytes(vault) == before_wrong_baseline

        scheduled = tool.schedule_retention(
            vault,
            record_path=write_schedule_record(
                root,
                state=prepared["state"],
                baseline_evidence_id=baseline_a["id"],
                route_binding_id=retention_route["binding_id"],
                not_before=(
                    datetime.now(timezone.utc) + timedelta(days=8)
                ).isoformat(),
            ),
        )
        assert scheduled["baseline_evidence_id"] == baseline_a["id"]
        ledger_path = vault / tool.ROUTE_BINDINGS_REL
        manifest_path = vault / tool.MANIFEST_REL
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        event = ledger["events"][-1]
        assert event["binding_id"] == retention_route["binding_id"]
        assert event["baseline_evidence_id"] == baseline_a["id"]
        event["source_ref_ids"] = [baseline_b["id"]]
        payload = dict(event)
        payload.pop("event_hash", None)
        event["event_hash"] = tool.sha256_fingerprint(payload)
        ledger["head_hash"] = event["event_hash"]
        manifest["route_binding_chain_head"] = event["event_hash"]
        tool.write_json(ledger_path, ledger)
        tool.write_json(manifest_path, manifest)
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            ".retention baseline_evidence_id 必须非空且属于 source_ref_ids"
            in item
            for item in errors
        ), errors


def test_retention_phase_purpose_open_receipt_and_task_reuse_guards() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-retention-guards-") as temporary:
        root = Path(temporary)
        prepared = prepare_immediate_met_call_stack(
            root, suffix="retention-guards"
        )
        vault = prepared["vault"]

        learning_binding_record = write_schedule_record(
            root,
            state=prepared["state"],
            baseline_evidence_id=prepared["baseline"]["id"],
            route_binding_id=prepared["latest_learning_route"]["binding_id"],
            not_before=None,
        )
        before_wrong_purpose = snapshot_tree_bytes(vault)
        try:
            tool.schedule_retention(vault, record_path=learning_binding_record)
        except tool.VaultError as exc:
            assert "purpose=retention" in str(exc), exc
        else:
            raise AssertionError("schedule 不得把 learning issuance 当 retention 使用")
        assert snapshot_tree_bytes(vault) == before_wrong_purpose

        issued = issue_retention_route_for_prepared(
            root, prepared, suffix="retention-guards"
        )
        prepared.update(issued)
        route = prepared["retention_route"]
        resource = prepared["retention_resource"]

        forged_verification = json.loads(json.dumps(prepared["baseline"]))
        forged_verification.update(
            {
                "id": "ev-retention-purpose-as-verification",
                "teaching_item_id": prepared["baseline"]["teaching_item_id"],
                "verification_item_id": route["verification_task_id"],
                "verification_task_id": route["verification_task_id"],
                "bound_verification_task_id": route["verification_task_id"],
                "route_id_at_observation": route["route_id"],
                "route_version_at_observation": route["route_version"],
                "activity": sorted(resource["supported_activities"])[0],
                "carrier": resource["carrier"],
                "observed_at": tool.utc_now_precise(),
            }
        )
        forged_record = write_raw_evidence_record(
            vault,
            forged_verification,
            evidence_id=forged_verification["id"],
            summary="试图把 retention route 当即时验证使用。",
        )
        try:
            tool.append_evidence(vault, record_path=forged_record)
        except tool.VaultError as exc:
            assert "verification 必须绑定 purpose=learning" in str(exc), exc
        else:
            raise AssertionError("verification 不得消费 purpose=retention issuance")

        duplicate = add_call_stack_resource(
            vault,
            suffix="retention-duplicate-task",
            duration_minutes=2,
        )
        duplicate_path = (
            vault / "30-learning/resources" / f"{duplicate['id']}.md"
        )
        duplicate, duplicate_body, duplicate_errors = tool.parse_note(
            duplicate_path
        )
        assert duplicate_errors == []
        duplicate["verification_task"] = json.loads(
            json.dumps(resource["verification_task"])
        )
        tool.atomic_write_text(
            duplicate_path,
            tool.render_frontmatter(duplicate)
            + "\n"
            + duplicate_body.rstrip()
            + "\n",
        )
        _index, rebuild_errors = tool.rebuild_index(vault)
        assert rebuild_errors == []
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors
        duplicate_record = write_retention_route_record(
            root,
            resource_id=duplicate["id"],
            baseline_evidence_id=prepared["baseline"]["id"],
        )
        before_duplicate = snapshot_tree_bytes(vault)
        try:
            tool.issue_route(vault, record_path=duplicate_record)
        except tool.VaultError as exc:
            assert "全新的 ID 与 task fingerprint" in str(exc), exc
        else:
            raise AssertionError("retention route 不得重复已签发 task/fingerprint")
        assert snapshot_tree_bytes(vault) == before_duplicate

        schedule = tool.schedule_retention(
            vault,
            record_path=write_schedule_record(
                root,
                state=prepared["state"],
                baseline_evidence_id=prepared["baseline"]["id"],
                route_binding_id=route["binding_id"],
                not_before=(
                    datetime.now(timezone.utc) + timedelta(days=8)
                ).isoformat(),
            ),
        )
        due_at = tool.parse_iso_instant(schedule["scheduled_for"]) + timedelta(
            seconds=1
        )
        with frozen_tool_clock(due_at) as clock:
            opened = tool.open_delayed_verification(
                vault, state_id=prepared["state"]["id"]
            )
            for label, forged_open_id in (
                ("missing", ""),
                ("wrong", "verification-open-not-current"),
            ):
                before = snapshot_tree_bytes(vault)
                try:
                    append_demo_retention_evidence(
                        vault,
                        opened=opened,
                        evidence_id=f"ev-retention-{label}-open-receipt",
                        teaching_item_id=forged_open_id,
                    )
                except tool.VaultError as exc:
                    assert "verification_open receipt" in str(exc), (label, exc)
                else:
                    raise AssertionError(
                        f"retention evidence 不得引用 {label} open receipt"
                    )
                assert snapshot_tree_bytes(vault) == before

            clock.current = due_at + timedelta(seconds=1)
            canonical = append_demo_retention_evidence(
                vault,
                opened=opened,
                evidence_id="ev-retention-receipt-validator",
            )
            canonical_path = (
                vault
                / "20-learner/evidence/ev-retention-receipt-validator.md"
            )
            canonical, canonical_body, canonical_errors = tool.parse_note(
                canonical_path
            )
            assert canonical_errors == []
            canonical["teaching_item_id"] = "verification-open-not-current"
            refresh_evidence_derivations(canonical)
            tool.atomic_write_text(
                canonical_path,
                tool.render_frontmatter(canonical)
                + "\n"
                + canonical_body.rstrip()
                + "\n",
            )
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert any(
                "必须引用 verification_open receipt" in error
                for error in errors
            ), errors


def test_retention_schedule_cas_late_due_and_transaction_rollbacks() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-retention-cas-") as temporary:
        root = Path(temporary)
        prepared = prepare_immediate_met_call_stack(
            root, suffix="retention-cas"
        )
        prepared.update(
            issue_retention_route_for_prepared(
                root, prepared, suffix="retention-cas"
            )
        )
        actual_epoch = prepared["state"]["evaluated_at"]
        stale_epoch = actual_epoch[:-1] + (
            "0" if actual_epoch[-1] != "0" else "1"
        )
        record = write_schedule_record(
            root,
            state=prepared["state"],
            baseline_evidence_id=prepared["baseline"]["id"],
            route_binding_id=prepared["retention_route"]["binding_id"],
            not_before=None,
            expected_state_evaluated_at=stale_epoch,
        )
        before = snapshot_tree_bytes(prepared["vault"])
        try:
            tool.schedule_retention(prepared["vault"], record_path=record)
        except tool.VaultError as exc:
            assert "CAS 冲突" in str(exc), exc
        else:
            raise AssertionError("schedule-retention 必须拒绝陈旧 state epoch")
        assert snapshot_tree_bytes(prepared["vault"]) == before

    with tempfile.TemporaryDirectory(
        prefix="uc-demo-retention-schedule-rollback-"
    ) as temporary:
        root = Path(temporary)
        prepared = prepare_immediate_met_call_stack(
            root, suffix="retention-schedule-rollback"
        )
        prepared.update(
            issue_retention_route_for_prepared(
                root, prepared, suffix="retention-schedule-rollback"
            )
        )
        record = write_schedule_record(
            root,
            state=prepared["state"],
            baseline_evidence_id=prepared["baseline"]["id"],
            route_binding_id=prepared["retention_route"]["binding_id"],
            not_before=(
                datetime.now(timezone.utc) + timedelta(days=8)
            ).isoformat(),
        )
        vault = prepared["vault"]
        before = snapshot_tree_bytes(vault)
        original_validate = tool.validate_vault
        fault = {"raised_after_write": False}

        def validate_then_fail_schedule(*args, **kwargs):
            result = original_validate(*args, **kwargs)
            if list((vault / "30-learning/retention-schedules").glob("*.md")):
                fault["raised_after_write"] = True
                raise RuntimeError("injected-after-schedule-write")
            return result

        tool.validate_vault = validate_then_fail_schedule
        try:
            try:
                tool.schedule_retention(vault, record_path=record)
            except RuntimeError as exc:
                assert str(exc) == "injected-after-schedule-write"
            else:
                raise AssertionError("schedule 写后故障必须触发回滚")
        finally:
            tool.validate_vault = original_validate
        assert fault["raised_after_write"] is True
        assert snapshot_tree_bytes(vault) == before
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors

    with tempfile.TemporaryDirectory(
        prefix="uc-demo-retention-open-rollback-"
    ) as temporary:
        root = Path(temporary)
        prepared = prepare_retention_schedule(
            root,
            suffix="retention-open-rollback",
            not_before=(
                datetime.now(timezone.utc) + timedelta(days=8)
            ).isoformat(),
        )
        vault = prepared["vault"]
        due_at = tool.parse_iso_instant(
            prepared["schedule"]["scheduled_for"]
        ) + timedelta(seconds=1)
        with frozen_tool_clock(due_at):
            before = snapshot_tree_bytes(vault)
            original_validate = tool.validate_vault
            fault = {"raised_after_write": False}

            def validate_then_fail_open(*args, **kwargs):
                result = original_validate(*args, **kwargs)
                if list(
                    (vault / "30-learning/verification-opens").glob("*.md")
                ):
                    fault["raised_after_write"] = True
                    raise RuntimeError("injected-after-open-write")
                return result

            tool.validate_vault = validate_then_fail_open
            try:
                try:
                    tool.open_delayed_verification(
                        vault, state_id=prepared["state"]["id"]
                    )
                except RuntimeError as exc:
                    assert str(exc) == "injected-after-open-write"
                else:
                    raise AssertionError("open 写后故障必须触发回滚")
            finally:
                tool.validate_vault = original_validate
            assert fault["raised_after_write"] is True
            assert snapshot_tree_bytes(vault) == before
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert errors == [], errors

    with tempfile.TemporaryDirectory(
        prefix="uc-demo-retention-late-schedule-"
    ) as temporary:
        root = Path(temporary)
        prepared = prepare_immediate_met_call_stack(
            root, suffix="retention-late"
        )
        prepared.update(
            issue_retention_route_for_prepared(
                root, prepared, suffix="retention-late"
            )
        )
        late_now = tool.parse_iso_instant(
            prepared["baseline"]["observed_at"]
        ) + timedelta(days=8)
        with frozen_tool_clock(late_now):
            scheduled = tool.schedule_retention(
                prepared["vault"],
                record_path=write_schedule_record(
                    root,
                    state=prepared["state"],
                    baseline_evidence_id=prepared["baseline"]["id"],
                    route_binding_id=prepared["retention_route"]["binding_id"],
                    not_before=None,
                ),
            )
            assert scheduled["retention_status"] == "due", scheduled
            assert scheduled["next_action"] == "issue_delayed_verification"
            opened = tool.open_delayed_verification(
                prepared["vault"], state_id=prepared["state"]["id"]
            )
            assert opened["status"] == "opened"


def test_validator_rejects_one_second_future_evidence_state_and_issuance() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-future-evidence-1s-") as temporary:
        vault = seed(Path(temporary))
        path = vault / "20-learner/evidence/ev-demo-a17-001.md"
        meta, body, parse_errors = tool.parse_note(path)
        assert parse_errors == []
        frozen_now = datetime.now(timezone.utc)
        meta["observed_at"] = (frozen_now + timedelta(seconds=1)).isoformat()
        refresh_evidence_derivations(meta)
        tool.atomic_write_text(
            path, tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n"
        )
        with frozen_tool_clock(frozen_now):
            errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "evidence observed_at 不得位于未来" in error for error in errors
        ), errors

    with tempfile.TemporaryDirectory(prefix="uc-demo-future-state-1s-") as temporary:
        vault = seed(Path(temporary))
        path = vault / "20-learner/states/ks-demo-a17-kc-python-call-stack.md"
        meta, body, parse_errors = tool.parse_note(path)
        assert parse_errors == []
        frozen_now = datetime.now(timezone.utc)
        meta["evaluated_at"] = (frozen_now + timedelta(seconds=1)).isoformat()
        tool.atomic_write_text(
            path, tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n"
        )
        with frozen_tool_clock(frozen_now):
            errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "state evaluated_at 不得位于未来" in error for error in errors
        ), errors

    with tempfile.TemporaryDirectory(prefix="uc-demo-future-delivery-1s-") as temporary:
        root = Path(temporary)
        vault = seed(root)
        ensure_teachable_call_stack(vault, suffix="future-delivery-1s")
        content_path = root / "future-delivery-content.json"
        tool.atomic_write_text(
            content_path,
            json.dumps(valid_delivery_content(vault=vault), ensure_ascii=False),
        )
        issued = tool.issue_teaching_delivery(vault, content_path=content_path)
        path = (
            vault
            / "30-learning/deliveries"
            / f"{issued['teaching_item_id']}.md"
        )
        meta, body, parse_errors = tool.parse_note(path)
        assert parse_errors == []
        frozen_now = datetime.now(timezone.utc)
        future = (frozen_now + timedelta(seconds=1)).isoformat()
        meta["issued_at"] = future
        meta["created_at"] = future
        meta["updated_at"] = future
        tool.atomic_write_text(
            path, tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n"
        )
        with frozen_tool_clock(frozen_now):
            errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "teaching_delivery issued_at 不得位于未来" in error
            for error in errors
        ), errors


def test_retention_repair_uses_new_baseline_binding_task_and_schedule() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-retention-repair-") as temporary:
        root = Path(temporary)
        prepared = prepare_retention_schedule(
            root,
            suffix="retention-repair",
            not_before=(
                datetime.now(timezone.utc) + timedelta(days=8)
            ).isoformat(),
        )
        vault = prepared["vault"]
        old_schedule = prepared["schedule"]
        due_at = tool.parse_iso_instant(old_schedule["scheduled_for"]) + timedelta(
            seconds=1
        )
        with frozen_tool_clock(due_at) as clock:
            opened = tool.open_delayed_verification(
                vault, state_id=prepared["state"]["id"]
            )
            clock.current = due_at + timedelta(seconds=1)
            failed = append_demo_retention_evidence(
                vault,
                opened=opened,
                evidence_id="ev-retention-repair-failed",
                result="fail",
            )
            state, _body, state_errors = tool.parse_note(prepared["state_path"])
            assert state_errors == []
            assert state["retention_status"] == "failed"
            assert state["next_action"] == "retention_repair"
            assert state["current_retention_schedule_id"] == old_schedule[
                "retention_schedule_id"
            ]

            stale_record = write_schedule_record(
                root,
                state=state,
                baseline_evidence_id=prepared["baseline"]["id"],
                route_binding_id=prepared["retention_route"]["binding_id"],
                not_before=None,
            )
            try:
                tool.schedule_retention(vault, record_path=stale_record)
            except tool.VaultError as exc:
                assert (
                    "已被 verification/retention/open 消费" in str(exc)
                    or "新 binding/task/fingerprint" in str(exc)
                    or "新合格 verification baseline" in str(exc)
                ), exc
            else:
                raise AssertionError("retention repair 不得复用旧 baseline/binding/task")

            clock.current = due_at + timedelta(seconds=2)
            learning_resource = add_call_stack_resource(
                vault,
                suffix="retention-repair-learning",
                duration_minutes=0.25,
            )
            new_learning_route = tool.issue_route(
                vault,
                record_path=write_learning_route_record(
                    root, learning_resource["id"]
                ),
            )
            assert new_learning_route["purpose"] == "learning"
            process = append_demo_call_stack_process(
                vault,
                evidence_id="ev-retention-repair-process",
                result="pass",
            )
            new_baseline = append_demo_call_stack_verification(
                vault,
                process=process,
                evidence_id="ev-retention-repair-new-baseline",
            )
            assert tool.parse_iso_instant(new_baseline["observed_at"]) > (
                tool.parse_iso_instant(failed["observed_at"])
            )
            state, _body, state_errors = tool.parse_note(prepared["state_path"])
            assert state_errors == []
            assert state["retention_status"] == "failed"
            assert state["next_action"] == "retention_repair"

            new_resource = add_call_stack_resource(
                vault,
                suffix="retention-repair-task-2",
                duration_minutes=2,
            )
            new_route = tool.issue_route(
                vault,
                record_path=write_retention_route_record(
                    root,
                    resource_id=new_resource["id"],
                    baseline_evidence_id=new_baseline["id"],
                ),
            )
            assert new_route["binding_id"] != prepared["retention_route"][
                "binding_id"
            ]
            assert new_route["verification_task_id"] != old_schedule[
                "retention_task_id"
            ]
            schedule = tool.schedule_retention(
                vault,
                record_path=write_schedule_record(
                    root,
                    state=state,
                    baseline_evidence_id=new_baseline["id"],
                    route_binding_id=new_route["binding_id"],
                    not_before=None,
                ),
            )
            assert schedule["retention_schedule_id"] != old_schedule[
                "retention_schedule_id"
            ]
            assert schedule["baseline_evidence_id"] == new_baseline["id"]
            assert schedule["retention_route_binding_id"] == new_route[
                "binding_id"
            ]
            old_path = (
                vault
                / "30-learning/retention-schedules"
                / f"{old_schedule['retention_schedule_id']}.md"
            )
            new_path = (
                vault
                / "30-learning/retention-schedules"
                / f"{schedule['retention_schedule_id']}.md"
            )
            old_receipt, _old_body, old_errors = tool.parse_note(old_path)
            new_receipt, new_body, new_errors = tool.parse_note(new_path)
            assert old_errors == [] and new_errors == []
            assert old_receipt["supersedes_schedule_id"] is None
            assert new_receipt["supersedes_schedule_id"] == old_receipt["id"]
            assert f"[[{old_receipt['id']}]]" in new_body
            assert new_receipt["verification_task_fingerprint"] != old_receipt[
                "verification_task_fingerprint"
            ]
            state, _body, state_errors = tool.parse_note(prepared["state_path"])
            assert state_errors == []
            assert state["current_retention_schedule_id"] == new_receipt["id"]
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert errors == [], errors


def test_route_registry_is_required_and_binds_task_and_issue_time() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-route-registry-missing-") as temporary:
        vault = seed(Path(temporary))
        registry = vault / tool.ROUTE_BINDINGS_REL
        assert registry.is_file()
        registry.rename(vault / "route-bindings.disabled")
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("账本文件不存在" in item for item in errors), errors

    with tempfile.TemporaryDirectory(prefix="uc-demo-route-registry-task-") as temporary:
        vault = seed(Path(temporary))
        registry = vault / tool.ROUTE_BINDINGS_REL
        document = json.loads(registry.read_text(encoding="utf-8"))
        assert document["schema"] == "uc-route-bindings/0.2"
        assert document["events"]
        document["events"][0]["verification_task_id"] = "task-not-issued"
        tool.write_json(registry, document)
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("resource verification_task id 与发行记录不一致" in item for item in errors), errors

    with tempfile.TemporaryDirectory(prefix="uc-demo-route-registry-time-") as temporary:
        vault = seed(Path(temporary))
        registry = vault / tool.ROUTE_BINDINGS_REL
        document = json.loads(registry.read_text(encoding="utf-8"))
        assert document["events"]
        document["events"][0]["issued_at"] = "2099-01-01T00:00:00+00:00"
        rehash_route_binding_document(vault, document)
        tool.write_json(registry, document)
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "route binding registry.events[0].issued_at 不得位于未来" in item
            for item in errors
        ), errors


def test_route_registry_hash_chain_detects_tamper_reorder_and_truncation() -> None:
    def validate_mutation(prefix: str, mutate) -> list[str]:
        with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
            vault = seed(Path(temporary))
            registry = vault / tool.ROUTE_BINDINGS_REL
            document = json.loads(registry.read_text(encoding="utf-8"))
            assert document["schema"] == tool.ROUTE_BINDING_SCHEMA
            assert len(document["events"]) >= 3
            mutate(document)
            tool.write_json(registry, document)
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert errors, document
            return errors

    errors = validate_mutation(
        "uc-demo-route-chain-tamper-",
        lambda document: document["events"][0]["source_ref_ids"].append(
            "turn-tampered"
        ),
    )
    assert any("event_hash 与内容不一致" in item for item in errors), errors

    def reorder(document: dict) -> None:
        document["events"][0], document["events"][1] = (
            document["events"][1],
            document["events"][0],
        )

    errors = validate_mutation("uc-demo-route-chain-reorder-", reorder)
    assert any("sequence 必须连续且等于文件顺序" in item for item in errors), errors
    assert any("previous_hash 断链" in item for item in errors), errors

    errors = validate_mutation(
        "uc-demo-route-chain-truncate-", lambda document: document["events"].pop()
    )
    assert any("head_sequence 与事件数不一致" in item for item in errors), errors
    assert any("manifest route_binding_chain_length" in item for item in errors), errors


def test_trusted_seed_rejects_coordinated_route_ledger_rehash() -> None:
    def validate_mutation(prefix: str, mutate) -> list[str]:
        with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
            vault = seed(Path(temporary))
            manifest_path = vault / tool.MANIFEST_REL
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert manifest["route_trust_level"] == "trusted_seed_source"
            registry_path = vault / tool.ROUTE_BINDINGS_REL
            document = json.loads(registry_path.read_text(encoding="utf-8"))
            mutate(document)
            rehash_route_binding_document(vault, document)
            tool.write_json(registry_path, document)
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert errors, document
            assert any(
                "route binding 账本的 Vault 外 trusted seed 前缀不一致" in item
                for item in errors
            ), errors
            return errors

    def mutate_task(document: dict) -> None:
        event = document["events"][0]
        event["verification_task_id"] = "verify-coordinated-tamper"
        for resource in event["issuance_snapshot"]["resources"]:
            resource["verification_task"]["id"] = "verify-coordinated-tamper"

    validate_mutation("uc-demo-trusted-task-", mutate_task)

    def mutate_context(document: dict) -> None:
        event = document["events"][0]
        event["comparison_context"]["domain"] = "live2d"
        event["context_key"] = tool.comparison_context_key(
            event["comparison_context"]
        )

    validate_mutation("uc-demo-trusted-context-", mutate_context)

    def mutate_snapshot(document: dict) -> None:
        task = document["events"][0]["issuance_snapshot"]["resources"][0][
            "verification_task"
        ]
        task["prompt"] = "被协同重写且重新哈希的验证题"

    validate_mutation("uc-demo-trusted-snapshot-", mutate_snapshot)

    with tempfile.TemporaryDirectory(prefix="uc-demo-trust-downgrade-") as temporary:
        vault = seed(Path(temporary))
        manifest_path = vault / tool.MANIFEST_REL
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["route_trust_level"] = "local_chain_only"
        tool.write_json(manifest_path, manifest)
        errors, warnings, _summary = tool.validate_vault(vault)
        assert any(
            "synthetic_demo 不得把 route trust 降级为 local_chain_only" in item
            for item in errors
        ), errors
        assert any("route trust=local_chain_only" in item for item in warnings), warnings


def test_route_registry_rejects_context_snapshot_and_active_resource_drift() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-route-context-") as temporary:
        vault = seed(Path(temporary))
        registry = vault / tool.ROUTE_BINDINGS_REL
        document = json.loads(registry.read_text(encoding="utf-8"))
        document["events"][0]["comparison_context"]["domain"] = "live2d"
        tool.write_json(registry, document)
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("context_key 不是 comparison_context" in item for item in errors), errors

    with tempfile.TemporaryDirectory(prefix="uc-demo-route-history-snapshot-") as temporary:
        vault = seed(Path(temporary))
        registry = vault / tool.ROUTE_BINDINGS_REL
        document = json.loads(registry.read_text(encoding="utf-8"))
        del document["events"][0]["issuance_snapshot"]
        tool.write_json(registry, document)
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("issuance_snapshot 必须是对象" in item for item in errors), errors

    with tempfile.TemporaryDirectory(prefix="uc-demo-active-resource-drift-") as temporary:
        vault = seed(Path(temporary))
        resource = vault / "30-learning/resources/res-python-call-stack-contrast.md"
        meta, body, parse_errors = tool.parse_note(resource)
        assert parse_errors == []
        meta["verification_task"] = dict(meta["verification_task"])
        meta["verification_task"]["success_criteria"] = "被篡改的通过条件"
        tool.atomic_write_text(
            resource,
            tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("active intervention/resource 已偏离 route issuance 快照" in item for item in errors), errors


def test_vault_rejects_missing_or_wrong_field_binding_for_actionable_value() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-field-binding-missing-") as temporary:
        vault = seed(Path(temporary))
        evidence_path = vault / "20-learner/evidence/ev-demo-a17-001.md"
        meta, body, parse_errors = tool.parse_note(evidence_path)
        assert parse_errors == []
        assert "elapsed_seconds" in meta["field_bindings"]
        del meta["field_bindings"]["elapsed_seconds"]
        tool.atomic_write_text(
            evidence_path,
            tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "缺少 field_bindings" in item and "elapsed_seconds" in item
            for item in errors
        ), errors

    with tempfile.TemporaryDirectory(prefix="uc-demo-field-binding-consumer-") as temporary:
        vault = seed(Path(temporary))
        evidence_path = vault / "20-learner/evidence/ev-demo-a17-001.md"
        meta, body, parse_errors = tool.parse_note(evidence_path)
        assert parse_errors == []
        binding = meta["field_bindings"]["elapsed_seconds"]
        binding["consumers"] = ["focus_priority"]
        tool.atomic_write_text(
            evidence_path,
            tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "field_binding consumers 未绑定到 note consumers" in item
            and "/elapsed_seconds" in item
            for item in errors
        ), errors


def test_source_receipts_cannot_be_forged_at_note_or_field_binding_level() -> None:
    evidence_id = "ev-demo-a17-001"
    relative_path = "20-learner/evidence/ev-demo-a17-001.md"

    with tempfile.TemporaryDirectory(prefix="uc-demo-forged-note-receipt-") as temporary:
        vault = seed(Path(temporary))
        path = vault / relative_path
        meta, body, parse_errors = tool.parse_note(path)
        assert parse_errors == []
        canonical_receipts = list(meta["source_ref_ids"])
        meta["source_ref_ids"] = canonical_receipts + ["receipt://caller-forged"]
        for binding in meta["field_bindings"].values():
            binding["source_ref_ids"] = list(meta["source_ref_ids"])
        tool.atomic_write_text(
            path, tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n"
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "source_ref_ids 必须严格等于 canonical session.source_ref" in error
            and relative_path in error
            for error in errors
        ), errors
        try:
            tool.build_response_observation_from_vault(vault, evidence_id)
        except tool.VaultError as exc:
            assert "source_ref_ids 必须严格等于 canonical session.source_ref" in str(
                exc
            )
        else:
            raise AssertionError("生产 adapter 不得接受额外伪造 receipt")

    with tempfile.TemporaryDirectory(prefix="uc-demo-forged-field-receipt-") as temporary:
        vault = seed(Path(temporary))
        path = vault / relative_path
        meta, body, parse_errors = tool.parse_note(path)
        assert parse_errors == []
        meta["field_bindings"]["elapsed_seconds"]["source_ref_ids"] = [
            "receipt://field-only-forged"
        ]
        tool.atomic_write_text(
            path, tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n"
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "field_binding source_ref_ids 非法" in error
            and f"{relative_path}/elapsed_seconds" in error
            for error in errors
        ), errors
        try:
            tool.build_response_observation_from_vault(vault, evidence_id)
        except tool.VaultError as exc:
            assert "field_binding source_ref_ids 非法" in str(exc)
            assert "/elapsed_seconds" in str(exc)
        else:
            raise AssertionError("生产 adapter 不得接受只指向伪造 receipt 的字段")


def _profile_observation(
    evidence_id: str,
    *,
    concept_id: str = "kc-python-call-stack",
    learner_id: str = "demo-a17",
    domain: str = "python",
    knowledge_kind: str = "rule",
    target_performance: str = "discriminate",
    prior_knowledge_band: str = "partial",
    task_difficulty: str = "medium",
    activity: str = "contrast_cases",
    carrier: str,
    mastery_eligible: bool,
    elapsed_seconds: float,
    attempts: int,
    immediate_performance: float,
    near_transfer: float,
    effort: float,
    phase: str = "verification",
    source_kind: str = "behavior_observation",
    confidence_override: str | None = None,
    source_context_key: str | None = None,
    forged_contract_claims: dict | None = None,
) -> dict:
    stored_mastery_eligible = (
        mastery_eligible and source_kind in tool.BEHAVIOR_SOURCE_KINDS
    )
    scope = {
        "learner_id": learner_id,
        "goal_id": f"goal-{learner_id}-profile",
        "concept_id": concept_id,
        "contract_id": f"mc-{concept_id}",
        "contract_version": 1,
    }
    context_key = canonical_context_key(
        domain=domain,
        knowledge_kind=knowledge_kind,
        target_performance=target_performance,
        prior_knowledge_band=prior_knowledge_band,
        task_difficulty=task_difficulty,
    )
    evidence = {
        "id": evidence_id,
        **scope,
        "phase": phase,
        "evidence_kind": {
            "diagnostic": "diagnostic_probe",
            "teaching_process": "explanation",
            "verification": "independent_performance",
            "retention": "delayed_transfer",
        }[phase],
        "context_key": source_context_key or context_key,
        "activity": activity,
        "carrier": carrier,
        "teaching_item_id": f"teach-{evidence_id}",
        "verification_item_id": f"verify-item-{evidence_id}",
        "verification_task_id": f"verify-task-{evidence_id}",
        "bound_verification_task_id": f"verify-task-{evidence_id}",
        "route_id_at_observation": "route-demo-a17-recursion",
        "route_version_at_observation": 1,
        "route_binding_id": "rb-demo-a17-profile-v1",
        "verification_unseen": True,
        "answer_revealed_before_first_attempt": False,
        "consumer_ids": [],
        "source_ref_ids": [f"turn-{evidence_id}"],
        "source_kind": source_kind,
        "observation_validity": "valid",
        "mastery_eligible": stored_mastery_eligible,
        "result": "pass",
        "response_correct": True,
        "demonstrates": ["independent_application", "near_transfer"],
        "independence": "independent" if mastery_eligible else "hinted",
        "assistance_level": "A0" if mastery_eligible else "A1",
        "elapsed_seconds": elapsed_seconds,
        "attempts": attempts,
        "hint_count": 0 if mastery_eligible else 1,
        "immediate_performance": immediate_performance,
        "near_transfer": near_transfer,
        "delayed_retention": "not_required",
        "explanation_quality": "pass",
        "self_reported_effort": effort,
        "observed_at": "2026-08-28T04:10:00+00:00",
    }
    evidence["consumer_ids"] = sorted(
        {
            consumer
            for field, allowed_consumers in tool.PHASE_FIELD_CONSUMERS[
                evidence["phase"]
            ].items()
            if tool.evidence_field_is_actionable(evidence, field)
            for consumer in allowed_consumers
        }
    )
    derived_eligible, failures = tool.evidence_mastery_eligibility(evidence)
    assert derived_eligible is stored_mastery_eligible, failures
    derived_confidence, confidence_basis = tool.derive_observation_confidence(
        evidence, derived_mastery_eligible=derived_eligible
    )
    evidence["observation_confidence"] = (
        confidence_override
        if confidence_override is not None
        else derived_confidence
    )
    evidence["observation_confidence_basis"] = confidence_basis
    evidence["consumer_ids"] = sorted(
        {
            consumer
            for field, allowed_consumers in tool.PHASE_FIELD_CONSUMERS[
                evidence["phase"]
            ].items()
            if tool.evidence_field_is_actionable(evidence, field)
            for consumer in allowed_consumers
        }
    )
    evidence["field_bindings"] = tool.build_evidence_field_bindings(evidence)
    contract = {
        "id": scope["contract_id"],
        "version": scope["contract_version"],
        "concept_id": scope["concept_id"],
        "requirements": {
            "minimum_qualified_evidence": 1,
            "required_capabilities": ["independent_application", "near_transfer"],
            "min_near_transfer": 0.75,
            "delayed_retention": {
                "required": False,
                "min_score": None,
                "min_delay_days": 0,
            },
        }
    }
    if forged_contract_claims:
        contract.update(forged_contract_claims)
    comparison_context = {
        "domain": domain,
        "knowledge_kind": knowledge_kind,
        "target_performance": target_performance,
        "prior_band": prior_knowledge_band,
        "task_difficulty": task_difficulty,
    }
    return text_policy._build_response_observation_from_validated_vault_inputs(
        evidence_id,
        evidence,
        contract,
        [(evidence_id, evidence)],
        comparison_context,
        as_of=evidence["observed_at"],
    )


def _profile_decision(observations: list[dict], **overrides) -> dict:
    refs = [item["source"]["evidence_id"] for item in observations]
    return text_policy.decide_text_activity(
        text_context(
            response_profile_refs=refs,
            response_profile_observations=observations,
            **overrides,
        )
    )


def _fast_retrieval_observation(evidence_id: str, concept_id: str, **overrides) -> dict:
    return _profile_observation(
        evidence_id,
        concept_id=concept_id,
        activity="retrieval_prompt",
        carrier="text_document",
        mastery_eligible=True,
        elapsed_seconds=20,
        attempts=1,
        immediate_performance=1.0,
        near_transfer=0.95,
        effort=1,
        **overrides,
    )


def _slow_contrast_observation(evidence_id: str, concept_id: str, **overrides) -> dict:
    return _profile_observation(
        evidence_id,
        concept_id=concept_id,
        activity="contrast_cases",
        carrier="text_hybrid",
        mastery_eligible=True,
        elapsed_seconds=100,
        attempts=2,
        immediate_performance=0.8,
        near_transfer=0.75,
        effort=5,
        **overrides,
    )


def test_response_profile_thresholds_control_activity_and_carrier() -> None:
    tentative = [
        _fast_retrieval_observation("ev-tentative-fast", "kc-profile-a"),
        _slow_contrast_observation("ev-tentative-slow", "kc-profile-b"),
    ]
    decision = _profile_decision(tentative)
    assert decision["profile_selection_status"] == "tentative_exploration", decision
    assert decision["profile_selection"]["evidence_level"] == "tentative"
    assert decision["activity"] == "contrast_cases", decision
    assert decision["carrier"] == "text_hybrid", decision
    assert decision["profile_usage_status"] == "exploration_only_threshold"

    pool_sufficient_winner_insufficient = tentative + [
        _fast_retrieval_observation("ev-emerging-fast", "kc-profile-a")
    ]
    decision = _profile_decision(pool_sufficient_winner_insufficient)
    assert decision["profile_selection_status"] == "tentative_exploration", decision
    assert decision["profile_selection"]["evidence_level"] == "tentative"
    assert decision["profile_selection"]["qualified_observation_count"] == 2
    assert decision["profile_selection"]["distinct_concept_count"] == 1
    assert decision["profile_selection"]["candidate_pool_observation_count"] == 3
    assert decision["profile_selection"]["candidate_pool_distinct_concept_count"] == 2
    assert decision["profile_selection"]["threshold_basis"] == (
        "retrieval_prompt|text_document"
    )
    assert decision["activity"] == "contrast_cases", decision
    assert decision["profile_usage_status"] == "exploration_only_threshold"

    emerging = pool_sufficient_winner_insufficient + [
        _fast_retrieval_observation("ev-emerging-fast-b", "kc-profile-b")
    ]
    decision = _profile_decision(emerging)
    assert decision["profile_selection_status"] == "pareto_selected", decision
    assert decision["profile_selection"]["evidence_level"] == "emerging"
    assert decision["profile_selection"]["qualified_observation_count"] == 3
    assert decision["profile_selection"]["distinct_concept_count"] == 2
    assert decision["activity"] == "retrieval_prompt", decision
    assert decision["carrier"] == "text_hybrid", decision
    assert decision["profile_usage_status"] == "activity_only"

    supported = emerging + [
        _fast_retrieval_observation("ev-supported-fast-c1", "kc-profile-c"),
        _fast_retrieval_observation("ev-supported-fast-c2", "kc-profile-c"),
    ]
    decision = _profile_decision(supported)
    assert decision["profile_selection_status"] == "pareto_selected", decision
    assert decision["profile_selection"]["evidence_level"] == "supported"
    assert decision["profile_selection"]["qualified_observation_count"] == 5
    assert decision["profile_selection"]["distinct_concept_count"] == 3
    assert decision["profile_selection"]["has_transfer_or_retention"] is True
    assert decision["activity"] == "retrieval_prompt", decision
    assert decision["carrier"] == "text_document", decision
    assert decision["selection_consumer"] == "activity_selection"
    assert decision["profile_usage_status"] == "activity_and_carrier"


def test_response_profile_rejects_wrong_learner_context_gate_help_and_confidence() -> None:
    wrong_learner = _fast_retrieval_observation(
        "ev-wrong-learner", "kc-profile-a", learner_id="other-learner"
    )
    try:
        _profile_decision([wrong_learner])
    except text_policy.TextPolicyError as exc:
        assert "learner" in str(exc)
    else:
        raise AssertionError("其他 learner 的画像不得参与当前活动选择")

    wrong_domain = _fast_retrieval_observation(
        "ev-wrong-domain", "kc-profile-a", domain="live2d"
    )
    try:
        _profile_decision([wrong_domain])
    except text_policy.TextPolicyError as exc:
        assert "context_key" in str(exc)
    else:
        raise AssertionError("其他 domain/context 的画像不得参与当前活动选择")

    base = _fast_retrieval_observation("ev-filter-base", "kc-profile-a")
    wrong_gate = json.loads(json.dumps(base))
    wrong_gate["comparison_gate"]["retention_required"] = True
    wrong_gate["mastery_gate_derivation"]["comparison_gate"][
        "retention_required"
    ] = True
    decision = _profile_decision([wrong_gate])
    assert decision["profile_selection_status"] == "no_qualified_observations"
    assert decision["activity"] == "contrast_cases"

    too_much_help = json.loads(json.dumps(base))
    too_much_help["assistance_level"] = "A1"
    decision = _profile_decision([too_much_help], max_assistance_level="A0")
    assert decision["profile_selection_status"] == "no_qualified_observations"
    assert decision["activity"] == "contrast_cases"

    low_confidence = _fast_retrieval_observation(
        "ev-low-confidence", "kc-profile-a", source_kind="self_report"
    )
    assert low_confidence["confidence"] == "low"
    decision = _profile_decision([low_confidence])
    assert decision["profile_selection_status"] == "no_qualified_observations"
    assert decision["profile_selection"]["qualified_observation_refs"] == []
    assert decision["profile_selection"]["rejected_observation_refs"] == [
        "ev-low-confidence"
    ]
    assert decision["activity"] == "contrast_cases"


def test_observation_confidence_is_derived_not_caller_selected() -> None:
    independent = _fast_retrieval_observation(
        "ev-derived-confidence-high", "kc-profile-confidence"
    )
    assert independent["confidence"] == "high"

    for phase in ("teaching_process", "diagnostic"):
        process = _profile_observation(
            f"ev-derived-confidence-{phase}",
            concept_id="kc-profile-confidence",
            carrier="text_hybrid",
            mastery_eligible=False,
            elapsed_seconds=40,
            attempts=1,
            immediate_performance=0.7,
            near_transfer=0.6,
            effort=2,
            phase=phase,
        )
        assert process["confidence"] == "medium"

    forged_cases = (
        {
            "evidence_id": "ev-forged-confidence-low",
            "mastery_eligible": True,
            "phase": "verification",
            "confidence_override": "low",
        },
        {
            "evidence_id": "ev-forged-confidence-high",
            "mastery_eligible": False,
            "phase": "teaching_process",
            "confidence_override": "high",
        },
    )
    for case in forged_cases:
        try:
            _profile_observation(
                case["evidence_id"],
                concept_id="kc-profile-confidence",
                carrier="text_hybrid",
                mastery_eligible=case["mastery_eligible"],
                elapsed_seconds=40,
                attempts=1,
                immediate_performance=0.8,
                near_transfer=0.75,
                effort=2,
                phase=case["phase"],
                confidence_override=case["confidence_override"],
            )
        except text_policy.TextPolicyError as exc:
            assert "observation_confidence 不是来源与资格推导值" in str(exc)
        else:
            raise AssertionError("调用者手填 high/low 不得覆盖可信度派生值")


def test_response_adapter_rejects_source_context_claim_mismatch() -> None:
    wrong_source_key = canonical_context_key(
        domain="live2d",
        knowledge_kind="rule",
        target_performance="discriminate",
        prior_knowledge_band="partial",
        task_difficulty="medium",
    )
    try:
        _fast_retrieval_observation(
            "ev-source-context-mismatch",
            "kc-profile-a",
            source_context_key=wrong_source_key,
        )
    except text_policy.TextPolicyError as exc:
        assert "context_key" in str(exc)
    else:
        raise AssertionError(
            "source evidence 的 context_key 与合同派生比较情境不一致时必须拒绝"
        )


def test_response_adapter_recomputes_and_ignores_forged_contract_outcome() -> None:
    observation = _profile_observation(
        "ev-forged-contract-outcome",
        concept_id="kc-profile-forgery",
        carrier="text_hybrid",
        mastery_eligible=False,
        elapsed_seconds=20,
        attempts=1,
        immediate_performance=1.0,
        near_transfer=1.0,
        effort=1,
        forged_contract_claims={
            "status": "met",
            "contract_status": "met",
            "qualified_evidence_ids": ["ev-forged-contract-outcome"],
            "qualified_failure_evidence_ids": [],
        },
    )
    assert observation["source"]["derived_mastery_eligible"] is False
    assert observation["mastery_gate_met"] is False
    assert observation["mastery_gate_derivation"]["contract_status"] != "met"
    assert "ev-forged-contract-outcome" not in observation[
        "mastery_gate_derivation"
    ]["qualified_evidence_ids"]


def test_verification_binding_and_contract_coverage_are_enforced() -> None:
    decision = text_policy.decide_text_activity(text_context())
    scope = decision_scope(decision)
    record = {
        "observation_kind": "verification",
        "learner_response_present": True,
        "teaching_item_id": "teach-1",
        "verification_item_id": "verify-2",
        "verification_unseen": True,
        "verification_task_id": decision["bound_verification_task_id"],
        "bound_verification_task_id": decision["bound_verification_task_id"],
        "route_id_at_observation": decision["route_id"],
        "route_version_at_observation": decision["route_version"],
        "bound_route_id": decision["route_id"],
        "bound_route_version": decision["route_version"],
        "answer_revealed_before_first_attempt": False,
        "verification_assistance_level": "A0",
        "response_correct": True,
        "required_capabilities": ["independent_application", "near_transfer"],
        "demonstrated_capabilities": ["independent_application", "near_transfer"],
        "scope": scope,
        "evidence_scope": dict(scope),
    }
    mismatch = dict(record, bound_verification_task_id="different-task")
    result = text_policy.evaluate_text_unit(mismatch, decision)
    assert result["mastery_eligible"] is False
    assert "verification_task_binding_mismatch" in result["qualification_failures"]

    uncovered = dict(record, demonstrated_capabilities=["independent_application"])
    result = text_policy.evaluate_text_unit(uncovered, decision)
    assert result["mastery_eligible"] is True
    assert result["verification_outcome"] == "qualified_fail"
    assert "contract_capability_not_covered" in result["performance_failures"]

    process = text_policy.evaluate_text_unit(
        {
            "observation_kind": "teaching_process",
            "scope": scope,
            "evidence_scope": dict(scope),
            "verification_task_id": decision["bound_verification_task_id"],
            "bound_verification_task_id": decision["bound_verification_task_id"],
            "route_id_at_observation": decision["route_id"],
            "route_version_at_observation": decision["route_version"],
            "bound_route_id": decision["route_id"],
            "bound_route_version": decision["route_version"],
            "response_correct": True,
            "verification_assistance_level": "A0",
        },
        decision,
    )
    assert process["mastery_eligible"] is False
    assert process["next_action"] == "continue_to_unseen_verification"


def test_text_unit_rejects_every_current_decision_binding_mismatch() -> None:
    decision = text_policy.decide_text_activity(text_context())
    scope = decision_scope(decision)
    record = {
        "observation_kind": "verification",
        "learner_response_present": True,
        "teaching_item_id": "teach-current",
        "verification_item_id": "verify-current-unseen",
        "verification_unseen": True,
        "verification_task_id": decision["bound_verification_task_id"],
        "bound_verification_task_id": decision["bound_verification_task_id"],
        "route_id_at_observation": decision["route_id"],
        "route_version_at_observation": decision["route_version"],
        "bound_route_id": decision["route_id"],
        "bound_route_version": decision["route_version"],
        "answer_revealed_before_first_attempt": False,
        "verification_assistance_level": "A0",
        "response_correct": True,
        "required_capabilities": ["independent_application"],
        "demonstrated_capabilities": ["independent_application"],
        "scope": dict(scope),
        "evidence_scope": dict(scope),
    }
    assert text_policy.evaluate_text_unit(record, decision)["verification_outcome"] == (
        "qualified_pass"
    )

    scope_variants = {
        "learner_id": "other-learner",
        "goal_id": "other-goal",
        "concept_id": "other-concept",
        "contract_id": "other-contract",
        "contract_version": 2,
    }
    for field, value in scope_variants.items():
        mismatched_scope = dict(scope, **{field: value})
        mismatched = {**record, "scope": mismatched_scope}
        result = text_policy.evaluate_text_unit(mismatched, decision)
        assert result["mastery_eligible"] is False, (field, result)
        assert "current_decision_scope_mismatch" in result["qualification_failures"], (
            field,
            result,
        )

    evidence_scope_mismatch = {
        **record,
        "evidence_scope": dict(scope, concept_id="other-concept"),
    }
    result = text_policy.evaluate_text_unit(evidence_scope_mismatch, decision)
    assert "evidence_scope_mismatch" in result["qualification_failures"], result

    binding_variants = (
        ("route_id_at_observation", "route-other", "verification_route_binding_mismatch"),
        ("route_version_at_observation", 2, "verification_route_binding_mismatch"),
        ("bound_route_id", "route-other", "verification_route_binding_mismatch"),
        ("bound_route_version", 2, "verification_route_binding_mismatch"),
        ("verification_task_id", "task-other", "verification_task_binding_mismatch"),
        ("bound_verification_task_id", "task-other", "verification_task_binding_mismatch"),
    )
    for field, value, failure in binding_variants:
        result = text_policy.evaluate_text_unit({**record, field: value}, decision)
        assert result["mastery_eligible"] is False, (field, result)
        assert failure in result["qualification_failures"], (field, result)

    rejected_process = text_policy.evaluate_text_unit(
        {
            "observation_kind": "teaching_process",
            "scope": dict(scope),
            "evidence_scope": dict(scope),
            "route_id_at_observation": "route-other",
            "route_version_at_observation": decision["route_version"],
            "bound_route_id": decision["route_id"],
            "bound_route_version": decision["route_version"],
        },
        decision,
    )
    assert rejected_process["qualification_status"] == "teaching_process_rejected"
    assert "verification_route_binding_mismatch" in rejected_process[
        "qualification_failures"
    ]


def test_retention_delay_must_come_from_baseline_timestamps() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-retention-derived-") as temporary:
        vault = seed(Path(temporary))
        retention = vault / "20-learner/evidence/ev-demo-a17-002.md"
        meta, body, parse_errors = tool.parse_note(retention)
        assert parse_errors == []
        assert meta["retention_delay_days"] == 7
        meta["retention_delay_days"] = 365
        tool.atomic_write_text(
            retention,
            tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n",
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any("retention_delay_days 不是时间链推导值" in item for item in errors), errors


def test_verification_and_retention_phase_sentinels_are_enforced() -> None:
    verification_mutations = {
        "delayed_retention": 0.9,
        "retention_delay_days": 1,
        "baseline_evidence_id": "ev-forged-baseline",
        "retention_task_id": "retain-forged-task",
        "scheduled_for": "2026-08-29T00:00:00+00:00",
    }
    for field, forged_value in verification_mutations.items():
        with tempfile.TemporaryDirectory(
            prefix=f"uc-demo-verification-sentinel-{field}-"
        ) as temporary:
            vault = seed(Path(temporary))
            path = vault / "20-learner/evidence/ev-demo-a17-001.md"
            meta, body, parse_errors = tool.parse_note(path)
            assert parse_errors == []
            meta[field] = forged_value
            refresh_evidence_derivations(meta)
            tool.atomic_write_text(
                path,
                tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n",
            )
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert any(
                "verification 不得保存 retention 阶段值" in error
                and f"/{field} " in error
                for error in errors
            ), (field, errors)

    retention_mutations = {
        "near_transfer": 0.9,
        "explanation_quality": "pass",
    }
    for field, forged_value in retention_mutations.items():
        with tempfile.TemporaryDirectory(
            prefix=f"uc-demo-retention-sentinel-{field}-"
        ) as temporary:
            vault = seed(Path(temporary))
            path = vault / "20-learner/evidence/ev-demo-a17-001-retention.md"
            meta, body, parse_errors = tool.parse_note(path)
            assert parse_errors == []
            meta[field] = forged_value
            refresh_evidence_derivations(meta)
            tool.atomic_write_text(
                path,
                tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n",
            )
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert any(
                f"retention {field} 必须为 not_tested" in error
                for error in errors
            ), (field, errors)

    for evidence_name in (
        "ev-demo-a17-001.md",
        "ev-demo-a17-001-retention.md",
    ):
        with tempfile.TemporaryDirectory(
            prefix="uc-demo-mastery-decision-sentinel-"
        ) as temporary:
            vault = seed(Path(temporary))
            path = vault / "20-learner/evidence" / evidence_name
            meta, body, parse_errors = tool.parse_note(path)
            assert parse_errors == []
            meta["decision_fingerprint_at_observation"] = "0" * 64
            refresh_evidence_derivations(meta)
            tool.atomic_write_text(
                path,
                tool.render_frontmatter(meta) + "\n" + body.rstrip() + "\n",
            )
            errors, _warnings, _summary = tool.validate_vault(vault)
            assert any(
                "verification/retention 只绑定 route issuance" in error
                for error in errors
            ), errors


def _retention_contract_fixture() -> tuple[dict, dict, dict]:
    scope = {
        "learner_id": "demo-a17",
        "goal_id": "goal-retention-state-machine",
        "concept_id": "kc-retention-state-machine",
        "contract_id": "mc-retention-state-machine",
        "contract_version": 1,
    }
    contract = {
        "requirements": {
            "minimum_qualified_evidence": 1,
            "required_capabilities": ["application", "near_transfer"],
            "min_near_transfer": 0.75,
            "delayed_retention": {
                "required": True,
                "min_score": 0.75,
                "min_delay_days": 7,
            },
        }
    }
    baseline = {
        "id": "ev-retention-baseline",
        **scope,
        "phase": "verification",
        "source_kind": "behavior_observation",
        "source_ref_ids": ["turn-retention-baseline"],
        "observation_validity": "valid",
        "teaching_item_id": "teach-retention",
        "verification_item_id": "verify-retention-baseline",
        "verification_unseen": True,
        "answer_revealed_before_first_attempt": False,
        "verification_task_id": "verify-retention-baseline",
        "bound_verification_task_id": "verify-retention-baseline",
        "route_id_at_observation": "route-retention",
        "route_version_at_observation": 1,
        "assistance_level": "A0",
        "independence": "independent",
        "hint_count": 0,
        "consumer_ids": [
            "verification_gate",
            "contract_recompute",
            "retention_recompute",
        ],
        "result": "pass",
        "response_correct": True,
        "immediate_performance": 0.9,
        "near_transfer": 0.85,
        "demonstrates": ["application", "near_transfer"],
        "observed_at": "2026-08-01T00:00:00+00:00",
    }
    eligible, failures = tool.evidence_mastery_eligibility(baseline)
    assert eligible, failures
    return contract, baseline, scope


def _retention_result_evidence(
    baseline: dict,
    *,
    result: str,
    response_correct: bool,
    delayed_retention: float,
) -> dict:
    evidence = {
        **{
            key: baseline[key]
            for key in (
                "learner_id",
                "goal_id",
                "concept_id",
                "contract_id",
                "contract_version",
            )
        },
        "id": f"ev-retention-{result}",
        "phase": "retention",
        "source_kind": "behavior_observation",
        "source_ref_ids": [f"turn-retention-{result}"],
        "observation_validity": "valid",
        "teaching_item_id": "teach-retention",
        "verification_item_id": f"retain-item-{result}",
        "verification_unseen": True,
        "answer_revealed_before_first_attempt": False,
        "verification_task_id": f"retain-task-{result}",
        "bound_verification_task_id": f"retain-task-{result}",
        "retention_task_id": f"retain-task-{result}",
        "route_id_at_observation": "route-retention",
        "route_version_at_observation": 1,
        "assistance_level": "A0",
        "independence": "independent",
        "hint_count": 0,
        "consumer_ids": [
            "verification_gate",
            "contract_recompute",
            "retention_recompute",
        ],
        "baseline_evidence_id": baseline["id"],
        "scheduled_for": "2026-08-08T00:00:00+00:00",
        "result": result,
        "response_correct": response_correct,
        "immediate_performance": delayed_retention,
        "delayed_retention": delayed_retention,
        "demonstrates": ["delayed_retention"],
        "observed_at": "2026-08-08T00:00:00+00:00",
    }
    eligible, failures = tool.evidence_mastery_eligibility(evidence)
    assert eligible, failures
    return evidence


def test_retention_state_machine_and_next_actions_are_exact() -> None:
    contract, baseline, _scope = _retention_contract_fixture()

    not_started = tool.evaluate_mastery_contract(
        contract,
        [(baseline["id"], baseline)],
        as_of="2026-08-01T00:00:00+00:00",
    )
    assert not_started["immediate_contract_status"] == "met", not_started
    assert not_started["retention_status"] == "not_started", not_started
    assert not_started["next_action"] == "schedule_retention", not_started

    pending = tool.evaluate_mastery_contract(
        contract,
        [(baseline["id"], baseline)],
        state_context={"scheduled_for": "2026-08-08T00:00:00+00:00"},
        as_of="2026-08-07T23:59:59+00:00",
    )
    assert pending["retention_status"] == "pending", pending
    assert pending["next_action"] == "wait_until_scheduled_for", pending
    assert pending["next_action"] not in {
        "issue_delayed_verification",
        "collect_immediate_verification",
    }

    due = tool.evaluate_mastery_contract(
        contract,
        [(baseline["id"], baseline)],
        state_context={"scheduled_for": "2026-08-08T00:00:00+00:00"},
        as_of="2026-08-08T00:00:00+00:00",
    )
    assert due["retention_status"] == "due", due
    assert due["next_action"] == "issue_delayed_verification", due

    passed_evidence = _retention_result_evidence(
        baseline,
        result="pass",
        response_correct=True,
        delayed_retention=0.82,
    )
    passed = tool.evaluate_mastery_contract(
        contract,
        [(baseline["id"], baseline), (passed_evidence["id"], passed_evidence)],
        state_context={"scheduled_for": "2026-08-08T00:00:00+00:00"},
        as_of="2026-08-08T00:00:00+00:00",
    )
    assert passed["retention_status"] == "passed_7d", passed
    assert passed["status"] == "met", passed
    assert passed["next_action"] == "none", passed

    failed_evidence = _retention_result_evidence(
        baseline,
        result="fail",
        response_correct=False,
        delayed_retention=0.4,
    )
    failed = tool.evaluate_mastery_contract(
        contract,
        [(baseline["id"], baseline), (failed_evidence["id"], failed_evidence)],
        as_of="2026-08-08T00:00:00+00:00",
    )
    assert failed["retention_status"] == "failed", failed
    assert failed["status"] == "not_met", failed
    assert failed["next_action"] == "retention_repair", failed

    conflicted_evidence = _retention_result_evidence(
        baseline,
        result="conflicted",
        response_correct=True,
        delayed_retention=0.82,
    )
    conflicted = tool.evaluate_mastery_contract(
        contract,
        [
            (baseline["id"], baseline),
            (conflicted_evidence["id"], conflicted_evidence),
        ],
        as_of="2026-08-08T00:00:00+00:00",
    )
    assert conflicted["retention_status"] == "conflicted", conflicted
    assert conflicted["status"] == "not_met", conflicted
    assert conflicted["next_action"] == "retention_repair", conflicted


def test_future_evidence_is_excluded_by_contract_as_of() -> None:
    contract, baseline, _scope = _retention_contract_fixture()
    future_retention = _retention_result_evidence(
        baseline,
        result="pass",
        response_correct=True,
        delayed_retention=0.9,
    )
    before_retention = tool.evaluate_mastery_contract(
        contract,
        [
            (baseline["id"], baseline),
            (future_retention["id"], future_retention),
        ],
        state_context={"scheduled_for": "2026-08-08T00:00:00+00:00"},
        as_of="2026-08-07T23:59:59+00:00",
    )
    assert before_retention["immediate_contract_status"] == "met"
    assert before_retention["retention_status"] == "pending"
    assert before_retention["qualified_evidence_ids"] == [baseline["id"]]
    assert before_retention["retention_evidence_ids"] == []

    at_retention = tool.evaluate_mastery_contract(
        contract,
        [
            (baseline["id"], baseline),
            (future_retention["id"], future_retention),
        ],
        state_context={"scheduled_for": "2026-08-08T00:00:00+00:00"},
        as_of=future_retention["observed_at"],
    )
    assert at_retention["status"] == "met"
    assert at_retention["retention_status"] == "passed_7d"
    assert at_retention["qualified_evidence_ids"] == [
        baseline["id"],
        future_retention["id"],
    ]


def test_teaching_process_evidence_never_satisfies_mastery() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-process-not-mastery-") as temporary:
        vault = seed(Path(temporary))
        process_note = vault / "20-learner/evidence/ev-demo-a17-003.md"
        process_meta, _body, parse_errors = tool.parse_note(process_note)
        assert parse_errors == []
        eligible, failures = tool.evidence_mastery_eligibility(process_meta)
        assert eligible is False
        assert "phase_not_verification" in failures

        contract = {
            "requirements": {
                "minimum_qualified_evidence": 1,
                "required_capabilities": ["explanation"],
                "min_near_transfer": 0.0,
                "delayed_retention": {
                    "required": False,
                    "min_score": None,
                    "min_delay_days": 0,
                },
            }
        }
        evaluation = tool.evaluate_mastery_contract(
            contract, [(process_meta["id"], process_meta)]
        )
        assert evaluation["status"] == "in_progress", evaluation
        assert evaluation["qualified_evidence_ids"] == []


def test_vault_and_text_field_consumer_maps_are_identical() -> None:
    assert tool.EVIDENCE_FIELD_CONSUMERS == text_policy.VAULT_EVIDENCE_FIELD_CONSUMERS
    assert set(tool.EVIDENCE_FIELD_CONSUMERS) == text_policy.VAULT_EVIDENCE_FIELD_NAMES
    phase_pairs = {
        "diagnostic": (
            tool.DIAGNOSTIC_FIELD_CONSUMERS,
            text_policy.DIAGNOSTIC_FIELD_CONSUMER_ALLOWLIST,
        ),
        "teaching_process": (
            tool.TEACHING_PROCESS_FIELD_CONSUMERS,
            text_policy.TEACHING_PROCESS_FIELD_CONSUMER_ALLOWLIST,
        ),
        "verification": (
            tool.VERIFICATION_FIELD_CONSUMERS,
            text_policy.VERIFICATION_FIELD_CONSUMER_ALLOWLIST,
        ),
        "retention": (
            tool.RETENTION_FIELD_CONSUMERS,
            text_policy.RETENTION_FIELD_CONSUMER_ALLOWLIST,
        ),
    }
    assert set(tool.PHASE_FIELD_CONSUMERS) == set(phase_pairs)
    assert set(text_policy.PHASE_VAULT_FIELD_CONSUMERS) == set(phase_pairs)
    for phase, (vault_map, text_map) in phase_pairs.items():
        assert vault_map == text_map, phase
        assert tool.PHASE_FIELD_CONSUMERS[phase] == vault_map
        assert text_policy.PHASE_VAULT_FIELD_CONSUMERS[phase] == text_map

    assert tool.EVIDENCE_ENVELOPE_GUARDS_BY_PHASE == (
        text_policy.EVIDENCE_ENVELOPE_GUARDS_BY_PHASE
    )
    required_envelope_fields = {
        "phase",
        "evidence_kind",
        "learner_id",
        "goal_id",
        "concept_id",
        "contract_id",
        "contract_version",
        "source_kind",
        "source_ref_ids",
        "observation_validity",
        "route_binding_id",
    }
    for phase, envelope in tool.EVIDENCE_ENVELOPE_GUARDS_BY_PHASE.items():
        assert set(envelope) == required_envelope_fields, phase
        assert all(envelope[field] for field in required_envelope_fields)
        assert envelope["phase"] == {"phase_schema_guard"}
        assert envelope["evidence_kind"] == {"phase_schema_guard"}
        assert envelope["source_kind"] == {"source_provenance_guard"}
        assert envelope["source_ref_ids"] == {"source_provenance_guard"}
        assert envelope["observation_validity"] == {
            "observation_validity_guard"
        }
        assert "route_binding_guard" in envelope["route_binding_id"]

    process_map_consumers = set().union(
        *tool.TEACHING_PROCESS_FIELD_CONSUMERS.values()
    )
    assert process_map_consumers.isdisjoint(
        {
            "mastery_recompute",
            "contract_recompute",
            "retention_recompute",
            "cost_pareto",
        }
    )
    assert tool.TEACHING_PROCESS_FIELD_CONSUMERS["observed_at"] == {
        "verification_gate",
        "feedback_selection",
        "event_identity_guard",
        "activity_selection",
        "representation_selection",
        "teaching_delivery_guard",
    }
    assert tool.TEACHING_PROCESS_FIELD_CONSUMERS["teaching_item_id"] == {
        "process_trace",
        "teaching_delivery_guard",
    }
    assert tool.TEACHING_PROCESS_FIELD_CONSUMERS[
        "observation_confidence"
    ] == {"process_evidence_gate", "representation_selection"}
    assert "representation_selection" in (
        tool.TEACHING_PROCESS_FIELD_CONSUMERS["carrier"]
    )
    assert "representation_selection" in (
        tool.TEACHING_PROCESS_FIELD_CONSUMERS["assistance_level"]
    )

    with tempfile.TemporaryDirectory(prefix="uc-demo-process-consumers-") as temporary:
        vault = seed(Path(temporary))
        process, _body, parse_errors = tool.parse_note(
            vault / "20-learner/evidence/ev-demo-a17-003.md"
        )
        assert parse_errors == []
        assert set(process["consumer_ids"]) == {
            "activity_selection",
            "event_identity_guard",
            "feedback_selection",
            "process_evidence_gate",
            "process_trace",
            "representation_selection",
            "teaching_delivery_guard",
            "verification_gate",
        }
        assert set(process["consumer_ids"]).isdisjoint(
            {"contract_recompute", "retention_recompute"}
        )
        bindings = process["field_bindings"]
        assert set(bindings).isdisjoint(
            {"independence", "near_transfer"}
        )
        assert set(bindings["observed_at"]["consumers"]) == {
            "verification_gate",
            "feedback_selection",
            "event_identity_guard",
            "activity_selection",
            "representation_selection",
            "teaching_delivery_guard",
        }
        assert set(bindings["observation_confidence"]["consumers"]) == {
            "process_evidence_gate",
            "representation_selection",
        }
        assert {
            "activity",
            "elapsed_seconds",
            "attempts",
            "hint_count",
            "assistance_level",
            "error_signature",
            "response_correct",
            "explanation_quality",
            "observed_at",
            "observation_confidence",
            "teaching_item_id",
            "teaching_delivery_fingerprint_at_observation",
            "carrier",
            "verification_unseen",
            "answer_revealed_before_first_attempt",
        }.issubset(bindings)
        for field, binding in bindings.items():
            assert set(binding["consumers"]) == (
                tool.TEACHING_PROCESS_FIELD_CONSUMERS[field]
            )


def test_resolve_uses_only_canonical_state_supported_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-canonical-window-") as temporary:
        vault = seed(Path(temporary))
        baseline = tool.resolve_active_teaching(
            vault, write=False, _include_internal=True
        )
        baseline_refs = baseline["_decision"]["response_profile_refs"]
        assert baseline_refs
        assert baseline["resolved_profile_refs"] == []

        source_path = vault / "20-learner/evidence/ev-demo-a17-001.md"
        copied_meta, copied_body, parse_errors = tool.parse_note(source_path)
        assert parse_errors == []
        copied_meta["id"] = "ev-demo-a17-001-isolated-copy"
        copied_meta["title"] = "孤立复制证据：不得进入 canonical profile"
        tool.write_note(
            vault,
            "20-learner/evidence/ev-demo-a17-001-isolated-copy.md",
            copied_meta,
            copied_body,
        )

        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "valid evidence 必须被唯一同 scope state.supported_by 消费" in item
            and copied_meta["id"] in item
            and "owners=0" in item
            for item in errors
        ), errors
        try:
            tool.resolve_active_teaching(vault, write=False)
        except tool.VaultError as exc:
            assert "owners=0" in str(exc)
        else:
            raise AssertionError("生产 resolve 不得接受孤立的 valid evidence")

        resolved = tool.resolve_active_teaching(
            vault,
            write=False,
            _skip_validation=True,
            _include_internal=True,
        )
        assert resolved["_decision"]["response_profile_refs"] == baseline_refs
        assert copied_meta["id"] not in resolved["_decision"][
            "response_profile_refs"
        ]

        state_path = vault / "20-learner/states/ks-demo-a17-kc-python-function.md"
        state_meta, state_body, state_errors = tool.parse_note(state_path)
        assert state_errors == []
        state_body = (
            state_body.rstrip()
            + f"\n- supported_by: [[{copied_meta['id']}]]\n"
        )
        tool.atomic_write_text(
            state_path,
            tool.render_frontmatter(state_meta) + "\n" + state_body,
        )
        errors, _warnings, _summary = tool.validate_vault(vault)
        assert any(
            "canonical supported evidence 重复 observation identity" in item
            and "ev-demo-a17-001" in item
            and copied_meta["id"] in item
            for item in errors
        ), errors


def test_seeded_vault_flows_through_canonical_response_adapter() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-core-interop-") as temporary:
        vault = seed(Path(temporary))
        errors, warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors
        assert warnings == [], warnings

        goal_meta, _goal_body, goal_errors = tool.parse_note(
            vault / "20-learner/goals/goal-demo-a17-recursion.md"
        )
        evidence_meta, _evidence_body, evidence_errors = tool.parse_note(
            vault / "20-learner/evidence/ev-demo-a17-001.md"
        )
        state_meta, _state_body, state_errors = tool.parse_note(
            vault / "20-learner/states/ks-demo-a17-kc-python-function.md"
        )
        assert goal_errors == [] and evidence_errors == [] and state_errors == []

        contract = next(
            item
            for item in goal_meta["mastery_contracts"]
            if item["id"] == evidence_meta["contract_id"]
            and item["version"] == evidence_meta["contract_version"]
        )
        scoped_evidence: list[tuple[str, dict]] = []
        for path in sorted((vault / "20-learner/evidence").glob("*.md")):
            candidate, _body, candidate_errors = tool.parse_note(path)
            assert candidate_errors == []
            if all(
                candidate.get(key) == evidence_meta.get(key)
                for key in (
                    "learner_id",
                    "goal_id",
                    "concept_id",
                    "contract_id",
                    "contract_version",
                )
            ):
                scoped_evidence.append((candidate["id"], candidate))
        evaluation = tool.evaluate_mastery_contract(
            contract,
            scoped_evidence,
            state_context=state_meta,
            as_of=state_meta["evaluated_at"],
            allow_synthetic_demo=True,
        )
        assert state_meta["immediate_contract_status"] == evaluation[
            "immediate_contract_status"
        ]
        assert state_meta["contract_status"] == evaluation["status"]
        assert state_meta["retention_status"] == evaluation["retention_status"]
        assert state_meta["next_action"] == evaluation["next_action"]

        scope = {
            key: evidence_meta[key]
            for key in (
                "learner_id",
                "goal_id",
                "concept_id",
                "contract_id",
                "contract_version",
            )
        }
        context_parts = dict(
            part.split("=", 1) for part in evidence_meta["context_key"].split("|")
        )
        comparison_context = {
            "domain": context_parts["domain"],
            "knowledge_kind": context_parts["knowledge_kind"],
            "target_performance": context_parts["target_performance"],
            "prior_band": context_parts["prior_band"],
            "task_difficulty": context_parts["task_difficulty"],
        }
        observation = tool.build_response_observation_from_vault(
            vault,
            evidence_meta["id"],
            as_of=state_meta["evaluated_at"],
        )
        assert observation["schema_version"] == "response-observation-v1"
        assert observation["source"]["evidence_id"] == evidence_meta["id"]
        assert observation["mastery_gate_met"] is True

        decision_context = text_context(
            concept_id=evidence_meta["concept_id"],
            contract_id=evidence_meta["contract_id"],
            contract_version=evidence_meta["contract_version"],
            route_id=evidence_meta["route_id_at_observation"],
            route_version=evidence_meta["route_version_at_observation"],
            bound_verification_task_id=evidence_meta["bound_verification_task_id"],
            evidence_refs=[evidence_meta["id"]],
            context_key=evidence_meta["context_key"],
            response_profile_refs=[evidence_meta["id"]],
            response_profile_observations=[observation],
            domain=comparison_context["domain"],
            knowledge_kind=comparison_context["knowledge_kind"],
            target_performance=comparison_context["target_performance"],
            prior_knowledge_band=comparison_context["prior_band"],
            task_difficulty=comparison_context["task_difficulty"],
            comparison_gate={
                "retention_required": evaluation["retention_required"],
                "task_difficulty": comparison_context["task_difficulty"],
            },
        )
        assert "mastery_gate_met" not in decision_context
        decision = text_policy.decide_text_activity(decision_context)
        assert decision["response_profile_refs"] == [evidence_meta["id"]]
        assert decision["profile_selection_status"] == "insufficient_alternatives"
        assert decision["route_id"] == evidence_meta["route_id_at_observation"]
        assert decision["bound_verification_task_id"] == evidence_meta[
            "bound_verification_task_id"
        ]


def test_seeded_vault_two_core_bridge_selects_emerging_profile() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-demo-two-core-bridge-") as temporary:
        vault = seed(Path(temporary))
        errors, warnings, _summary = tool.validate_vault(vault)
        assert errors == [], errors
        assert warnings == [], warnings

        goal_meta, _body, parse_errors = tool.parse_note(
            vault / "20-learner/goals/goal-demo-a17-recursion.md"
        )
        assert parse_errors == []
        contracts = {
            (item["id"], item["version"]): item
            for item in goal_meta["mastery_contracts"]
        }
        evidence_by_id: dict[str, dict] = {}
        for path in sorted((vault / "20-learner/evidence").glob("*.md")):
            meta, _body, evidence_errors = tool.parse_note(path)
            assert evidence_errors == []
            evidence_by_id[meta["id"]] = meta
        states_by_concept: dict[str, dict] = {}
        for path in sorted((vault / "20-learner/states").glob("*.md")):
            meta, _body, state_errors = tool.parse_note(path)
            assert state_errors == []
            states_by_concept[meta["concept_id"]] = meta

        historical_ids = [
            "ev-demo-a17-001",
            "ev-demo-a17-001-retention",
            "ev-demo-a17-002-baseline",
            "ev-demo-a17-002",
        ]
        observations: list[dict] = []
        for evidence_id in historical_ids:
            evidence = evidence_by_id[evidence_id]
            scope = {
                key: evidence[key]
                for key in (
                    "learner_id",
                    "goal_id",
                    "concept_id",
                    "contract_id",
                    "contract_version",
                )
            }
            scoped_evidence = [
                (item_id, item)
                for item_id, item in evidence_by_id.items()
                if all(item.get(key) == scope[key] for key in scope)
            ]
            contract = contracts[(evidence["contract_id"], evidence["contract_version"])]
            state = states_by_concept[evidence["concept_id"]]
            observation = tool.build_response_observation_from_vault(
                vault,
                evidence_id,
                as_of=state["evaluated_at"],
            )
            assert observation["profile_actionability"]["status"] == "actionable"
            assert observation["mastery_gate_met"] is True
            observations.append(observation)

        current_contract = contracts[("mc-python-call-stack", 1)]
        current_context = comparison_context_from_key(
            evidence_by_id["ev-demo-a17-003"]["context_key"]
        )
        decision = text_policy.decide_text_activity(
            text_context(
                concept_id="kc-python-call-stack",
                contract_id="mc-python-call-stack",
                contract_version=1,
                evidence_refs=historical_ids,
                context_key=evidence_by_id["ev-demo-a17-003"]["context_key"],
                response_profile_refs=historical_ids,
                response_profile_observations=observations,
                domain=current_context["domain"],
                knowledge_kind=current_context["knowledge_kind"],
                target_performance=current_context["target_performance"],
                prior_knowledge_band=current_context["prior_band"],
                task_difficulty=current_context["task_difficulty"],
                comparison_gate={
                    "retention_required": current_contract["requirements"][
                        "delayed_retention"
                    ]["required"],
                    "task_difficulty": current_context["task_difficulty"],
                },
            )
        )
        assert decision["profile_selection_status"] == "pareto_selected", decision
        assert decision["profile_selection"]["evidence_level"] == "emerging"
        assert decision["profile_selection"]["qualified_observation_count"] == 3
        assert decision["profile_selection"]["distinct_concept_count"] == 2
        assert decision["profile_selection"]["candidate_pool_observation_count"] == 4
        assert decision["profile_selection"]["selected_option"]["sample_count"] == 3
        assert decision["profile_selection"]["qualified_observation_refs"] == sorted(
            historical_ids
        )
        assert decision["profile_selection"]["selected_option"][
            "observation_refs"
        ] == sorted(
            [
                "ev-demo-a17-001",
                "ev-demo-a17-001-retention",
                "ev-demo-a17-002-baseline",
            ]
        )
        assert decision["profile_usage_status"] == "activity_only"
        assert decision["activity"] == "contrast_cases"
        assert decision["carrier"] == "text_hybrid"


def main() -> int:
    tests = [
        test_happy_path,
        test_inspect_cone_is_deterministic_and_read_only,
        test_cone_never_falls_back_to_highest_score_without_active_route,
        test_unknown_focus_input_is_null_and_unranked,
        test_route_recovery,
        test_due_retention_recovery_issues_delayed_verification,
        test_no_silent_creation,
        test_mastery_rejects_high_help,
        test_nonbehavior_canonical_sources_cannot_satisfy_mastery,
        test_mastery_contract_requires_delayed_evidence,
        test_evidence_contract_version_must_match_state,
        test_contract_cannot_omit_transfer_requirement,
        test_duplicate_evidence_cannot_satisfy_minimum_count,
        test_newer_failure_invalidates_older_mastery,
        test_retention_days_cannot_exceed_observed_delay,
        test_failed_explanation_cannot_satisfy_explanation_capability,
        test_evidence_scores_must_stay_in_unit_interval,
        test_route_checkpoint_must_be_teachable,
        test_route_cannot_reuse_state_from_another_goal_scope,
        test_route_cannot_reuse_completed_evidence_from_another_goal,
        test_focus_snapshot_must_remain_private_and_rebuildable,
        test_route_recovery_requires_unique_active_route,
        test_requires_cycle_is_rejected,
        test_title_is_not_inserted_as_html,
        test_text_hybrid_is_default_for_text_sufficient_learning,
        test_every_demo_concept_uses_text_policy_vocabulary,
        test_validator_rejects_old_text_protocol,
        test_focus_diagnosis_requires_explicit_probe_binding,
        test_diagnostic_probe_must_come_from_issuance_snapshot,
        test_diagnostic_evidence_recomputes_state_and_rejects_stale_or_forged_snapshot,
        test_first_text_failure_repairs_text_before_video,
        test_prerequisite_gap_replans_without_medium_escalation,
        test_repeated_text_failure_requires_matching_affordance_to_escalate,
        test_delivery_plan_allowlist_hides_internal_fields,
        test_process_evidence_drives_repair_delivery_and_measured_cost,
        test_measured_process_cost_changes_repair_activity_selection,
        test_process_attempt_identity_rejects_replay_but_allows_later_retry,
        test_process_event_identity_does_not_depend_on_teaching_item_id,
        test_teaching_process_rejects_unobserved_mastery_and_retention_values,
        test_only_text_carriers_count_as_process_text_variants,
        test_process_adaptation_requires_medium_or_high_observation_confidence,
        test_observed_assistance_controls_repeated_error_escalation_gate,
        test_process_support_load_changes_feedback_and_next_action,
        test_verification_task_is_revealed_only_after_accepted_process_evidence,
        test_vault_is_the_only_production_verification_opening_boundary,
        test_teaching_delivery_issuance_binds_process_exactly,
        test_failed_process_cannot_open_after_explicit_repair_decision_epoch,
        test_open_verification_requires_explanation_to_be_observed,
        test_historical_as_of_cannot_be_written_as_current_resolution,
        test_resolved_at_cannot_be_rolled_back_without_epoch_recompute,
        test_verification_item_must_equal_the_issued_task,
        test_verification_content_guard_blocks_prompt_examples_and_answers,
        test_new_term_requires_complete_grounding,
        test_complex_relation_requires_concrete_static_visual,
        test_delivery_plan_rejects_missing_core_teaching_content,
        test_delivery_plan_rejects_nested_internal_fields,
        test_delivery_plan_rejects_internal_routing_bindings,
        test_nontext_affordance_requires_auditable_reason,
        test_text_unit_requires_unseen_independent_verification,
        test_v3_selector_orders_pareto_priority_then_focus,
        test_v3_selector_refuses_scope_mix_and_unresolved_cost_shortcut,
        test_v3_selector_enforces_route_scope_and_traced_focus,
        test_v3_selector_never_compares_different_action_gate_level_or_time_scope,
        test_v3_selector_invalid_or_inconsistent_priority_never_reaches_focus,
        test_observation_update_requires_consumer_scope_source_time_and_validity,
        test_prepare_observation_update_drops_fields_without_real_consumers,
        test_phase_kind_and_mixed_phase_prepared_updates_are_rejected,
        test_issue_learning_route_extends_trusted_seed_with_route_v2,
        test_issue_learning_route_next_action_matches_resolved_teach_branch,
        test_issue_route_requires_explicit_user_cost_priority_field,
        test_issue_route_user_cost_priority_selects_real_resource_frontier,
        test_issue_route_rejects_invalid_duplicate_and_retention_priority_zero_write,
        test_issue_route_priority_never_promotes_fallback_cost_estimates,
        test_issue_route_focus_snapshot_scope_time_and_batch_are_exact,
        test_issue_route_consumes_current_stable_tie_break_focus_batch,
        test_issue_route_recomputes_predeclared_route_default_focus_batch,
        test_issue_route_rejects_mixed_focus_selection_basis_zero_write,
        test_retention_chain_head_invalidates_old_focus_until_current_batch,
        test_issue_learning_route_rolls_back_byte_exact_after_resolution_write,
        test_cross_process_issue_route_cas_allows_exactly_one_commit,
        test_cross_process_lock_timeout_is_zero_write,
        test_cross_process_failed_schedule_rollback_preserves_waiting_success,
        test_retention_schedule_open_and_append_receipt_happy_chain,
        test_retention_receipts_are_exact_immutable_safe_records,
        test_retention_binding_is_scoped_to_its_issued_baseline,
        test_retention_phase_purpose_open_receipt_and_task_reuse_guards,
        test_retention_schedule_cas_late_due_and_transaction_rollbacks,
        test_validator_rejects_one_second_future_evidence_state_and_issuance,
        test_retention_repair_uses_new_baseline_binding_task_and_schedule,
        test_route_registry_is_required_and_binds_task_and_issue_time,
        test_route_registry_hash_chain_detects_tamper_reorder_and_truncation,
        test_trusted_seed_rejects_coordinated_route_ledger_rehash,
        test_route_registry_rejects_context_snapshot_and_active_resource_drift,
        test_vault_rejects_missing_or_wrong_field_binding_for_actionable_value,
        test_source_receipts_cannot_be_forged_at_note_or_field_binding_level,
        test_response_profile_thresholds_control_activity_and_carrier,
        test_response_profile_rejects_wrong_learner_context_gate_help_and_confidence,
        test_observation_confidence_is_derived_not_caller_selected,
        test_response_adapter_rejects_source_context_claim_mismatch,
        test_response_adapter_recomputes_and_ignores_forged_contract_outcome,
        test_verification_binding_and_contract_coverage_are_enforced,
        test_text_unit_rejects_every_current_decision_binding_mismatch,
        test_retention_delay_must_come_from_baseline_timestamps,
        test_verification_and_retention_phase_sentinels_are_enforced,
        test_retention_state_machine_and_next_actions_are_exact,
        test_future_evidence_is_excluded_by_contract_as_of,
        test_teaching_process_evidence_never_satisfies_mastery,
        test_vault_and_text_field_consumer_maps_are_identical,
        test_resolve_uses_only_canonical_state_supported_evidence,
        test_seeded_vault_flows_through_canonical_response_adapter,
        test_seeded_vault_two_core_bridge_selects_emerging_profile,
    ]
    completed: list[str] = []
    for test in tests:
        test()
        completed.append(test.__name__)
    print(
        json.dumps(
            {"status": "ok", "tests": completed, "count": len(completed)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
