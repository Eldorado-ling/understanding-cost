"""Behavior tests for the compact, evidence-backed teaching handoff."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

import self_test as fixtures
import teaching_contract
import text_learning as policy
import vault_tool as tool


class TeachingBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="uc-bridge-test-")
        self.addCleanup(self.temporary.cleanup)
        self.vault = Path(self.temporary.name) / "vault"
        tool.seed_demo(self.vault)

    def test_brief_is_read_only_scoped_and_does_not_reveal_test_content(self):
        before = fixtures.snapshot_tree_bytes(self.vault)
        brief = tool.prepare_teaching_brief(self.vault)
        self.assertEqual(brief["current_concept"], "调用栈")
        intervention = tool.parse_note(self.vault / "30-learning/interventions/int-demo-a17-recursion-path.md")[0]
        self.assertEqual(brief["activity"], intervention["resolved_activity"])
        self.assertEqual(brief["resource_id"], intervention["resolved_resource_id"])
        self.assertEqual([item["concept_id"] for item in brief["verified_anchors"]], ["kc-python-function"])
        self.assertTrue(brief["verified_anchors"][0]["evidence_ids"])
        self.assertEqual(brief["cost_inputs"]["practice_feedback"]["basis"], "observed")
        self.assertEqual(brief["cost_inputs"]["core_learning"]["basis"], "estimated")
        serialized = json.dumps(brief, ensure_ascii=False)
        resource = tool.parse_note(self.vault / "30-learning/resources/res-python-call-stack-trace.md")[0]
        task = resource["verification_task"]
        for secret in [task["prompt"], *task["protected_answers"]]:
            self.assertNotIn(secret, serialized)
        self.assertEqual(fixtures.snapshot_tree_bytes(self.vault), before)

    def test_unverified_or_interesting_node_cannot_be_a_known_anchor(self):
        brief = tool.prepare_teaching_brief(self.vault)
        content = fixtures.valid_delivery_content(vault=self.vault)
        content["teaching_basis"]["anchor_ids"] = ["kc-python-stack-overflow"]
        with self.assertRaisesRegex(ValueError, "独立掌握证据"):
            teaching_contract.validate_teaching_basis(brief, content)
        content["teaching_basis"]["anchor_ids"] = ["kc-python-function"]
        teaching_contract.validate_teaching_basis(brief, content)

    def test_teaching_capabilities_cannot_drift_outside_current_contract(self):
        brief = tool.prepare_teaching_brief(self.vault)
        for values in ([], ["unrelated_animation_skill"], ["explanation", "explanation"]):
            content = fixtures.valid_delivery_content(vault=self.vault)
            content["teaching_basis"]["focus_capabilities"] = values
            with self.assertRaises(ValueError):
                teaching_contract.validate_teaching_basis(brief, content)

    def test_new_issuance_requires_valid_basis_and_hides_it_from_learner(self):
        fixtures.ensure_teachable_call_stack(self.vault, suffix="bridge-success")
        path = Path(self.temporary.name) / "content.json"
        content = fixtures.valid_delivery_content(vault=self.vault)
        invalid = copy.deepcopy(content)
        invalid.pop("teaching_basis")
        tool.atomic_write_text(path, json.dumps(invalid, ensure_ascii=False))
        before = fixtures.snapshot_tree_bytes(self.vault)
        with self.assertRaisesRegex(tool.VaultError, "teaching_basis"):
            tool.issue_teaching_delivery(self.vault, content_path=path)
        self.assertEqual(fixtures.snapshot_tree_bytes(self.vault), before)
        tool.atomic_write_text(path, json.dumps(content, ensure_ascii=False))
        result = tool.issue_teaching_delivery(self.vault, content_path=path)
        self.assertNotIn("teaching_basis", result["delivery_plan"])
        self.assertEqual(tool.validate_vault(self.vault)[0], [])

    def test_prepare_and_issue_share_persisted_epoch_and_stable_brief(self):
        brief = tool.prepare_teaching_brief(self.vault)
        self.assertEqual(brief, tool.prepare_teaching_brief(self.vault))
        self.assertEqual(brief["routing_action"], "diagnose_now")
        selected = next(node for node in tool.load_cone_data(self.vault)["nodes"] if node["candidate"])
        self.assertEqual(brief["routing_action"], selected["routing_action"])
        self.assertEqual(brief["diagnostic_probe"]["id"], selected["probe_id"])
        self.assertEqual(brief["diagnostic_probe"]["id"], "probe-python-call-stack-faded-v1")
        self.assertIn("process_next_action", brief)
        self.assertNotIn("next_action", brief)
        path = Path(self.temporary.name) / "bound-content.json"
        content = fixtures.valid_delivery_content(vault=self.vault)
        tool.atomic_write_text(path, json.dumps(content, ensure_ascii=False))
        before = fixtures.snapshot_tree_bytes(self.vault)
        with self.assertRaisesRegex(tool.VaultError, "diagnose_now"):
            tool.issue_teaching_delivery(self.vault, content_path=path)
        self.assertEqual(fixtures.snapshot_tree_bytes(self.vault), before)

    def test_real_diagnosis_then_fresh_route_allows_consistent_teaching(self):
        fixtures.ensure_teachable_call_stack(self.vault, suffix="bridge-real-diagnosis")
        brief = tool.prepare_teaching_brief(self.vault)
        self.assertEqual(brief["routing_action"], "teach_now")
        self.assertIsNone(brief["diagnostic_probe"])
        path = Path(self.temporary.name) / "bound-teaching-content.json"
        content = fixtures.valid_delivery_content(vault=self.vault)
        tool.atomic_write_text(path, json.dumps(content, ensure_ascii=False))
        issued = tool.issue_teaching_delivery(self.vault, content_path=path)
        self.assertEqual(issued["process_binding"]["activity"], brief["activity"])
        self.assertEqual(issued["process_binding"]["route_binding_id"], brief["route_binding_id"])
        self.assertEqual(issued["process_binding"]["decision_fingerprint_at_observation"], brief["decision_fingerprint"])

    def test_new_process_invalidates_draft_even_when_decision_epoch_is_preserved(self):
        fixtures.ensure_teachable_call_stack(self.vault, suffix="brief-stale-draft")
        before_brief = tool.prepare_teaching_brief(self.vault)
        content = fixtures.valid_delivery_content(vault=self.vault)
        fixtures.append_demo_call_stack_process(
            self.vault, evidence_id="ev-brief-process-after-draft", result="fail"
        )
        after_brief = tool.prepare_teaching_brief(self.vault)
        self.assertEqual(before_brief["decision_fingerprint"], after_brief["decision_fingerprint"])
        self.assertNotEqual(before_brief["brief_fingerprint"], after_brief["brief_fingerprint"])
        self.assertEqual(before_brief["activity"], after_brief["activity"])
        intervention = tool.parse_note(self.vault / "30-learning/interventions/int-demo-a17-recursion-path.md")[0]
        self.assertEqual(after_brief["feedback_rule"], intervention["resolved_process_feedback_rule"])
        self.assertEqual(after_brief["process_next_action"], intervention["resolved_process_next_action"])
        self.assertEqual(after_brief["cost_inputs"]["practice_feedback"]["value"],
                         intervention["resolved_cost_vector"]["practice_feedback"])
        path = Path(self.temporary.name) / "stale-content.json"
        tool.atomic_write_text(path, json.dumps(content, ensure_ascii=False))
        before = fixtures.snapshot_tree_bytes(self.vault)
        with self.assertRaisesRegex(tool.VaultError, "brief_fingerprint"):
            tool.issue_teaching_delivery(self.vault, content_path=path)
        self.assertEqual(fixtures.snapshot_tree_bytes(self.vault), before)
        fresh_content = fixtures.valid_delivery_content(vault=self.vault)
        tool.atomic_write_text(path, json.dumps(fresh_content, ensure_ascii=False))
        fresh_issued = tool.issue_teaching_delivery(self.vault, content_path=path)
        self.assertEqual(fresh_issued["process_binding"]["activity"], after_brief["activity"])
        self.assertEqual(fresh_issued["delivery_plan"]["feedback_rule"],
                         policy.PROCESS_FEEDBACK_RULE_PUBLIC[after_brief["feedback_rule"]])
        tool.resolve_active_teaching(self.vault, write=True)
        resolved_brief = tool.prepare_teaching_brief(self.vault)
        self.assertNotEqual(resolved_brief["decision_fingerprint"], after_brief["decision_fingerprint"])
        self.assertNotEqual(resolved_brief["activity"], after_brief["activity"])

    def test_all_binding_fields_are_required_and_cannot_be_forged(self):
        brief = tool.prepare_teaching_brief(self.vault)
        for field in ("route_binding_id", "decision_fingerprint", "brief_fingerprint"):
            content = fixtures.valid_delivery_content(vault=self.vault)
            content["teaching_basis"][field] = "unrelated-binding"
            with self.assertRaisesRegex(ValueError, field):
                teaching_contract.validate_teaching_basis(brief, content)

    def test_brief_rejects_reserved_task_copied_into_source_question(self):
        index, _ = tool.build_index(self.vault)
        goal_path = self.vault / index["nodes"]["goal-demo-a17-recursion"]["path"]
        goal, body, _ = tool.parse_note(goal_path)
        resource = tool.parse_note(self.vault / "30-learning/resources/res-python-call-stack-faded.md")[0]
        goal["source_question"] = resource["verification_task"]["prompt"]
        tool.replace_note_meta(goal_path, goal, body)
        before = fixtures.snapshot_tree_bytes(self.vault)
        with self.assertRaisesRegex(tool.VaultError, "保留验证内容"):
            tool.prepare_teaching_brief(self.vault)
        self.assertEqual(fixtures.snapshot_tree_bytes(self.vault), before)

    def test_declared_terms_cannot_depend_on_not_yet_grounded_terms(self):
        def grounding(term, what):
            return {"term": term, "what_it_is": what, "owner_scope": "模型内部",
                    "role_here": "控制画面", "relation_direction": "控制项影响图形"}
        terms = [grounding("参数", "用于改变关键帧的数值"), grounding("关键帧", "保存指定状态的记录")]
        with self.assertRaisesRegex(policy.TextPolicyError, "尚未落地"):
            policy._validate_term_grounding(["参数", "关键帧"], terms)
        reordered = [terms[1], terms[0]]
        self.assertEqual(policy._validate_term_grounding(["参数", "关键帧"], reordered), reordered)

    def test_ascii_term_next_to_chinese_is_still_a_declared_dependency(self):
        terms = [
            {"term": "返回值", "what_it_is": "x表示输入", "owner_scope": "函数",
             "role_here": "作为结果", "relation_direction": "计算后返回"},
            {"term": "x", "what_it_is": "一个输入数值", "owner_scope": "函数",
             "role_here": "参与计算", "relation_direction": "输入到计算"},
        ]
        with self.assertRaisesRegex(policy.TextPolicyError, "尚未落地"):
            policy._validate_term_grounding(["返回值", "x"], terms)
        # An x embedded in the unrelated ASCII identifier max is not a match.
        terms[0]["what_it_is"] = "max 表示求最大数的操作"
        self.assertEqual(policy._validate_term_grounding(["返回值", "x"], terms), terms)


if __name__ == "__main__":
    unittest.main()
