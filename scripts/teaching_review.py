"""Shared, in-memory concept checks for persisted and session-only teaching.

This is a bounded literal check, not an NLP assessor or proof of learning.
The CLI reads one JSON object from stdin and writes a report to stdout only.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any
import unicodedata

import text_learning as policy


def _key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def draft_terms(required_terms: list[str], content: dict[str, Any]) -> list[str]:
    """Keep required terms; allow the author to ground newly discovered terms.

Adding a definition changes the draft, not the issued route or method epoch.
It never makes a missing required definition optional.
"""
    required = policy._unique_string_list("required_terms", required_terms)
    entries = content.get("term_grounding") or []
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        raise ValueError("term_grounding 必须是定义对象数组")
    terms = list(required)
    for item in entries:
        term = policy._nonempty_string("term_grounding.term", item.get("term"))
        if term.casefold() not in {value.casefold() for value in terms}:
            terms.append(term)
    return terms


def _inventory_names(inventory: list[dict[str, Any]]) -> dict[str, set[str]]:
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("concept_inventory 必须至少交接本步目标概念，不能用空词表跳过审阅")
    names: dict[str, set[str]] = {}
    ids: set[str] = set()
    for item in inventory:
        if not isinstance(item, dict) or set(item) != {"concept_id", "title", "aliases"}:
            raise ValueError("concept_inventory 每项必须包含 concept_id、title、aliases")
        concept_id = policy._nonempty_string("concept_id", item["concept_id"])
        title = policy._nonempty_string("title", item["title"])
        aliases = policy._unique_string_list("aliases", item["aliases"])
        if concept_id in ids:
            raise ValueError("concept_inventory 的 concept_id 不得重复")
        ids.add(concept_id)
        for name in [title, *aliases]:
            names.setdefault(_key(name), set()).add(concept_id)
    return names


def _mentioned_ids(value: Any, names: dict[str, set[str]]) -> set[str]:
    """Match registered names, using longest non-overlapping literal spans.

ASCII words need identifier boundaries; Chinese matching is literal, not word
segmentation. A longer registered name does not imply its shorter substring.
"""
    if isinstance(value, dict):
        return set().union(*(_mentioned_ids(item, names) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_mentioned_ids(item, names) for item in value))
    if not isinstance(value, str):
        return set()
    text = _key(value)
    spans = []
    for name, ids in names.items():
        pattern = re.escape(name)
        if name.isascii():
            pattern = r"(?<![A-Za-z0-9_])" + pattern + r"(?![A-Za-z0-9_])"
        spans.extend((match.start(), match.end(), name, ids)
                     for match in re.finditer(pattern, text))
    accepted: list[tuple[int, int]] = []
    result: set[str] = set()
    for start, end, name, ids in sorted(spans, key=lambda span: (-(span[1] - span[0]), span[0])):
        if any(start < previous_end and previous_start < end for previous_start, previous_end in accepted):
            continue
        if len(ids) != 1:
            raise ValueError(f"概念名称 {name} 对应多个知识点；先使用唯一名称或消除歧义")
        accepted.append((start, end))
        result.update(ids)
    return result


def review_teaching_content(
    *, concept_inventory: list[dict[str, Any]], verified_concept_ids: list[str],
    required_terms: list[str], content: dict[str, Any],
) -> dict[str, Any]:
    """Reject recognized but ungrounded dependencies in the actual projection.

Production supplies the fresh brief's inventory and validated declared anchors.
In a session the Agent supplies only authorized evidence; this function cannot
authenticate that evidence. Unknown vocabulary and semantic sufficiency still
require an Agent pass over the final text before any learner sees it.
"""
    if not isinstance(content, dict) or set(content) - set(policy.USER_DELIVERY_FIELDS):
        raise ValueError("content 必须只包含用户教学字段；不要传入内部简报或 teaching_basis")
    for field in ("learning_objective", "method_label", "orientation", "explanation", "example",
                  "learner_task", "response_format", "feedback_rule", "verification_rule", "success_criteria"):
        policy._nonempty_string(field, content.get(field))
    for field, value in content.items():
        policy._validate_user_value(value, field)
    policy._validated_next_step(content.get("next_step"))
    if "medium" in content:
        policy._nonempty_string("medium", content["medium"])
    grounded = policy._validate_term_grounding(draft_terms(required_terms, content), content.get("term_grounding"))
    if any(set(item) != {"term", "what_it_is", "owner_scope", "role_here", "relation_direction"}
           for item in content.get("term_grounding") or []):
        raise ValueError("term_grounding 只能包含五项用户定义字段")
    visual = content.get("visual")
    if visual is not None:
        visual_fields = {"kind", "asset", "observation_focus", "text_equivalent", "learner_reading_task"}
        if not isinstance(visual, dict) or set(visual) != visual_fields:
            raise ValueError("visual 必须是已经投影的五项用户图示字段")
        for field, value in visual.items():
            policy._nonempty_string("visual." + field, value)
    names = _inventory_names(concept_inventory)
    catalog_ids = {item["concept_id"] for item in concept_inventory}
    available = set(policy._unique_string_list("verified_concept_ids", verified_concept_ids))
    if not available.issubset(catalog_ids):
        raise ValueError("已验证前提必须属于本步 concept_inventory")
    titles = {item["concept_id"]: item["title"] for item in concept_inventory}
    own_ids: list[set[str]] = []
    for item in grounded:
        name = _key(item["term"])
        if name not in names:
            # A local explanation need not create a persistent graph node.
            local_id = "local-term:" + name
            names[name] = {local_id}
            titles[local_id] = item["term"]
        if len(names[name]) != 1:
            raise ValueError(f"定义名称 {item['term']} 有歧义；使用唯一名称")
        own_ids.append(names[name])
    for item, self_ids in zip(grounded, own_ids):
        definitions = {key: value for key, value in item.items() if key != "term"}
        missing = _mentioned_ids(definitions, names) - available - self_ids
        if missing:
            label = "、".join(sorted(titles[concept_id] for concept_id in missing))
            raise ValueError(f"{item['term']} 的定义依赖未先落地的概念：{label}；先解释依赖或改用已知语言")
        available.update(self_ids)
    # Topic/goal headings can name a term before its definition, but still need
    # coverage in this unit. They cannot carry unexplained reasoning; only the
    # Agent's semantic pass can enforce that lead-in distinction.
    visible_text = {key: value for key, value in content.items() if key != "term_grounding"}
    if isinstance(visible_text.get("visual"), dict):
        # A path is not visible prose. Image labels need a separate Agent review;
        # observation_focus/text_equivalent/learner_reading_task are checked here.
        visible_text["visual"] = {key: value for key, value in visible_text["visual"].items() if key != "asset"}
    missing = _mentioned_ids(visible_text, names) - available
    if missing:
        label = "、".join(sorted(titles[concept_id] for concept_id in missing))
        raise ValueError(f"实际教学正文使用了未验证且未落地的概念：{label}；补最小定义或移除依赖，不得只删声明")
    return {"status": "structural_pass", "semantic_review_required": True,
            "coverage_limit": "registered_literal_names_only"}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        expected = {"concept_inventory", "verified_concept_ids", "required_terms", "content"}
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError("输入必须为 concept_inventory、verified_concept_ids、required_terms、content 四项对象")
        report = review_teaching_content(**payload)
    except (ValueError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
