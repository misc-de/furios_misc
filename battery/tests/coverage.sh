#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
# Line coverage for battctl, using the standard library's own tracer.
#
# No third-party coverage package: this has to run on the phone, and trace is
# already there.
#
# The cover file is found by its CONTENT, not by its name. trace names its
# output after the module path, and for a program without a .py extension
# that name is neither battctl.cover nor anything else worth guessing - the
# obvious guess matches test-battctl.cover instead and reports the coverage
# of the test file.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT

( cd "$ROOT" && python3 -m trace --count --coverdir="$OUT" --missing \
    "$HERE/test-battctl.py" >/dev/null 2>&1 )

python3 - "$ROOT/battctl" "$OUT" <<'PY'
import os, re, sys

source_file, out = sys.argv[1], sys.argv[2]
lines = open(source_file, errors="replace").read().splitlines()

# The entry point at the bottom never runs in an imported module. Counting it
# would leave the file short by two lines for a reason that has nothing to do
# with testing.
end_line = len(lines)
for n, line in enumerate(lines, 1):
    if line.startswith("if __name__"):
        end_line = n - 1
        break

# The prefix is exactly six columns and a space: ">>>>>>" for a line that
# never ran, a right-aligned count with its colon for one that did, and six
# blanks for a line that cannot run at all. Six and a space, not "whatever
# whitespace is there" - a greedy \s* would eat the indentation of the source
# line as well, and the comparison below would never match anything.
counter_re = re.compile(r"^(>>>>>>|\s*\d+:|\s{6})\s(.*)$")


def decipher(path):
    """(lines without their counters, hit list) of a .cover file."""
    text, hits = [], []
    for raw in open(path, errors="replace").read().splitlines():
        m = counter_re.match(raw)
        if m is None:
            text.append(raw)
            hits.append(None)
            continue
        head, rest = m.group(1), m.group(2)
        text.append(rest)
        hits.append("missed" if head == ">>>>>>"
                       else ("hit" if head.strip() else None))
    return text, hits


match = None
for name in sorted(os.listdir(out)):
    if not name.endswith(".cover"):
        continue
    text, hits = decipher(os.path.join(out, name))
    if text[:len(lines)] == lines:
        match = (name, hits)
        break

if match is None:
    print("  %-20s not measured - never imported" % os.path.basename(source_file))
    sys.exit(1)

name, hits = match
total = hit = 0
missing = []
for n, state in enumerate(hits[:end_line], 1):
    if state is None:
        continue
    total += 1
    if state == "hit":
        hit += 1
    else:
        missing.append(n)

share = hit / total * 100 if total else 100.0
print("  %-20s %6.2f %% of %d lines" % (os.path.basename(source_file), share, total))
if missing:
    print("      not reached:", " ".join(str(n) for n in missing[:60]))
PY
