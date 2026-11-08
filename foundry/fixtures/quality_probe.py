"""Independent fixed oracle for the synthetic agent patch demonstration."""
from pathlib import Path
import runpy

subject = runpy.run_path(str(Path(__file__).with_name("calculator.py")))
assert subject["add"](2, 3) == 5, "addition oracle mismatch: 2+3"
assert subject["add"](9, -4) == 5, "addition oracle mismatch: 9 + (-4)"
assert subject["add"](-5, -7) == -12, "addition oracle mismatch: negative values"
print("FIXTURE_ORACLE_PASS")
