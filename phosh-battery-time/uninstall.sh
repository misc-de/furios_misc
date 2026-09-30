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
#
# battctl adds the entry, and before it does it writes down what the list
# was (and whether the key was set at all) - so battctl takes it out again:
# `battctl unlist` puts back exactly the recorded list, or only takes our
# entry out when somebody changed the list since. The one in this checkout
# first, because an installed battctl from before 30.9.2026 does not know
# "unlist"; both read the same record.
BATTCTL=
for c in "$SRC/../battery/battctl" "$HOME/.local/bin/battctl"; do
    [ -x "$c" ] && { BATTCTL=$c; break; }
done
if [ -n "$BATTCTL" ] && "$BATTCTL" unlist; then
    :
elif command -v gsettings >/dev/null; then
    # No battctl that could do it, so no record either: the old way, said
    # as such.
    current=$(gsettings get $KEY 2>/dev/null || echo "@as []")
    if [ "$current" != "${current/$PLUGIN/}" ]; then
        echo "No battctl, so no record of the plugin list before our entry:"
        echo "taking our entry out, and resetting the key if the rest is the shipped list."
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
if rest == shipped:
    subprocess.run(["gsettings", "reset"] + key, check=False)
else:
    subprocess.run(["gsettings", "set"] + key + [str(rest)], check=False)
PY
    fi
fi

# The two files: back to what the install record says phosh's directory held
# before the first install, and left alone where they changed since. Without
# a record (installed before 30.9.2026) make removes them by name, as always.
DIR=$(pkg-config --variable=status_icons_plugins_dir phosh-plugins 2>/dev/null)
REC_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/furios-battery-time/install-record"
REC_SUDO=sudo
# shellcheck source=install-record.sh
. "$SRC/install-record.sh"
if [ -n "$DIR" ] && rec_exists; then
    rec_restore
    rmdir "$(dirname "$REC_DIR")" 2>/dev/null
else
    echo "No install record (installed before 30.9.2026): removing the plugin"
    echo "by name - what was at those paths before cannot be known."
    sudo make -C "$SRC" uninstall DESTDIR="${DESTDIR:-}"
fi

echo "Removed. The shell drops it at its next start."
