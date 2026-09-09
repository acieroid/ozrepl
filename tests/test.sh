#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python3 -m ozrepl --browse=terminal < tests/session.in > tests/session.out 2>&1

for expected in "Commands:" "Alt-Enter" 42 300 777 5 6 "parse error" \
    "compiler environment reset" bye; do
    if ! grep -Fq "$expected" tests/session.out; then
        echo "missing expected output: $expected" >&2
        sed -n '1,240p' tests/session.out >&2
        exit 1
    fi
done

for unwanted in "Mozart Compiler" "accepted" "Declared variables" \
    "__OZREPL_BROWSE__"; do
    if grep -Fq "$unwanted" tests/session.out; then
        echo "unexpected raw compiler output: $unwanted" >&2
        sed -n '1,240p' tests/session.out >&2
        exit 1
    fi
done

python3 tests/test_interactive.py
python3 tests/test_vim.py

echo "ozrepl integration test passed"
