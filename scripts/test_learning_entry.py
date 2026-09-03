"""Behavioral regressions for explicit, session-only learning-data choices."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import learning_entry as entry
import vault_tool as tool


@contextlib.contextmanager
def no_filesystem_access():
    """A failed consent/scope gate must not even inspect user path metadata."""
    with contextlib.ExitStack() as stack:
        for name in ("resolve", "stat", "lstat", "open", "read_text", "read_bytes", "mkdir"):
            stack.enter_context(patch.object(Path, name, side_effect=AssertionError("unexpected filesystem access: " + name)))
        stack.enter_context(patch.object(entry.os, "walk", side_effect=AssertionError("unexpected walk")))
        stack.enter_context(patch.object(tool, "vault_transaction_lock", side_effect=AssertionError("unexpected lock")))
        yield


def run_cli(arguments):
    output = io.StringIO()
    errors = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        code = tool.main(arguments)
    return code, json.loads(output.getvalue() or errors.getvalue())


class LearningEntryPlanTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.gettempdir()) / "uc-entry-unused-scope"

    def plan(self, mode="use_existing", **kwargs):
        return entry.build_entry_plan(mode, "user-message-17", str(self.root), **kwargs)

    def test_missing_choice_only_asks_three_options_without_path_access(self):
        with no_filesystem_access():
            result = entry.build_entry_plan(data_root=str(self.root))
        self.assertEqual(result["next_action"], "ask_data_mode")
        self.assertEqual(result["user_prompt"], entry.CHOICE_QUESTION)
        self.assertIsNone(result["data_root"])
        self.assertFalse(result["can_read_personal_data"])
        self.assertFalse(result["can_write_personal_data"])

    def test_all_modes_need_a_specific_confirmation_reference(self):
        for mode in entry.DATA_MODES:
            for reference in (None, "", " ", "yes", "确认", "TODO", "<user-message>"):
                with self.subTest(mode=mode, reference=reference), no_filesystem_access():
                    result = entry.build_entry_plan(mode, reference, str(self.root))
                self.assertEqual(result["next_action"], "ask_mode_confirmation")
                self.assertFalse(result["can_read_personal_data"])

    def test_modes_have_different_next_actions_but_no_measured_boundary(self):
        expected = {
            "create_boundary": ("diagnose_and_create_boundary", True, True),
            "use_existing": ("review_existing_boundary", True, False),
            "no_personal_data": ("local_boundary_check", False, False),
        }
        for mode, (action, can_read, can_write) in expected.items():
            root = None if mode == "no_personal_data" else str(self.root)
            with self.subTest(mode=mode), no_filesystem_access():
                result = entry.build_entry_plan(mode, "user-message-17", root)
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["next_action"], action)
            self.assertEqual(result["can_read_personal_data"], can_read)
            self.assertEqual(result["can_write_personal_data"], can_write)
            self.assertEqual(result["boundary_status"], "not_assessed")
            self.assertTrue(result["session_only"])

    def test_personal_data_modes_require_precise_absolute_scope(self):
        for mode in ("create_boundary", "use_existing"):
            for root in (None, "", "relative/vault", str(self.root / ".." / "other"), self.root.anchor):
                with self.subTest(mode=mode, root=root), no_filesystem_access():
                    result = entry.build_entry_plan(mode, "user-message-17", root)
                self.assertEqual(result["next_action"], "ask_data_scope")
                self.assertIsNone(result["data_root"])

    def test_invalid_modes_are_not_inferred(self):
        for mode in ("auto", "", "2", "USE_EXISTING"):
            with self.subTest(mode=mode), no_filesystem_access():
                result = entry.build_entry_plan(mode, "user-message-17", self.root)
            self.assertEqual(result["status"], "blocked")

    def test_existing_write_needs_its_own_non_ambiguous_reference(self):
        readonly = self.plan()
        self.assertFalse(readonly["can_write_personal_data"])
        for reference in ("", "yes", "确认"):
            result = self.plan(write_confirmation_ref=reference)
            self.assertEqual(result["next_action"], "ask_write_confirmation")
            self.assertFalse(result["can_write_personal_data"])
        writable = self.plan(write_confirmation_ref="user-message-20-write-permission")
        self.assertTrue(writable["can_write_personal_data"])

    def test_no_personal_data_rejects_root_or_write_permission(self):
        for kwargs in ({"data_root": str(self.root)}, {"data_root": ""},
                       {"write_confirmation_ref": "user-message-20"}):
            with self.subTest(kwargs=kwargs), no_filesystem_access():
                result = entry.build_entry_plan("no_personal_data", "user-message-19", **kwargs)
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["can_read_personal_data"])

    def test_new_choice_cannot_reuse_previous_root_or_permissions(self):
        first = self.plan("create_boundary")
        self.assertEqual(first["status"], "ready")
        second = entry.build_entry_plan("use_existing", "user-message-20")
        third = entry.build_entry_plan("no_personal_data", "user-message-21")
        fourth = entry.build_entry_plan()
        self.assertEqual(second["next_action"], "ask_data_scope")
        self.assertIsNone(third["data_root"])
        self.assertFalse(third["can_write_personal_data"])
        self.assertEqual(fourth["next_action"], "ask_data_mode")

    def test_guard_blocks_missing_choice_no_data_readonly_and_init_before_io(self):
        cases = [
            (entry.build_entry_plan(), {}, "entry_not_confirmed"),
            (entry.build_entry_plan("no_personal_data", "user-message-19"), {}, "personal_data_disabled"),
            (self.plan(), {"write": True}, "readonly_database"),
            (self.plan(write_confirmation_ref="user-message-20"), {"initialize": True}, "existing_database_no_init"),
        ]
        for plan, kwargs, expected in cases:
            with self.subTest(expected=expected), no_filesystem_access():
                with self.assertRaises(entry.EntryGateError) as blocked:
                    entry.guard_operation(plan, self.root, **kwargs)
            self.assertEqual(blocked.exception.code, expected)

    def test_mismatched_or_relative_target_is_blocked_before_io(self):
        for target in (self.root.parent, self.root / "child", "relative"):
            with self.subTest(target=target), no_filesystem_access():
                with self.assertRaises(entry.EntryGateError) as blocked:
                    entry.guard_operation(self.plan(), target)
            self.assertEqual(blocked.exception.code, "data_scope_mismatch")

    def test_extra_input_and_output_paths_must_stay_inside_confirmed_scope(self):
        with no_filesystem_access():
            with self.assertRaises(entry.EntryGateError) as blocked:
                entry.guard_operation(self.plan("create_boundary"), self.root,
                                      extra_paths=(self.root.parent / "external.json",))
        self.assertEqual(blocked.exception.code, "file_outside_data_scope")

    def test_resolved_alias_is_rejected(self):
        with patch.object(Path, "resolve", return_value=self.root.parent / "elsewhere"):
            with self.assertRaises(entry.EntryGateError) as blocked:
                entry.guard_operation(self.plan(), self.root)
        self.assertEqual(blocked.exception.code, "linked_data_scope")

    def test_symbolic_links_and_windows_reparse_points_are_rejected(self):
        infos = [SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0),
                 SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)]
        for info in infos:
            with self.subTest(info=info), patch.object(Path, "lstat", return_value=info):
                with self.assertRaises(entry.EntryGateError) as blocked:
                    entry._reject_link(self.root)
            self.assertEqual(blocked.exception.code, "linked_data_scope")

    def test_linked_parent_is_rejected_before_resolving_or_inspecting_child(self):
        visited = []
        parent = self.root.parent

        def fake_lstat(path):
            visited.append(path)
            return SimpleNamespace(st_mode=stat.S_IFLNK if path == parent else stat.S_IFDIR,
                                   st_file_attributes=0)

        with patch.object(Path, "lstat", fake_lstat), patch.object(
            Path, "resolve", side_effect=AssertionError("must not resolve through linked parent")
        ):
            with self.assertRaises(entry.EntryGateError) as blocked:
                entry.guard_operation(self.plan(), self.root)
        self.assertEqual(blocked.exception.code, "linked_data_scope")
        self.assertEqual(visited[-1], parent)
        self.assertNotIn(self.root, visited)


class LearningEntryCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="uc-learning-entry-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.vault = self.root / "vault"

    def flags(self, mode="use_existing", *, write=False):
        arguments = ["--data-mode", mode, "--confirmation-ref", "user-message-test-1"]
        if mode != "no_personal_data":
            arguments += ["--data-root", str(self.vault)]
        if write:
            arguments += ["--write-confirmation-ref", "user-message-test-2-write"]
        return arguments

    def commands(self):
        inputs = ["--record", str(self.vault / "input.json")]
        return [
            ["init", "--learner-id", "test-learner"], ["validate"], ["rebuild-index"],
            ["recover-learning-route"], ["resolve-teaching"], ["resolve-teaching", "--dry-run"],
            ["prepare-teaching"], ["issue-teaching", "--content", str(self.vault / "content.json")],
            ["issue-route", *inputs], ["schedule-retention", *inputs],
            ["open-delayed-verification", "--state-id", "state-test"],
            ["append-evidence", *inputs], ["open-verification", "--process-evidence-id", "evidence-test"],
            ["inspect-cone"], ["export-cone", "--output", str(self.vault / "cone.html")],
        ]

    def test_cli_no_argument_entry_only_returns_question(self):
        with no_filesystem_access():
            code, result = run_cli(["learning-entry"])
        self.assertEqual(code, 0)
        self.assertEqual(result["next_action"], "ask_data_mode")

    def test_cli_all_user_data_commands_block_before_reads_writes_and_locks(self):
        for command in self.commands():
            with self.subTest(command=command[0]), no_filesystem_access():
                code, result = run_cli([*command, "--vault", str(self.vault)])
            self.assertEqual(code, 2)
            self.assertEqual(result["next_action"], "ask_data_mode")

    def test_cli_no_data_mode_blocks_every_vault_command_before_io(self):
        for command in self.commands():
            with self.subTest(command=command[0]), no_filesystem_access():
                code, result = run_cli([*command, "--vault", str(self.vault), *self.flags("no_personal_data")])
            self.assertEqual(code, 2)
            self.assertEqual(result["reason"], "personal_data_disabled")

    def test_cli_missing_scope_does_not_fall_back_to_vault_argument(self):
        with no_filesystem_access():
            code, result = run_cli(["validate", "--vault", str(self.vault),
                                    "--data-mode", "use_existing", "--confirmation-ref", "user-message-1"])
        self.assertEqual(code, 2)
        self.assertEqual(result["next_action"], "ask_data_scope")

    def test_cli_existing_default_rejects_writers_including_exports(self):
        for command in (["init", "--learner-id", "test-learner"], ["resolve-teaching"],
                        ["rebuild-index"], ["export-cone", "--output", str(self.vault / "cone.html")]):
            with self.subTest(command=command[0]), no_filesystem_access():
                code, result = run_cli([*command, "--vault", str(self.vault), *self.flags()])
            self.assertEqual(code, 2)
            self.assertIn(result["reason"], {"readonly_database", "existing_database_no_init"})

    def test_cli_existing_write_permission_does_not_allow_initialization(self):
        with no_filesystem_access():
            code, result = run_cli(["init", "--vault", str(self.vault), "--learner-id", "test-learner",
                                    *self.flags(write=True)])
        self.assertEqual(code, 2)
        self.assertEqual(result["reason"], "existing_database_no_init")

    def test_cli_explicit_create_initializes_only_selected_new_database(self):
        code, result = run_cli(["init", "--vault", str(self.vault), "--learner-id", "test-learner",
                               *self.flags("create_boundary")])
        self.assertEqual(code, 0, result)
        self.assertEqual(result["status"], "created")
        self.assertTrue((self.vault / tool.MANIFEST_REL).is_file())
        self.assertEqual([item.name for item in self.root.iterdir()], ["vault"])
        meta, body, _ = tool.parse_note(self.vault / "20-learner/usr-test-learner.md")
        self.assertIn("尚未采集", body)
        self.assertNotIn("mastered", meta)

    def test_cli_missing_existing_database_is_not_created(self):
        code, result = run_cli(["validate", "--vault", str(self.vault), *self.flags()])
        self.assertEqual(code, 2)
        self.assertEqual(result["reason"], "data_root_missing")
        self.assertFalse(self.vault.exists())

    def test_cli_readonly_can_validate_and_dry_run_without_database_mutation(self):
        tool.seed_demo(self.vault)
        before = self.tree_bytes()
        for command in (["validate"], ["resolve-teaching", "--dry-run"], ["prepare-teaching"]):
            with self.subTest(command=command[0]):
                code, result = run_cli([*command, "--vault", str(self.vault), *self.flags()])
                self.assertEqual(code, 0, result)
                self.assertEqual(self.tree_bytes(), before)

    def test_cli_existing_explicit_write_can_rebuild_index(self):
        tool.seed_demo(self.vault)
        index = self.vault / tool.INDEX_REL
        index.unlink()
        code, result = run_cli(["rebuild-index", "--vault", str(self.vault), *self.flags(write=True)])
        self.assertEqual(code, 0, result)
        self.assertTrue(index.is_file())

    def test_cli_recovery_never_scans_parent_directories(self):
        for flags, expected in (([], "ask_data_mode"), (self.flags(), "ask_exact_vault")):
            with self.subTest(flags=flags), no_filesystem_access():
                code, result = run_cli(["recover-route", "--start", str(self.vault), *flags])
            self.assertEqual(code, 2)
            self.assertEqual(result["next_action"], expected)

    def test_cli_seed_demo_remains_synthetic_maintenance_only(self):
        for mode in entry.DATA_MODES:
            with self.subTest(mode=mode), no_filesystem_access():
                code, result = run_cli(["seed-demo", "--vault", str(self.vault), *self.flags(mode)])
            self.assertEqual(code, 2)
            self.assertEqual(result["reason"], "synthetic_maintenance_only")
        code, result = run_cli(["seed-demo", "--vault", str(self.vault)])
        self.assertEqual(code, 0, result)
        self.assertEqual(tool.validate_vault(self.vault)[0], [])

    def test_cli_external_content_is_rejected_before_reading_either_location(self):
        with no_filesystem_access():
            code, result = run_cli(["issue-teaching", "--vault", str(self.vault),
                                    "--content", str(self.root / "outside.json"),
                                    *self.flags("create_boundary")])
        self.assertEqual(code, 2)
        self.assertEqual(result["reason"], "file_outside_data_scope")

    def tree_bytes(self):
        return {path.relative_to(self.vault).as_posix(): path.read_bytes()
                for path in self.vault.rglob("*") if path.is_file()}


if __name__ == "__main__":
    unittest.main()
