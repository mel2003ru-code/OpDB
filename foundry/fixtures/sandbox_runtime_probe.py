"""Reviewed synthetic CONFINEMENT probe, not a general untrusted code executor.

Executed inside an OS container on a disposable GitHub CI runner. Its checks
verify observed restrictions for this one run only, not Docker isolation against
privileged host actors, kernel exploits, malicious OCI images or LLM output.
"""
import json
import os
from pathlib import Path
import socket
import sys

def _read(path):
    try:
        return Path(path).read_text(encoding="ascii").strip()
    except OSError:
        return None

def _cgroups():
    # Docker GitHub runners are normally cgroup v2; v1 paths are included so a
    # missing cgroup cannot be silently treated as unrestricted PASS.
    mem = _read("/sys/fs/cgroup/memory.max")
    if mem is None:
        mem = _read("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    pids = _read("/sys/fs/cgroup/pids.max")
    if pids is None:
        pids = _read("/sys/fs/cgroup/pids/pids.max")
    cpu = _read("/sys/fs/cgroup/cpu.max")
    if cpu is not None:
        fields = cpu.split()
        try:
            cpu_ok = len(fields) == 2 and fields[0] != "max" and (
                0 < int(fields[0]) / int(fields[1]) <= 0.55
            )
        except (ValueError, ZeroDivisionError):
            cpu_ok = False
    else:
        q = _read("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
        p = _read("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
        try:
            cpu_ok = 0 < int(q) / int(p) <= 0.55
        except (ValueError, TypeError, ZeroDivisionError):
            cpu_ok = False
    try:
        memory_ok = 0 < int(mem) <= 128 * 1024 * 1024
        pids_ok = 0 < int(pids) <= 32
    except (ValueError, TypeError):
        memory_ok, pids_ok = False, False
    return {
        "cgroup_memory_128m": memory_ok,
        "cgroup_pids_32": pids_ok,
        "cgroup_cpu_half": cpu_ok,
    }

def _proc_status():
    status = _read("/proc/self/status") or ""
    fields = {}
    for line in status.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k] = v.strip()
    return {
        "no_new_privileges": fields.get("NoNewPrivs") == "1",
        "no_effective_caps": fields.get("CapEff") == "0000000000000000",
    }

def inspect():
    results = {
        "non_root_uid": os.getuid() == 65534,
        "root_filesystem_read_only": bool(os.statvfs("/").f_flag & os.ST_RDONLY),
        "work_mount_read_only": bool(os.statvfs("/work").f_flag & os.ST_RDONLY),
        "tmpfs_noexec": bool(os.statvfs("/tmp").f_flag & os.ST_NOEXEC),
        "network_only_loopback": set(name for _, name in socket.if_nameindex()) == {"lo"},
    }
    results.update(_cgroups())
    results.update(_proc_status())
    # Only probe outbound TCP while the namespace appears loopback-only.
    # The NEGATIVE CONTROL deliberately removes --network=none; when eth0
    # appears, fail closed WITHOUT contacting any outside host.
    if not results["network_only_loopback"]:
        results["outbound_tcp_denied"] = False
    else:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                results["outbound_tcp_denied"] = sock.connect_ex(
                    ("1.1.1.1", 443)
                ) != 0
        except OSError:
            results["outbound_tcp_denied"] = True
    # Read-only bind is checked by mount flags, not just write-permission
    # errors that could also be produced by our unprivileged uid.
    return results

if __name__ == "__main__":
    checks = inspect()
    print(json.dumps({
        "probe": "synthetic-fixed-review-only",
        "checked": checks,
        "passed": bool(checks) and all(v is True for v in checks.values()),
        "untrusted_code_executed": False,
        "full_agent_sandbox_attested": False,
    }, sort_keys=True))
    sys.exit(0 if all(v is True for v in checks.values()) else 1)
