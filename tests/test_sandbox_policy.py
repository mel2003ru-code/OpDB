"""Sandbox-policy checks; a policy plan MUST NOT be confused with confinement."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from foundry.agent_executor import _FIXTURE
from foundry.sandbox_policy import main, plan


IMAGE = "python:3.11-slim@sha256:" + "a" * 64


class SandboxPolicyTests(unittest.TestCase):
    def denied(self, result):
        self.assertFalse(result["runtime_verified"])
        self.assertFalse(result["network_isolation_verified"])
        self.assertFalse(result["candidate_executed"])
        self.assertFalse(result["container_started"])
        self.assertFalse(result["github_write_allowed"])
        self.assertFalse(result["production_allowed"])
        self.assertFalse(result["automatic_merge_allowed"])
        self.assertFalse(result["launch_authorized"])

    def test_not_configured_when_no_image(self):
        result = plan(None, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.denied(result)

    def test_digest_is_mandatory(self):
        for image in ("python:latest", "python:3.11-slim", "ubuntu:latest",
                      "python:3.11-slim@sha256:bad", IMAGE + "malicious",
                      None, 1, True):
            with self.subTest(image=image):
                result = plan(image, _FIXTURE)
                self.assertEqual(result["state"], "BLOCKED")
                self.denied(result)

    def test_strict_image_digest_has_no_unverified_execute(self):
        result = plan(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "POLICY_PLAN_ONLY")
        self.denied(result)
        self.assertIn("--network=none", result["command_argv"])
        self.assertIn("--read-only", result["command_argv"])
        self.assertIn("--pull=never", result["command_argv"])
        self.assertIn("--cap-drop=ALL", result["command_argv"])
        self.assertIn("--security-opt=no-new-privileges", result["command_argv"])
        self.assertIn("--pids-limit=32", result["command_argv"])
        self.assertIn("--memory=128m", result["command_argv"])
        self.assertIn("--cpus=0.5", result["command_argv"])
        self.assertIn("--user=65534:65534", result["command_argv"])

    def test_work_directory_is_read_only(self):
        result = plan(IMAGE, _FIXTURE)
        mounts = [x for x in result["command_argv"] if "type=bind" in x]
        self.assertEqual(len(mounts), 1)
        self.assertIn("readonly", mounts[0])
        self.assertIn("dst=/work", mounts[0])
        self.denied(result)

    def test_no_arbitrary_test_or_shell(self):
        result = plan(IMAGE, _FIXTURE)
        self.assertEqual(
            result["command_argv"][-4:],
            ["python", "-I", "-B", "/work/quality_probe.py"],
        )
        self.assertNotIn("sh", result["command_argv"])
        self.assertNotIn("bash", result["command_argv"])

    def test_bounds_never_pass_true_or_float(self):
        for budget in (True, False, 0, 16, 5.0, "10", -1):
            with self.subTest(budget=budget):
                r = plan(IMAGE, _FIXTURE, budget)
                self.assertEqual(r["state"], "BLOCKED")
                self.denied(r)

    def test_relative_or_missing_work_directory_denied(self):
        for directory in ("relative", "/nonexistent/opdb-12345", None):
            with self.subTest(directory=directory):
                if directory is None:
                    continue  # pathlib rejects None as an API input.
                self.assertEqual(plan(IMAGE, directory)["state"], "BLOCKED")

    def test_symlink_path_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "malicious"
            link.symlink_to(_FIXTURE, target_is_directory=True)
            self.assertEqual(plan(IMAGE, link)["state"], "BLOCKED")

    def test_lookalike_fixture_directory_denied(self):
        """A stranger can supply identical filenames but different executable bytes."""
        with tempfile.TemporaryDirectory(prefix="untrusted-fixture-") as tmp:
            for filename in ("calculator.py", "quality_probe.py",
                             "sandbox_runtime_probe.py",
                             "sandbox_adversarial_probe.py"):
                (Path(tmp) / filename).write_text(
                    "raise RuntimeError('unreviewed code')\n", encoding="utf-8")
            for probe in ("quality", "confinement", "adversarial"):
                with self.subTest(probe=probe):
                    verdict = plan(IMAGE, tmp, probe=probe)
                    self.assertEqual(verdict["state"], "BLOCKED",
                                     "Unreviewed path must not be mounted")

    def test_reviewed_fixture_root_with_modified_source_must_fail_closed(self):
        """Matching a trusted path does NOT make altered Python bytes trusted."""
        import shutil
        from unittest.mock import patch as patch_value
        names = ("calculator.py", "quality_probe.py",
                 "sandbox_runtime_probe.py", "sandbox_adversarial_probe.py")
        with tempfile.TemporaryDirectory(prefix="tampered-reviewed-fixture-") as tmp:
            root = Path(tmp)
            for name in names:
                shutil.copyfile(_FIXTURE / name, root / name)
            (root / "sandbox_runtime_probe.py").write_text(
                "raise RuntimeError('unreviewed code')\\n", encoding="utf-8"
            )
            with patch_value("foundry.sandbox_policy._REVIEWED_FIXTURE", root):
                for probe in ("confinement", "adversarial"):
                    with self.subTest(probe=probe):
                        decision = plan(IMAGE, root, probe=probe)
                        self.assertEqual(decision["state"], "BLOCKED",
                                         "Changed reviewed bytes must not run")

    def test_no_fixture_files_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(plan(IMAGE, tmp)["state"], "BLOCKED")

    def test_policy_cannot_invoke_docker(self):
        with patch("subprocess.run", side_effect=AssertionError("executed docker")):
            result = plan(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "POLICY_PLAN_ONLY")
        self.denied(result)

    def test_cli_without_image_fails_closed(self):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = main(["--fixture", str(_FIXTURE)])
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(buf.getvalue())["state"], "BLOCKED")

    def test_cli_fake_image_is_policy_plan_not_attestation(self):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = main(["--fixture", str(_FIXTURE), "--image", IMAGE])
        self.assertEqual(rc, 0)
        result = json.loads(buf.getvalue())
        self.assertEqual(result["state"], "POLICY_PLAN_ONLY")
        self.denied(result)


if __name__ == "__main__":
    unittest.main()
