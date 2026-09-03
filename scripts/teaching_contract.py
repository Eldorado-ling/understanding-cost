"""Small, agent-only handoff from a validated route to text generation.

No learner model or evidence is stored here. The Vault builds the brief from
canonical data. Issuance checks this binding, then passes the actual projection
to teaching_review; binding validation alone is not a complete content review.
"""

from __future__ import annotations

from typing import Any


def validate_teaching_basis(brief: dict[str, Any], content: dict[str, Any]) -> None:
    """Reject unsupported declared anchors and out-of-contract teaching scope.

This checks declared dependencies, not the semantics of arbitrary prose. An
agent must still review whether all load-bearing unfamiliar terms are declared.
"""
    basis = content.get("teaching_basis")
    binding_fields = ("route_binding_id", "decision_fingerprint", "brief_fingerprint")
    if not isinstance(basis, dict) or set(basis) != {"anchor_ids", "focus_capabilities", *binding_fields}:
        raise ValueError("新教学内容必须提供 teaching_basis: anchor_ids + focus_capabilities + route_binding_id + decision_fingerprint + brief_fingerprint")
    for field in binding_fields:
        if not isinstance(basis[field], str) or not basis[field] or basis[field] != brief.get(field):
            raise ValueError(f"teaching_basis.{field} 已过期或不属于当前简报；重新准备并审阅内容后再签发")
    for field in ("anchor_ids", "focus_capabilities"):
        values = basis[field]
        if (
            not isinstance(values, list)
            or any(not isinstance(item, str) or not item.strip() for item in values)
            or len(values) != len(set(values))
        ):
            raise ValueError(f"teaching_basis.{field} 必须是无重复字符串数组")
    anchors = {item["concept_id"] for item in brief["verified_anchors"]}
    if not set(basis["anchor_ids"]).issubset(anchors):
        raise ValueError("知识锚点没有同范围独立掌握证据；兴趣或接触经历不能充当推理前提")
    if not basis["focus_capabilities"] or not set(basis["focus_capabilities"]).issubset(
        set(brief["required_capabilities"])
    ):
        raise ValueError("本单元 focus_capabilities 必须是当前合同的非空能力子集")
