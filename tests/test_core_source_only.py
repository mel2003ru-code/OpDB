"""Adversarial checks against actual new SQLite-backed Core adapter.

Independent source oracle is raw SQLite on a separate connection; the tested
Core API is never the oracle. This validates Source-only observations under
SQLite assumptions, NOT trusted Lens publication, independent OpDB WAL, ACID
implementation, power-loss durability, or full SQL conformance.
"""
import concurrent.futures
import os
import random
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from opdb.core import TruthStore


def oracle(path):
    with sqlite3.connect(path) as db:
        return tuple((key, bytes(value)) for key, value in db.execute(
            "SELECT k,v FROM opdb_source_kv ORDER BY k COLLATE BINARY"
        ))

class CoreOracleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "core.db")
        self.store = TruthStore(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_source_only_is_default_and_permanent(self):
        self.assertEqual(self.store.read_mode, "SOURCE_ONLY")
        self.assertFalse(self.store.lens_enabled)
        candidate = self.store.build_lens_candidate()
        self.assertFalse(self.store.admit_lens(candidate).accepted)
        self.assertEqual(self.store.read_mode, "SOURCE_ONLY")

    def test_insert_update_delete_match_independent_sqlite(self):
        self.store.put("a", b"x")
        self.store.put("b", b"y")
        self.store.put("a", b"z")
        self.store.delete("b")
        self.assertEqual(oracle(self.path), (("a", b"z"),))
        self.assertEqual(self.store.get("a"), b"z")
        self.assertIsNone(self.store.get("b"))

    def test_empty_value_allowed(self):
        self.store.put("a", b"")
        self.assertEqual(self.store.get("a"), b"")

    def test_binary_value_roundtrips_without_text_conversion(self):
        self.store.put("bin", b"\x00\xff\x80\x01")
        self.assertEqual(self.store.get("bin"), b"\x00\xff\x80\x01")

    def test_unicode_keys_are_distinct(self):
        for key in ("ключ", "clé", "🛠", "a", "A"):
            self.store.put(key, key.encode("utf-8"))
        self.assertEqual(self.store.snapshot().rows, oracle(self.path))

    def test_scan_prefix_treats_percent_underscore_as_literals(self):
        for key in ("a%", "a_", "abc", "a1", "z"):
            self.store.put(key, key.encode())
        self.assertEqual(self.store.scan("a%"), (("a%", b"a%"),))
        self.assertEqual(self.store.scan("a_"), (("a_", b"a_"),))
        self.assertEqual(self.store.scan("a"), tuple((k,v) for k,v in oracle(self.path) if k.startswith("a")))

    def test_missing_key_is_not_fabricated(self):
        self.assertIsNone(self.store.get("unknown"))

    def test_ordered_scan_respects_limit(self):
        for key in ("c", "b", "a"):
            self.store.put(key, key.encode())
        self.assertEqual([x[0] for x in self.store.scan(limit=2)], ["a", "b"])

    def test_invalid_prefix_limit_does_not_mutate(self):
        for limit in (True, 0, -1, 1001, 1.1, "5"):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    self.store.scan(limit=limit)
        self.assertEqual(oracle(self.path), ())

    def test_disallow_nul_and_oversize_keys(self):
        for key in ("", "x\x00y", "a" * 513, "\ud800"):
            with self.subTest(key=repr(key)):
                with self.assertRaises(ValueError):
                    self.store.put(key, b"x")
        self.assertEqual(oracle(self.path), ())

    def test_invalid_value_never_commits(self):
        for value in ("abc", bytearray(b"x"), b"x" * (1024 * 1024 + 1), None):
            with self.subTest(type=str(type(value))):
                with self.assertRaises(ValueError):
                    self.store.put("key", value)
        self.assertEqual(oracle(self.path), ())

    def test_injection_key_is_data_not_sql(self):
        key = "k'); DROP TABLE opdb_source_kv; --"
        self.store.put(key, b"safe")
        self.assertEqual(self.store.get(key), b"safe")
        self.assertEqual(len(oracle(self.path)), 1)

    def test_batch_commit_is_atomic_on_success(self):
        self.store.apply([("put", "a", b"1"), ("put", "b", b"2"), ("delete", "a")])
        self.assertEqual(oracle(self.path), (("b", b"2"),))

    def test_batch_validation_rejects_all_without_writes(self):
        with self.assertRaises(ValueError):
            self.store.apply([("put", "a", b"1"), ("put", "bad", "not bytes")])
        self.assertEqual(oracle(self.path), ())

    def test_streaming_unbounded_generator_stops_at_batch_limit(self):
        def forever():
            n = 0
            while True:
                yield ("delete", f"key{n}")
                n += 1
        with self.assertRaisesRegex(ValueError, "10000"):
            self.store.apply(forever())
        self.assertEqual(oracle(self.path), ())

    def test_batch_payload_is_bounded_before_write(self):
        large = b"x" * (1024 * 1024)
        with self.assertRaisesRegex(ValueError, "8 MiB"):
            self.store.apply([("put", f"k{i}", large) for i in range(9)])
        self.assertEqual(oracle(self.path), ())

    def test_trigger_abort_rolls_back_entire_batch(self):
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TRIGGER deny_bad BEFORE INSERT ON opdb_source_kv "
                "WHEN NEW.k='bad' BEGIN SELECT RAISE(ABORT,'injected'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.apply([("put", "good", b"1"), ("put", "bad", b"2")])
        self.assertEqual(oracle(self.path), ())

    def test_external_untracked_writer_is_always_seen_on_source(self):
        self.store.put("k", b"initial")
        candidate = self.store.build_lens_candidate()
        with sqlite3.connect(self.path) as writer:
            writer.execute("UPDATE opdb_source_kv SET v=? WHERE k=?", (b"external", "k"))
        self.assertFalse(self.store.check_candidate_against_source(candidate))
        self.assertEqual(self.store.get("k"), b"external")
        self.assertFalse(self.store.admit_lens(candidate).accepted)

    def test_external_delete_never_returns_old_candidate(self):
        self.store.put("a", b"old")
        candidate = self.store.build_lens_candidate()
        with sqlite3.connect(self.path) as writer:
            writer.execute("DELETE FROM opdb_source_kv WHERE k='a'")
        self.assertIsNone(self.store.get("a"))
        self.assertFalse(self.store.check_candidate_against_source(candidate))

    def test_external_insert_never_returns_old_scan(self):
        candidate = self.store.build_lens_candidate()
        with sqlite3.connect(self.path) as writer:
            writer.execute("INSERT INTO opdb_source_kv VALUES('new', ?)", (b"v",))
        self.assertEqual(self.store.scan(), (("new", b"v"),))
        self.assertFalse(self.store.admit_lens(candidate).accepted)

    def test_forged_log_metadata_cannot_enable_lens(self):
        self.store.put("a", b"v0")
        candidate = self.store.build_lens_candidate()
        with sqlite3.connect(self.path) as writer:
            writer.execute("CREATE TABLE IF NOT EXISTS fake_change_log (seq INTEGER, v BLOB)")
            writer.execute("INSERT INTO fake_change_log VALUES (1, ?)", (b"faked",))
            writer.execute("UPDATE opdb_source_kv SET v=? WHERE k=?", (b"v1", "a"))
        self.assertEqual(self.store.get("a"), b"v1")
        self.assertFalse(self.store.admit_lens(candidate).accepted)
        self.assertFalse(self.store.lens_enabled)

    def test_drop_trigger_and_reset_schema_cookie_cannot_enable_lens(self):
        self.store.put("a", b"v0")
        candidate = self.store.build_lens_candidate()
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TRIGGER custom_log AFTER UPDATE ON opdb_source_kv BEGIN SELECT 1; END")
            schema = db.execute("PRAGMA schema_version").fetchone()[0]
            db.execute("DROP TRIGGER custom_log")
            db.execute("UPDATE opdb_source_kv SET v=? WHERE k=?", (b"v1", "a"))
            db.execute("PRAGMA schema_version=%d" % schema)
        self.assertEqual(self.store.get("a"), b"v1")
        self.assertFalse(self.store.admit_lens(candidate).accepted)

    def test_external_integer_value_must_not_be_fabricated_by_bytes_coercion(self):
        """SQLite BLOB affinity allows INTEGER; bytes(3) silently makes 3 NULs."""
        self.store.put("k", b"original")
        with sqlite3.connect(self.path) as writer:
            writer.execute("UPDATE opdb_source_kv SET v=3 WHERE k='k'")
            self.assertEqual(writer.execute(
                "SELECT typeof(v) FROM opdb_source_kv WHERE k='k'"
            ).fetchone()[0], "integer")
        with self.assertRaisesRegex(RuntimeError, "non-BLOB"):
            self.store.get("k")

    def test_external_zero_integer_must_not_appear_as_empty_blob(self):
        """bytes(0)==b'' was even more misleading than the positive INTEGER."""
        self.store.put("k", b"original")
        with sqlite3.connect(self.path) as writer:
            writer.execute("UPDATE opdb_source_kv SET v=0 WHERE k='k'")
        with self.assertRaisesRegex(RuntimeError, "non-BLOB"):
            self.store.get("k")

    def test_external_non_blob_fails_all_core_read_paths(self):
        self.store.put("k", b"initial")
        candidate = self.store.build_lens_candidate()
        with sqlite3.connect(self.path) as writer:
            writer.execute("UPDATE opdb_source_kv SET v=? WHERE k=?", (5, "k"))
        for read in (
            lambda: self.store.get("k"),
            lambda: self.store.scan(),
            lambda: self.store.snapshot(),
            lambda: self.store.build_lens_candidate(),
        ):
            with self.subTest(read=read), self.assertRaisesRegex(RuntimeError, "non-BLOB"):
                read()
        self.assertFalse(self.store.admit_lens(candidate).accepted)

    def test_external_text_value_reports_integrity_error_not_type_error(self):
        self.store.put("k", b"initial")
        with sqlite3.connect(self.path) as writer:
            writer.execute("UPDATE opdb_source_kv SET v=? WHERE k=?", ("oops", "k"))
        for read in (lambda: self.store.get("k"), lambda: self.store.snapshot()):
            with self.subTest(read=read), self.assertRaisesRegex(RuntimeError, "non-BLOB"):
                read()

    def test_external_oversize_blob_fails_closed_even_if_written_directly(self):
        self.store.put("k", b"small")
        with sqlite3.connect(self.path) as writer:
            writer.execute("UPDATE opdb_source_kv SET v=? WHERE k=?",
                           (b"z" * (1024 * 1024 + 1), "k"))
        with self.assertRaisesRegex(RuntimeError, "oversized"):
            self.store.get("k")
        with self.assertRaisesRegex(RuntimeError, "oversized"):
            self.store.snapshot()

    def test_external_nul_key_cannot_escape_core_input_contract(self):
        with sqlite3.connect(self.path) as writer:
            writer.execute("INSERT INTO opdb_source_kv VALUES (?,?)",
                           ("bad\x00key", b"value"))
        with self.assertRaisesRegex(RuntimeError, "invalid source key"):
            self.store.snapshot()
        with self.assertRaisesRegex(RuntimeError, "invalid source key"):
            self.store.scan()

    def test_external_value_repair_restores_authoritative_reads(self):
        self.store.put("k", b"original")
        with sqlite3.connect(self.path) as writer:
            writer.execute("UPDATE opdb_source_kv SET v=3 WHERE k='k'")
        with self.assertRaisesRegex(RuntimeError, "non-BLOB"):
            self.store.get("k")
        with sqlite3.connect(self.path) as writer:
            writer.execute("UPDATE opdb_source_kv SET v=? WHERE k=?", (b"repaired", "k"))
        self.assertEqual(self.store.get("k"), b"repaired")
        self.assertEqual(self.store.snapshot().rows, (("k", b"repaired"),))
        self.assertFalse(self.store.lens_enabled)

    def test_source_table_drop_fails_explicitly_not_stale(self):
        self.store.put("a", b"v0")
        candidate = self.store.build_lens_candidate()
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TABLE opdb_source_kv")
        with self.assertRaises(sqlite3.OperationalError):
            self.store.get("a")
        self.assertFalse(self.store.admit_lens(candidate).accepted)

    def test_candidate_snapshot_cannot_be_mutated(self):
        self.store.put("x", b"1")
        candidate = self.store.build_lens_candidate()
        with self.assertRaises(AttributeError):
            candidate.rows = (("x", b"2"),)
        self.assertEqual(candidate.rows, (("x", b"1"),))

    def test_candidate_content_equal_is_not_admission(self):
        self.store.put("a", b"1")
        candidate = self.store.build_lens_candidate()
        self.assertTrue(self.store.check_candidate_against_source(candidate))
        self.assertFalse(self.store.admit_lens(candidate).accepted)

    def test_aba_digest_is_not_claimed_as_commit_identity(self):
        self.store.put("a", b"one")
        candidate = self.store.build_lens_candidate()
        self.store.put("a", b"two")
        self.store.put("a", b"one")
        self.assertTrue(self.store.check_candidate_against_source(candidate))
        self.assertFalse(self.store.admit_lens(candidate).accepted)

    def test_snapshot_hash_changes_with_source(self):
        self.store.put("k", b"v0")
        one = self.store.snapshot()
        self.store.put("k", b"v1")
        two = self.store.snapshot()
        self.assertNotEqual(one.digest_sha256, two.digest_sha256)

    def test_snapshot_hash_is_stable_across_reopen(self):
        self.store.put("x", b"y")
        before = self.store.snapshot()
        self.store.close()
        self.store = TruthStore(self.path)
        self.assertEqual(before, self.store.snapshot())

    def test_python_reference_model_randomized_operations(self):
        rng = random.Random(20261108)
        expected = {}
        for i in range(320):
            key = f"k{rng.randrange(80):03}"
            if rng.randrange(4) == 0:
                self.store.delete(key)
                expected.pop(key, None)
            else:
                value = rng.randbytes(rng.randrange(0, 36))
                self.store.put(key, value)
                expected[key] = value
            if i % 17 == 0:
                snap = self.store.snapshot()
                self.assertEqual(dict(snap.rows), expected)
                self.assertEqual(snap.rows, oracle(self.path))
        self.assertEqual(dict(self.store.snapshot().rows), expected)

    def test_concurrent_external_writer_and_reader_source_only(self):
        self.store.put("k", b"0")
        started = threading.Event()
        def writer():
            with sqlite3.connect(self.path, timeout=5) as db:
                started.set()
                for n in range(40):
                    db.execute("UPDATE opdb_source_kv SET v=? WHERE k='k'", (str(n).encode(),))
                    db.commit()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            task = ex.submit(writer)
            self.assertTrue(started.wait(timeout=3))
            seen = [self.store.get("k") for _ in range(120)]
            task.result(timeout=10)
        self.assertTrue(all(isinstance(x, bytes) for x in seen))
        self.assertEqual(self.store.get("k"), b"39")
        self.assertFalse(self.store.lens_enabled)

    def test_separate_connection_committed_transactions_visible(self):
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN")
            db.execute("INSERT INTO opdb_source_kv VALUES('external', ?)", (b"yes",))
            self.assertIsNone(self.store.get("external"))
            db.commit()
        self.assertEqual(self.store.get("external"), b"yes")

    def test_uncommitted_external_transaction_is_invisible(self):
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN")
            db.execute("INSERT INTO opdb_source_kv VALUES('uncommitted', ?)", (b"x",))
            self.assertIsNone(self.store.get("uncommitted"))
            db.rollback()
        self.assertIsNone(self.store.get("uncommitted"))

    def test_reopen_after_process_kill_before_commit_keeps_old_value(self):
        self.store.put("key", b"old")
        code = (
            "import os,sqlite3,sys;"
            "c=sqlite3.connect(sys.argv[1]);"
            "c.execute('BEGIN IMMEDIATE');"
            "c.execute('UPDATE opdb_source_kv SET v=? WHERE k=?',(b'new','key'));"
            "os._exit(17)"
        )
        process = subprocess.run([sys.executable, "-c", code, self.path], check=False)
        self.assertEqual(process.returncode, 17)
        self.assertEqual(self.store.get("key"), b"old")

    def test_reopen_after_process_kill_after_commit_sees_new_value(self):
        self.store.put("key", b"old")
        code = (
            "import os,sqlite3,sys;"
            "c=sqlite3.connect(sys.argv[1]);"
            "c.execute('BEGIN IMMEDIATE');"
            "c.execute('UPDATE opdb_source_kv SET v=? WHERE k=?',(b'new','key'));"
            "c.commit();"
            "os._exit(18)"
        )
        process = subprocess.run([sys.executable, "-c", code, self.path], check=False)
        self.assertEqual(process.returncode, 18)
        self.assertEqual(self.store.get("key"), b"new")
        self.store.close()
        self.store = TruthStore(self.path)
        self.assertEqual(self.store.get("key"), b"new")

    def test_close_fails_cleanly(self):
        self.store.close()
        with self.assertRaises(RuntimeError):
            self.store.get("x")

    def test_wrong_candidate_type_fails_explicitly(self):
        with self.assertRaises(TypeError):
            self.store.admit_lens(None)
        with self.assertRaises(TypeError):
            self.store.check_candidate_against_source({})


if __name__ == "__main__":
    unittest.main()
