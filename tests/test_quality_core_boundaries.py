"""Independent Quality negative controls against the *real* Core adapter.

Target: the exact code from Core PR #33 at SHA
14ad0415db0a9fdf6dc3a68fe4c858b08cf467d5.
Created independently from the Core author's existing test cases; no producer
implementation should be trusted merely because these finite tests pass.

Reproduce: python -m unittest -v tests.test_quality_core_boundaries
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opdb.core import TruthStore, SourceIntegrityError


class IndependentBoundaryQuality(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="quality-opdb-")
        self.path = str(Path(self.temp.name) / "source.sqlite")
        self.store = TruthStore(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _oracle(self):
        with sqlite3.connect(self.path) as db:
            return tuple(db.execute("SELECT k,v FROM opdb_source_kv ORDER BY k"))

    def test_legitimate_source_schema_reopens_with_persisted_value(self):
        self.store.put("case", b"persisted")
        self.store.close()
        with TruthStore(self.path) as reopened:
            self.assertEqual(reopened.get("case"), b"persisted")
            self.assertEqual(reopened.read_mode, "SOURCE_ONLY")
            self.assertFalse(reopened.lens_enabled)

    def test_existing_view_must_not_masquerade_as_source_table(self):
        self.store.close()
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TABLE opdb_source_kv")
            db.execute(
                "CREATE VIEW opdb_source_kv AS "
                "SELECT 'forged' AS k, CAST('payload' AS BLOB) AS v"
            )
            # SQLite itself accepts CREATE TABLE IF NOT EXISTS for a VIEW.
            db.execute(
                "CREATE TABLE IF NOT EXISTS opdb_source_kv "
                "(k TEXT PRIMARY KEY COLLATE BINARY NOT NULL, v BLOB NOT NULL)"
            )
        with self.assertRaisesRegex(SourceIntegrityError, "source table schema"):
            TruthStore(self.path)

    def test_incompatible_existing_kv_tables_refused_at_open(self):
        self.store.close()
        altered_tables = (
            "CREATE TABLE opdb_source_kv (k TEXT, v BLOB)",
            "CREATE TABLE opdb_source_kv "
            "(k TEXT PRIMARY KEY COLLATE NOCASE NOT NULL, v BLOB NOT NULL)",
            "CREATE TABLE opdb_source_kv "
            "(k TEXT PRIMARY KEY COLLATE BINARY NOT NULL, v TEXT NOT NULL)",
        )
        for ddl in altered_tables:
            with self.subTest(ddl=ddl):
                with sqlite3.connect(self.path) as db:
                    db.execute("DROP TABLE IF EXISTS opdb_source_kv")
                    db.execute(ddl)
                with self.assertRaisesRegex(SourceIntegrityError, "source table schema"):
                    TruthStore(self.path)

    def test_external_committed_dml_is_still_read_from_authoritative_source(self):
        with sqlite3.connect(self.path) as outside:
            outside.execute(
                "INSERT INTO opdb_source_kv(k,v) VALUES (?, ?)",
                ("external", b"correct"),
            )
        self.assertEqual(self.store.get("external"), b"correct")
        self.assertEqual(self.store.scan("external"), (("external", b"correct"),))
        self.assertEqual(self.store.snapshot().rows, self._oracle())
        self.assertEqual(self.store.read_mode, "SOURCE_ONLY")

    def test_post_open_view_substitution_refused_by_every_public_operation(self):
        self.store.put("before", b"source")
        with sqlite3.connect(self.path) as outside:
            outside.execute("DROP TABLE opdb_source_kv")
            outside.execute(
                "CREATE VIEW opdb_source_kv AS "
                "SELECT 'forged' AS k, CAST('payload' AS BLOB) AS v"
            )
        for name, operation in (
            ("get", lambda: self.store.get("forged")),
            ("scan", lambda: self.store.scan()),
            ("snapshot", lambda: self.store.snapshot()),
            ("put", lambda: self.store.put("new", b"v")),
            ("delete", lambda: self.store.delete("forged")),
            ("lens-build", lambda: self.store.build_lens_candidate()),
        ):
            with self.subTest(operation=name):
                with self.assertRaisesRegex(SourceIntegrityError, "source table schema"):
                    operation()
                self.assertEqual(self.store.read_mode, "SOURCE_ONLY")
                self.assertFalse(self.store.lens_enabled)

    def test_post_open_table_contract_loss_refused(self):
        self.store.put("before", b"source")
        with sqlite3.connect(self.path) as outside:
            outside.execute("DROP TABLE opdb_source_kv")
            outside.execute("CREATE TABLE opdb_source_kv (k TEXT, v BLOB)")
            outside.execute(
                "INSERT INTO opdb_source_kv(k,v) VALUES (?, ?)", ("duplicate", b"a")
            )
            outside.execute(
                "INSERT INTO opdb_source_kv(k,v) VALUES (?, ?)", ("duplicate", b"b")
            )
        with self.assertRaisesRegex(SourceIntegrityError, "source table schema"):
            self.store.get("duplicate")
        with self.assertRaisesRegex(SourceIntegrityError, "source table schema"):
            self.store.scan()
        with self.assertRaisesRegex(SourceIntegrityError, "source table schema"):
            self.store.snapshot()
        self.assertFalse(self.store.lens_enabled)

    def test_abort_generator_at_first_invalid_operation(self):
        """Do not prefetch thousands of operations after an invalid first one."""
        seen = []
        def input_stream():
            seen.append(0)
            yield ("invalid", "entry")
            for i in range(10_500):
                seen.append(i + 1)
                yield ("delete", f"k{i}")
        with self.assertRaisesRegex(ValueError, "invalid operation"):
            self.store.apply(input_stream())
        self.assertEqual(seen, [0], "generator must stop at first invalid record")
        self.assertEqual(self._oracle(), ())

    def test_abort_generator_at_payload_budget_not_at_ten_thousand(self):
        """Total payload budget must be enforced as input is consumed.

        Reuse one 1 MiB object to make the *test* cheap. Real generators could
        allocate a unique 1 MiB object every yield; eager list() can OOM.
        """
        count = 0
        one_mib = b"x" * (1024 * 1024)
        def input_stream():
            nonlocal count
            for i in range(10_500):
                count += 1
                yield ("put", f"k{i:06d}", one_mib)
        with self.assertRaisesRegex(ValueError, "8 MiB"):
            self.store.apply(input_stream())
        self.assertLessEqual(
            count, 9, "Core over-read generator before checking byte budget"
        )
        self.assertEqual(self._oracle(), ())

    def test_closed_store_never_consumes_untrusted_stream(self):
        self.store.close()
        calls = []
        def input_stream():
            calls.append("consumed")
            yield ("put", "k", b"v")
        with self.assertRaisesRegex(RuntimeError, "closed"):
            self.store.apply(input_stream())
        self.assertEqual(calls, [], "closed DB must not execute iterator side effects")

    def test_successful_streaming_batch_is_atomic(self):
        def input_stream():
            for i in range(100):
                yield ("put", f"k{i:03}", i.to_bytes(2, "big"))
        self.store.apply(input_stream())
        expected = tuple((f"k{i:03}", i.to_bytes(2, "big")) for i in range(100))
        self.assertEqual(self._oracle(), expected)

    def test_snapshot_cap_on_row_count_fails_closed(self):
        for i in range(4):
            self.store.put(str(i), b"1")
        with patch("opdb.core.MAX_SNAPSHOT_ROWS", 3, create=True):
            with self.assertRaisesRegex(RuntimeError, "snapshot.*row"):
                self.store.snapshot()
        self.assertFalse(self.store.lens_enabled)
        self.assertEqual(len(self._oracle()), 4)

    def test_snapshot_cap_on_total_payload_fails_closed(self):
        for i in range(3):
            self.store.put(str(i), b"four")
        with patch("opdb.core.MAX_SNAPSHOT_BYTES", 10, create=True):
            with self.assertRaisesRegex(RuntimeError, "snapshot.*bytes"):
                self.store.snapshot()
        self.assertFalse(self.store.lens_enabled)
        self.assertEqual(len(self._oracle()), 3)

    def test_scan_cap_on_total_payload_fails_closed(self):
        for i in range(3):
            self.store.put(str(i), b"four")
        with patch("opdb.core.MAX_SCAN_BYTES", 10, create=True):
            with self.assertRaisesRegex(RuntimeError, "scan.*bytes"):
                self.store.scan()
        self.assertFalse(self.store.lens_enabled)
        self.assertEqual(len(self._oracle()), 3)

    def test_healthy_source_under_budget_keeps_reference_equivalence(self):
        for i in range(3):
            self.store.put(str(i), b"ab")
        with (patch("opdb.core.MAX_SNAPSHOT_ROWS", 3, create=True),
              patch("opdb.core.MAX_SNAPSHOT_BYTES", 10, create=True),
              patch("opdb.core.MAX_SCAN_BYTES", 10, create=True)):
            self.assertEqual(self.store.snapshot().rows, self._oracle())
            self.assertEqual(self.store.scan(), self._oracle())
            candidate = self.store.build_lens_candidate()
            self.assertTrue(self.store.check_candidate_against_source(candidate))
            self.assertFalse(self.store.admit_lens(candidate).accepted)

    def test_source_only_lens_never_reenabled_by_resource_failure(self):
        self.store.put("x", b"payload")
        candidate = self.store.build_lens_candidate()
        with patch("opdb.core.MAX_SNAPSHOT_BYTES", 1, create=True):
            with self.assertRaises(RuntimeError):
                self.store.snapshot()
        self.assertFalse(self.store.admit_lens(candidate).accepted)
        self.assertEqual(self.store.read_mode, "SOURCE_ONLY")


if __name__ == "__main__":
    unittest.main()
