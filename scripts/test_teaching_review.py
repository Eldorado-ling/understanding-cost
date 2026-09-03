"""Behavioral regression tests for actual-prose and session-only concept review."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import self_test as fixtures
from teaching_review import review_teaching_content
import vault_tool as tool


def definition(term, what="一种比较可选下一步的办法"):
    return {"term": term, "what_it_is": what, "owner_scope": "当前学习任务",
            "role_here": "决定先尝试哪一步", "relation_direction": "已有依据影响选择顺序"}


def session_case():
    content = fixtures.valid_delivery_content()
    content.pop("teaching_basis")
    content.update(learning_objective="说清这个排序办法的用途", explanation="聚焦圆锥用于比较剩余可学步骤。")
    return {
        "concept_inventory": [
            {"concept_id": "cone", "title": "聚焦圆锥", "aliases": ["Focus Cone"]},
            {"concept_id": "pareto", "title": "帕累托比较", "aliases": ["Pareto"]},
        ],
        "verified_concept_ids": [], "required_terms": [], "content": content,
    }


class ActualProseReviewTests(unittest.TestCase):
    def test_empty_handoff_is_not_a_successful_review(self):
        payload = session_case()
        payload["concept_inventory"] = []
        with self.assertRaisesRegex(ValueError, "空词表"):
            review_teaching_content(**payload)

    def test_omitting_declared_terms_does_not_hide_registered_concept(self):
        with self.assertRaisesRegex(ValueError, "实际教学正文.*聚焦圆锥"):
            review_teaching_content(**session_case())

    def test_grounded_alias_covers_concept_and_unused_neighbor_is_not_a_lesson(self):
        payload = session_case()
        payload["content"]["term_grounding"] = [definition("Focus Cone")]
        result = review_teaching_content(**payload)
        self.assertEqual(result["status"], "structural_pass")
        self.assertTrue(result["semantic_review_required"])

    def test_english_alias_next_to_chinese_is_checked(self):
        payload = session_case()
        payload["content"]["explanation"] = "由FOCUS CONE决定尝试顺序。"
        with self.assertRaisesRegex(ValueError, "聚焦圆锥"):
            review_teaching_content(**payload)

    def test_false_claim_of_existing_understanding_does_not_prove_an_anchor(self):
        payload = session_case()
        payload["content"]["explanation"] = "根据你已经理解的聚焦圆锥，直接看这个结果。"
        with self.assertRaisesRegex(ValueError, "未验证且未落地"):
            review_teaching_content(**payload)

    def test_verified_anchor_is_usable_but_cannot_be_outside_inventory(self):
        payload = session_case()
        payload["verified_concept_ids"] = ["cone"]
        review_teaching_content(**payload)
        payload["verified_concept_ids"] = ["unknown-id"]
        with self.assertRaisesRegex(ValueError, "本步"):
            review_teaching_content(**payload)

    def test_definition_cannot_hide_an_undeclared_registered_dependency(self):
        payload = session_case()
        payload["content"]["term_grounding"] = [definition("聚焦圆锥", "经过Pareto之后采用的办法")]
        with self.assertRaisesRegex(ValueError, "未先落地.*帕累托比较"):
            review_teaching_content(**payload)

    def test_alias_dependency_order_is_checked_even_if_spelling_differs(self):
        payload = session_case()
        first = definition("聚焦圆锥", "经过Pareto之后采用的办法")
        second = definition("帕累托比较", "去掉每方面都不更好且至少一方面更差的办法")
        payload["content"]["term_grounding"] = [first, second]
        with self.assertRaisesRegex(ValueError, "未先落地"):
            review_teaching_content(**payload)
        payload["content"]["term_grounding"] = [second, first]
        review_teaching_content(**payload)

    def test_obvious_bad_definitions_fail_through_shared_review(self):
        for what in ("聚焦圆锥就是聚焦圆锥", "不知道", " "):
            with self.subTest(what=what):
                payload = session_case()
                payload["content"]["term_grounding"] = [definition("聚焦圆锥", what)]
                with self.assertRaises(ValueError):
                    review_teaching_content(**payload)

    def test_required_term_cannot_be_dropped_from_draft(self):
        payload = session_case()
        payload["verified_concept_ids"] = ["cone"]
        payload["required_terms"] = ["必须补的词"]
        with self.assertRaisesRegex(ValueError, "term_grounding"):
            review_teaching_content(**payload)

    def test_required_term_keeps_original_name_even_when_prose_can_use_alias(self):
        payload = session_case()
        payload["required_terms"] = ["聚焦圆锥"]
        payload["content"]["term_grounding"] = [definition("Focus Cone")]
        with self.assertRaisesRegex(ValueError, "逐项覆盖"):
            review_teaching_content(**payload)
        payload["content"]["term_grounding"] = [definition("聚焦圆锥")]
        payload["content"]["explanation"] = "使用Focus Cone选下一步。"
        review_teaching_content(**payload)

    def test_longer_name_does_not_inherit_short_substring_or_ascii_identifier(self):
        payload = session_case()
        payload["concept_inventory"] = [
            {"concept_id": "stack", "title": "调用栈", "aliases": []},
            {"concept_id": "stack-overflow", "title": "调用栈溢出", "aliases": []},
            {"concept_id": "x", "title": "x", "aliases": []},
        ]
        payload["verified_concept_ids"] = ["stack-overflow"]
        payload["content"]["explanation"] = "调用栈溢出与max相互无关。"
        review_teaching_content(**payload)

    def test_ambiguous_alias_is_not_silently_assigned_to_known_concept(self):
        payload = session_case()
        payload["concept_inventory"][1]["aliases"].append("Focus Cone")
        payload["content"]["explanation"] = "使用 Focus Cone。"
        payload["verified_concept_ids"] = ["cone"]
        with self.assertRaisesRegex(ValueError, "对应多个"):
            review_teaching_content(**payload)

    def test_final_example_task_and_visual_text_are_scanned(self):
        for field in ("example", "learner_task", "orientation", "visual"):
            with self.subTest(field=field):
                payload = session_case()
                payload["verified_concept_ids"] = ["cone"]
                payload["content"][field] = (
                    {"kind": "relation_diagram", "asset": "diagram.png", "text_equivalent": "先做Pareto。",
                     "observation_focus": "看箭头", "learner_reading_task": "解释箭头方向"}
                    if field == "visual" else "先做Pareto。"
                )
                with self.assertRaisesRegex(ValueError, "帕累托比较"):
                    review_teaching_content(**payload)

    def test_session_content_rejects_nested_private_inventory(self):
        for field in ("concept_inventory", "verified_concept_ids", "required_terms", "terms_to_ground"):
            payload = session_case()
            payload["content"]["next_step"] = {"instruction": "继续", "when": None, field: []}
            with self.assertRaisesRegex(ValueError, "内部字段"):
                review_teaching_content(**payload)

    def test_session_content_cannot_hide_text_in_unprojected_nested_fields(self):
        payload = session_case()
        payload["verified_concept_ids"] = ["cone"]
        payload["content"]["next_step"] = {"instruction": "继续", "when": None, "extra": "Pareto"}
        with self.assertRaises(ValueError):
            review_teaching_content(**payload)
        payload["content"].pop("next_step")
        payload["content"]["term_grounding"] = [{**definition("聚焦圆锥"), "extra": "Pareto"}]
        with self.assertRaisesRegex(ValueError, "五项用户定义字段"):
            review_teaching_content(**payload)

    def test_unregistered_vocabulary_is_explicitly_outside_structural_proof(self):
        payload = session_case()
        payload["content"]["explanation"] = "由某个未登记的数学模型决定。"
        result = review_teaching_content(**payload)
        self.assertEqual(result["coverage_limit"], "registered_literal_names_only")
        self.assertTrue(result["semantic_review_required"])

    def test_cli_has_same_rejection_and_no_files_in_session_directory(self):
        script = Path(__file__).with_name("teaching_review.py")
        with tempfile.TemporaryDirectory(prefix="uc-session-review-") as directory:
            for valid in (False, True):
                payload = session_case()
                if valid:
                    payload["content"]["term_grounding"] = [definition("聚焦圆锥")]
                result = subprocess.run(
                    [sys.executable, "-B", "-X", "utf8", str(script)],
                    input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                    text=True, encoding="utf-8", cwd=directory, timeout=20,
                )
                self.assertEqual(result.returncode, 0 if valid else 1, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "structural_pass" if valid else "blocked")
                self.assertEqual(list(Path(directory).iterdir()), [])


class IssuanceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="uc-prose-issue-")
        self.addCleanup(self.temporary.cleanup)
        self.vault = Path(self.temporary.name) / "vault"
        tool.seed_demo(self.vault)
        fixtures.ensure_teachable_call_stack(self.vault, suffix="prose-review")

    def test_brief_inventory_is_derived_from_current_graph_not_authors_terms(self):
        brief = tool.prepare_teaching_brief(self.vault)
        self.assertEqual(brief["terms_to_ground"], [])
        self.assertEqual({item["title"] for item in brief["concept_inventory"]}, {"调用栈", "函数调用", "栈溢出"})

    def test_real_issuance_rejects_omission_without_writes_then_accepts_grounding(self):
        content = fixtures.valid_delivery_content(vault=self.vault)
        content["explanation"] = "调用栈保存函数调用结束后需要返回的位置。"
        content["teaching_basis"]["anchor_ids"] = ["kc-python-function"]
        path = Path(self.temporary.name) / "draft.json"
        tool.atomic_write_text(path, json.dumps(content, ensure_ascii=False))
        before = fixtures.snapshot_tree_bytes(self.vault)
        with self.assertRaisesRegex(tool.VaultError, "实际教学正文.*调用栈"):
            tool.issue_teaching_delivery(self.vault, content_path=path)
        self.assertEqual(fixtures.snapshot_tree_bytes(self.vault), before)
        content["term_grounding"] = [{
            "term": "调用栈", "what_it_is": "记录正在执行和暂停等待的函数调用的顺序表",
            "owner_scope": "程序运行时维护", "role_here": "保存当前操作结束后要回到的位置",
            "relation_direction": "新调用登记在最上面，结束时移除，并回到下面等待的调用",
        }]
        tool.atomic_write_text(path, json.dumps(content, ensure_ascii=False))
        issued = tool.issue_teaching_delivery(self.vault, content_path=path)
        self.assertEqual(issued["delivery_plan"]["term_grounding"], content["term_grounding"])
        self.assertNotIn("concept_inventory", issued["delivery_plan"])
        self.assertNotIn("teaching_basis", issued["delivery_plan"])
        self.assertEqual(tool.validate_vault(self.vault)[0], [])

    def test_known_graph_node_still_requires_the_validated_declared_anchor(self):
        content = fixtures.valid_delivery_content(vault=self.vault)
        content["explanation"] = "从函数调用继续。"
        path = Path(self.temporary.name) / "anchor-draft.json"
        tool.atomic_write_text(path, json.dumps(content, ensure_ascii=False))
        before = fixtures.snapshot_tree_bytes(self.vault)
        with self.assertRaisesRegex(tool.VaultError, "未验证且未落地.*函数调用"):
            tool.issue_teaching_delivery(self.vault, content_path=path)
        self.assertEqual(fixtures.snapshot_tree_bytes(self.vault), before)
        content["teaching_basis"]["anchor_ids"] = ["kc-python-function"]
        tool.atomic_write_text(path, json.dumps(content, ensure_ascii=False))
        tool.issue_teaching_delivery(self.vault, content_path=path)


if __name__ == "__main__":
    unittest.main()
