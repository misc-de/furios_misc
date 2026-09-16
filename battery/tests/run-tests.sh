#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
# Everything that can be checked without watching a charge.
#
# Runs without a display, without a battery and without root. NEVER with sudo.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
FAILED=0

if [ "$(id -u)" = 0 ]; then
    echo "never start run-tests.sh with sudo." >&2
    exit 1
fi

run() {
    printf '\n\033[1m== %s\033[0m\n' "$1"
    shift
    if "$@"; then :; else FAILED=$((FAILED + 1)); fi
}

run "battctl: readings, thresholds, themes, daemon" python3 "$HERE/test-battctl.py"
run "the restart policy of the unit" bash "$HERE/test-restart-policy.sh"

printf '\n\033[1m== shell\033[0m\n'
if command -v shellcheck >/dev/null; then
    for f in "$ROOT"/*.sh "$HERE"/*.sh; do
        # -P, because -x alone follows `. "$HERE/lib.sh"` relative to the
        # working directory and reports it as unreadable (SC1091).
        if shellcheck -x -P "$HERE" "$f"; then
            printf '  \033[32mok\033[0m   %s\n' "${f#"$ROOT"/}"
        else
            FAILED=$((FAILED + 1))
        fi
    done
else
    printf '  \033[33mskipped\033[0m - no shellcheck (apt install shellcheck)\n'
fi

printf '\n\033[1m== the unit, as systemd reads it\033[0m\n'
if command -v systemd-analyze >/dev/null; then
    # Only the parse errors of our own file: verify also follows the unit's
    # dependencies into the rest of the system, and a warning about somebody
    # else's drop-in is not this project's test failing.
    message=$(systemd-analyze verify "$ROOT"/systemd/*.service 2>&1 \
        | grep -E 'furios-battery-color' | grep -v 'battctl is not executable')
    if [ -z "$message" ]; then
        printf '  \033[32mok\033[0m   furios-battery-color.service\n'
    else
        printf '  \033[31mFAIL\033[0m %s\n' "$message"
        FAILED=$((FAILED + 1))
    fi
else
    printf '  \033[33mskipped\033[0m - no systemd-analyze\n'
fi

printf '\n\033[1m== SPDX headers\033[0m\n'
missing=0
while IFS= read -r f; do
    if ! head -5 "$f" | grep -q 'SPDX-License-Identifier'; then
        printf '  \033[31mFAIL\033[0m %s without an SPDX header\n' "${f#"$ROOT"/}"
        missing=$((missing + 1))
    fi
done < <(find "$ROOT" -type f \( -name '*.sh' -o -name '*.py' -o -name '*.service' \
    -o -name battctl \) -not -path '*/.git/*')
if [ "$missing" -eq 0 ]; then
    printf '  \033[32mok\033[0m   every file\n'
else
    FAILED=$((FAILED + 1))
fi

echo
if [ "$FAILED" -eq 0 ]; then
    printf '\033[32mall suites passed\033[0m\n'
else
    printf '\033[31m%d suite(s) failed\033[0m\n' "$FAILED"
fi
exit $((FAILED > 0))
