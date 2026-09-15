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

quelle, out = sys.argv[1], sys.argv[2]
zeilen = open(quelle, errors="replace").read().splitlines()

# The entry point at the bottom never runs in an imported module. Counting it
# would leave the file short by two lines for a reason that has nothing to do
# with testing.
ende = len(zeilen)
for n, zeile in enumerate(zeilen, 1):
    if zeile.startswith("if __name__"):
        ende = n - 1
        break

# The prefix is exactly six columns and a space: ">>>>>>" for a line that
# never ran, a right-aligned count with its colon for one that did, and six
# blanks for a line that cannot run at all. Six and a space, not "whatever
# whitespace is there" - a greedy \s* would eat the indentation of the source
# line as well, and the comparison below would never match anything.
zaehler = re.compile(r"^(>>>>>>|\s*\d+:|\s{6})\s(.*)$")


def entziffern(pfad):
    """(Zeilen ohne Zaehler, Trefferliste) einer .cover-Datei."""
    text, treffer = [], []
    for roh in open(pfad, errors="replace").read().splitlines():
        m = zaehler.match(roh)
        if m is None:
            text.append(roh)
            treffer.append(None)
            continue
        kopf, rest = m.group(1), m.group(2)
        text.append(rest)
        treffer.append("verfehlt" if kopf == ">>>>>>"
                       else ("getroffen" if kopf.strip() else None))
    return text, treffer


passend = None
for name in sorted(os.listdir(out)):
    if not name.endswith(".cover"):
        continue
    text, treffer = entziffern(os.path.join(out, name))
    if text[:len(zeilen)] == zeilen:
        passend = (name, treffer)
        break

if passend is None:
    print("  %-20s nicht gemessen - nie importiert" % os.path.basename(quelle))
    sys.exit(1)

name, treffer = passend
gesamt = getroffen = 0
fehlend = []
for n, zustand in enumerate(treffer[:ende], 1):
    if zustand is None:
        continue
    gesamt += 1
    if zustand == "getroffen":
        getroffen += 1
    else:
        fehlend.append(n)

quote = getroffen / gesamt * 100 if gesamt else 100.0
print("  %-20s %6.2f %% von %d Zeilen" % (os.path.basename(quelle), quote, gesamt))
if fehlend:
    print("      nicht erreicht:", " ".join(str(n) for n in fehlend[:60]))
PY
