#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
#
# Builds the plugin and loads it the way phosh does. NEVER with sudo.
#
# Two things can be missing here, and they are missing for different reasons:
# phosh's headers, which an ordinary runner has no reason to carry, and a
# display, which a runner has none of. Both are a skip; anything else is a
# failure.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
FAILED=0

if [ "$(id -u)" = 0 ]; then
    echo "never start run-tests.sh with sudo." >&2
    exit 1
fi

printf '\n\033[1m== the plugin, built and loaded like the shell loads it\033[0m\n'
if ! pkg-config --exists phosh-plugins gtk+-3.0 2>/dev/null; then
    printf '  \033[33mskipped\033[0m - no phosh-plugins/gtk+-3.0 (apt install phosh-dev libgtk-3-dev)\n'
else
    # GDK looks for the Wayland socket under XDG_RUNTIME_DIR, and the test
    # moves that aside so it can write the plugin's file without touching the
    # running shell's. An absolute WAYLAND_DISPLAY is read as the socket
    # itself, which is how both can be true at once.
    if [ -z "${WAYLAND_DISPLAY:-}" ] && [ -S "${XDG_RUNTIME_DIR:-/nonexistent}/wayland-0" ]; then
        export WAYLAND_DISPLAY="$XDG_RUNTIME_DIR/wayland-0"
    elif [ -n "${WAYLAND_DISPLAY:-}" ] && [ "${WAYLAND_DISPLAY#/}" = "${WAYLAND_DISPLAY}" ]; then
        export WAYLAND_DISPLAY="${XDG_RUNTIME_DIR:-/nonexistent}/$WAYLAND_DISPLAY"
    fi
    if make -C "$ROOT" check; then
        :
    elif [ $? -eq 77 ]; then
        printf '  \033[33mskipped\033[0m - no display\n'
    else
        FAILED=$((FAILED + 1))
    fi
fi

printf '\n\033[1m== shell\033[0m\n'
if command -v shellcheck >/dev/null; then
    if shellcheck "$HERE/run-tests.sh"; then
        printf '  \033[32mok\033[0m   tests/run-tests.sh\n'
    else
        FAILED=$((FAILED + 1))
    fi
else
    printf '  \033[33mskipped\033[0m - no shellcheck (apt install shellcheck)\n'
fi

printf '\n\033[1m== SPDX headers\033[0m\n'
missing=0
while IFS= read -r f; do
    if ! head -5 "$f" | grep -q 'SPDX-License-Identifier'; then
        printf '  \033[31mFAIL\033[0m %s without an SPDX header\n' "${f#"$ROOT"/}"
        missing=$((missing + 1))
    fi
done < <(find "$ROOT" -type f \( -name '*.c' -o -name '*.sh' -o -name Makefile \) \
    -not -path '*/.git/*')
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
