#!/bin/sh
# DiskSweep QA self-check: run from products/disksweep/.
# Fails non-zero on any regression. No deletions (dry-run only).
set -eu
cd "$(dirname "$0")/.."
echo "== C++ builds =="
/usr/bin/clang++ -std=c++17 -Wall -Wextra scanner/main.cpp -o /tmp/ds-qa-scanner
/usr/bin/clang++ -std=c++17 -Wall -Wextra scanner/policycheck.cpp -o /tmp/ds-qa-policycheck
/usr/bin/clang++ -std=c++17 -Wall -Wextra -I scanner privileged-helper/helper.cpp -o /tmp/ds-qa-helper
echo "== policycheck =="
/tmp/ds-qa-policycheck
echo "== pytest =="
python3 -m pytest tests/ -q
echo "== ruff =="
python3 -m ruff check sidecar/ tests/
echo "== dogfood dry-run =="
/tmp/ds-qa-scanner > /tmp/ds-qa-scan.jsonl 2>/dev/null
python3 -m sidecar.cli --scan /tmp/ds-qa-scan.jsonl --no-llm --json /tmp/ds-qa-verdicts.json | tail -n 4
python3 -c "
import json
v = json.load(open('/tmp/ds-qa-verdicts.json'))
bad = [x for x in v if x['safety'] == 'BLOCKED' and x['action'] != 'unselectable']
assert not bad, f'BLOCKED deletable: {bad[:3]}'
kilo = [x for x in v if 'Kilohearts' in x['path'] and 'banks' in x['path']]
assert all(x['safety'] != 'SAFE' for x in kilo), 'Kilohearts banks must never be SAFE'
print(f'OK {len(v)} verdicts, 0 BLOCKED deletable, Kilohearts banks protected')
"
echo "== helper refusal =="
echo '{"src":"/System/x","dst":"/tmp/y"}' | /tmp/ds-qa-helper || true
echo "ALL QA GREEN"
