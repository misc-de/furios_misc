#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
#
# Die Tests aller Unterprojekte. NIE mit sudo starten.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
FAILED=0
GEFUNDEN=0

if [ "$(id -u)" = 0 ]; then
    echo "run-tests.sh niemals mit sudo starten." >&2
    exit 1
fi

for suite in "$HERE"/*/tests/run-tests.sh; do
    [ -x "$suite" ] || continue
    projekt=$(basename "$(dirname "$(dirname "$suite")")")
    GEFUNDEN=$((GEFUNDEN + 1))
    printf '\n\033[1m#### %s\033[0m\n' "$projekt"
    if bash "$suite"; then :; else FAILED=$((FAILED + 1)); fi
done

echo
if [ "$GEFUNDEN" -eq 0 ]; then
    # Sonst meldet eine leere Sammlung fröhlich Erfolg.
    printf '\033[31mkeine Testsuite gefunden\033[0m\n'
    exit 1
fi
if [ "$FAILED" -eq 0 ]; then
    printf '\033[32malle %d Projekte bestanden\033[0m\n' "$GEFUNDEN"
else
    printf '\033[31m%d von %d Projekten gescheitert\033[0m\n' "$FAILED" "$GEFUNDEN"
fi
exit $((FAILED > 0))
