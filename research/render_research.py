"""Render a research test from its template: python3 render_research.py <template> <out.rs> <seed> <ops> <keys> <sha> [--inject]

Only numbers and a 40-hex SHA are substituted; anything else is rejected."""
import re
import sys

tmpl, out, seed, ops, keys, sha = sys.argv[1:7]
inject = '--inject' in sys.argv[7:]
for name, value in (('seed', seed), ('ops', ops), ('keys', keys)):
    if not re.fullmatch(r'[0-9]{1,12}', value):
        raise SystemExit('bad ' + name)
if not re.fullmatch(r'[0-9a-f]{40}|unknown', sha):
    raise SystemExit('bad sha')
s = open(tmpl, encoding='utf-8').read()
for key, value in (('__SEED__', seed), ('__OPS__', ops), ('__KEYS__', keys), ('__SHA__', sha)):
    assert s.count(key) == 1, key
    s = s.replace(key, value)
if inject:
    assert s.count('const INJECT_MODEL_FAULT: bool = false;') == 1
    s = s.replace('const INJECT_MODEL_FAULT: bool = false;', 'const INJECT_MODEL_FAULT: bool = true;')
open(out, 'w', encoding='utf-8').write(s)
print('rendered')
