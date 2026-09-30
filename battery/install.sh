#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
#
# Installs battctl into the user's home, and the widget that shows what it
# computes - phosh-battery-time, next door - into phosh's plugin directory.
# battctl itself needs no root: it reads files in /sys, writes two small
# files in the runtime directory and adds the widget to phosh's plugin list.
# The widget's `sudo make install` is the one line that asks. Without the
# widget there is nothing on screen at all - neither the colour nor the time
# (found on 30.9.2026: battctl listed a widget that was never installed, and
# phosh said "Custom status-icon 'furios-battery-time' not found").
# NEVER start it with sudo.
set -euo pipefail

if [ "$(id -u)" = 0 ]; then
    echo "Please run WITHOUT sudo - the program runs in the user session." >&2
    exit 1
fi

# Checked before anything is installed. Without gsettings the colour can be
# computed and never shown, and a tool that installs cleanly and then does
# nothing is harder to understand than one that refuses.
missing=()
command -v gsettings >/dev/null || missing+=("gsettings (apt install libglib2.0-bin)")
python3 - <<'CHECK' 2>/dev/null || missing+=("python3-gi")
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: F401
CHECK
# What the widget's build needs - asked here, before anything is installed,
# rather than by its own installer half-way through.
command -v cc >/dev/null || missing+=("a C compiler (apt install build-essential)")
command -v make >/dev/null || missing+=("make (apt install build-essential)")
pkg-config --exists phosh-plugins 2>/dev/null \
    || missing+=("phosh's plugin headers (apt install phosh-dev)")
pkg-config --exists gtk+-3.0 2>/dev/null \
    || missing+=("GTK 3 headers (apt install libgtk-3-dev)")
if [ ${#missing[@]} -gt 0 ]; then
    printf 'Missing: %s\n' "${missing[@]}" >&2
    echo "Nothing was installed." >&2
    exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
UNIT="$HOME/.config/systemd/user"
DOC="$HOME/.local/share/doc/furios-battery"

# The install record: what each path held before the first install, so that
# uninstall.sh puts exactly that back rather than assuming there was nothing
# (install-record.sh explains it). Beside battctl's own state, which
# uninstall.sh removes after using it.
REC_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/furios-battery/install-record"
# shellcheck source=install-record.sh
. "$SRC/install-record.sh"

install -d "$BIN" "$UNIT"
rec_dir "$DOC"
install -d "$DOC"
# The mark is a word every version of that file carries: a file of ours from
# an install before records existed is told apart from somebody else's by it.
rec_install 0755 "$SRC/battctl" "$BIN/battctl" battctl
rec_install 0644 "$SRC/systemd/furios-battery-color.service" \
    "$UNIT/furios-battery-color.service" battctl
rec_install 0644 "$SRC/README.md" "$DOC/README.md" battctl
rec_install 0644 "$SRC/FINDINGS.md" "$DOC/FINDINGS.md" battctl

# The widget. FURIOS_BATTERY_WIDGET=skip is for the tests that look at
# battctl on a phone without it.
if [ "${FURIOS_BATTERY_WIDGET:-install}" != skip ]; then
    echo
    "$SRC/../phosh-battery-time/install.sh"
    echo
fi

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
