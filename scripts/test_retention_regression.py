#!/usr/bin/env python3
"""Behavioral checks for evidence-backed, pre-due retention re-baselining."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

import self_test as fixtures
import vault_tool as tool


class ProactiveRetentionTests(unittest.TestCase):
    def prepare(self, root: Path) -> dict:
        return fixtures.prepare_retention_schedule(
            root, suffix="proactive-review", not_before=None
        )

    def append_review(self, root: Path, prepared: dict) -> dict:
        """Use only production issuance/delivery/open/append paths for review."""
        vault = prepared["vault"]
        resource = fixtures.add_call_stack_resource(
            vault, suffix="proactive-review-learning", duration_minutes=0.25
        )
        learning = tool.issue_route(
            vault,
            record_path=fixtures.write_learning_route_record(root, resource["id"]),
        )
        process = fixtures.append_demo_call_stack_process(
            vault, evidence_id="ev-proactive-review-process", result="pass"
        )
        baseline = fixtures.append_demo_call_stack_verification(
            vault, process=process, evidence_id="ev-proactive-review-baseline"
        )
        state, _body, errors = tool.parse_note(prepared["state_path"])
        self.assertEqual(errors, [])
        self.assertEqual(state["retention_status"], "pending")
        return {"baseline": baseline, "process": process, "state": state, "learning": learning}

    def issue_review_retention(self, root: Path, prepared: dict, review: dict) -> dict:
        resource = fixtures.add_call_stack_resource(
            prepared["vault"], suffix="proactive-review-next-retention", duration_minutes=2
        )
        return tool.issue_route(
            prepared["vault"],
            record_path=fixtures.write_retention_route_record(
                root, resource_id=resource["id"], baseline_evidence_id=review["baseline"]["id"]
            ),
        )

    def record(self, root: Path, review: dict, route: dict, *, not_before=None) -> Path:
        return fixtures.write_schedule_record(
            root, state=review["state"], baseline_evidence_id=review["baseline"]["id"],
            route_binding_id=route["binding_id"], not_before=not_before,
        )

    def test_pre_due_review_uses_fresh_baseline_and_preserves_history(self):
        with tempfile.TemporaryDirectory(prefix="uc-review-positive-") as temporary:
            root = Path(temporary)
            prepared = self.prepare(root)
            vault = prepared["vault"]
            old = prepared["schedule"]
            old_path = vault / "30-learning/retention-schedules" / f"{old['retention_schedule_id']}.md"
            old_bytes = old_path.read_bytes()
            manifest = tool.json.loads((vault / tool.MANIFEST_REL).read_text(encoding="utf-8"))
            _registry, old_events, errors = tool.load_route_binding_registry(vault, manifest)
            self.assertEqual(errors, [])
            review_at = tool.parse_iso_instant(old["committed_at"]) + timedelta(hours=1)
            with fixtures.frozen_tool_clock(review_at) as clock:
                review = self.append_review(root, prepared)
                route = self.issue_review_retention(root, prepared, review)
                result = tool.schedule_retention(vault, record_path=self.record(root, review, route))
                self.assertEqual(result["schedule_reason"], "proactive_review")
                self.assertEqual(result["supersedes_schedule_id"], old["retention_schedule_id"])
                self.assertEqual(result["baseline_evidence_id"], review["baseline"]["id"])
                self.assertNotEqual(result["retention_task_id"], old["retention_task_id"])
                self.assertGreater(tool.parse_iso_instant(result["scheduled_for"]), tool.parse_iso_instant(old["scheduled_for"]))
                self.assertEqual(old_path.read_bytes(), old_bytes)
                manifest = tool.json.loads((vault / tool.MANIFEST_REL).read_text(encoding="utf-8"))
                _registry, current_events, errors = tool.load_route_binding_registry(vault, manifest)
                self.assertEqual(errors, [])
                self.assertEqual(current_events[:len(old_events)], old_events)
                self.assertEqual(tool.validate_vault(vault)[0], [])
                # New failures must not retroactively invalidate earlier receipts.
                clock.current = tool.parse_iso_instant(result["scheduled_for"]) + timedelta(seconds=1)
                opened = tool.open_delayed_verification(vault, state_id=review["state"]["id"])
                clock.current += timedelta(seconds=1)
                fixtures.append_demo_retention_evidence(
                    vault, opened=opened, evidence_id="ev-proactive-review-later-fail", result="fail"
                )
                self.assertEqual(old_path.read_bytes(), old_bytes)
                self.assertEqual(tool.validate_vault(vault)[0], [])

    def test_existing_baseline_cannot_postpone_pending_schedule(self):
        with tempfile.TemporaryDirectory(prefix="uc-review-reused-") as temporary:
            root = Path(temporary)
            prepared = self.prepare(root)
            before = fixtures.snapshot_tree_bytes(prepared["vault"])
            record = fixtures.write_schedule_record(
                root, state=prepared["state"], baseline_evidence_id=prepared["baseline"]["id"],
                route_binding_id=prepared["retention_route"]["binding_id"], not_before=None,
            )
            with self.assertRaisesRegex(tool.VaultError, "主动复习 gate"):
                tool.schedule_retention(prepared["vault"], record_path=record)
            self.assertEqual(fixtures.snapshot_tree_bytes(prepared["vault"]), before)

    def test_process_evidence_is_not_a_review_baseline(self):
        with tempfile.TemporaryDirectory(prefix="uc-review-process-") as temporary:
            root = Path(temporary)
            prepared = self.prepare(root)
            review_at = tool.parse_iso_instant(prepared["schedule"]["committed_at"]) + timedelta(hours=1)
            with fixtures.frozen_tool_clock(review_at):
                review = self.append_review(root, prepared)
                resource = fixtures.add_call_stack_resource(
                    prepared["vault"], suffix="process-baseline-rejected", duration_minutes=2
                )
                before = fixtures.snapshot_tree_bytes(prepared["vault"])
                with self.assertRaisesRegex(tool.VaultError, "合格 pass verification"):
                    tool.issue_route(
                        prepared["vault"], record_path=fixtures.write_retention_route_record(
                            root, resource_id=resource["id"], baseline_evidence_id=review["process"]["id"]
                        ),
                    )
                self.assertEqual(fixtures.snapshot_tree_bytes(prepared["vault"]), before)

    def test_explicit_extra_postponement_and_binding_mismatch_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="uc-review-not-before-") as temporary:
            root = Path(temporary)
            prepared = self.prepare(root)
            review_at = tool.parse_iso_instant(prepared["schedule"]["committed_at"]) + timedelta(hours=1)
            with fixtures.frozen_tool_clock(review_at):
                review = self.append_review(root, prepared)
                route = self.issue_review_retention(root, prepared, review)
                before = fixtures.snapshot_tree_bytes(prepared["vault"])
                with self.assertRaisesRegex(tool.VaultError, "not_before 必须为 null"):
                    tool.schedule_retention(
                        prepared["vault"], record_path=self.record(
                            root, review, route, not_before=(review_at + timedelta(days=30)).isoformat()
                        ),
                    )
                with self.assertRaisesRegex(tool.VaultError, "同 baseline"):
                    tool.schedule_retention(
                        prepared["vault"], record_path=self.record(root, review, prepared["retention_route"]),
                    )
                self.assertEqual(fixtures.snapshot_tree_bytes(prepared["vault"]), before)

    def test_due_schedule_cannot_be_reset_by_an_earlier_review(self):
        with tempfile.TemporaryDirectory(prefix="uc-review-due-") as temporary:
            root = Path(temporary)
            prepared = self.prepare(root)
            review_at = tool.parse_iso_instant(prepared["schedule"]["committed_at"]) + timedelta(hours=1)
            with fixtures.frozen_tool_clock(review_at) as clock:
                review = self.append_review(root, prepared)
                route = self.issue_review_retention(root, prepared, review)
                clock.current = tool.parse_iso_instant(prepared["schedule"]["scheduled_for"]) + timedelta(seconds=1)
                before = fixtures.snapshot_tree_bytes(prepared["vault"])
                with self.assertRaisesRegex(tool.VaultError, "主动复习 gate"):
                    tool.schedule_retention(prepared["vault"], record_path=self.record(root, review, route))
                self.assertEqual(fixtures.snapshot_tree_bytes(prepared["vault"]), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
