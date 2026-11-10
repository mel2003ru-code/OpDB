"""Fail a pull request that changes files agents must not change.

Usage: check_protected_paths.py BASE_SHA HEAD_SHA APPROVED(true|false)
Adding new files under tests/ is allowed; modifying or deleting existing
ones is not. See AGENTS.md, "Protected files".
"""
import subprocess
import sys

ANY_CHANGE = (".github/", "docs/adr/")
ANY_CHANGE_FILES = {"AGENTS.md", "CLAUDE.md", "ROADMAP.md", "LICENSE",
                    "scripts/check_protected_paths.py"}
EXISTING_ONLY = ("tests/",)


def violations(name_status: str) -> list[str]:
    found = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, paths = parts[0], parts[1:]
        for index, path in enumerate(paths):
            # For renames/copies the first path is the old name.
            removed_or_changed = status[0] != "A" and not (
                status[0] in "RC" and index == 1)
            if path.startswith(ANY_CHANGE) or path in ANY_CHANGE_FILES:
                found.append(f"{status}\t{path}")
            elif path.startswith(EXISTING_ONLY) and removed_or_changed:
                found.append(f"{status}\t{path}")
    return found


def main(argv: list[str]) -> int:
    base, head, approved = argv[1], argv[2], argv[3].lower() == "true"
    merge_base = subprocess.run(["git", "merge-base", base, head], check=True,
                                capture_output=True, text=True).stdout.strip()
    diff = subprocess.run(["git", "diff", "--name-status", "-M", merge_base, head],
                          check=True, capture_output=True, text=True).stdout
    found = violations(diff)
    if not found:
        print("No protected files changed.")
        return 0
    print("Protected files changed:")
    print("\n".join(found))
    if approved:
        print("Label 'owner-approved' is present: allowed.")
        return 0
    print("Not allowed without the 'owner-approved' label (AGENTS.md).")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
