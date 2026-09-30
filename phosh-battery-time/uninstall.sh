#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
#
# Takes the status icon out of phosh's plugin directory, and out of the
# setting that lists it. Run WITHOUT sudo.
set -uo pipefail

if [ "$(id -u)" = 0 ]; then
    echo "Please run WITHOUT sudo." >&2
    exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="furios-battery-time"
KEY="mobi.phosh.shell.plugins status-icons"

# The setting first, and only our own entry in it: a shell that goes on being
# told to load a plugin which is no longer there logs a warning on every
# start, and somebody else's plugin in the same list is none of our business.
if command -v gsettings >/dev/null; then
    current=$(gsettings get $KEY 2>/dev/null || echo "@as []")
    if [ "$current" != "${current/$PLUGIN/}" ]; then
        python3 - "$PLUGIN" <<'PY' || true
import ast, os, subprocess, sys
key = ["mobi.phosh.shell.plugins", "status-icons"]
def names(env=None):
    out = subprocess.run(["gsettings", "get"] + key, capture_output=True,
                         text=True, env=env)
    text = out.stdout.strip()
    if text.startswith("@as "):
        text = text[4:]
    return ast.literal_eval(text)
try:
    rest = [n for n in names() if n != sys.argv[1]]
    # The memory backend answers with the schema's default: no dconf behind it.
    shipped = names(dict(os.environ, GSETTINGS_BACKEND="memory"))
except (ValueError, SyntaxError):
    sys.exit(0)
# Back to the shipped list means the key goes, rather than staying behind as
# a copy of the default - a copy a new phone does not have, and one that
# would stop following the default when an update changes it.
if rest == shipped:
    subprocess.run(["gsettings", "reset"] + key, check=False)
else:
    subprocess.run(["gsettings", "set"] + key + [str(rest)], check=False)
PY
    fi
fi

sudo make -C "$SRC" uninstall

echo "Removed. The shell drops it at its next start."
