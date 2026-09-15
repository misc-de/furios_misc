#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
#
# Installs into the user's home. No root anywhere: this reads two files in
# /sys, writes ~/.themes and sets one gsettings key - all of it things the
# session may do anyway. NEVER start it with sudo.
set -euo pipefail

if [ "$(id -u)" = 0 ]; then
    echo "Please run WITHOUT sudo - the program runs in the user session." >&2
    exit 1
fi

# Checked before anything is installed. Without gsettings the colour can be
# computed and never shown, and a tool that installs cleanly and then does
# nothing is harder to understand than one that refuses.
missing=()
command -v gsettings >/dev/null || missing+=("gsettings (Paket libglib2.0-bin)")
python3 - <<'CHECK' 2>/dev/null || missing+=("python3-gi")
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: F401
CHECK
if [ ${#missing[@]} -gt 0 ]; then
    printf 'Missing: %s\n' "${missing[@]}" >&2
    echo "Nothing was installed." >&2
    exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
UNIT="$HOME/.config/systemd/user"
DOC="$HOME/.local/share/doc/furios-battery"

install -d "$BIN" "$UNIT" "$DOC"
install -m 0755 "$SRC/battctl" "$BIN/battctl"
install -m 0644 "$SRC/systemd/furios-battery-color.service" \
    "$UNIT/furios-battery-color.service"
install -m 0644 "$SRC/README.md" "$SRC/FINDINGS.md" "$DOC/"

systemctl --user daemon-reload
# Installed, not started. Unlike the other projects here this one changes how
# the phone LOOKS, and that is a choice somebody makes - from the app, or
# with the line printed below.
if systemctl --user is-active --quiet furios-battery-color.service; then
    systemctl --user restart furios-battery-color.service
fi

echo
echo "Installed. State:"
"$BIN/battctl" status || true
echo
if ! systemctl --user is-enabled --quiet furios-battery-color.service; then
    echo "Turn it on:  systemctl --user enable --now furios-battery-color.service"
    echo "(or in the app, under \"Battery\")"
fi
