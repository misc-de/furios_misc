#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
# Everything that can be checked without watching a charge.
#
# Runs without a display, without a battery and without root. NIE mit sudo.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
FAILED=0

if [ "$(id -u)" = 0 ]; then
    echo "run-tests.sh niemals mit sudo starten." >&2
    exit 1
fi

run() {
    printf '\n\033[1m== %s\033[0m\n' "$1"
    shift
    if "$@"; then :; else FAILED=$((FAILED + 1)); fi
}

run "battctl: Messung, Schwellen, Themes, Daemon" python3 "$HERE/test-battctl.py"
run "die Neustart-Politik der Unit" bash "$HERE/test-restart-policy.sh"

printf '\n\033[1m== shell\033[0m\n'
if command -v shellcheck >/dev/null; then
    for f in "$ROOT"/*.sh "$HERE"/*.sh; do
        if shellcheck -x "$f"; then
            printf '  \033[32mok\033[0m   %s\n' "${f#"$ROOT"/}"
        else
            FAILED=$((FAILED + 1))
        fi
    done
else
    printf '  \033[33muebersprungen\033[0m - kein shellcheck (apt install shellcheck)\n'
fi

printf '\n\033[1m== die Unit, wie systemd sie liest\033[0m\n'
if command -v systemd-analyze >/dev/null; then
    # Only the parse errors of our own file: verify also follows the unit's
    # dependencies into the rest of the system, and a warning about somebody
    # else's drop-in is not this project's test failing.
    meldung=$(systemd-analyze verify "$ROOT"/systemd/*.service 2>&1 \
        | grep -E 'furios-battery-color' | grep -v 'battctl is not executable')
    if [ -z "$meldung" ]; then
        printf '  \033[32mok\033[0m   furios-battery-color.service\n'
    else
        printf '  \033[31mFAIL\033[0m %s\n' "$meldung"
        FAILED=$((FAILED + 1))
    fi
else
    printf '  \033[33muebersprungen\033[0m - kein systemd-analyze\n'
fi

printf '\n\033[1m== SPDX-Koepfe\033[0m\n'
fehlend=0
while IFS= read -r f; do
    if ! head -5 "$f" | grep -q 'SPDX-License-Identifier'; then
        printf '  \033[31mFAIL\033[0m %s ohne SPDX-Kopf\n' "${f#"$ROOT"/}"
        fehlend=$((fehlend + 1))
    fi
done < <(find "$ROOT" -type f \( -name '*.sh' -o -name '*.py' -o -name '*.service' \
    -o -name battctl \) -not -path '*/.git/*')
if [ "$fehlend" -eq 0 ]; then
    printf '  \033[32mok\033[0m   alle Dateien\n'
else
    FAILED=$((FAILED + 1))
fi

echo
if [ "$FAILED" -eq 0 ]; then
    printf '\033[32malle Suiten bestanden\033[0m\n'
else
    printf '\033[31m%d Suite(n) gescheitert\033[0m\n' "$FAILED"
fi
exit $((FAILED > 0))
