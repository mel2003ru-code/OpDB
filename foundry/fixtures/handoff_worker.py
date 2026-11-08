"""S-008 fixed data-only handoff guest. NOT an LLM/source-code executor.

Executed only in a restricted Docker container with a read-only, reviewed
fixture mount. The request carries a commit hash as data; no candidate code is
run, no shell is used, and no network or host credentials are required.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import sys

_ORIGINAL_SHA = "97ecad52211a40a7ebf00716cc9ee9c2f76a9b4a5eda731afe2921221f3e7452"
_SHA = re.compile(r"[a-f0-9]{40}\Z")
_PATH = "foundry/fixtures/calculator.py"
_BEFORE = "    return left - right\n"
_AFTER = "    return left + right\n"


def inspect():
    base = runpy.run_path("/work/sandbox_runtime_probe.py")["inspect"]()
    negative = runpy.run_path("/work/sandbox_adversarial_probe.py")["inspect"]()
    checks = dict(base)
    checks.update(negative)
    for path, key in (("/dev/shm", "shm_8m"), ("/tmp", "tmp_8m")):
        try:
            v = os.statvfs(path)
            checks[key] = 0 < v.f_blocks * v.f_frsize <= 8 * 1024 * 1024
        except OSError:
            checks[key] = False
    return checks


def main():
    sha = os.environ.get("OPDB_SOURCE_SHA", "")
    checks = inspect()
    reply = None
    if _SHA.fullmatch(sha) and all(type(v) is bool and v for v in checks.values()):
        with Path("/work/calculator.py").open("rb") as file:
            original = file.read(4097)
        if len(original) <= 4096 and hashlib.sha256(original).hexdigest() == _ORIGINAL_SHA:
            source = original.decode("utf-8", "strict")
            if source.count(_BEFORE) == 1 and _AFTER not in source:
                candidate = source.replace(_BEFORE, _AFTER).encode("utf-8")
                reply = {
                    "schema_version": 1,
                    "source_sha": sha,
                    "task_key": "demo-add-v1",
                    "issue_number": 31,
                    "path": _PATH,
                    "original_sha256": _ORIGINAL_SHA,
                    "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
                    "candidate_text": candidate.decode("utf-8"),
                }
    passed = reply is not None
    print(json.dumps({
        "probe": "fixed-data-only-handoff-s008",
        "passed": passed,
        "checked": checks,
        "reply": reply,
        "model_invoked": False,
        "arbitrary_model_code_executed": False,
        "github_write_allowed": False,
        "trusted_controller_attested": False,
        "launch_authorized": False,
    }, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
