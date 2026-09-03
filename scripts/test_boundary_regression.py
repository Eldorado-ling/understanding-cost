#!/usr/bin/env python3
"""Boundary semantics and production fail-closed regression checks."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import vault_tool as tool


def requires(*targets: str) -> list[dict[str, str]]:
    return [{"type": "requires", "target": target} for target in targets]


class BoundaryRegressionTests(unittest.TestCase):
    def test_empty_requires_is_not_evidence_of_graph_completeness(self):
        legacy = tool.derive_boundary_assessments({"a": []}, {"a": "unknown"})["a"]
        self.assertEqual(legacy["graph_status"], "legacy_unspecified")
        self.assertEqual(legacy["next_action"], "diagnose_now")
        for coverage in ("incomplete", "unassessed"):
            result = tool.derive_boundary_assessments(
                {"a": []}, {"a": "unknown"},
                concept_metadata={"a": {"prerequisite_coverage": coverage}},
            )["a"]
            self.assertEqual(result["next_action"], "defer_unmodeled")
            self.assertEqual(result["graph_issue_ids"], ["a"])
            self.assertEqual(result["diagnostic_concept_ids"], [])
        complete = tool.derive_boundary_assessments(
            {"a": []}, {"a": "unknown"},
            concept_metadata={"a": {"prerequisite_coverage": "complete"}},
        )["a"]
        self.assertEqual(complete["graph_status"], "complete")
        self.assertEqual(complete["diagnostic_concept_ids"], ["a"])

    def test_optional_contrasts_do_not_expand_mastery_requirements(self):
        graph = {"a": [{"type": "contrasts_with", "target": "b"}], "b": []}
        mastery = {"a": "mastered", "b": "unknown"}
        optional = tool.derive_boundary_assessments(graph, mastery)["a"]
        self.assertEqual(optional["boundary_position"], "interior")
        required = tool.derive_boundary_assessments(
            graph, mastery, concept_metadata={"a": {"required_contrast_ids": ["b"]}}
        )["a"]
        self.assertEqual(required["boundary_position"], "inner_fringe")
        self.assertEqual(required["required_contrast_gap_ids"], ["b"])
        self.assertEqual(required["learner_status"], "mastered")
        self.assertEqual(required["next_action"], "exclude_mastered")

    def test_unknown_chain_targets_diagnosis_not_reteaching_guesses(self):
        result = tool.derive_boundary_assessments(
            {"a": requires("b"), "b": requires("c"), "c": []},
            {"a": "none", "b": "partial", "c": "unknown"},
        )["a"]
        self.assertEqual(result["next_action"], "defer_blocked")
        self.assertEqual(result["blocking_prerequisite_ids"], ["b"])
        self.assertEqual(result["diagnostic_concept_ids"], ["c"])
        self.assertIn("learner_prerequisite_unknown", result["reason_codes"])

    def test_missing_chain_is_graph_gap_not_learner_failure(self):
        result = tool.derive_boundary_assessments(
            {"a": requires("b"), "b": requires("missing")},
            {"a": "partial", "b": "unknown"},
        )["a"]
        self.assertEqual(result["graph_status"], "unmodeled")
        self.assertEqual(result["next_action"], "defer_unmodeled")
        self.assertEqual(result["graph_issue_ids"], ["missing"])
        self.assertEqual(result["diagnostic_concept_ids"], [])

    def test_prerequisite_coverage_on_unmastered_chain_is_consumed(self):
        result = tool.derive_boundary_assessments(
            {"a": requires("b"), "b": []}, {"a": "partial", "b": "unknown"},
            concept_metadata={"a": {"prerequisite_coverage": "complete"},
                              "b": {"prerequisite_coverage": "incomplete"}},
        )["a"]
        self.assertEqual(result["next_action"], "defer_unmodeled")
        self.assertEqual(result["graph_issue_ids"], ["b"])
        self.assertEqual(result["diagnostic_concept_ids"], [])

    def test_independent_mastery_is_not_undone_by_transitive_unknown(self):
        graph = {"a": requires("b"), "b": requires("c"), "c": []}
        results = tool.derive_boundary_assessments(
            graph, {"a": "partial", "b": "mastered", "c": "unknown"}
        )
        self.assertEqual(results["a"]["next_action"], "teach_now")
        self.assertEqual(results["a"]["diagnostic_concept_ids"], [])
        self.assertEqual(results["a"]["transitive_unknown_ids"], ["c"])
        self.assertIn("transitive_unknown_covered_by_mastered_prerequisite", results["a"]["reason_codes"])
        self.assertEqual(results["b"]["learner_status"], "mastered")
        self.assertEqual(results["b"]["next_action"], "exclude_mastered")

    def test_missing_target_graph_is_not_empty_audited_requires(self):
        result = tool.derive_boundary_assessments({}, {"a": "partial"})["a"]
        self.assertEqual(result["next_action"], "defer_unmodeled")
        self.assertEqual(result["graph_issue_ids"], ["a"])

    def _seed(self, root: Path):
        vault = root / "vault"
        tool.seed_demo(vault)
        index, errors = tool.build_index(vault)
        self.assertEqual(errors, [])
        return vault, index

    def _change_meta(self, vault: Path, index: dict, node_id: str, changes: dict):
        path = vault / index["nodes"][node_id]["path"]
        meta, body, errors = tool.parse_note(path)
        self.assertEqual(errors, [])
        meta.update(changes)
        tool.replace_note_meta(path, meta, body)

    def _sync_boundary_caches(self, vault: Path, index: dict):
        all_meta = {node_id: tool.parse_note(vault / node["path"])[0]
                    for node_id, node in index["nodes"].items()}
        state = next(item for item in all_meta.values() if item.get("type") == "state")
        assessment = tool.boundary_assessments_for_scope(
            index, all_meta, state["learner_id"], state["goal_id"]
        )
        for node_id, item in all_meta.items():
            if item.get("type") == "state":
                self._change_meta(vault, index, node_id, {
                    "boundary_position": assessment[item["concept_id"]]["boundary_position"]
                })

    def test_cone_consumes_unmodeled_state_without_claiming_learner_gap(self):
        with tempfile.TemporaryDirectory() as raw:
            vault, index = self._seed(Path(raw))
            self._change_meta(vault, index, "kc-python-base-case", {"prerequisite_coverage": "incomplete"})
            self._sync_boundary_caches(vault, index)
            errors, _, _ = tool.validate_vault(vault)
            self.assertEqual(errors, [])
            node = next(item for item in tool.load_cone_data(vault)["nodes"] if item["id"] == "kc-python-base-case")
            self.assertEqual(node["routing_action"], "defer_unmodeled")
            self.assertIn("graph_incomplete", node["reason_codes"])
            self.assertFalse(node["eligible_teaching_candidate"])

    def test_resolve_rejects_incomplete_active_graph_before_teaching(self):
        with tempfile.TemporaryDirectory() as raw:
            vault, index = self._seed(Path(raw))
            self._change_meta(vault, index, "kc-python-call-stack", {"prerequisite_coverage": "unassessed"})
            self._sync_boundary_caches(vault, index)
            before = {str(p): p.read_bytes() for p in vault.rglob("*") if p.is_file()}
            with self.assertRaisesRegex(tool.VaultError, "defer_unmodeled"):
                tool.resolve_active_teaching(vault, write=False)
            after = {str(p): p.read_bytes() for p in vault.rglob("*") if p.is_file()}
            self.assertEqual(before, after)

    def test_new_concept_metadata_is_strictly_validated(self):
        invalid_values = (
            {"prerequisite_coverage": []},
            {"required_contrast_ids": ["kc-python-function"]},
            {"required_contrast_ids": ["kc-python-recursion", "kc-python-recursion"]},
            {"required_contrast_ids": [{"bad": "shape"}]},
        )
        for invalid in invalid_values:
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as raw:
                vault, index = self._seed(Path(raw))
                self._change_meta(vault, index, "kc-python-iteration", invalid)
                errors, _, _ = tool.validate_vault(vault)
                self.assertTrue(any(next(iter(invalid)) in error for error in errors), errors)

    def test_legacy_mastered_inner_cache_remains_readable(self):
        with tempfile.TemporaryDirectory() as raw:
            vault, index = self._seed(Path(raw))
            path = vault / index["nodes"]["kc-python-iteration"]["path"]
            meta, body, _ = tool.parse_note(path)
            meta.pop("required_contrast_ids")
            meta.pop("prerequisite_coverage")
            tool.replace_note_meta(path, meta, body)
            state_id = next(node_id for node_id, node in index["nodes"].items()
                            if node.get("type") == "state" and
                            tool.parse_note(vault / node["path"])[0].get("concept_id") == "kc-python-iteration")
            self._change_meta(vault, index, state_id, {"boundary_position": "inner_fringe"})
            errors, _, _ = tool.validate_vault(vault)
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
