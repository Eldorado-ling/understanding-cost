#!/usr/bin/env python3
"""Request-local scan regressions and opt-in, same-machine runtime measurements.

Run this file normally for tests; add --benchmark for seven warm local runs.
The uncached reference reparses Markdown at each consumer, independently of
snapshot metadata.  Timings measure local execution, not model token savings.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import vault_tool as tool


@contextlib.contextmanager
def uncached_consumers(vault: Path):
    """Reference path: read facts from disk again for every downstream consumer."""
    with patch.object(
        tool._VaultReadSnapshot,
        "read_note",
        lambda _snapshot, relative: tool.parse_note(vault / relative),
    ):
        yield


class SnapshotRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="uc-snapshot-test-")
        self.addCleanup(self.temporary.cleanup)
        self.vault = Path(self.temporary.name) / "vault"
        tool.seed_demo(self.vault)
        self.as_of = tool.utc_now_precise()

    def test_each_read_request_parses_each_note_once(self) -> None:
        count = tool.build_index(self.vault)[0]["node_count"]
        original = tool.parse_note
        for operation in (
            lambda: tool.build_index(self.vault),
            lambda: tool.validate_vault(self.vault),
            lambda: tool.resolve_active_teaching(
                self.vault, write=False, _as_of=self.as_of
            ),
        ):
            with patch.object(tool, "parse_note", wraps=original) as observed:
                operation()
            self.assertEqual(observed.call_count, count)

    def test_reused_and_independently_reparsed_decisions_are_equal(self) -> None:
        before = self.tree_bytes()
        expected_validation = tool.validate_vault(self.vault)
        expected_resolution = tool.resolve_active_teaching(
            self.vault, write=False, _as_of=self.as_of, _include_internal=True
        )
        with uncached_consumers(self.vault):
            self.assertEqual(tool.validate_vault(self.vault), expected_validation)
            self.assertEqual(
                tool.resolve_active_teaching(
                    self.vault, write=False, _as_of=self.as_of, _include_internal=True
                ),
                expected_resolution,
            )
        self.assertEqual(self.tree_bytes(), before)

    def test_new_request_detects_manual_edits_even_with_preserved_mtime(self) -> None:
        import os

        self.assertEqual(tool.validate_vault(self.vault)[0], [])
        index, _ = tool.build_index(self.vault)
        concept = next(node for node in index["nodes"].values() if node["type"] == "concept")
        path = self.vault / concept["path"]
        previous = path.stat()
        meta, body, _ = tool.parse_note(path)
        meta["privacy"] = "invalid"
        tool.replace_note_meta(path, meta, body)
        os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        errors = tool.validate_vault(self.vault)[0]
        self.assertTrue(any("privacy 非法" in error for error in errors), errors)
        with self.assertRaisesRegex(tool.VaultError, "Vault 校验失败"):
            tool.resolve_active_teaching(self.vault, write=False, _as_of=self.as_of)
        with uncached_consumers(self.vault):
            self.assertEqual(tool.validate_vault(self.vault)[0], errors)

    def test_snapshot_consumers_cannot_mutate_another_consumers_facts(self) -> None:
        snapshot = tool._read_vault_snapshot(self.vault)
        original_index, original_errors = snapshot.index_result()
        index, errors = snapshot.index_result()
        goal = next(node for node in index["nodes"].values() if node["type"] == "goal")
        before = snapshot.read_note(goal["path"])
        metadata, _body, parse_errors = snapshot.read_note(goal["path"])
        metadata["mastery_contracts"][0]["id"] = "mutated-by-consumer"
        parse_errors.append("mutated-by-consumer")
        index["nodes"].clear()
        errors.append("mutated-by-consumer")
        self.assertEqual(snapshot.read_note(goal["path"]), before)
        self.assertEqual(snapshot.index_result(), (original_index, original_errors))
        self.assertEqual(tool.build_index(self.vault)[0]["nodes"], original_index["nodes"])

    def test_public_entrypoints_do_not_accept_a_supplied_snapshot(self) -> None:
        snapshot = tool._read_vault_snapshot(self.vault)
        with self.assertRaises(TypeError):
            tool.validate_vault(self.vault, _snapshot=snapshot)
        with self.assertRaises(TypeError):
            tool.resolve_active_teaching(self.vault, write=False, _snapshot=snapshot)

    def test_invalid_note_errors_match_independent_reads(self) -> None:
        bad_note = self.vault / "bad-note.md"
        bad_note.write_bytes(b"\xff\xfe")
        reused = tool.validate_vault(self.vault)
        self.assertTrue(any("不是 UTF-8" in error for error in reused[0]))
        with uncached_consumers(self.vault):
            self.assertEqual(tool.validate_vault(self.vault), reused)

    def test_write_rebuilds_from_disk_and_remains_valid(self) -> None:
        count = tool.build_index(self.vault)[0]["node_count"]
        original = tool.parse_note
        with patch.object(tool, "parse_note", wraps=original) as observed:
            result = tool.resolve_active_teaching(self.vault, write=True)
        self.assertEqual(observed.call_count, count * 2)
        self.assertEqual(result["node_count"], count)
        self.assertEqual(tool.validate_vault(self.vault)[0], [])

    def tree_bytes(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in self.vault.rglob("*")
            if path.is_file()
        }


def benchmark() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-snapshot-benchmark-") as temporary:
        vault = Path(temporary) / "vault"
        tool.seed_demo(vault)
        as_of = tool.utc_now_precise()
        operations = {
            "validate": lambda: tool.validate_vault(vault),
            "resolve_readonly": lambda: tool.resolve_active_teaching(
                vault, write=False, _as_of=as_of
            ),
        }
        results = {}
        expected_outcomes = {}
        original = tool.parse_note
        for mode in ("reused", "independent_consumer_reads"):
            mode_results = {}
            context = (
                contextlib.nullcontext() if mode == "reused" else uncached_consumers(vault)
            )
            with context:
                for name, operation in operations.items():
                    elapsed, counts = [], []
                    for _ in range(7):
                        with patch.object(tool, "parse_note", wraps=original) as observed:
                            started = time.perf_counter()
                            outcome = operation()
                            elapsed.append((time.perf_counter() - started) * 1000)
                            counts.append(observed.call_count)
                        if name == "validate":
                            assert not outcome[0], outcome[0]
                        else:
                            assert outcome["status"] == "resolved", outcome
                        if name not in expected_outcomes:
                            expected_outcomes[name] = outcome
                        else:
                            assert outcome == expected_outcomes[name], name
                    mode_results[name] = {
                        "parse_calls": counts,
                        "median_ms": round(statistics.median(elapsed), 3),
                    }
            results[mode] = mode_results
        print(json.dumps({
            "note_count": tool.build_index(vault)[0]["node_count"],
            "runs": 7,
            "scope": "warm local runtime only; not token usage or a scale guarantee",
            "results": results,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if "--benchmark" in sys.argv:
        benchmark()
    else:
        unittest.main()
