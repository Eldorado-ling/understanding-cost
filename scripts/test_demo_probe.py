"""Executable diagnostic materials and strict versioned Demo seed compatibility."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import self_test as fixtures
import vault_tool as tool


def trace_functions(prompt: str, entry: str) -> list[str]:
    """Execute the tiny numbered-function notation supplied in the actual prompt."""
    functions = {
        match.group(1): match.group(2).rstrip("。").split("；")
        for match in re.finditer(r"^函数([^：]+)：(.+)$", prompt, re.MULTILINE)
    }

    def execute(name: str, stack: tuple[str, ...]) -> list[str]:
        assert name in functions, f"Missing input for called function: {name}"
        assert name not in stack, "This beginner fixture must terminate without recursion"
        positions = []
        for ordinal, instruction in enumerate(functions[name]):
            label = "①②③④⑤"[ordinal]
            assert instruction.startswith(label), instruction
            positions.append(name + label)
            action = instruction[len(label):]
            if action.startswith("调用"):
                positions.extend(execute(action[len("调用"):], (*stack, name)))
            else:
                assert re.fullmatch(r"写下“[^”]+”", action), action
        return positions

    return execute(entry, ())


class DemoProbeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="uc-demo-probe-")
        self.addCleanup(self.temporary.cleanup)
        self.vault = Path(self.temporary.name) / "vault"
        tool.seed_demo(self.vault)

    def test_diagnostic_has_complete_input_partial_task_and_response_format(self):
        brief = tool.prepare_teaching_brief(self.vault)
        self.assertEqual(brief["routing_action"], "diagnose_now")
        prompt = brief["diagnostic_probe"]["prompt"]
        example = re.search(r"^已完成：(.+)。$", prompt, re.MULTILINE)
        exercise = re.search(r"^待补：(.+)。$", prompt, re.MULTILINE)
        self.assertIsNotNone(example, "Worked example must contain an actual full trace")
        self.assertIsNotNone(exercise, "Learner task must contain an actual incomplete trace")
        self.assertEqual(example.group(1).split(" → "), trace_functions(prompt, "送信"))
        answer = trace_functions(prompt, "整理")
        partial = exercise.group(1).split(" → ")
        self.assertEqual(len(partial), len(answer))
        self.assertEqual(partial.count("___"), 2)
        for provided, expected in zip(partial, answer):
            if provided != "___":
                self.assertEqual(provided, expected)
        self.assertNotIn(" → ".join(answer), prompt, "Do not supply the exercise's full answer")
        self.assertIn("答题格式：两个空依次是___、___；因为___", prompt)
        self.assertIn("如果没把握，指出卡在哪一步", prompt)

    def test_brief_exposes_complete_probe_without_reserved_verification(self):
        before = fixtures.snapshot_tree_bytes(self.vault)
        brief = tool.prepare_teaching_brief(self.vault)
        self.assertEqual(set(brief["diagnostic_probe"]), {"id", "prompt", "success_criteria"})
        resource = tool.parse_note(
            self.vault / "30-learning/resources/res-python-call-stack-faded.md"
        )[0]
        self.assertEqual(brief["diagnostic_probe"], resource["diagnostic_probe"])
        serialized = json.dumps(brief, ensure_ascii=False)
        for secret in [resource["verification_task"]["prompt"],
                       *resource["verification_task"]["protected_answers"]]:
            self.assertNotIn(secret, serialized)
        # prepare-teaching itself applies the opaque overlap guard before return.
        self.assertEqual(fixtures.snapshot_tree_bytes(self.vault), before)
        self.assertEqual(tool.validate_vault(self.vault)[0], [])

    def test_versionless_old_seed_stays_valid_without_record_migration(self):
        old_vault = Path(self.temporary.name) / "old-vault"
        with patch.object(tool, "SEED_PATH", tool.LEGACY_SEED_PATH), \
             patch.object(tool, "CURRENT_SEED_VERSION", "0.1.1"):
            tool.seed_demo(old_vault)
        manifest_path = old_vault / tool.MANIFEST_REL
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.pop("seed_version")
        tool.write_json(manifest_path, manifest)
        before = fixtures.snapshot_tree_bytes(old_vault)
        self.assertEqual(tool.validate_vault(old_vault)[0], [])
        self.assertTrue(tool.trusted_synthetic_demo_authorized(old_vault, manifest))
        self.assertEqual(fixtures.snapshot_tree_bytes(old_vault), before)

    def test_new_seed_version_cannot_be_deleted_downgraded_or_use_a_path(self):
        manifest_path = self.vault / tool.MANIFEST_REL
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(original["seed_version"], "0.1.2")
        for version in (None, "0.1.1", "99.0.0", "../../untrusted-seed.json"):
            with self.subTest(version=version):
                manifest = dict(original)
                if version is None:
                    manifest.pop("seed_version")
                else:
                    manifest["seed_version"] = version
                tool.write_json(manifest_path, manifest)
                errors = tool.validate_vault(self.vault)[0]
                self.assertTrue(any("seed" in error for error in errors), errors)
                self.assertFalse(tool.trusted_synthetic_demo_authorized(self.vault, manifest))
        tool.write_json(manifest_path, original)
        self.assertEqual(tool.validate_vault(self.vault)[0], [])

    def test_old_seed_cannot_claim_new_authority(self):
        old_vault = Path(self.temporary.name) / "old-vault"
        with patch.object(tool, "SEED_PATH", tool.LEGACY_SEED_PATH), \
             patch.object(tool, "CURRENT_SEED_VERSION", "0.1.1"):
            tool.seed_demo(old_vault)
        manifest_path = old_vault / tool.MANIFEST_REL
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["seed_version"] = "0.1.2"
        tool.write_json(manifest_path, manifest)
        errors = tool.validate_vault(old_vault)[0]
        self.assertTrue(any("trusted seed 前缀不一致" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
